/**
 * Coze API 代理示例。
 *
 * 当前文件只作为方案参考，不会被项目构建或部署。
 * 适合放到 Cloudflare Worker / Vercel Function 一类的服务里，再按实际
 * Coze API 文档补齐 endpoint、鉴权字段和响应解析。
 */

type Env = {
  COZE_API_TOKEN: string;
  COZE_BOT_ID: string;
  COZE_API_BASE?: string;
  ALLOWED_ORIGINS?: string;
};

type ChatRequest = {
  query?: string;
  userId?: string;
  context?: Array<{
    title: string;
    content: string;
    pdfUrl?: string;
  }>;
};

function json(data: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(data), {
    ...init,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...init.headers,
    },
  });
}

function resolveAllowedOrigin(origin: string | null, env: Env): string {
  const allowList = (env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  if (!allowList.length) return origin || "*";
  if (origin && allowList.includes(origin)) return origin;
  return allowList[0];
}

function corsHeaders(origin: string | null, env: Env) {
  return {
    "access-control-allow-origin": resolveAllowedOrigin(origin, env),
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type, authorization",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("origin");

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(origin, env) });
    }

    if (request.method !== "POST") {
      return json({ error: "Method not allowed" }, {
        status: 405,
        headers: corsHeaders(origin, env),
      });
    }

    if (!env.COZE_API_TOKEN || !env.COZE_BOT_ID) {
      return json({ error: "Missing Coze environment variables" }, {
        status: 500,
        headers: corsHeaders(origin, env),
      });
    }

    let body: ChatRequest;
    try {
      body = (await request.json()) as ChatRequest;
    } catch {
      return json({ error: "Invalid JSON body" }, {
        status: 400,
        headers: corsHeaders(origin, env),
      });
    }

    const query = body.query?.trim();

    if (!query) {
      return json({ error: "Missing query" }, {
        status: 400,
        headers: corsHeaders(origin, env),
      });
    }

    const contextText = (body.context ?? [])
      .slice(0, 5)
      .map((item, index) => {
        const pdf = item.pdfUrl ? `\nPDF: ${item.pdfUrl}` : "";
        return `参考 ${index + 1}: ${item.title}\n${item.content}${pdf}`;
      })
      .join("\n\n");

    const apiBase = env.COZE_API_BASE || "https://api.coze.cn";

    const cozePayload = {
      bot_id: env.COZE_BOT_ID,
      user_id: body.userId || "web-user",
      query,
      additional_messages: contextText
        ? [
            {
              role: "user",
              content_type: "text",
              content: `请优先参考以下笔记片段回答，并在答案末尾列出来源。\n\n${contextText}`,
            },
          ]
        : undefined,
    };

    // 注意：这里的 /v3/chat 是占位示例。启用前请按 Coze 控制台和官方文档
    // 调整 endpoint、流式响应、conversation_id 和消息字段。
    const response = await fetch(`${apiBase}/v3/chat`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.COZE_API_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(cozePayload),
    });

    const responseText = await response.text();

    return new Response(responseText, {
      status: response.status,
      headers: {
        ...corsHeaders(origin, env),
        "content-type": response.headers.get("content-type") || "application/json; charset=utf-8",
      },
    });
  },
};
