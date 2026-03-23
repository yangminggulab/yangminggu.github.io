import fs from "fs";
import path from "path";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type SearchBlock = {
  id: string;
  repo: string;
  title: string;
  pdf: string;
  main_tex: string;
  synctex?: string;
  sourcePath?: string;
  startLine?: number;
  endLine?: number;
  [key: string]: any;
};

type PdfLocator = {
  page: number;
  x: number | null;
  y: number | null;
  h: number | null;
  v: number | null;
  W: number | null;
  H: number | null;
};

const ROOT_DIR = path.resolve(__dirname, "..");
const INPUT_PATH = path.join(ROOT_DIR, "public", "search-index.json");
const OUTPUT_PATH = path.join(ROOT_DIR, "public", "search-index.enriched.json");

// 设为 null 表示处理所有仓库
const ONLY_REPO: string | null = null;

function parseSynctexOutput(output: string): PdfLocator | null {
  const lines = output.split(/\r?\n/);

  let page: number | null = null;
  let x: number | null = null;
  let y: number | null = null;
  let h: number | null = null;
  let v: number | null = null;
  let W: number | null = null;
  let H: number | null = null;

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("Page:")) page = Number(trimmed.slice(5).trim());
    else if (trimmed.startsWith("x:")) x = Number(trimmed.slice(2).trim());
    else if (trimmed.startsWith("y:")) y = Number(trimmed.slice(2).trim());
    else if (trimmed.startsWith("h:")) h = Number(trimmed.slice(2).trim());
    else if (trimmed.startsWith("v:")) v = Number(trimmed.slice(2).trim());
    else if (trimmed.startsWith("W:")) W = Number(trimmed.slice(2).trim());
    else if (trimmed.startsWith("H:")) H = Number(trimmed.slice(2).trim());
  }

  if (page == null || Number.isNaN(page)) return null;

  return { page, x, y, h, v, W, H };
}

function resolveBestPdfPath(block: SearchBlock): string | null {
  if (block.synctex) {
    const synctexAbs = path.isAbsolute(block.synctex)
      ? block.synctex
      : path.join(ROOT_DIR, block.synctex);

    const synctexDir = path.dirname(synctexAbs);
    const mainPdf = path.join(synctexDir, "main.pdf");

    if (fs.existsSync(mainPdf)) return mainPdf;

    if (fs.existsSync(synctexDir)) {
      const pdfs = fs
        .readdirSync(synctexDir)
        .filter((name) => name.toLowerCase().endsWith(".pdf"));
      if (pdfs.length === 1) {
        return path.join(synctexDir, pdfs[0]);
      }
    }
  }

  const copiedPdf = path.isAbsolute(block.pdf)
    ? block.pdf
    : path.join(ROOT_DIR, block.pdf);

  if (fs.existsSync(copiedPdf)) return copiedPdf;

  return null;
}

function main() {
  if (!fs.existsSync(INPUT_PATH)) {
    console.error(`Missing input: ${INPUT_PATH}`);
    process.exit(1);
  }

  const blocks = JSON.parse(fs.readFileSync(INPUT_PATH, "utf-8")) as SearchBlock[];
  const enriched: SearchBlock[] = [];

  for (const block of blocks) {
    if (ONLY_REPO && block.repo !== ONLY_REPO) {
      enriched.push(block);
      continue;
    }

    try {
      if (!block.sourcePath || !block.startLine || !block.synctex) {
        enriched.push({
          ...block,
          pdfLocator: null,
          debugReason: "missing sourcePath/startLine/synctex",
        });
        continue;
      }

      const synctexAbs = path.isAbsolute(block.synctex)
        ? block.synctex
        : path.join(ROOT_DIR, block.synctex);

      if (!fs.existsSync(synctexAbs)) {
        enriched.push({
          ...block,
          pdfLocator: null,
          debugReason: `synctex missing: ${synctexAbs}`,
        });
        continue;
      }

      const pdfPath = resolveBestPdfPath(block);
      if (!pdfPath) {
        enriched.push({
          ...block,
          pdfLocator: null,
          debugReason: "no usable pdf found",
        });
        continue;
      }

      const synctexDir = path.dirname(synctexAbs);

      const args = [
        "view",
        "-i",
        `${block.startLine}:1:${block.sourcePath}`,
        "-o",
        pdfPath,
        "-d",
        synctexDir,
      ];

      const result = spawnSync("synctex", args, {
        encoding: "utf-8",
        cwd: synctexDir,
      });

      const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
      const pos = parseSynctexOutput(output);

      enriched.push({
        ...block,
        pdfLocator: pos,
        debugExitStatus: result.status,
        debugPdfPath: pdfPath,
      });
    } catch (err: any) {
      enriched.push({
        ...block,
        pdfLocator: null,
        debugReason: err?.message ?? "unknown error",
      });
    }
  }

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(enriched, null, 2), "utf-8");
  console.log(`Wrote: ${OUTPUT_PATH}`);
}

main();