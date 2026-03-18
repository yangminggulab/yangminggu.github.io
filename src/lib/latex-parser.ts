export type LatexBlockType =
  | "section"
  | "subsection"
  | "definition"
  | "note"
  | "example"
  | "text";

export interface LatexBlock {
  id: string;
  blockType: LatexBlockType;
  blockTitle: string;
  content: string;
  rawContent: string;
  docTitle?: string;
  sectionTitle?: string;
  subsectionTitle?: string;
  sourcePath?: string;
  order: number;
}

interface ParseLatexOptions {
  docTitle?: string;
  sourcePath?: string;
}

const SUPPORTED_ENVIRONMENTS = ["definition", "note", "example"] as const;

function normalizeWhitespace(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\t/g, " ")
    .replace(/[ \u00A0]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripComments(tex: string): string {
  return tex
    .split("\n")
    .map((line) => {
      let result = "";
      let escaped = false;

      for (let i = 0; i < line.length; i++) {
        const ch = line[i];

        if (ch === "\\" && !escaped) {
          escaped = true;
          result += ch;
          continue;
        }

        if (ch === "%" && !escaped) {
          break;
        }

        escaped = false;
        result += ch;
      }

      return result;
    })
    .join("\n");
}

function stripMath(tex: string): string {
  return tex
    .replace(/\$\$[\s\S]*?\$\$/g, " ")
    .replace(/\$[^$]*\$/g, " ")
    .replace(/\\\[[\s\S]*?\\\]/g, " ")
    .replace(/\\\([\s\S]*?\\\)/g, " ");
}

function stripCommands(tex: string): string {
  let text = tex;

  text = text.replace(/\\item\b/g, " ");
  text = text.replace(/\\begin\{[^}]+\}/g, " ");
  text = text.replace(/\\end\{[^}]+\}/g, " ");

  // \command{...} -> 保留花括号里的内容
  text = text.replace(/\\[a-zA-Z*]+\{([^}]*)\}/g, "$1");

  // \command[...]{...} -> 保留最后的大括号内容
  text = text.replace(/\\[a-zA-Z*]+\[[^\]]*\]\{([^}]*)\}/g, "$1");

  // 剩余无参数命令去掉
  text = text.replace(/\\[a-zA-Z*]+/g, " ");

  // 花括号本身去掉
  text = text.replace(/[{}]/g, " ");

  return text;
}

function cleanLatexToSearchableText(tex: string): string {
  const noComments = stripComments(tex);
  const noMath = stripMath(noComments);
  const noCommands = stripCommands(noMath);
  return normalizeWhitespace(noCommands);
}

function sanitizeIdPart(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fff\-]/g, "")
    .replace(/\-+/g, "-")
    .replace(/^\-+|\-+$/g, "")
    .slice(0, 50);
}

function makeBlockId(
  docTitle: string | undefined,
  blockType: LatexBlockType,
  title: string,
  order: number,
): string {
  const left = sanitizeIdPart(docTitle || "doc");
  const mid = sanitizeIdPart(blockType);
  const right = sanitizeIdPart(title || `block-${order}`);
  return `${left}-${mid}-${right || order}`;
}

function extractCommandTitle(line: string, command: "section" | "subsection"): string | null {
  const regex = new RegExp(String.raw`\\${command}\*?\{([^}]*)\}`);
  const match = line.match(regex);
  return match ? normalizeWhitespace(match[1]) : null;
}

function extractEnvironmentBlocks(
  tex: string,
): Array<{
  start: number;
  end: number;
  envName: (typeof SUPPORTED_ENVIRONMENTS)[number];
  rawContent: string;
  innerContent: string;
}> {
  const blocks: Array<{
    start: number;
    end: number;
    envName: (typeof SUPPORTED_ENVIRONMENTS)[number];
    rawContent: string;
    innerContent: string;
  }> = [];

  for (const envName of SUPPORTED_ENVIRONMENTS) {
    const regex = new RegExp(
      String.raw`\\begin\{${envName}\}([\s\S]*?)\\end\{${envName}\}`,
      "g",
    );

    let match: RegExpExecArray | null;
    while ((match = regex.exec(tex)) !== null) {
      blocks.push({
        start: match.index,
        end: match.index + match[0].length,
        envName,
        rawContent: match[0],
        innerContent: match[1],
      });
    }
  }

  return blocks.sort((a, b) => a.start - b.start);
}

function rangesOverlap(
  aStart: number,
  aEnd: number,
  bStart: number,
  bEnd: number,
): boolean {
  return aStart < bEnd && bStart < aEnd;
}

export function parseLatexToBlocks(
  tex: string,
  options: ParseLatexOptions = {},
): LatexBlock[] {
  const cleanedSource = stripComments(tex);
  const envBlocks = extractEnvironmentBlocks(cleanedSource);

  const blocks: LatexBlock[] = [];
  const lines = cleanedSource.split("\n");

  let currentSection = "";
  let currentSubsection = "";
  let order = 0;

  // 先记录 section / subsection
  for (const line of lines) {
    const sectionTitle = extractCommandTitle(line, "section");
    if (sectionTitle) {
      currentSection = sectionTitle;
      currentSubsection = "";

      blocks.push({
        id: makeBlockId(options.docTitle, "section", sectionTitle, order),
        blockType: "section",
        blockTitle: sectionTitle,
        content: sectionTitle,
        rawContent: line,
        docTitle: options.docTitle,
        sectionTitle: sectionTitle,
        subsectionTitle: "",
        sourcePath: options.sourcePath,
        order: order++,
      });
      continue;
    }

    const subsectionTitle = extractCommandTitle(line, "subsection");
    if (subsectionTitle) {
      currentSubsection = subsectionTitle;

      blocks.push({
        id: makeBlockId(options.docTitle, "subsection", subsectionTitle, order),
        blockType: "subsection",
        blockTitle: subsectionTitle,
        content: subsectionTitle,
        rawContent: line,
        docTitle: options.docTitle,
        sectionTitle: currentSection,
        subsectionTitle: subsectionTitle,
        sourcePath: options.sourcePath,
        order: order++,
      });
    }
  }

  // 再扫描正文里的 environment
  let runningSection = "";
  let runningSubsection = "";
  let currentOffset = 0;

  for (const line of lines) {
    const lineWithNewline = `${line}\n`;
    const lineStart = currentOffset;
    const lineEnd = currentOffset + lineWithNewline.length;

    const sectionTitle = extractCommandTitle(line, "section");
    if (sectionTitle) {
      runningSection = sectionTitle;
      runningSubsection = "";
    }

    const subsectionTitle = extractCommandTitle(line, "subsection");
    if (subsectionTitle) {
      runningSubsection = subsectionTitle;
    }

    for (const env of envBlocks) {
      if (env.start >= lineStart && env.start < lineEnd) {
        const searchable = cleanLatexToSearchableText(env.innerContent);
        if (!searchable) {
          continue;
        }

        blocks.push({
          id: makeBlockId(options.docTitle, env.envName, searchable.slice(0, 30), order),
          blockType: env.envName,
          blockTitle: runningSubsection || runningSection || env.envName,
          content: searchable,
          rawContent: env.rawContent,
          docTitle: options.docTitle,
          sectionTitle: runningSection,
          subsectionTitle: runningSubsection,
          sourcePath: options.sourcePath,
          order: order++,
        });
      }
    }

    currentOffset = lineEnd;
  }

  // 补充普通文本块：把不在 environment 里的正文也收进去
  const textRanges: Array<{ start: number; end: number; raw: string }> = [];
  let cursor = 0;

  for (const env of envBlocks) {
    if (cursor < env.start) {
      textRanges.push({
        start: cursor,
        end: env.start,
        raw: cleanedSource.slice(cursor, env.start),
      });
    }
    cursor = env.end;
  }

  if (cursor < cleanedSource.length) {
    textRanges.push({
      start: cursor,
      end: cleanedSource.length,
      raw: cleanedSource.slice(cursor),
    });
  }

  let sectionAtCursor = "";
  let subsectionAtCursor = "";
  currentOffset = 0;

  for (const line of lines) {
    const lineWithNewline = `${line}\n`;
    const lineStart = currentOffset;
    const lineEnd = currentOffset + lineWithNewline.length;

    const sectionTitle = extractCommandTitle(line, "section");
    if (sectionTitle) {
      sectionAtCursor = sectionTitle;
      subsectionAtCursor = "";
    }

    const subsectionTitle = extractCommandTitle(line, "subsection");
    if (subsectionTitle) {
      subsectionAtCursor = subsectionTitle;
    }

    for (const range of textRanges) {
      if (!rangesOverlap(lineStart, lineEnd, range.start, range.end)) {
        continue;
      }

      const cleaned = cleanLatexToSearchableText(range.raw)
        .replace(/\b(section|subsection|definition|note|example)\b/gi, "")
        .trim();

      if (!cleaned || cleaned.length < 20) {
        continue;
      }

      const alreadyExists = blocks.some(
        (b) =>
          b.blockType === "text" &&
          b.rawContent === range.raw &&
          b.sectionTitle === sectionAtCursor &&
          b.subsectionTitle === subsectionAtCursor,
      );

      if (!alreadyExists) {
        blocks.push({
          id: makeBlockId(options.docTitle, "text", cleaned.slice(0, 30), order),
          blockType: "text",
          blockTitle: subsectionAtCursor || sectionAtCursor || "text",
          content: cleaned,
          rawContent: range.raw,
          docTitle: options.docTitle,
          sectionTitle: sectionAtCursor,
          subsectionTitle: subsectionAtCursor,
          sourcePath: options.sourcePath,
          order: order++,
        });
      }
    }

    currentOffset = lineEnd;
  }

  return blocks.sort((a, b) => a.order - b.order);
}
