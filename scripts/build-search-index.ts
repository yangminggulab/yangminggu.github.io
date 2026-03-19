import fs from "fs";
import path from "path";
import { parseLatexToBlocks, type LatexBlock } from "../src/lib/latex-parser";

/**
 * =========================
 * 这部分：类型定义
 * =========================
 * 这一块基本没有问题。
 * 它只是约定数据长什么样，不太会导致“搜索不出来”。
 */

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

/**
 * =========================
 * 这部分：项目根目录
 * =========================
 * 这一块通常也没有问题。
 * process.cwd() 一般就是当前仓库根目录。
 */
const PROJECT_ROOT = process.cwd();

/**
 * =========================
 * 这部分：NOTE_SOURCES
 * =========================
 * 这是【高风险区域 1】。
 * 最容易出问题的地方之一。
 *
 * 你要重点检查：
 * 1. texPath 是否真的是仓库里的真实路径
 * 2. pdfPath 是否和你网站实际 PDF 路径一致
 *
 * 你当前很可能有两个问题：
 * - texPath: "notes/real-analysis/main.tex"
 *   这个路径很可能不对，因为你仓库截图里未必有 notes 目录
 *
 * - pdfPath: "/pdfs/real-analysis.pdf"
 *   这个路径也可能不对，因为你仓库里看起来是 pdf/ 不是 pdfs/
 *
 * 建议你之后优先改这里排查。
 */
const NOTE_SOURCES: NoteSource[] = [
  {
    id: "real-analysis",
    title: "Real Analysis",

    // 【重点检查】这个路径必须是仓库根目录出发的真实相对路径
    // 比如如果真实文件在 来源/real-analysis/main.tex
    // 就要改成 "来源/real-analysis/main.tex"
    texPath: "notes/real-analysis/main.tex",

    // 【重点检查】如果你网站里实际目录是 /pdf/xxx.pdf
    // 这里就应该写 "/pdf/real-analysis.pdf"，不是 "/pdfs/..."
    pdfPath: "/pdfs/real-analysis.pdf",
  },
];

/**
 * =========================
 * 这部分：创建目录
 * =========================
 * 这一块逻辑本身没有问题。
 * 但你当前项目里“要不要创建 public 目录”是值得怀疑的。
 * 因为你的网站是静态 GitHub Pages，不一定需要 public/。
 */
function ensureDirExists(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * =========================
 * 这部分：读取文本文件
 * =========================
 * 这一块基本没问题。
 * 只要传进来的路径是对的，就能正常读。
 */
function readTextFile(absPath: string): string {
  return fs.readFileSync(absPath, "utf-8");
}

/**
 * =========================
 * 这部分：给单篇笔记建立索引
 * =========================
 * 这是【高风险区域 2】。
 * 它本身逻辑没什么大问题，但非常依赖：
 * 1. texPath 路径正确
 * 2. latex-parser.ts 能正确切块
 *
 * 如果这里出问题，常见表现是：
 * - 直接提示文件不存在
 * - 生成出来 blocks.length = 0
 */
function buildIndexForOneNote(note: NoteSource): SearchIndexItem[] {
  const absTexPath = path.join(PROJECT_ROOT, note.texPath);

  /**
   * 【建议保留这个日志】
   * 用来检查程序实际去找的绝对路径到底是什么。
   * 如果路径不对，你会很容易看出来。
   */
  console.log("[search-index] absTexPath =", absTexPath);

  /**
   * 【重点检查】
   * 如果你看到控制台输出：
   * Skipped missing file: ...
   * 那几乎肯定就是 texPath 写错了。
   */
  if (!fs.existsSync(absTexPath)) {
    console.warn(`[search-index] Skipped missing file: ${note.texPath}`);
    return [];
  }

  const texContent = readTextFile(absTexPath);

  const blocks = parseLatexToBlocks(texContent, {
    docTitle: note.title,
    sourcePath: note.texPath,
  });

  /**
   * 【建议保留这个日志】
   * 如果这里 blocks.length 是 0，
   * 说明问题不在路径，而更可能在 latex-parser.ts。
   */
  console.log(`[search-index] Parsed ${blocks.length} blocks from ${note.title}`);

  return blocks.map((block) => ({
    ...block,
    noteId: note.id,
    noteTitle: note.title,
    texPath: note.texPath,
    pdfPath: note.pdfPath,
  }));
}

/**
 * =========================
 * 这部分：写出 search-index.json
 * =========================
 * 这是【高风险区域 3】。
 * 也是你现在最可能真的有问题的地方。
 *
 * 你当前代码是写到：
 *   public/search-index.json
 *
 * 但你的前端 index.html 里写的是：
 *   fetch("search-index.json")
 *
 * 这意味着网页在找“仓库根目录/search-index.json”，
 * 而不是 public/search-index.json。
 *
 * 所以如果你现在网页搜不出来，
 * 这一块非常可能就是原因之一。
 *
 * 对你当前 GitHub Pages 静态站，更建议直接写到根目录：
 *
 *   const outputPath = path.join(PROJECT_ROOT, "search-index.json");
 *
 * 而不是 public/ 目录。
 */
function writeSearchIndex(items: SearchIndexItem[]): void {
  const outputDir = path.join(PROJECT_ROOT, "public");
  const outputPath = path.join(outputDir, "search-index.json");

  /**
   * 【建议保留这个日志】
   * 看看最终文件到底被写到哪了。
   */
  console.log("[search-index] outputDir =", outputDir);
  console.log("[search-index] outputPath =", outputPath);

  ensureDirExists(outputDir);

  fs.writeFileSync(outputPath, JSON.stringify(items, null, 2), "utf-8");

  console.log(`[search-index] Wrote ${items.length} blocks to public/search-index.json`);
}

/**
 * =========================
 * 这部分：主流程 main
 * =========================
 * 这一块整体逻辑基本没有问题。
 * 它就是：
 * 1. 遍历 NOTE_SOURCES
 * 2. 一篇一篇建索引
 * 3. 汇总写出 JSON
 *
 * 如果出问题，往往不是 main 本身有错，
 * 而是：
 * - NOTE_SOURCES 路径错
 * - parser 没切出块
 * - 输出位置不对
 */
function main(): void {
  const allItems: SearchIndexItem[] = [];

  for (const note of NOTE_SOURCES) {
    const items = buildIndexForOneNote(note);
    allItems.push(...items);
    console.log(`[search-index] Indexed ${note.title}: ${items.length} blocks`);
  }

  /**
   * 【建议保留这个日志】
   * 看看最终总共有多少条。
   * 如果这里是 0，说明前面某一步出了问题。
   */
  console.log(`[search-index] Total blocks = ${allItems.length}`);

  writeSearchIndex(allItems);
}

main();
