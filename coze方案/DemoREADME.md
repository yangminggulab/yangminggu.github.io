# Coze 接入 Demo 方案

这个目录是一个独立的 Coze 接入演示方案，当前不会启用，也不会影响现有网站构建、首页搜索或 GitHub Pages 发布。

## 适合怎么接

当前项目已经把 LaTeX 笔记处理成了结构化搜索索引：

- `public/search-index.previews.json`：包含书名、章节、内容块、PDF 页码、预览图等信息。
- `pdf/*.pdf`：原始 PDF 阅读入口。
- `books.json`：书架数据。

因此 Coze 最适合接在“AI 导学/问答”这一层，而不是替换现有静态站。

推荐产品形态：

1. 用户仍然用原网站浏览 PDF、视频和搜索。
2. 网站旁边新增一个“AI 学习助手”入口。
3. 助手基于笔记知识库回答问题，并返回来源：书名、章节、页码、PDF 链接。
4. 对数学证明、定理条件、公式推导保持谨慎，不知道就说明不知道。

## 目录说明

```text
coze方案/
├── DemoREADME.md
├── bot-prompt.md
├── export-coze-kb.ts
├── frontend-widget-snippet.html
├── worker-proxy-example.ts
└── out/
    └── 运行导出脚本后生成，不提交也不启用
```

## 第一步：导出 Coze 知识库文件

在项目根目录执行：

```bash
npx tsx coze方案/export-coze-kb.ts
```

默认读取：

```text
public/search-index.previews.json
```

默认输出：

```text
coze方案/out/coze-kb.jsonl
coze方案/out/coze-kb.md
```

用途：

- `coze-kb.jsonl`：适合后续用 API 或脚本同步到知识库。
- `coze-kb.md`：适合人工预览，也可以拆分后手动上传。

可以先只导出少量内容测试：

```bash
npx tsx coze方案/export-coze-kb.ts --limit 50
```

如果要让 Coze 回答里直接给完整线上链接，可以加站点域名：

```bash
npx tsx coze方案/export-coze-kb.ts --site-origin https://yangminggu.github.io
```

常用参数：

```text
--limit 50                         只导出前 50 条，适合测试
--site-origin https://...          把 /pdf/... 转成完整 URL
--max-content-chars 6000           限制单条知识块长度，避免过长
--input public/search-index...     指定输入索引
--out-dir coze方案/out             指定输出目录
```

导出内容会同时包含两类信息：

- `可读文本`：适合 Coze 检索和回答。
- `原始 LaTeX`：保留公式、环境和符号，避免数学内容被纯文本清洗后丢失语义。

## 第二步：在 Coze 创建 Bot

建议配置：

- 名称：数学笔记学习助手
- 类型：知识库问答 / 学习助手
- 知识库：上传或同步 `coze-kb.md` / `coze-kb.jsonl`
- 提示词：参考 `bot-prompt.md`

回答要求：

- 先根据知识库回答。
- 尽量引用原笔记来源。
- 涉及数学结论时保留条件，不随意补充不存在的假设。
- 如果知识库没有信息，直接说明“当前笔记中没有找到可靠依据”。

## 第三步：前端接入方式

### MVP 方式

直接使用 Coze 提供的网页发布、iframe 或官方 Web SDK 挂件。可以参考：

```text
frontend-widget-snippet.html
```

这个文件只是示例，不会自动插入 `index.html`。

### 进阶方式

使用 Worker/Vercel Function 作为代理：

```text
frontend -> worker-proxy-example.ts -> Coze API
```

好处：

- 不在浏览器暴露 Coze Token。
- 可以先查本地搜索索引，再把最相关的内容块作为上下文传给 Coze。
- 后续可以加限流、日志、白名单和缓存。

示例代码见：

```text
worker-proxy-example.ts
```

## 当前不启用的边界

本目录目前只是方案和 demo 代码：

- 不修改 `index.html`
- 不修改 `.github/workflows/build.yml`
- 不新增线上依赖
- 不上传任何知识库
- 不调用 Coze API
- 不读取或写入任何密钥

真正启用时，建议再做三件事：

1. 确认 Coze Bot 发布方式。
2. 确认是否需要 Worker 代理。
3. 把知识库导出步骤接入 GitHub Actions，但先做手动同步测试。

## 建议的验收标准

上线前可以用这几类问题测试：

1. “什么是互斥事件？给我来源。”
2. “实分析里紧致性相关的定义有哪些？”
3. “PDE 的 Robin 边界条件怎么理解？”
4. “给我找一个机器学习里的例题。”
5. “这个问题笔记里没有的话，请直接说没有。”

理想回答应该做到：

- 能指出具体笔记、章节和 PDF 页码。
- 不把检索不到的内容硬编成答案。
- 对公式和定理条件保持准确。
- 回答末尾有来源链接。
