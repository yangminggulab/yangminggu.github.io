import fs from "node:fs";
import path from "node:path";

type SearchIndexItem = {
  id?: string;
  repo?: string;
  title?: string;
  noteTitle?: string;
  pdf?: string;
  pdfPath?: string;
  section?: string;
  sectionTitle?: string;
  subsection?: string;
  subsectionTitle?: string;
  kind?: string;
  blockType?: string;
  blockTitle?: string;
  previewTitle?: string;
  text?: string;
  content?: string;
  rawContent?: string;
  sourcePath?: string;
  startLine?: number;
  endLine?: number;
  pdfLocator?: {
    page?: number;
  } | null;
  previewImage?: string | null;
};

type ExportRecord = {
  id: string;
  title: string;
  content: string;
  metadata: {
    repo: string;
    noteTitle: string;
    sectionTitle: string;
    subsectionTitle: string;
    blockType: string;
    blockTitle: string;
    page: number | null;
    pdfUrl: string;
    previewImage: string;
    sourcePath: string;
    startLine: number | null;
    endLine: number | null;
  };
};

const ROOT_DIR = path.resolve(__dirname, "..");
const DEFAULT_INPUT = path.join(ROOT_DIR, "public", "search-index.previews.json");
const DEFAULT_OUT_DIR = path.join(__dirname, "out");
const DEFAULT_MAX_CONTENT_CHARS = 6000;

function readArg(name: string): string | undefined {
  const prefix = `${name}=`;
  const exactIndex = process.argv.indexOf(name);
  if (exactIndex >= 0) return process.argv[exactIndex + 1];
  const pair = process.argv.find((arg) => arg.startsWith(prefix));
  return pair ? pair.slice(prefix.length) : undefined;
}

function readLimit(): number | null {
  const raw = readArg("--limit");
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error("--limit must be a positive number");
  }
  return Math.floor(value);
}

function readPositiveInt(name: string, fallback: number): number {
  const raw = readArg(name);
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive number`);
  }
  return Math.floor(value);
}

function showHelpAndExit() {
  if (!process.argv.includes("--help") && !process.argv.includes("-h")) return;

  console.log(`Coze knowledge export

Usage:
  npx tsx coze方案/export-coze-kb.ts [options]

Options:
  --input <path>              Source search index. Default: public/search-index.previews.json
  --out-dir <path>            Output directory. Default: coze方案/out
  --limit <number>            Export only the first N records for testing.
  --site-origin <url>         Prefix PDF and preview links, e.g. https://yangminggu.github.io
  --max-content-chars <num>   Max characters per exported content block. Default: ${DEFAULT_MAX_CONTENT_CHARS}
`);
  process.exit(0);
}

function compact(value: unknown): string {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeMultiline(value: unknown): string {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function trimLatexNoise(value: string): string {
  return value
    .replace(/\\begin\{[^}]+\}/g, "")
    .replace(/\\end\{[^}]+\}/g, "")
    .replace(/\\item\b/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function ensureLeadingSlash(value: string): string {
  if (!value) return "";
  return value.startsWith("/") ? value : `/${value}`;
}

function absoluteUrl(pathOrUrl: string, siteOrigin: string): string {
  if (!pathOrUrl) return "";
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  if (!siteOrigin) return pathOrUrl;

  const origin = siteOrigin.replace(/\/+$/, "");
  return `${origin}${ensureLeadingSlash(pathOrUrl)}`;
}

function makePdfUrl(item: SearchIndexItem, siteOrigin: string): string {
  const pdf = ensureLeadingSlash(compact(item.pdf ?? item.pdfPath));
  const page = item.pdfLocator?.page;
  if (!pdf) return "";
  const url = absoluteUrl(pdf, siteOrigin);
  return page ? `${url}#page=${page}` : url;
}

function getText(item: SearchIndexItem): string {
  const text = compact(item.text);
  if (text) return text;

  const content = compact(item.content);
  if (content) return trimLatexNoise(content);

  const rawContent = compact(item.rawContent);
  return trimLatexNoise(rawContent);
}

function getRawLatex(item: SearchIndexItem): string {
  return normalizeMultiline(item.rawContent || item.content);
}

function truncateContent(value: string, maxChars: number): string {
  if (value.length <= maxChars) return value;
  return `${value.slice(0, maxChars).trim()}\n\n[内容已截断，完整内容请查看来源 PDF]`;
}

function toRecord(
  item: SearchIndexItem,
  options: { siteOrigin: string; maxContentChars: number },
): ExportRecord | null {
  const id = compact(item.id);
  const noteTitle = compact(item.noteTitle ?? item.title);
  const sectionTitle = compact(item.sectionTitle ?? item.section);
  const subsectionTitle = compact(item.subsectionTitle ?? item.subsection);
  const blockType = compact(item.blockType ?? item.kind);
  const blockTitle = compact(item.blockTitle ?? item.previewTitle);
  const body = getText(item);
  const rawLatex = getRawLatex(item);

  if (!id || !body) return null;

  const titleParts = [noteTitle, sectionTitle, subsectionTitle, blockTitle].filter(Boolean);
  const title = titleParts.join(" / ") || id;
  const pdfUrl = makePdfUrl(item, options.siteOrigin);
  const previewImage = absoluteUrl(compact(item.previewImage), options.siteOrigin);
  const page = item.pdfLocator?.page ?? null;
  const latexBlock =
    rawLatex && rawLatex !== body
      ? ["", "原始 LaTeX：", "```latex", rawLatex, "```"].join("\n")
      : "";

  const content = truncateContent([
    `标题：${title}`,
    noteTitle ? `笔记：${noteTitle}` : "",
    sectionTitle ? `章节：${sectionTitle}` : "",
    subsectionTitle ? `小节：${subsectionTitle}` : "",
    blockType ? `类型：${blockType}` : "",
    page ? `PDF 页码：${page}` : "",
    pdfUrl ? `PDF 链接：${pdfUrl}` : "",
    "",
    body,
    latexBlock,
  ]
    .filter((line, index, lines) => line || lines[index - 1])
    .join("\n")
    .trim(), options.maxContentChars);

  return {
    id,
    title,
    content,
    metadata: {
      repo: compact(item.repo),
      noteTitle,
      sectionTitle,
      subsectionTitle,
      blockType,
      blockTitle,
      page,
      pdfUrl,
      previewImage,
      sourcePath: compact(item.sourcePath),
      startLine: item.startLine ?? null,
      endLine: item.endLine ?? null,
    },
  };
}

function toMarkdown(records: ExportRecord[]): string {
  const chunks = records.map((record) => {
    const meta = record.metadata;
    return [
      `# ${record.title}`,
      "",
      `ID: ${record.id}`,
      meta.repo ? `Repo: ${meta.repo}` : "",
      meta.page ? `Page: ${meta.page}` : "",
      meta.pdfUrl ? `PDF: ${meta.pdfUrl}` : "",
      meta.previewImage ? `Preview: ${meta.previewImage}` : "",
      "",
      record.content,
    ]
      .filter(Boolean)
      .join("\n");
  });

  return `${chunks.join("\n\n---\n\n")}\n`;
}

function main() {
  showHelpAndExit();

  const inputPath = path.resolve(readArg("--input") ?? DEFAULT_INPUT);
  const outDir = path.resolve(readArg("--out-dir") ?? DEFAULT_OUT_DIR);
  const limit = readLimit();
  const siteOrigin = compact(readArg("--site-origin"));
  const maxContentChars = readPositiveInt("--max-content-chars", DEFAULT_MAX_CONTENT_CHARS);

  if (!fs.existsSync(inputPath)) {
    throw new Error(`Input file not found: ${inputPath}`);
  }

  const raw = fs.readFileSync(inputPath, "utf8");
  const items = JSON.parse(raw) as SearchIndexItem[];
  const records = items
    .map((item) => toRecord(item, { siteOrigin, maxContentChars }))
    .filter((record): record is ExportRecord => Boolean(record));
  const selected = limit ? records.slice(0, limit) : records;

  fs.mkdirSync(outDir, { recursive: true });

  const jsonlPath = path.join(outDir, "coze-kb.jsonl");
  const mdPath = path.join(outDir, "coze-kb.md");

  fs.writeFileSync(
    jsonlPath,
    selected.map((record) => JSON.stringify(record)).join("\n") + "\n",
    "utf8",
  );
  fs.writeFileSync(mdPath, toMarkdown(selected), "utf8");

  console.log(`[coze-kb] input: ${inputPath}`);
  console.log(`[coze-kb] records: ${selected.length}/${records.length}`);
  console.log(`[coze-kb] siteOrigin: ${siteOrigin || "(relative links)"}`);
  console.log(`[coze-kb] maxContentChars: ${maxContentChars}`);
  console.log(`[coze-kb] wrote: ${jsonlPath}`);
  console.log(`[coze-kb] wrote: ${mdPath}`);
}

main();
