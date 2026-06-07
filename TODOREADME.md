# TODO README

## 本次调查范围

本次只调查，不改代码。调查对象：

- `README.md` 中描述的现有架构。
- `.github/workflows/build.yml` 的实际 CI 流程。
- `dx-real-analysis` 的本地构建日志和 SSH 远端状态。
- 最近几次 GitHub Actions 主构建的运行时间。
- GitHub Actions 官方文档里关于缓存、跳过任务、并发控制的方案。

## 当前结论

### 1. `dx-real-analysis` 不是导致 workflow 整体失败，而是 LaTeX 内部有错误

SSH 检查远端仓库可访问：

```text
git@github.com:yangminggulab/dx-real-analysis.git
HEAD/main = 76febff47bc7efd3601253d6c329a0d62909565f
```

本地 `temp_repos/dx-real-analysis/main.log` 中有 LaTeX Error，但日志末尾仍然写出了 `main.xdv`，并且仓库里也存在 `main.pdf`。

本地按 workflow 同样的命令执行：

```bash
latexmk -xelatex -synctex=1 -interaction=nonstopmode -f main.tex
```

返回码是 `12`，输出提示：

```text
xelatex: gave an error in previous invocation of latexmk.
```

这说明实分析确实有 LaTeX 编译错误；只是当前 `scripts/build_notes.py` 里调用 `subprocess.run(..., check=False)`，不会让 workflow 因 LaTeX 返回非 0 立刻失败。只要后面还能找到 PDF，脚本就会继续把 PDF 复制到 `pdf/`，所以 GitHub Actions 最终仍然显示 success。

### 2. 实分析当前明确的 LaTeX 错误点

#### `main.tex:116`

当前内容开头是：

```tex
\\E中不是聚点就是孤立点...
```

问题：段落开头直接写 `\\`，LaTeX 会报：

```text
LaTeX Error: There's no line here to end.
```

建议：去掉开头的 `\\`，或者改成正常段落/列表。

#### `main.tex:1024`

当前内容类似：

```tex
\text{设 } g : \mathbb${R}^n$ \to \mathbb{R}，\text{则其支集定义为：}
```

问题：

- `\text{}` 被放在普通文本环境里使用。
- `\mathbb` 没有完整放在数学模式里。
- `$` 把 `\mathbb` 和 `{R}^n` 拆坏了。

日志里对应错误：

```text
LaTeX Error: \mathbb allowed only in math mode.
Missing $ inserted.
Bad math environment delimiter.
\begin{document} ended by \end{equation*}.
```

建议改成普通文本 + 行内公式：

```tex
设 $g:\mathbb{R}^n \to \mathbb{R}$，则其支集定义为：
```

#### `main.tex:1583-1588`

当前内容：

```tex
\end{theorem}\\

性质1 ，常数可以提出来。\\
性质2 不为异号无穷大加法可以拆开，拆括号蕴藏了同构。\\
性质3，如果E1，E2不相交可以吧E上的积分拆分成E1上的积分加上E2上的积分。\\
性质4，不等号的传递性\\
```

问题：

- `\end{theorem}\\` 后面紧接空行，会触发 `There's no line here to end`。
- 连续使用 `\\` 写自然语言说明，不适合长期维护。

建议：

- 删除 `\end{theorem}` 后面的 `\\`。
- 把性质说明改成 `itemize` 或普通段落。

#### 其他非致命但应该整理的问题

日志里还有：

```text
Missing character: There is no ； in font cmr10
Missing character: There is no 。 in font cmr10
Missing character: There is no ∈ in font ...
LaTeX Warning: There were multiply-defined labels.
```

这些通常不是主失败原因，但说明有中文/符号进入了不合适的字体或数学/文本模式。例如 `x∈(0,6)` 建议写成 `$x\in(0,6)$`。

## workflow 为什么现在一次要十几二十分钟

最近 8 次 `Build LaTeX Notes` 主 workflow 都是成功的 schedule run，但耗时稳定在 19-21 分钟左右：

| run | 开始 | 结束 | 约耗时 |
| --- | --- | --- | --- |
| 580 | 2026-05-30 06:19:22 UTC | 2026-05-30 06:39:10 UTC | 19m48s |
| 579 | 2026-05-30 02:35:06 UTC | 2026-05-30 02:54:25 UTC | 19m19s |
| 578 | 2026-05-29 22:24:32 UTC | 2026-05-29 22:44:36 UTC | 20m04s |
| 577 | 2026-05-29 18:08:32 UTC | 2026-05-29 18:29:02 UTC | 20m30s |
| 576 | 2026-05-29 12:10:26 UTC | 2026-05-29 12:30:24 UTC | 19m58s |
| 575 | 2026-05-29 06:49:09 UTC | 2026-05-29 07:10:03 UTC | 20m54s |
| 574 | 2026-05-29 02:40:43 UTC | 2026-05-29 03:00:41 UTC | 19m58s |
| 573 | 2026-05-28 22:29:59 UTC | 2026-05-28 22:49:31 UTC | 19m32s |

最新 run 580 的 step 时间分布：

| step | 耗时 |
| --- | --- |
| Initialize containers | 约 2m00s |
| Checkout website repo | 约 25s |
| Run Python build script | 约 5m14s |
| Build search index | 约 1s |
| Enrich search index | 约 5m27s |
| Render search previews | 约 6m21s |
| Commit updated files | 约 6s |

瓶颈不是 `pip install` 或 `npm install`，它们只有几秒。真正慢的是：

1. `build_notes.py` 每次都要访问 GitHub、clone/fetch 多个 `dx*` 仓库，并检查/编译 PDF。
2. `enrich-search-index.ts` 对大量搜索块调用 `synctex view`，给每个块做 PDF 坐标定位。
3. `render_search_previews.py` 对定义、定理、例题、note、dxtips 等块重新裁剪 PNG。

当前索引规模：

- `public/search-index.previews.json`：3492 个搜索块。
- 有 `previewImage` 的块：1902 个。
- `public/search-previews/`：约 2694 个 PNG 文件，目录大小约 144MB。

所以“每 3 小时全量定位 + 全量截图”自然会慢。

## 推荐优化方案

### 方案 A：先做 no-change 快速跳过，性价比最高

目标：如果所有 `dx*` 仓库的 `pushed_at` 都没有变化，且视频列表也没有变化，就不要跑后面的搜索索引、SyncTeX 定位和预览图裁剪。

当前问题是：即使没有笔记内容变化，workflow 仍然会完整执行：

```text
build_notes.py
-> build-search-index.ts
-> enrich-search-index.ts
-> render_search_previews.py
```

建议：

1. 让 `build_notes.py` 输出一个构建状态文件，例如 `build_meta.json`：

```json
{
  "changed_repos": [],
  "video_changed": false,
  "needs_search_rebuild": false
}
```

2. workflow 读取这个状态：

```yaml
- name: Build search index
  if: steps.detect.outputs.needs_search_rebuild == 'true'
  run: npx tsx scripts/build-search-index.ts
```

3. 当 `needs_search_rebuild=false` 时，直接跳过：

- `Build search index`
- `Enrich search index`
- `Render search previews`
- 大部分 commit 工作

预期收益：

- 无笔记更新的 schedule run 从约 20 分钟降到 1-3 分钟。
- 这是最应该先做的优化。

### 方案 B：不要每次 clone 所有未变化仓库

当前 `build_notes.py` 的逻辑是先 clone/fetch 仓库，再判断是否需要编译。对 schedule run 来说，如果远端 `pushed_at` 和 `build_state.json` 一样，且根目录已经有 `pdf/<repo>.pdf`，其实可以不 clone 这个仓库。

建议：

1. 先用 GitHub API 拿 `pushed_at`。
2. 如果 `state[name] == repo["pushed_at"]` 且 `pdf/<name>.pdf` 存在，直接复用现有数据。
3. 只有变化仓库才 clone/fetch。

注意：

- 如果后续仍然全量重建搜索索引，就需要所有 TeX 源码；所以这个方案最好和“no-change 快速跳过”一起做。
- 更进一步可以做“按 repo 增量索引”，见方案 C。

### 方案 C：按 repo 增量生成搜索索引和预览图

当前搜索索引是全量文件：

```text
public/search-index.json
public/search-index.enriched.json
public/search-index.previews.json
```

建议长期改成按仓库拆分：

```text
public/search-index/by-repo/dx-real-analysis.json
public/search-index/by-repo/dx-real-analysis.enriched.json
public/search-index/by-repo/dx-real-analysis.previews.json
```

构建时只重建变化仓库对应的索引和预览，最后再 merge 成首页读取的总索引。

预期收益：

- 单个课程仓库更新时，只处理那一本书。
- 不必每次对 3492 个块重新定位。
- 不必每次对 1902 个截图块重新裁剪。

### 方案 D：给预览图加内容 hash，未变化就复用

当前 `render_search_previews.py` 会重新处理所有适合截图的块。可以给每个 block 计算签名：

```text
repo + sourcePath + startLine + endLine + rawContent hash + pdf mtime/hash
```

如果旧的 `public/search-index.previews.json` 里已经有同 ID、同签名、同 previewImage，且对应 PNG 文件存在，就直接复用，不重新调用 SyncTeX/不重新截图。

预期收益：

- 大量未变化的定义、定理、例题不重复截图。
- 对当前 1902 个预览块特别有效。

### 方案 E：降低预览图生成范围

当前会给这些环境生成预览：

```text
definition, theorem, example, note, remark,
proposition, lemma, corollary, dxtips
```

如果只保留最有价值的：

```text
definition, theorem, example, dxtips
```

可以减少截图数量。当前各类块数量大致是：

| kind | 总数 | 有 previewImage |
| --- | ---: | ---: |
| definition | 491 | 438 |
| dxtips | 416 | 381 |
| theorem | 422 | 368 |
| note | 356 | 314 |
| example | 204 | 165 |
| proposition | 124 | 117 |
| lemma | 40 | 36 |
| corollary | 45 | 40 |
| remark | 49 | 43 |

如果去掉 `note/remark/proposition/lemma/corollary` 的截图，只保留文本 fallback，可以明显减少 `render_search_previews.py` 的耗时和 `public/search-previews/` 体积。

### 方案 F：缓存依赖可以做，但不是当前主要瓶颈

官方文档支持用 `actions/cache` 缓存依赖，也支持 `setup-node` / `setup-python` 自带 cache。但当前最新 run 里：

- `pip install` 约 3 秒。
- `npm install` 约 1 秒。

所以依赖缓存不是当前优先级。真正该缓存/跳过的是：

- `synctex view` 的定位结果。
- `public/search-previews/*.png` 的裁剪结果。
- 未变化仓库的 TeX/PDF 处理。

## 建议执行顺序

1. 先修 `dx-real-analysis/main.tex` 的 3 个明确 LaTeX 错误点。
2. 在 `build_notes.py` 增加 no-change 检测，输出 `needs_search_rebuild`。
3. 在 workflow 里按 `needs_search_rebuild` 跳过搜索索引、enrich、preview 三个重步骤。
4. 再考虑把搜索索引按 repo 拆分，实现真正增量构建。
5. 最后再做 preview hash 复用和预览范围收窄。

## 待办：事件驱动触发（替代 3 小时定时轮询）

### 背景

当前 `.github/workflows/build.yml` 通过 `schedule: cron: '0 */3 * * *'` 每 3 小时轮询一次，进入 workflow 后由 `scripts/build_notes.py` 调 GitHub API 比对 `pushed_at`，无变化就提前退出（`needs_rebuild=false`）。这套增量检测已经存在，但触发仍是轮询，最长有 3 小时延迟。

要做到"dx\* 仓库一 push 就触发"，GitHub 的模型决定了必须有一个"中间人"把信号传到本站仓库。中间人只有两种形态：放在每个源仓库里（notify workflow，维护 N 个文件）或放在仓库外（接收 org webhook 的一个 endpoint）。

### 选定方案：Cloudflare Worker + org webhook

**原理**

1. 在 GitHub org `yangminggulab` 的 Settings → Webhooks 里添加一条 org webhook，事件类型选 `push`，指向 Cloudflare Worker 的 URL。
2. Cloudflare Worker（~25 行 JS）收到 push 事件后，过滤仓库名以 `dx` 开头，调用本站的 `repository_dispatch`（事件类型 `dx_repo_updated`）。
3. 本站 `build.yml` 入口改为：

```yaml
on:
  workflow_dispatch:
  repository_dispatch:
    types: [dx_repo_updated]
  schedule:
    - cron: '0 2 * * *'   # 每日凌晨兜底一次，防止 Worker 偶发失败漏更新
```

4. 同时加并发控制，防止多个 dx\* 仓库短时间连续 push 时并发抢 commit：

```yaml
concurrency:
  group: notes-build-main
  cancel-in-progress: false
```

**Cloudflare Worker 代码骨架**

```js
export default {
  async fetch(request, env) {
    const payload = await request.json();
    const repoName = payload?.repository?.name ?? '';
    if (!repoName.startsWith('dx')) {
      return new Response('ignored', { status: 200 });
    }
    await fetch(
      'https://api.github.com/repos/yangminggulab/yangminggu.github.io/dispatches',
      {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: `Bearer ${env.WEBSITE_DISPATCH_TOKEN}`,
          'User-Agent': 'dx-notifier',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          event_type: 'dx_repo_updated',
          client_payload: {
            repo: repoName,
            sha: payload?.after ?? '',
            ref: payload?.ref ?? '',
          },
        }),
      }
    );
    return new Response('dispatched', { status: 200 });
  },
};
```

**Token 配置**

- `WEBSITE_DISPATCH_TOKEN`：fine-grained PAT，只授权 `yangminggu.github.io` 仓库的 `contents: write`（或用 GitHub App token，不会过期）。
- 放到 Cloudflare Worker 的 Environment Variables（加密存储），不要硬编码在代码里。

**好处**

- 所有 `dx*` 仓库不需要任何改动，新增仓库也自动覆盖。
- Cloudflare Workers 免费额度 10 万次/天，完全够用。
- 现有 `build_notes.py` 的增量检测逻辑不需要改，dispatch 只是替代"闹钟"。

**执行步骤（备忘）**

1. Cloudflare 创建 Worker，粘贴上面骨架代码，配置 `WEBSITE_DISPATCH_TOKEN` 环境变量，部署拿到 URL。
2. GitHub org Settings → Webhooks → Add webhook，URL 填 Worker 地址，Content type 选 `application/json`，事件选 `Pushes`（或 `Let me select individual events` → `Pushes`）。
3. 修改本站 `build.yml` 的 `on:` 块，加 `repository_dispatch` + 把 schedule 改成每日兜底。
4. 加 `concurrency` 块。
5. 推送后手动 `workflow_dispatch` 验证一次，再在某个 `dx*` 仓库随意 push 一个空 commit，确认本站 workflow 被触发。

## 参考资料

- GitHub Actions dependency caching 官方文档：https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- GitHub Actions workflow syntax 官方文档：https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub Actions concurrency 官方文档：https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
- GitHub REST API: workflow runs：https://docs.github.com/en/rest/actions/workflow-runs
