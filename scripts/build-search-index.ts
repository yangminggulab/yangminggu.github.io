import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type ManifestItem = {
  repo: string;
  title: string;
  pdf: string;
  main_tex: string;
  synctex?: string;
};

type SearchBlock = {
  id: string;
  repo: string;
  title: string;
  pdf: string;
  main_tex: string;
  synctex?: string;
  section: string;
  subsection: string;
  kind: string;
  blockTitle: string;
  previewType: string;
  previewTitle: string;
  rawContent: string;
  content: string;
  text: string;
  sourcePath: string;
  startLine: number;
  endLine: number;
};

type SharedState = {
  currentSection: string;
  currentSubsection: string;
  counter: number;
};

const ROOT_DIR = path.resolve(__dirname, "..");
const MANIFEST_PATH = path.join(ROOT_DIR, "notes_manifest.json");
const OUTPUT_DIR = path.join(ROOT_DIR, "public");
const OUTPUT_PATH = path.join(OUTPUT_DIR, "search-index.json");

const CARD_ENVIRONMENTS = new Set([
  "definition",
  "theorem",
  "lemma",
  "proposition",
  "corollary",
  "example",
  "note",
  "remark",
  "homework",
  "solution",
  "dxtips",
  "tip",
]);

function latexToPlainText(input: string): string {
  let s = input;
  s = s.replace(/(^|[^\\])%.*/gm, "$1");
  s = s.replace(/\\begin\{[^}]+\}/g, " ");
  s = s.replace(/\\end\{[^}]+\}/g, " ");
  for (let i = 0; i < 4; i++) {
    s = s.replace(/\\[a-zA-Z*]+(?:\[[^\]]*\])?\{([^{}]*)\}/g, "$1");
  }
  s = s.replace(/\\[a-zA-Z@]+[*]?(?:\[[^\]]*\])?/g, " ");
  s = s.replace(/\$\$[\s\S]*?\$\$/g, " ");
  s = s.replace(/\$[^$]*\$/g, " ");
  s = s.replace(/\\\[[\s\S]*?\\\]/g, " ");
  s = s.replace(/\\\([\s\S]*?\\\)/g, " ");
  s = s.replace(/[{}]/g, " ");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

function extractCommandArg(line: string, cmd: string): string | null {
  const re = new RegExp(`\\\\${cmd}\\*?(?:\$begin:math:display$\[\^\\$end:math:display$]*\\])?\\{([^}]*)\\}`);
  const m = line.match(re);
  return m ? m[1].trim() : null;
}

function extractEnvironmentName(line: string): string | null {
  const m = line.match(/\\begin\{([^}]+)\}/);
  return m ? m[1].trim() : null;
}

function extractIncludeTarget(line: string): string | null {
  const m = line.match(/\\(?:input|include)\{([^}]+)\}/);
  return m ? m[1].trim() : null;
}

function resolveIncludedTexPath(baseDir: string, target: string): string {
  let p = target.trim();
  if (!p.endsWith(".tex")) p += ".tex";
  return path.resolve(baseDir, p);
}

function extractEnvironmentDisplayTitle(raw: string, envName: string): string {
  const escapedEnv = envName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = raw.match(new RegExp(`\\\\begin\\{${escapedEnv}\\}\$begin:math:display$\(\[\^\\$end:math:display$]+)\\]`));
  if (m) {
    const title = latexToPlainText(m[1]);
    if (title) return title;
  }
  return "";
}

function makeBlockTitle(
  kind: string,
  raw: string,
  text: string,
  currentSection: string,
  currentSubsection: string,
): string {
  const envTitle = extractEnvironmentDisplayTitle(raw, kind);
  if (envTitle) return envTitle;
  if (currentSubsection) return currentSubsection;
  if (currentSection) return currentSection;

  const kindLabelMap: Record<string, string> = {
    definition: "Definition",
    theorem: "Theorem",
    lemma: "Lemma",
    proposition: "Proposition",
    corollary: "Corollary",
    example: "Example",
    note: "Note",
    remark: "Remark",
    homework: "Homework",
    solution: "Solution",
    dxtips: "Tip",
    tip: "Tip",
    paragraph: "Text",
  };

  if (kind !== "paragraph") return kindLabelMap[kind] || kind;
  return text.slice(0, 36) || "Text";
}

function makePreviewType(kind: string): string {
  if (kind === "dxtips" || kind === "tip") return "tip";
  if (kind === "definition") return "definition";
  if (["theorem", "lemma", "proposition", "corollary"].includes(kind)) return "theorem";
  if (kind === "example") return "example";
  if (kind === "note" || kind === "remark") return "note";
  if (kind === "homework") return "homework";
  if (kind === "solution") return "solution";
  return "text";
}

function shouldKeepParagraph(raw: string, text: string): boolean {
  if (!text || text.length < 45) return false;
  const slashCount = (raw.match(/\\/g) || []).length;
  if (slashCount > 8) return false;
  return true;
}

function extractBlocksFromTex(
  tex: string,
  item: ManifestItem,
  filePath: string,
  visited = new Set<string>(),
  state?: SharedState,
  bodyOnly = false
): SearchBlock[] {
  const absPath = path.resolve(filePath);
  if (visited.has(absPath)) return [];
  visited.add(absPath);

  const sharedState: SharedState = state ?? {
    currentSection: "",
    currentSubsection: "",
    counter: 0,
  };

  const lines = tex.split(/\r?\n/);
  const blocks: SearchBlock[] = [];

  let paragraphBuffer: string[] = [];
  let paragraphStartLine = 0;
  let envBuffer: string[] = [];
  let envStartLine = 0;
  let inEnv = false;
  let currentEnv = "";
  let inDocument = !bodyOnly;

  const pushBlock = (kind: string, raw: string, text: string, startLine: number, endLine: number) => {
    sharedState.counter += 1;
    const blockTitle = makeBlockTitle(
      kind, raw, text, sharedState.currentSection, sharedState.currentSubsection
    );

    blocks.push({
      id: `${item.repo}-${sharedState.counter}`,
      repo: item.repo,
      title: item.title,
      pdf: item.pdf,
      main_tex: item.main_tex,
      synctex: item.synctex,
      section: sharedState.currentSection,
      subsection: sharedState.currentSubsection,
      kind,
      blockTitle,
      previewType: makePreviewType(kind),
      previewTitle: blockTitle,
      rawContent: raw,
      content: raw,
      text,
      sourcePath: absPath,
      startLine,
      endLine,
    });
  };

  const flushParagraph = (endLine: number) => {
    const raw = paragraphBuffer.join("\n").trim();
    const startLine = paragraphStartLine;
    paragraphBuffer = [];
    paragraphStartLine = 0;
    if (!raw) return;
    const text = latexToPlainText(raw);
    if (!shouldKeepParagraph(raw, text)) return;
    pushBlock("paragraph", raw, text, startLine, endLine);
  };

  const flushEnv = (endLine: number) => {
    const raw = envBuffer.join("\n").trim();
    const startLine = envStartLine;
    envBuffer = [];
    envStartLine = 0;
    inEnv = false;
    if (!raw) {
      currentEnv = "";
      return;
    }
    const text = latexToPlainText(raw);
    if (!text || text.length < 5) {
      currentEnv = "";
      return;
    }
    if (CARD_ENVIRONMENTS.has(currentEnv)) {
      pushBlock(currentEnv, raw, text, startLine, endLine);
    }
    currentEnv = "";
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    const lineNo = i + 1;

    if (bodyOnly && !inDocument) {
      if (/^\\begin\{document\}/.test(trimmed)) inDocument = true;
      continue;
    }

    if (bodyOnly && /^\\end\{document\}/.test(trimmed)) {
      if (inEnv) flushEnv(lineNo - 1);
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      break;
    }

    const sec = extractCommandArg(trimmed, "section");
    if (sec !== null && !inEnv) {
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      sharedState.currentSection = latexToPlainText(sec);
      sharedState.currentSubsection = "";
      continue;
    }

    const subsec = extractCommandArg(trimmed, "subsection");
    if (subsec !== null && !inEnv) {
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      sharedState.currentSubsection = latexToPlainText(subsec);
      continue;
    }

    const includeTarget = extractIncludeTarget(trimmed);
    if (!inEnv && includeTarget) {
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      const childPath = resolveIncludedTexPath(path.dirname(absPath), includeTarget);
      if (fs.existsSync(childPath)) {
        const childTex = fs.readFileSync(childPath, "utf-8");
        const childBlocks = extractBlocksFromTex(
          childTex, item, childPath, visited, sharedState, false
        );
        blocks.push(...childBlocks);
      }
      continue;
    }

    const envName = extractEnvironmentName(trimmed);
    if (!inEnv && envName) {
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      inEnv = true;
      currentEnv = envName;
      envStartLine = lineNo;
      envBuffer.push(line);
      continue;
    }

    if (inEnv) {
      envBuffer.push(line);
      const escapedEnv = currentEnv.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (trimmed.match(new RegExp(String.raw`\\end\{${escapedEnv}\}`))) {
        flushEnv(lineNo);
      }
      continue;
    }

    if (trimmed === "") {
      if (paragraphBuffer.length > 0) flushParagraph(lineNo - 1);
      continue;
    }

    if (paragraphBuffer.length === 0) paragraphStartLine = lineNo;
    paragraphBuffer.push(line);
  }

  if (inEnv) flushEnv(lines.length);
  if (paragraphBuffer.length > 0) flushParagraph(lines.length);

  return blocks;
}

function main() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    console.error(`[search-index] Missing manifest: ${MANIFEST_PATH}`);
    process.exit(1);
  }

  const rawManifest = fs.readFileSync(MANIFEST_PATH, "utf-8");
  const manifest = JSON.parse(rawManifest) as ManifestItem[];
  const allBlocks: SearchBlock[] = [];

  console.log(`[search-index] manifestPath = ${MANIFEST_PATH}`);
  console.log(`[search-index] manifest entries = ${manifest.length}`);

  for (const item of manifest) {
    const absTexPath = path.isAbsolute(item.main_tex)
      ? item.main_tex
      : path.resolve(ROOT_DIR, item.main_tex);

    console.log(`\n[search-index] title = ${item.title}`);
    console.log(`[search-index] absTexPath = ${absTexPath}`);

    if (!fs.existsSync(absTexPath)) {
      console.log(`[search-index] Skipped missing file: ${item.main_tex}`);
      continue;
    }

    const tex = fs.readFileSync(absTexPath, "utf-8");
    const blocks = extractBlocksFromTex(
      tex, item, absTexPath, new Set<string>(), undefined, true
    );

    console.log(`[search-index] Indexed ${item.title}: ${blocks.length} blocks`);
    allBlocks.push(...blocks);
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(allBlocks, null, 2), "utf-8");

  console.log(`\n[search-index] Total blocks = ${allBlocks.length}`);
  console.log(`[search-index] outputDir = ${OUTPUT_DIR}`);
  console.log(`[search-index] outputPath = ${OUTPUT_PATH}`);
  console.log(`[search-index] Wrote ${allBlocks.length} blocks to public/search-index.json`);
}

main();