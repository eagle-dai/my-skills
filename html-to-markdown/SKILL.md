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

- 页面包含图片时，fast path 默认返回 `strict_required`，因为它尚未执行“原图备份 → 去水印 → 压缩 → 原尺寸验证”的完整合同。
- 只有用户明确接受图片保持原样、跳过所有图片后处理时，才可传 `--allow-unprocessed-images`。
- 该参数只放宽图片后处理，不会绕过外部资源、本地化失败、题注、虚拟化或其他 strict 条件。
- 已确认的 `<caption>` / `<figcaption>` 默认进入 strict，因为 deterministic converter 尚未实现 caption ledger 守恒。

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

strict 流程默认执行去站点水印和完整图片合同；只有用户明确要求保留原始水印时才跳过去水印步骤：

1. 保存原图副本；
2. 尝试安全去站点水印；
3. 记录处理文件和 bbox；
4. 使用原图而不是缩略图检测；
5. 特征色命中正文时只处理最右下连通块，禁止扩大擦除范围；
6. 原尺寸逐图验证正文未被擦除；
7. 无法安全去除时保留原图；
8. 去水印后再压缩。

图片保留/删除/人工复核与 ledger 规则见 @image-disposition.md、@image_disposition.py 和 @conversion-rules.md。

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
