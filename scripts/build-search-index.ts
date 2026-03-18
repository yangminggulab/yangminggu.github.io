import fs from "fs";
import path from "path";
import { parseLatexToBlocks, type LatexBlock } from "../src/lib/latex-parser";

interface NoteSource {
  id: string;
  title: string;
  texPath: string;
  pdfPath?: string;
}

interface SearchIndexItem extends LatexBlock {
  noteId: string;
  noteTitle: string;
  texPath: string;
  pdfPath?: string;
}

const PROJECT_ROOT = process.cwd();

const NOTE_SOURCES: NoteSource[] = [
  {
    id: "real-analysis",
    title: "Real Analysis",
    texPath: "notes/real-analysis/main.tex",
    pdfPath: "/pdfs/real-analysis.pdf",
  },
];

function ensureDirExists(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function readTextFile(absPath: string): string {
  return fs.readFileSync(absPath, "utf-8");
}

function buildIndexForOneNote(note: NoteSource): SearchIndexItem[] {
  const absTexPath = path.join(PROJECT_ROOT, note.texPath);

  if (!fs.existsSync(absTexPath)) {
    console.warn(`[search-index] Skipped missing file: ${note.texPath}`);
    return [];
  }

  const texContent = readTextFile(absTexPath);

  const blocks = parseLatexToBlocks(texContent, {
    docTitle: note.title,
    sourcePath: note.texPath,
  });

  return blocks.map((block) => ({
    ...block,
    noteId: note.id,
    noteTitle: note.title,
    texPath: note.texPath,
    pdfPath: note.pdfPath,
  }));
}

function writeSearchIndex(items: SearchIndexItem[]): void {
  const outputDir = path.join(PROJECT_ROOT, "public");
  const outputPath = path.join(outputDir, "search-index.json");

  ensureDirExists(outputDir);

  fs.writeFileSync(outputPath, JSON.stringify(items, null, 2), "utf-8");

  console.log(`[search-index] Wrote ${items.length} blocks to public/search-index.json`);
}

function main(): void {
  const allItems: SearchIndexItem[] = [];

  for (const note of NOTE_SOURCES) {
    const items = buildIndexForOneNote(note);
    allItems.push(...items);
    console.log(`[search-index] Indexed ${note.title}: ${items.length} blocks`);
  }

  writeSearchIndex(allItems);
}

main();
