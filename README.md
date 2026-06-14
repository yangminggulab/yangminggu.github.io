# yangminggu.github.io

## 整体架构

`yangminggu.github.io` 是一个面向数学/技术笔记的静态知识站点。它的核心不是传统后端服务，而是一条自动化内容生产流水线：从多个 `dx*` LaTeX 笔记仓库拉取源文件，编译成 PDF，再把 LaTeX 内容抽取成可搜索的结构化索引，最后由一个纯静态首页负责展示书架、视频和搜索结果。

最上层可以看成下面这棵树：

```text
yangminggu.github.io
├── 内容输入层
│   ├── GitHub: yangminggulab/dx* 仓库
│   │   ├── main.tex
│   │   ├── 章节 .tex 文件
│   │   └── LaTeX 编译资源
│   └── 本仓库 video/*.mp4
│
├── 自动构建层
│   ├── .github/workflows/build.yml
│   │   ├── 安装 Python / Node / TeX Live 依赖
│   │   ├── 运行 Python 构建脚本
│   │   ├── 运行 TypeScript 搜索索引脚本
│   │   └── 把生成结果提交回 main 分支
│   │
│   └── scripts/
│       ├── build_notes.py
│       │   ├── 调 GitHub API 找到 dx* 仓库
│       │   ├── clone / fetch 最新笔记仓库
│       │   ├── latexmk 编译 main.tex
│       │   ├── 复制 PDF 到 pdf/
│       │   ├── 生成 books.json
│       │   ├── 生成 notes_manifest.json
│       │   ├── 更新 build_state.json
│       │   ├── 写出 build_changed.json（本次重新编译的仓库）
│       │   └── 生成 video/videos.json
│       │
│       ├── build-search-index.ts
│       │   ├── 读取 notes_manifest.json 和 build_changed.json
│       │   ├── 变动仓库递归解析 main.tex / input / include，未变动仓库复用旧块
│       │   ├── 抽取 definition/theorem/example/note/dxtips 等块
│       │   └── 合并生成 public/search-index.json
│       │
│       ├── enrich-search-index.ts
│       │   ├── 读取 public/search-index.json 和 build_changed.json
│       │   ├── 变动仓库调用 synctex view 定位，未变动仓库复用旧坐标
│       │   └── 合并生成 public/search-index.enriched.json
│       │
│       └── render_search_previews.py
│           ├── 读取 public/search-index.enriched.json 和 build_changed.json
│           ├── 变动仓库用 PyMuPDF 重新截图，未变动仓库复用旧图
│           ├── 用 pdfLocator 锚点裁剪：有框卡片贴彩色框，无框块裁到下一块
│           ├── 输出/复用 public/search-previews/*.png 并清理孤儿图
│           └── 合并生成 public/search-index.previews.json
│
├── 静态数据层
│   ├── pdf/*.pdf
│   ├── books.json
│   ├── notes_manifest.json
│   ├── build_state.json
│   ├── video/videos.json
│   └── public/
│       ├── search-index.json
│       ├── search-index.enriched.json
│       ├── search-index.previews.json
│       └── search-previews/*.png
│
└── 前端展示层
    ├── index.html
    │   ├── 加载 books.json 渲染 PDF 书架
    │   ├── 加载 video/videos.json 渲染视频列表
    │   ├── 加载 public/search-index.previews.json 做全文搜索
    │   └── 打开 pdf/*.pdf 或展示搜索预览
    └── src/
        ├── components/
        └── lib/
```

这个架构的重点是“构建时做重活，运行时只读静态文件”。LaTeX 编译、PDF 坐标定位、搜索预览图裁剪都在 GitHub Actions 里提前完成；用户访问网站时，浏览器只需要请求 JSON、PDF、图片和视频，不需要服务器实时计算。

## 信息传递链路

整个项目的信息流可以分成五段：

```text
dx* 仓库的 LaTeX 源码
  -> build_notes.py
  -> PDF 文件 + 笔记清单
  -> build-search-index.ts
  -> 文本搜索块
  -> enrich-search-index.ts
  -> PDF 定位信息
  -> render_search_previews.py
  -> 搜索预览图片
  -> index.html
  -> 用户在网页上浏览、搜索、打开 PDF
```

更具体地说：

1. `build_notes.py` 先通过 GitHub API 获取 `yangminggulab` 用户名下所有仓库，只保留仓库名以 `dx` 开头的课程笔记仓库。
2. 对每个匹配仓库，脚本会在 `temp_repos/` 中 clone 或更新到最新版本，然后查找 `main.tex`。
3. 找到 `main.tex` 后，脚本调用 `latexmk -xelatex -synctex=1` 编译 PDF。这里开启 SyncTeX 是后续“从搜索结果跳回 PDF 位置”和“裁剪预览图”的关键。
4. 编译产物会被复制到 `pdf/`，同时生成 `books.json` 给首页书架使用，生成 `notes_manifest.json` 给搜索索引脚本使用。
5. `build-search-index.ts` 读取 `notes_manifest.json`，再打开每本笔记的 `main.tex`，沿着 `\input{}` 和 `\include{}` 递归读取章节文件，把 LaTeX 中的定义、定理、例题、笔记、提示和普通段落抽成结构化 JSON。
6. `enrich-search-index.ts` 读取基础搜索索引，对每个带有源文件路径和行号的内容块调用 `synctex view`，把“某个 TeX 文件第几行”转换成“PDF 第几页、页面坐标是多少”。
7. `render_search_previews.py` 读取带坐标的索引，用 PyMuPDF 打开 PDF，按 `pdfLocator` 锚点裁剪：有框卡片（定义/定理/提示等）贴合彩色 tcolorbox 边界，无框块（例题/笔记/注）从标签裁到下一个块，生成 PNG 预览图。
8. `index.html` 在浏览器中读取最终的 `public/search-index.previews.json`，搜索时展示文本摘要或预览图片，并通过 `books.json` 和 `pdf/` 渲染可打开的 PDF 书架。

## 运行时和构建时的分工

| 层级 | 做什么 | 产物 |
| --- | --- | --- |
| 构建时 | 拉取笔记仓库、编译 PDF、解析 LaTeX、定位 PDF 坐标、裁剪预览图 | `pdf/`、`books.json`、`notes_manifest.json`、`public/search-*.json`、`public/search-previews/` |
| 运行时 | 浏览器加载静态资源，完成书架展示、视频展示、搜索匹配和结果渲染 | 用户看到的 GitHub Pages 页面 |

这样设计的好处是部署简单、访问速度快、没有服务器维护成本。复杂计算全部被前置到 CI 里，最终站点只是 GitHub Pages 上的一组静态文件。

## Python 文件说明

项目里参与主流程的 Python 文件有两个。

### `scripts/build_notes.py`

这个文件负责“内容输入层 -> 静态数据层”的第一段，是整个构建流水线的入口。

输入：

- GitHub API 返回的 `yangminggulab` 账号仓库列表。
- 每个 `dx*` 仓库里的 LaTeX 源文件，尤其是 `main.tex`。
- 本仓库已有的 `build_state.json`，用于判断仓库是否需要重新编译。
- 本仓库 `video/*.mp4`，用于生成视频清单。

核心逻辑：

1. 读取环境变量 `GITHUB_TOKEN`，用于访问 GitHub API，减少 API 限流风险。
2. 读取环境变量 `FORCE_REBUILD`，当它等于 `1` 时强制重新编译所有匹配仓库。
3. 调用 GitHub API 分页获取 `yangminggulab` 下的仓库列表。
4. 只处理仓库名以 `dx` 开头的仓库。
5. 如果 `temp_repos/<repo>` 不存在，就用浅克隆拉取仓库；如果已经存在，就 fetch 最新远端状态并 reset 到 `origin/HEAD`。
6. 在仓库中递归查找 `main.tex`，并选取第一个候选文件作为编译入口。
7. 根据 `build_state.json`、远端 `pushed_at`、本地 PDF 和 SyncTeX 是否存在，判断是否需要编译。
8. 需要编译时调用 `latexmk -xelatex -synctex=1 -interaction=nonstopmode -f main.tex`。
9. 如果编译失败，会输出 `main.log` 或 `build.log` 的关键尾部日志，方便在 GitHub Actions 里定位 LaTeX 错误。
10. 编译成功后，把 PDF 复制到根目录的 `pdf/`。
11. 记录每本书的展示信息到 `books.json`。
12. 记录每本书的搜索入口信息到 `notes_manifest.json`，包括仓库名、标题、PDF 路径、`main_tex` 路径和 SyncTeX 路径。
13. 更新 `build_state.json`，避免下一次构建重复编译没有变化的仓库。
14. 把本次真正重新编译（`need_compile` 为真）的笔记仓库写入 `build_changed.json`，供后续索引/预览脚本做增量重建；早退时写入空列表。
15. 清理已经不存在的仓库对应的孤儿 PDF。
16. 扫描 `video/*.mp4`，生成 `video/videos.json`。

输出：

- `temp_repos/`：构建时拉取的 `dx*` 仓库副本。
- `pdf/*.pdf`：网站最终展示和下载的 PDF。
- `books.json`：首页书架数据。
- `notes_manifest.json`：后续搜索索引生成脚本的输入清单。
- `build_state.json`：增量构建状态。
- `build_changed.json`：本次重新编译的笔记仓库清单，驱动索引和预览图的增量重建（不提交，按 run 生成）。
- `video/videos.json`：首页视频模块的数据源。

### `scripts/render_search_previews.py`

这个文件负责“PDF 定位信息 -> 搜索预览图”的最后一段，让搜索结果不只是普通文本，而能展示 PDF 中真实排版后的截图。

输入：

- `public/search-index.enriched.json`：已经带有源文件路径、行号和 PDF 定位信息（`pdfLocator`）的搜索索引。
- `pdf/*.pdf` 或构建目录中的 PDF。

核心逻辑：

1. 读取 `public/search-index.enriched.json` 和 `build_changed.json`。
2. 未变动仓库的块（不在变动集合、`id` 命中上一轮 `search-index.previews.json`）直接沿用旧预览条目，对应 PNG 已在 `public/` 中，无需重绘。
3. 只对适合截图展示的 LaTeX 环境生成预览图，比如 `definition`、`theorem`、`example`、`note`、`remark`、`proposition`、`lemma`、`corollary`、`dxtips`。
4. 普通段落不截图，而是在索引中标记为文本 fallback，避免生成过多低价值图片。
5. 对每个可截图块，读取 enrich 阶段算好的 `pdfLocator`（块 `\begin` 行的 PDF 锚点，直接当 top-down 坐标用，不翻转、不依赖 `endLine`）。
6. 用 PyMuPDF 检测当前页的彩色 tcolorbox 框（按颜色识别四套主题色边框）。
7. **有框块**（定义/定理/提示/引理/命题/推论）：锚点落在某个彩色框内，裁该框的精确 bbox 加少量留白。
8. **无框块**（例题/笔记/注）：从锚点所在的标签行向下，裁到“下一个块的开始”为止——取下一个块锚点、下一个彩色框顶部、高度上限、页面底部中最先出现者。
9. 找不到合理裁切区域时不强行出图，标记为文本回退。
10. 把裁剪结果以 PNG 保存到 `public/search-previews/`。
11. 把每个搜索块对应的 `previewImage` 和 `previewClip` 写回最终索引。
12. 清理孤儿 PNG：最终索引未引用的图片（来自已删除仓库，或变动仓库重绘后 `id` 改变的旧图）会被删除。

输出：

- `public/search-previews/*.png`：搜索结果展示用的 PDF 局部截图（变动仓库重绘、未变动仓库复用，孤儿图会被清理）。
- `public/search-index.previews.json`：首页搜索实际读取的最终索引。

## TypeScript 脚本说明

虽然用户访问时看到的是静态页面，但搜索能力主要来自两个构建期 TypeScript 脚本。

| 文件 | 作用 |
| --- | --- |
| `scripts/build-search-index.ts` | 把 LaTeX 源文件解析成结构化搜索块，识别章节、子章节、定义、定理、例题、笔记、作业、解答、提示和普通段落；按 `build_changed.json` 增量重建，未变动仓库复用旧块。 |
| `scripts/enrich-search-index.ts` | 调用 SyncTeX，把搜索块的源文件行号转换成 PDF 页码和坐标，为后续预览图裁剪提供定位；按块 `id` 复用未变动仓库的旧坐标。 |

`src/` 目录下也有 TypeScript 搜索相关代码，主要包括搜索组件和搜索评分工具函数；当前首页主要由 `index.html` 内嵌逻辑读取最终 JSON 数据并渲染。

## 数据文件说明

| 文件 | 生产者 | 消费者 | 作用 |
| --- | --- | --- | --- |
| `books.json` | `build_notes.py` | `index.html` | 书架数据，告诉首页有哪些 PDF、标题是什么、文件在哪里。 |
| `notes_manifest.json` | `build_notes.py` | `build-search-index.ts` | 搜索构建入口，记录每本笔记的主 TeX 文件、PDF 路径和 SyncTeX 路径。 |
| `build_state.json` | `build_notes.py` | `build_notes.py` | 增量构建状态，用于跳过未更新的仓库。 |
| `build_changed.json` | `build_notes.py` | 三个索引/预览脚本 | 本次重新编译的笔记仓库列表，驱动索引和预览图的增量重建（不提交，按 run 生成）。 |
| `video/videos.json` | `build_notes.py` | `index.html` | 视频列表，来自 `video/*.mp4`。 |
| `public/search-index.json` | `build-search-index.ts` | `enrich-search-index.ts` | 基础搜索索引，只包含文本、标题、章节和源文件行号。 |
| `public/search-index.enriched.json` | `enrich-search-index.ts` | `render_search_previews.py` | 增强搜索索引，加入 PDF 定位信息和调试信息。 |
| `public/search-index.previews.json` | `render_search_previews.py` + `add_pinyin.py` | `index.html` | 最终搜索索引，包含文本、定位、预览图路径和拼音字段。 |
| `public/search-previews/*.png` | `render_search_previews.py` | `index.html` | 搜索结果中的 PDF 局部截图。 |

## 自动构建流程

自动构建由 `.github/workflows/build.yml` 负责。它支持两种触发方式：

- `workflow_dispatch`：手动触发。
- `schedule`：每 3 小时自动运行一次。

CI 的执行顺序是：

```text
checkout 仓库
  -> 安装 Python / Node
  -> pip3 install -r requirements.txt
  -> npm install
  -> 安装 elegantbook.cls
  -> python3 scripts/build_notes.py
  -> npx tsx scripts/build-search-index.ts
  -> npx tsx scripts/enrich-search-index.ts
  -> python3 scripts/render_search_previews.py
  -> python3 scripts/add_pinyin.py
  -> 输出构建诊断信息
  -> git add 生成物
  -> commit
  -> pull --rebase
  -> push origin main
```

CI 使用 `ghcr.io/xu-cheng/texlive-full` 作为容器环境，因为这个项目依赖完整 LaTeX 工具链，包括 `latexmk`、XeLaTeX 和 SyncTeX。

## 构建时长优化

### 原始耗时分析

每次 CI 运行（每 3 小时一次）都执行完整构建，即使笔记没有任何更新：

| 阶段 | 耗时 |
| --- | --- |
| clone 全部 dx* 仓库（浅克隆） | ~2 min |
| latexmk 编译 12 本笔记 | ~7 min |
| 生成搜索索引（TypeScript） | ~2 min |
| SyncTeX 坐标映射（enrich） | ~5 min |
| 渲染搜索预览图（PyMuPDF） | ~5 min |
| **合计** | **~20 min** |

一天 8 次定时触发，绝大多数情况下笔记没有更新，全部白跑。

### Phase 1：无变更早退

在克隆任何仓库之前，先判断是否真的需要构建。

`build_notes.py` 通过 GitHub API 拿到所有 dx* 仓库的 `pushed_at`，和两个本地状态文件比对：

| 文件 | 内容 |
| --- | --- |
| `build_state.json` | 笔记仓库（有 `main.tex` 且产出了 PDF）→ 要求 PDF 存在 |
| `build_nonnotes.json` | 无 `main.tex` 的 dx* 仓库（如测试/工具仓库）→ 不要求 PDF |

所有 `pushed_at` 匹配且所有笔记 PDF 存在 → `sys.exit(0)`，跳过全部 clone / compile / 索引 / 预览，同时输出 `needs_rebuild=false` 让 workflow 后续三个步骤也跳过。

两类仓库必须分开跟踪：若把无 `main.tex` 的仓库混入 `build_state.json` 并要求它们有 PDF，早退条件永远为 `False`，优化完全失效。

**早退时的日志：**

```text
No repository changes detected — skipping clone, compile, and index.
[Output] needs_rebuild=false
========== SUMMARY ==========
Matched dx repos: 14 (12 notes, 2 non-notes, all unchanged, early exit)
Done.
```

GitHub Actions 界面中，搜索索引、坐标映射、预览图三步全部显示 `skipped`。

### Route A：仓库级增量编译

有笔记更新时，只编译真正变动的仓库，跳过未变动的仓库。

在 `build.yml` 中启用 `actions/cache` 缓存 `temp_repos/`：

```yaml
- uses: actions/cache@v4
  with:
    path: temp_repos
    key: temp-repos-${{ github.run_id }}   # 每次 run 都写一份新缓存
    restore-keys: |
      temp-repos-                           # 每次都能恢复上一次的缓存
```

缓存恢复后，`build_notes.py` 对每个仓库判断 `need_compile`：若 `pushed_at` 未变、缓存中有 PDF 和 SyncTeX，则跳过 `latexmk`。只有真正更新过的仓库才会触发编译。

**此前被禁用的原因**：Route A 早在 Phase 1 之前就曾配置过，但当时搜索索引/预览图不受 `needs_rebuild` 控制，不论是否编译都会跑完整的 ~12 min，节省的编译时间被完全掩盖，被误判为"缓存无效"而注释禁用。Phase 1 加入条件控制后，Route A 才有实际效果。

### 优化效果对比

| 场景 | 优化前 | Phase 1 | + Route A | + Route B |
| --- | --- | --- | --- | --- |
| 无变更定时 run | ~20 min | **~3 min** | **~3 min** | **~3 min** |
| 1 本笔记更新 | ~20 min | ~20 min | ~13 min | **~3–4 min** |
| 多本同时更新 | ~20 min | ~20 min | ~13–20 min | 随变动本数线性增长 |
| 首次 run（无缓存） | ~20 min | ~20 min | ~20 min | ~20 min |

### Route B：索引级增量

Route A 之后，搜索索引、坐标映射、预览图三步仍对全部 12 本笔记重跑（约 12 min）。Route B 把这三步也改成按仓库增量：只对变动仓库重新解析 LaTeX、映射坐标、截图，未变动仓库复用上一次的索引条目和预览图，最后合并成完整 JSON。单本笔记更新的构建时间因此从 ~13 min 降到 ~3–4 min。

实现链路：

1. `build_notes.py` 记录本次真正重新编译（`need_compile` 为真）的笔记仓库，写入 `build_changed.json`（如 `{"changed_repos": ["dx-sql"]}`）。该文件不提交，每个 run 由 `build_notes.py` 重新生成；早退时写入空列表。
2. 三个下游脚本读取 `build_changed.json`，按"变动集合"决定每个仓库是重算还是复用：
   - `build-search-index.ts`：按 `repo` 复用——不在变动集合的仓库直接沿用旧 `search-index.json` 里的块，变动仓库重新解析 `main.tex`。
   - `enrich-search-index.ts`：按块 `id` 复用——未变动仓库的块 `id` 稳定（上一步原样保留），直接沿用旧 `pdfLocator`，不再调用 `synctex view`。
   - `render_search_previews.py`：按块 `id` 复用——未变动仓库沿用旧预览条目，对应 PNG 已在 `public/` 中，无需重绘。
3. 三个脚本都按 `notes_manifest.json` 顺序输出：结果保持完整（已删除的仓库自然从清单消失、被丢弃），同时让 JSON diff 最小化。
4. `render_search_previews.py` 额外清理孤儿 PNG：最终索引未引用的图片（来自已删除仓库，或变动仓库重绘后 `id` 改变的旧图）会被删除，避免预览目录无限增长。

**回退到全量**：缺少 `build_changed.json`（首次 run、本地单独跑脚本）或缺少上一轮产物时，三个脚本都回退到全量重建以保证正确性；`FORCE_REBUILD=1` 会让所有仓库进入变动集合，等价于全量重跑。

## 前端展示逻辑

`index.html` 是最终页面入口，承担运行时展示职责：

1. 页面加载时读取 `/books.json`，生成 PDF 书架。
2. 点击书架中的书，打开 `/pdf/<file>`。
3. 读取 `/video/videos.json`，展示视频列表和视频弹窗。
4. 读取 `/public/search-index.previews.json`，把搜索框输入和索引内容做匹配：支持多词任意顺序（AND）、中文拼音首字母/全拼、英文术语拼写容错、前缀匹配，并对输入做防抖、对命中词高亮。
5. 搜索结果优先展示预览图；如果某个块没有预览图，就回退到文本摘要。
6. 搜索结果保留 PDF 路径、章节信息和预览信息，方便用户从关键词跳到具体笔记内容。

这里没有运行时后端，所有数据都通过静态 JSON 文件传给浏览器。

## 本地开发

首页是纯静态页面，可以在仓库根目录启动一个简单服务器查看：

```bash
python3 -m http.server 8000
```

然后打开 `http://localhost:8000`。

如果需要完整重新生成 PDF、索引和预览图，可以按 CI 顺序运行：

```bash
pip3 install -r requirements.txt
npm install
python3 scripts/build_notes.py
npx tsx scripts/build-search-index.ts
npx tsx scripts/enrich-search-index.ts
python3 scripts/render_search_previews.py
```

本地完整构建需要系统已经安装 `latexmk`、XeLaTeX、SyncTeX 和 `elegantbook.cls`。如果只是改首页样式或 README，不需要跑完整构建；如果改搜索索引、PDF 编译或预览图生成逻辑，最好在 GitHub Actions 的 TeX Live 环境里验证。
