# 搜索预览图裁切优化日志

## 背景

搜索结果里的预览图（由 `scripts/render_search_previews.py` 生成）存在裁切问题：

- 裁切位置不准，经常裁不到正确区域；
- 裁出的缩略图带着相邻块的残影（上一个卡片的底边、下一个卡片的开头），看起来有“遮挡”；
- 偶尔裁出整页，甚至几乎全白的图。

## 根因

旧的 `make_block_rect` 有三个问题，叠加放大了误差：

1. **坐标翻转错误。** `pt_to_pdf_y()` 把 SyncTeX 的 `y` 又翻转了一次。但 SyncTeX 的 `y` 本就是 PDF 的 top-down 坐标，翻转后锚点跑到了页面的**对侧** —— 这是“全白 / 裁错位置”的主因。
2. **下边界依赖 `endLine` 的 SyncTeX 映射。** `endLine` 映射极不可靠（经常落到页底或跨页），再叠加按 kind 的固定上下 padding，于是裁出整页。
3. **完全没用 PDF 里的彩色框边界。** 这些笔记卡片本身是带色边框的 tcolorbox，框的 bbox 就是精确的视觉边界，旧逻辑却靠经验 padding 估算。

实证：

- 取 4 个块用 PyMuPDF 的 `search_for` 拿文字真实位置做基准，`pdfLocator.y` 直接命中，翻转后全部落空。
- `dx-ML-14` 旧裁切高 754pt、`dx-PDE-167` 旧裁切高 817pt（几乎整页），而真实卡片分别只有约 150pt、69pt。

## 笔记块的两类渲染（实测 2316 个可截图块）

| 类型 | 环境 | PDF 里的样子 | 锚点是否落在彩色框内 |
| --- | --- | --- | --- |
| **有框 ~68%** | definition / theorem / dxtips / lemma / proposition / corollary | 彩色 tcolorbox（紫 / 橙 / 绿 / 蓝 四套主题色，跨所有 PDF 一致） | 约 100% |
| **无框 ~24%** | example / note / remark | 红色标签（“解 / 例题 / 笔记 / 注”）开头的纯文字，夹在别的卡片之间 | 0%（本就没有框） |

彩色框的颜色判据：`(max(rgb) - min(rgb)) > 0.2 且 min(rgb) < 0.85`（鲜艳色相、非浅色背景），能覆盖四套主题色、排除浅色填充背景与黑白文字。

## 新方案

定位仍然完全建立在原有的“LaTeX 源码行号 → SyncTeX → PDF 坐标”机制上：用 enrich 阶段已经算好的 `pdfLocator`（块 `\begin` 行的映射）作锚点，**不再翻转**，也**不再依赖 `endLine`**。

- **锚点** = `pdfLocator.y`（直接当 top-down PDF 坐标用）。
- **有框块**：锚点落在某个彩色框内 → 裁该框的 bbox + 3.5pt 留白。不合并同页相邻框（同页每个 tcolorbox 是独立卡片，breakable 主要跨页才分段）。
- **无框块**：找到锚点所在的标签行 → 向下裁到“下一个块的开始”为止，取以下最先出现者：
  - 下一个块的锚点 `pdfLocator.y`（同 repo 的下一个块，源码顺序即页面顺序）；
  - 下一个彩色框的顶部；
  - 高度上限 240pt（保证缩略图大小）；
  - 页面底部。
  左右边界贴合裁切区间内文字行的实际 x 范围（不用 `pdfLocator` 自带的 `x/W`，因为部分标签行的 `W` 是负值）。
- **失败兜底**：找不到合理裁切区域时 `previewImage = null`，前端回退到文字摘要。

附带：render 阶段不再调用 `synctex view`（直接用 `pdfLocator`），CI 里这一步从约 6 分钟降到约 16 秒。

## 验证

本地用现有 `public/search-index.enriched.json` + `pdf/` 全量重生成：

- **成功 2315 / 2316**（有框 1582 + 无框 733），比旧版多 400+ 张（修正坐标后更多块能正确裁切，且修掉了 note 标签负宽导致的编码失败）。
- 抽样 10 个 repo × 有框/无框（Math-Stat 的 tip 框、topology / functional-analysis 的例题、real-analysis 的定理、Abstract-Algebra 的命题等），全部精确贴边。
- 预览图高度中位数 84pt（缩略图尺寸合理）。

## 已知边缘情况

- `dx-Numerical-ODEs-97`（note，1 / 2316）：SyncTeX 把标签锚点异常映射到页顶（`y≈56.7`，而最近文字行在 82 且落在一个框内），无法裁出有意义区域，回退文字预览。属个例，不强行裁错图。

## 兼容性

- 输出格式（`previewImage` / `previewClip`）保持不变，前端 `index.html` 无需改动。
- Route B 增量复用逻辑保留（未变动 repo 沿用旧条目与旧 PNG）。
- 新增 `previewDebug` 记录裁切模式（`frame` / `noframe` / 失败原因），便于诊断。

## 关键参数（`scripts/render_search_previews.py`）

| 参数 | 值 | 含义 |
| --- | --- | --- |
| `BOX_MIN_WIDTH` | 300 | 彩色框最小宽度（卡片占据大半文本栏） |
| `FRAME_MARGIN` | 3.5 | 有框块裁切的四周留白 |
| `NOFRAME_MAX_H` | 240 | 无框块裁切的高度上限 |
| `NEXT_BLOCK_GAP` / `NEXT_BOX_GAP` | 8 / 6 | 无框块停在下一个块锚点 / 下一个框顶之前的间隙 |
| `RENDER_SCALE` | 2 | 2 倍像素图，缩略图更清晰 |
