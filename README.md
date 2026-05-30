# yangminggu.github.io

## 整体架构

这个项目是“阳明谷”的静态网站仓库，核心目标是把 `yangminggulab` 账号下的 `dx*` 笔记仓库自动整理成一个可以浏览、下载和搜索的 GitHub Pages 站点。它不是一个传统的前后端服务，而是一条“内容仓库 -> 自动构建 -> 静态资源 -> 浏览器展示”的流水线。

主线可以理解为：

1. 内容来源：各个 `dx*` 仓库保存课程笔记的 LaTeX 源文件，本站仓库也保存视频、PDF、索引 JSON 等最终要发布的静态资源。
2. 自动构建：GitHub Actions 定时或手动触发构建，运行 Python 和 TypeScript 脚本拉取笔记仓库、编译 PDF、抽取 LaTeX 内容、生成搜索索引和预览图。
3. 静态展示：`index.html` 直接读取生成好的 `books.json`、`pdf/`、`video/videos.json` 和 `public/search-index.previews.json`，在浏览器里展示书架、视频和搜索结果。

各部分之间的关系：

- `dx*` 笔记仓库 -> `scripts/build_notes.py` -> `temp_repos/`、`pdf/`、`books.json`、`notes_manifest.json`、`build_state.json`
- `notes_manifest.json` + LaTeX 源文件 -> `scripts/build-search-index.ts` -> `public/search-index.json`
- `public/search-index.json` + SyncTeX -> `scripts/enrich-search-index.ts` -> `public/search-index.enriched.json`
- `public/search-index.enriched.json` + PDF -> `scripts/render_search_previews.py` -> `public/search-index.previews.json` 和 `public/search-previews/`
- `books.json`、`pdf/`、`video/`、`public/` -> `index.html` -> GitHub Pages 页面

## 目录说明

| 路径 | 作用 |
| --- | --- |
| `index.html` | 网站入口，包含页面结构、样式和前端交互逻辑。 |
| `scripts/build_notes.py` | 从 GitHub 拉取 `dx*` 仓库，编译 LaTeX，生成 PDF 清单、构建状态和视频清单。 |
| `scripts/build-search-index.ts` | 解析 LaTeX 文件，把定义、定理、例题、笔记、段落等内容抽成搜索块。 |
| `scripts/enrich-search-index.ts` | 使用 SyncTeX 给搜索块补充 PDF 中的位置定位信息。 |
| `scripts/render_search_previews.py` | 使用 PyMuPDF 按定位信息裁剪 PDF，生成搜索结果里的预览图片。 |
| `src/` | 搜索组件和搜索工具函数的 TypeScript 源码，目前主要作为搜索逻辑的开发区。 |
| `pdf/` | 已编译并发布的课程 PDF。 |
| `public/` | 搜索索引、增强索引、预览索引和预览图片。 |
| `video/` | 页面展示的视频文件和 `videos.json` 清单。 |
| `temp_repos/` | 构建时拉取的 `dx*` 仓库副本，用来编译 PDF 和解析源文件。 |
| `.github/workflows/build.yml` | 自动构建流程，每 3 小时运行一次，也支持手动触发。 |

## 构建流程

自动构建由 `.github/workflows/build.yml` 负责，运行环境使用完整 TeX Live 容器。流程如下：

1. 安装 Python、Node、Python 依赖和 npm 依赖。
2. 安装 `elegantbook.cls`，保证各个 LaTeX 笔记可以编译。
3. 执行 `python3 scripts/build_notes.py`，拉取并编译 `dx*` 仓库。
4. 执行 `npx tsx scripts/build-search-index.ts`，生成基础搜索索引。
5. 执行 `npx tsx scripts/enrich-search-index.ts`，用 SyncTeX 生成 PDF 定位。
6. 执行 `python3 scripts/render_search_previews.py`，生成搜索预览图。
7. 把更新后的 `index.html`、`pdf/`、`books.json`、`build_state.json`、`notes_manifest.json`、`public/`、`video/videos.json` 提交回仓库。

## 关键数据文件

| 文件 | 说明 |
| --- | --- |
| `books.json` | 书架数据，告诉首页有哪些 PDF 可以展示和打开。 |
| `notes_manifest.json` | 每本笔记的仓库名、标题、PDF 路径、主 TeX 文件和 SyncTeX 文件位置。 |
| `build_state.json` | 记录每个 `dx*` 仓库上次构建时的提交状态，用于判断是否需要重新编译。 |
| `video/videos.json` | 视频列表，由 `scripts/build_notes.py` 根据 `video/*.mp4` 自动生成。 |
| `public/search-index.json` | 从 LaTeX 抽取出的基础搜索块。 |
| `public/search-index.enriched.json` | 在基础搜索块上增加 PDF 定位信息。 |
| `public/search-index.previews.json` | 在搜索块上增加预览图信息，是首页搜索实际读取的索引。 |

## 本地开发

这个项目没有单独的应用构建命令，首页是纯静态页面。查看页面时可以在仓库根目录启动一个静态文件服务器：

```bash
python3 -m http.server 8000
```

然后打开 `http://localhost:8000`。

如果需要重新生成笔记和搜索索引，通常按下面的顺序运行：

```bash
pip3 install -r requirements.txt
npm install
python3 scripts/build_notes.py
npx tsx scripts/build-search-index.ts
npx tsx scripts/enrich-search-index.ts
python3 scripts/render_search_previews.py
```

本地完整构建依赖 `latexmk`、XeLaTeX、SyncTeX 和 `elegantbook.cls`，所以最稳定的构建环境仍然是 GitHub Actions 里的 TeX Live 容器。
