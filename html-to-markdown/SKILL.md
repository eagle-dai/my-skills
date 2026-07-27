---
name: html-to-markdown
description: Convert SingleFile-saved HTML pages into clean offline Markdown packages. Use the deterministic auto pipeline first; deliver converted results after independent verification, resolve formula-validation blockers, and enter the Playwright/sub-agent strict workflow only when the pipeline reports strict_required.
---

# SingleFile HTML 转离线 Markdown 包

将 SingleFile 保存的网页转换为结构清晰、可离线阅读且可审计的 Markdown 包。

> **改这个 skill 本身？** 先读 `../_meta/skill-self-improvement.md` 和 @self-improvement.md。selector、默认行为、结构守恒与可执行代码不一致时，以实现和测试为权威，并在同一 PR 中修正文档。

## 执行架构

默认顺序不是“先人工分析，再让 sub agent 从头转换”，而是：

```text
Phase 0  deterministic pipeline：预检、分流、可支持页面的转换
Phase 1  strict 主 agent：渲染 DOM 分析与审计基线
Phase 2  strict sub agent：按已确认参数执行复杂转换
Phase 3  主 agent：独立计数、渲染与截图验收
Phase 4  修复循环
Phase 5  输出 zip + 报告
```

Phase 1-5 只在 deterministic pipeline 返回 `strict_required` 时启动。`blocked` 与 `strict_required` 不是同一种状态，不得混为一谈。

## Phase 0：确定性入口与状态分流

### 0.1 默认执行

```bash
python html-to-markdown/pipeline.py input.html \
  --mode auto \
  --output dist
```

详细 CLI、输出结构和限制见 @pipeline.md。pipeline 会：

1. 选择唯一正文容器并生成 compact HTML；
2. 建立结构 manifest、公式记录和资源记录；
3. canonicalize 可确定的 DOM 计数；
4. 按 fail-closed 规则选择 fast 或 strict；
5. 对 fast 支持的页面执行公式 batch、Markdown 转换、数量守恒与确定性打包。

### 0.2 根据 `report.json.status` 行动

| status | 含义 | 下一步 |
|---|---|---|
| `converted` | deterministic path 已完成并生成 ZIP | 主 agent 独立检查报告、ZIP 内容和关键渲染；通过后交付 |
| `blocked` | 已生成 Markdown 工作产物，但公式验证或结构守恒未完成 | 根据 `blockers` 修复；需要时运行 formula validation 后重跑；不得交付 ZIP |
| `strict_required` | deterministic path 已确认不应猜测或不能满足完整合同 | 读取 `strict_reasons`，进入本 skill 的 Phase 1-5 strict 工作流 |

- `converted` 不等于无需验收；仍要抽检内容、结构、公式与图片。
- `blocked` 不应直接丢弃并重新走 strict；先处理明确 blocker。
- `strict_required` 不得通过 `--mode fast` 强行绕过。
- 顶层 `recommended_mode` 反映最终路由；原始 preflight 建议保留在 `preflight.recommended_mode` 供审计。

### 0.3 图片与题注的 deterministic 边界

- data-URI 图片默认走 fast path：`@image_processing.py` 在写盘前确定性执行“原图备份 → 去水印 → 压缩 → 原尺寸验证”的完整合同（fail-closed，见下方护栏）。纯 data-URI 图片页面不再因图片单独返回 `strict_required`。
- 仍进入 strict 的图片：外部/未本地化 `src`（`fast_converter` 抛 `FastPathUnsupported`）、lazy/missing（preflight 信号）、iframe/video、已确认的 `<caption>`/`<figcaption>`（caption ledger 守恒未实现）。
- 只有用户明确接受图片保持原样、跳过所有图片后处理时，才可传 `--allow-unprocessed-images`：它只跳过图片后处理、按原样打包 data-URI 图，不改变 fast/strict 路由，也不会绕过外部资源、本地化失败、题注、虚拟化或其他 strict 条件。
- 已确认的 `<caption>` / `<figcaption>` 默认进入 strict，因为 deterministic converter 尚未实现 caption ledger 守恒。

### 0.4 fast path 结构处理边界

- **代码块行换行**：Slate/hljs 代码块每行是独立块级 `<div>`，换行靠块边界而非 `\n` 文本。`fast_converter.py::_code_text` 检测这种「每行一个 line div」布局并按行 `\n` join，多行代码不再糊成一行。
- **无语义 wrapper 穿透**：段落内嵌无 `data-slate` 语义的 `<div>/<section>/<article>/<main>` 且无块子时，inline 上下文像 block 上下文一样递归穿透（等价 `<span>`），不再因单个包裹 div 把整页推到 strict。藏了块子的 wrapper、未知 inline 元素仍 fail-close 路由 strict。详见 `conversion-rules.md`。

### 0.4 输出命名合同

命名是数据合同，不是文案创作。禁止让 agent 翻译、概括标题或自由生成 slug。

- pipeline 默认把输入文件 stem 传给 `canonical_output_name()` 一次；也可由用户通过 `--output-name` 明确指定逻辑名。
- 规范化只做机械转换：NFKC、空白、下划线、点号和其他标点/路径分隔符统一为 `-`、连续 `-` 合并、Windows 保留名加 `article-` 前缀；中文不会被翻译或丢弃。例如 `report v1.2` 固定为 `report-v1-2`。
- 结果写入 `report.json.output_name`，并原样复用于 `<name>/<name>.md`、`<name>/files/<name>/` 和 `<name>.zip`。目录、Markdown、资源目录和 ZIP 不得再分别命名。
- strict handoff 必须携带 `output_name`。单文档 strict 输出原样复用它，禁止根据正文标题另起名字。
- 一个 strict 输入拆成多个 Markdown 时，先按渲染 DOM 中的稳定文档顺序从 1 编号，再调用 `numbered_document_name(exact_title, ordinal)`；标题必须是 DOM 原文，禁止翻译、摘要或自由 slug。Markdown stem 与其资源子目录必须完全相同。这个 helper 是给 agent-driven strict handoff 使用的确定性合同；pipeline 当前只处理单文档，因此有意不直接调用它。
- dispatch 前写出完整 naming manifest；sub-agent 只能照表创建路径，不得自行更改。

## Phase 1：strict 主 agent 分析

### 1.1 使用渲染后的 DOM

用 Playwright 打开原始 SingleFile，确认页面结构。strict 基线必须基于渲染后的 DOM，不能只依赖静态解析结果。

### 1.2 使用权威 selector 与 canonicalization

权威 selector 在 @contracts.py 的 `CSS_SELECTORS`：

| 项目 | selector |
|---|---|
| 代码块 | `[data-slate-type="pre"], pre > code` |
| 表格 | `[data-slate-type="table"], table` |
| 列表 | `[data-slate-type="list"], ul, ol` |
| 列表项 | `[data-slate-type="list-line"], li` |
| 公式 | `[data-slate-type*="katex"], .katex, math` |
| 题注 | `figure > figcaption, table > caption` |
| 标题 | `[data-slate-type^="heading"], h1, h2, h3, h4, h5, h6` |

selector 命中数不是语义基线。同一块可能同时命中 wrapper 和原生节点。必须：

1. 用 `discover_semantic_candidates()` 建立候选；
2. 为同一语义块使用相同 `semantic_id`；
3. 调用 `canonicalize_candidates()`；
4. 按 canonical candidate 计数。

不得另造与 @contracts.py 冲突的 selector 或复杂度规则。

### 1.3 记录审计基线

至少记录：

```text
formula block / inline
tables
lists / list items
images
captions
code blocks
headings
comments
```

复杂度调用 `classify_complexity()`，不得凭自然语言重新实现。

### 1.4 页面类型和参数

识别文章、Slate、Notebook、虚拟化编辑器与 lazy-load。Notebook、Monaco、CodeMirror、react-virtualized 等规则见 @notebook-and-virtualized.md。

在 dispatch 前确认：

- 正文容器；
- 编辑器/页面类型；
- 评论顶层 selector；
- 公式来源；
- canonical DOM 基线；
- Notebook cell/output 参数；
- pipeline 的 `output_name`；多文档时的有序 `document_name -> markdown -> asset_dir` naming manifest；
- 每条 `strict_reason` 的处理方案。

## Phase 2：strict sub-agent 执行

Prompt 必须包含已确认参数，不得让 sub agent 重新猜 selector 或基线。

### DOM 与结构

- 无语义 wrapper 递归穿透；
- 表格、代码块、列表和列表项与 canonical 基线对齐；
- Slate code block 使用 `data-slate-type="pre"`；
- 有序列表只根据 `<ol>`、属性或 CSS counter 等证据判断；无法确认时默认无序；禁止双 marker。

### 评论

- 不得整体默认删除；只匹配顶层评论容器；
- 保留技术问题、纠错、作者回复和长评论；
- 每个 source_id 必须写 ledger：`source_id | status | emitted_count | reason`；
- status 只能是 `kept / removed_as_noise / failed / manual_review`；
- 用 `validate_comment_ledger()` 验证 source_id 集合和 emitted_count。

### 图片

fast pipeline 的 `@image_processing.py` 对每张 data-URI 图默认确定性执行去站点水印和完整图片合同（fail-closed，永不抛、永不丢图）；只有用户明确要求保留原始水印（`--allow-unprocessed-images`）时才跳过：

1. 保存原图副本（写入打包树外的 `<output>/<package>__images_orig/`，仅供离线审计，**不进交付 ZIP**）；
2. 尝试安全去站点水印（仅四角 ROI、右下优先、特征色半透明灰）；
3. 记录处理文件和 bbox（写入 `report.json.image_ledger`）；
4. 使用原图而不是缩略图检测；
5. 特征色命中正文时只处理最右下连通块，禁止扩大擦除范围；
6. 原尺寸逐图验证正文未被擦除（擦除区外零容差全等；区内内容色占比超阈值判水印压正文 → 回退保留原图）；
7. 无法安全去除时保留原图（`fallback_to_original=True`）；
8. 去水印后再压缩（宽 > 1600 等比缩放，webp q82；webp 变大则保留原格式；svg/gif 不转）。

图片保留/删除/人工复核与 ledger 规则见 @image-disposition.md、@image_disposition.py、@image_processing.py 和 @conversion-rules.md。

### 输出路径

- 单文档：只允许 naming manifest 中的 `<output_name>/<output_name>.md` 与 `<output_name>/files/<output_name>/`。
- 多文档：每个 `<document_name>.md` 只引用 `files/<document_name>/`；编号来自渲染 DOM 顺序。
- 不得混用裸编号、英文 slug、中文自由标题、空格加竖线等多套命名形式。
- 遇到重名或路径碰撞必须回到主 agent 修正 naming manifest，禁止 sub-agent 临时追加随机后缀。

### 代码与 fence

- 无充分语言证据时使用 `text`；
- 代码内部 NBSP 转普通空格；
- 使用 @markdown_fences.py 扫描和剥离 fenced blocks；不得用 fence 数量奇偶或跨行正则代替 parser。

### 公式

公式提取与验证以 `formula-extraction` skill 为权威：

- 优先使用 annotation/data 属性/script 中的原始 LaTeX；
- KaTeX HTML 重建使用可复用 parser，未知结构 fail closed；
- 命令边界只在 parser token/part join 阶段处理；
- 上下标、分式、limits、字体和矩阵结构必须忠实原 DOM；
- 失败时截图或人工复核，不得使用 `textContent` 假装成功。

## Phase 3：主 agent 独立验收

### 结构守恒

- 表格和代码块：canonical HTML 基线等于 Markdown 实际；少一个即阻断；
- 列表项：数量和 marker 类型对齐；
- 图片：ledger 合法，保留项与文件一致；
- 题注：每个 confirmed caption `emitted_count == 1`；
- 评论：`validate_comment_ledger()` 无错误；
- 公式：数量、来源、结构和验证状态对齐。
- 命名：实际 Markdown stem、资源目录、ZIP 与 naming manifest 完全一致；不得存在未登记目录或随机后缀。

所有 Markdown 结构扫描必须先排除 fenced code block。

### 渲染验证

1. 使用统一 `render.html`；
2. `.katex-error == 0`；
3. 红色 MathML error 节点为 0；
4. 捕获 KaTeX/MathJax warning；
5. 渲染后公式数与基线对比；
6. 整页截图，并对公式、列表、表格、评论和处理后图片做局部截图。

### ZIP 验证

- 使用 Python `zipfile`；
- 修改 Markdown 后重新打包；
- 打包后直接读取 ZIP 内文件核对关键内容，不能只看时间戳。

## Phase 4：修复循环

- 个别问题由主 agent 局部修复；
- 系统性问题重新 dispatch，并明确失败计数、selector 和修复要求；
- 每次修复后重跑相关阻断项；
- deterministic `blocked` 状态修复后应重新运行 pipeline，不能手工伪造 `converted` 报告。

## Phase 5：交付

只在所有阻断项通过后提供 ZIP。报告至少包含：

```text
pipeline status / requested mode / recommended mode
output_name / naming manifest / 实际路径对比
strict reasons 或 blockers
DOM 基线 / Markdown 实际
公式来源、失败、pending validation、error/warning
图片原图、处理方式、bbox、压缩和逐图验证
caption/comment/image ledger
人工复核项目
```

## 参考文档

- @pipeline.py / @pipeline.md — deterministic auto/fast/strict 路由
- @preflight.py / @preflight.md — 正文选择、compact HTML 与 manifest
- @contracts.py — selector、复杂度、canonicalization、评论 ledger
- @formula_batch.py — 公式 dedup/cache/batch validation
- @conversion-rules.md — 非公式转换规则
- @notebook-and-virtualized.md — Notebook、虚拟化与 lazy-load
- @image-disposition.md / @image_disposition.py — 图片判定与 ledger
- @fence-validation.md / @markdown_fences.py — fence 合同
- @blocking-rules.md — 阻断规则
- @checklist.md — 主 agent 验收
- `../_meta/skill-self-improvement.md` — 通用改进规则
- @self-improvement.md — 本 skill 回归用例
- `formula-extraction` skill — 公式提取权威规则
