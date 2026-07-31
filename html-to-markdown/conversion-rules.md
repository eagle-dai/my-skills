# 转换规则参考（非公式部分）

本文档覆盖 HTML → Markdown 转换中除公式外的内容规则。公式见 `formula-extraction` skill。selector、复杂度分级、语义候选发现与去重、评论 ledger 的可执行合同以 @contracts.py 为准；图片保留/删除以 @image_disposition.py 为准；fence 验证以 @markdown_fences.py 为准。

## 识别主体内容

SingleFile HTML 包含导航、侧边栏、弹窗、评论等完整页面内容。

1. 在渲染后的 DOM 中优先查 `<article>`、`<main>`、`[role="main"]`、`[data-slate-editor]`。
2. 无唯一选择器时，用截图和文本密度确认正文范围。
3. 标题、作者、时间等元信息必须限定在正文容器内查询。

## DOM 完整性审计

提取前用 Playwright 对主体容器建立基线。原始 selector 命中必须先分配 `semantic_id` 并调用 `canonicalize_candidates()`，不得直接作为基线。

| 审计项 | 权威查询/分类 | 记录值 |
|---|---|---|
| 块级公式 | `CSS_SELECTORS["formula"]` 后按 display/Slate 类型分类 | `N_formula_block` |
| 行内公式 | canonical 公式候选排除 display 后分类 | `N_formula_inline` |
| 表格 | `[data-slate-type="table"], table` 后 canonicalize | `N_table` |
| 列表 | `[data-slate-type="list"], ul, ol` 后 canonicalize | `N_list` |
| 列表项 | `[data-slate-type="list-line"], li` 后 canonicalize | `N_list_item` |
| 图片 | `img`，每张建立 image ledger | `N_image` |
| 题注 | `figure > figcaption, table > caption` 与已验证 Slate 关系 | `N_caption` |
| 代码块 | `[data-slate-type="pre"], pre > code` 后 canonicalize | `N_codeblock` |
| 标题 | `[data-slate-type^="heading"], h1, h2, h3, h4, h5, h6` | `N_heading` |
| 评论 | 顶层评论容器与完整稳定 `source_ids` | `N_comment` |

规则：

- 表格、代码块、列表项、正文图片和块级公式减少均为阻断。
- 审计和验收使用相同 selector、`semantic_id` 与 canonicalization。
- Slate 代码块的权威映射是 `[data-slate-type="pre"]`；不得改成 `code-block`。
- selector list 使用逗号，不得把自然语言 `OR` 拼进 `querySelectorAll()`。

## 富文本编辑器适配

先枚举实际 `[data-slate-type]`，再建立映射。

| 标准语义 | Slate 标记 | 提取要点 |
|---|---|---|
| 段落 | `paragraph` | 普通段落 |
| 标题 | `heading` 或标准 h 标签 | 保留层级 |
| 列表 | `list` | wrapper/native 共享身份，嵌套列表独立 |
| 列表项 | `list-line` | wrapper/native 共享身份 |
| 表格 | 外层 `table` + 内部 `<table>` | 原生节点优先 |
| 代码块 | `pre` + `code-line` | 使用 `[data-slate-type="pre"]` |
| 引用 | `block-quote` + `quote-line` | 输出 blockquote |
| 图片 | `image` | 图片、题注和 image ledger 一起处理 |
| 加粗/斜体 | `bold` / `italic` | 保留语义 |

## 列表处理

有序证据来自 `<ol>`、`data-list-type="ordered"`、CSS counter 或连续编号属性； `<ul>`/bullet 为无序证据。无法确认时默认无序并标记复核。

禁止：

- 双 marker，如 `- 1. item` 或 `1. - item`；
- 根据内容“像步骤”擅自改变 marker；
- 把代码块行号当列表编号；
- 把嵌套 `ul/ol` 与父列表合并为同一 `semantic_id`。

## 表格处理

- DOM 基线计 canonical 表格，不计 selector 原始命中数。
- Slate wrapper 与内部标准 `<table>` 使用同一 `semantic_id`。
- canonical candidate 优先原生 `<table>`，wrapper 只作 fallback。
- 保留行列、表头和顺序；rowspan/colspan 无法等价表达时使用 fenced HTML 或人工复核。
- 表标题与表格之间保留空行。

## 评论区处理

不得默认整体删除评论区。只匹配顶层评论容器，转换前记录完整稳定 `source_ids`。

保留技术问题、纠错、补充、作者回复、代码、公式、链接和说明图；纯打卡、纯表情、广告和 UI 控件可有理由过滤。

每条源评论建立 ledger：

```text
source_id | status | emitted_count | reason
```

`status` 只能为 `kept / removed_as_noise / failed / manual_review`。交付前调用：

```python
assert_valid_comment_ledger(entries, source_ids=source_ids)
```

- `kept` 必须输出一次；
- 其他状态输出 0 次且必须有原因；
- ledger ID 集合与源 ID 集合完全一致。

## 相邻行内公式（避免 `$$` 定界符碰撞）

两个行内公式在源 DOM 中相邻（中间无文字）时，逐个按 `$...$` 拼接会产生定界符碰撞：`$D_t=P_t/P_0-1$` 紧跟 `$T_t=D_t≤-S$` 拼成 `...-1$$T_t...`，中间的 `$$` 被 GitHub/KaTeX 当成块公式定界符，渲染破坏。

规则：

- 在相邻行内公式之间**插入一个空格分隔符**，输出 `$a$ $b$`。这保持二者仍是行内公式，**不改 display 类型**：`formula_inline` 计数不变、无审计不一致、排版语义不变。
- **不要**把行内公式改成 `$$ ... $$` display 块——那会改变源 DOM 的排版语义，并造成报告按 `formula_inline` 计数、输出却是块公式的审计不一致。
- 只有**前一片段以 `$` 结尾且后一片段以 `$` 开头**才需分隔；公式与文字、文字与公式、行内 code 与公式等其它边界不插空格。

**仓库已有实现**：`html-to-markdown/fast_converter.py` 的 `_join_inline()` 在 `inline_children` 拼接时执行此分隔（前片段 `$` 结尾 + 后片段 `$` 开头 → 插空格）；回归见 `tests/test_pipeline.py::test_adjacent_inline_formulas_are_separated`。strict 路径的临时转换器同样须在相邻行内公式间保留分隔符。

## 数学段反斜杠加倍（GitHub GFM，`markdown_postprocess.py`）

GitHub GFM 在 `$…$` / `$$…$$` 内会把 `\`+ASCII标点的反斜杠**剥掉一层**再喂 MathJax，所以矩阵/cases 换行 `\\`、`\,` `\;` `\%` 等在源 md 里必须**双写**（`\\`→`\\\\`）才能在 GitHub 上渲染正确；`\`+字母（`\sigma` `\frac` 命令）不受影响，不动。这条规则由共享后处理门 `markdown_postprocess.py::_double_math_backslashes` 机械执行（fast/strict 两路径都经过），与 `formula-extraction` skill gap #31 的提取器侧 `\\_` 产出幂等兼容。完整机制、transform 三分支与实证表见 self-improvement.md「数学段反斜杠加倍（缺陷 38）」。

## 无语义 wrapper 穿透（inline 上下文）

SingleFile/Slate 常在段落内嵌无语义 `<div>`（无 `data-slate-*`、纯排版包裹）。fast path 的 **block** 上下文对 `div/section/article/main` 已按 `has_block_child` 穿透（有块子→当块，无块子→当内联），但 **inline** 上下文旧实现遇 `<div>` 一律 `FastPathUnsupported` → 整页被迫 strict（~19min），两处不对称即 bug。

规则：inline 上下文遇 `BLOCK_TRANSPARENT_TAGS`（`div/section/article/main`）且**无 `data-slate` 语义**时——

- 无块级子节点（`has_block_child` 为假）→ 递归 `_join_inline` 穿透，等价于 `<span>`；
- 有块级子节点 → 仍 fail-close 抛错，路由 strict（wrapper 藏了真正块内容，不能扁平化）；
- 未知 inline 元素（如自定义 `<custom-widget>`）→ 仍 fail-close，路由 strict。

实现见 `fast_converter.py::inline`；回归 `test_inline_div_wrapper_is_transparent_on_fast_path`（穿透正例）+ `test_inline_div_with_block_child_still_routes_to_strict` / `test_unknown_inline_element_still_routes_to_strict`（两反例）。

## mdnice/微信编辑器结构（`<p>`/`<li>` 内块 wrapper、游离嵌套 list、双层公式）

mdnice 编辑器（微信公众号排版）产出的正文里，块级内容常被塞进本应只含行内的容器，或被多层透明 span 包装。这类结构历史上被整页 fail-close 挡住，属 fast path 支持范围内应确定性转换的：

- **原生 `<p>` 尾部块 wrapper**：`<p><span>导语句</span><section data-tool="mdnice"><table>…</table></section></p>`——行内导语后跟被 section 包住的块级 table。规则：仅 `node.name == "p" and not slate` 时，若 p 含块 wrapper 且**块全在尾部**（最后一个块 wrapper 之后无非空白行内），拆成「前导行内 → 段落」+「尾部块 wrapper → 走 block 穿透」。块夹中间 / 块后有行内 / Slate 段落（`slate == "paragraph"`）/ 带 slate 属性的子 wrapper → 维持 `inline_children`，遇块子仍 fail-close 到 strict。前导段落 `.strip()` 空则跳过（不发孤立空段落）。实现 `fast_converter.py::block` 的 p 分支；回归 `test_p_with_tail_block_wrapper_converts_on_fast_path`、`test_p_with_multiple_tail_block_wrappers_converts`、`test_p_pure_block_wrapper_no_empty_paragraph`（正例）+ `test_p_with_block_wrapper_then_inline_still_strict`、`test_slate_paragraph_with_block_wrapper_still_strict`（fail-close 反例）。

- **`<li>` 内 mdnice section 裹段落**：`<li><section data-tool="mdnice"><p>列表项文字</p></section></li>`——列表项文字被 section+p 包了一层。规则：li 内容遇「块 wrapper（section/div，无 slate，`has_block_child`）裹**单个可行内表达的段落**（`<p>`/`<div>`，且该段落无更深块子）」时，穿透取内层段落的 `inline_children` 并入列表项；裹 table/list/pre/多段落/更深块 → 维持原 `inline`，fail-close 到 strict（列表内嵌真块 GFM 表达受限）。实现 `fast_converter.py::_li_inline_passthrough_target`；回归 `test_li_with_mdnice_section_paragraph_converts`（正例）+ `test_li_with_section_wrapping_table_still_strict`（反例）。

- **游离嵌套 list**：`<ol><li>…</li><ul>…</ul><li>…</li></ol>`——嵌套 `<ul>`/`<ol>` 直接挂在父 list 下而非 `<li>` 内（浏览器对非法 HTML 的解析结果）。`list_block` 旧实现 `find_all("li", recursive=False)` 只遍历 li，整块吞掉游离嵌套 list（连同其中的公式、列表项）。规则：遍历 list 的**所有直接子**——`<li>` 输出列表项并递增序号，游离 `<ul>`/`<ol>` 当嵌套列表递归（缩进 `level+1`）。实现 `fast_converter.py::list_block`；回归 `test_list_with_floating_nested_list_converts`。

- **双层相同 data-formula span**：`<span data-formula='X' style='cursor:pointer'><span data-formula='X'><svg/></span></span>`——公式被两层携带**相同** LaTeX 的 span 包装（外层加点击效果）。`FORMULA_SELECTOR` 匹配两层但 `_matches_formula` 不认 `data-formula`，导致父子都判 top-level → `formula_total` 翻倍 → 下游守恒 blocked。规则：`_top_level_formula_nodes` 的 nested 检查补一条——祖先**自身** data 属性（`_own_attr_latex`，不搜后代）携带相同 LaTeX 时判 nested 去重；LaTeX 不同的祖先公式是合法嵌套（块级公式内嵌不同行内公式），不判 nested。实现 `preflight.py::_top_level_formula_nodes`；回归 `test_double_wrapped_same_latex_data_formula_counted_once`（去重）+ `test_inline_formula_under_block_formula_ancestor_stays_inline`（不同 LaTeX 保留）。

## 块级居中与题注

原网页居中的公式块/图片/图表/图注/署名 → Markdown 也必须居中：

```markdown
<div align="center">

$$
V_\pi(s)=\mathbb{E}_\pi\left[R_t+\gamma V_\pi(S_{t+1})\mid S_t=s\right]
$$

</div>
```

**居中证据：** `text-align:center` / `align="center"` / `display:flex; justify-content:center` / `margin:auto` / `.katex-display` / 截图。

无证据不得擅自居中（正文段落、列表等）。块级公式不能降级成行内 `$...$`。

**例外——内容块及其短标题默认居中**（排版惯例，即使原文无居中证据）。

**通用模型：区分「内容块 / 短标题 / 说明段落」三者**，不要靠前缀词（图/表/公式）判断：

| 元素 | 特征 | 处理 |
|------|------|------|
| **内容块** | 表格、图片、块级公式 `$$…$$` | 居中 |
| **短标题**（题注/caption） | 紧邻内容块、简短（≤ 约 40 字、通常一行）、命名性（`表 X-Y　…`、`图 X-Y …`、`代码 X-Y　…`、`清单 X-Y　…`、`公式 X-Y（…）` 的**纯标题**） | 与内容块**同一个 `<div>`** 一起居中，并**统一加粗** |
| **说明段落** | 多句、讲解/定义/背景、长（常 > 40 字，如「公式 D-4 中，$\rho$ 为…」「图 D-1 给出…它不是…而是…」） | **正文，左对齐**，即使以 图/表/公式 开头 |

判据是**长度 + 功能**（命名性短标题 vs 讲解性长段落），**不是开头词**。实测：`公式 D-4 中，$\rho$ 为单笔风险比例…`（267 字）、`图 D-1 给出本讲核心知识地图。它不是…`（200+ 字）都是说明段落，**不居中**。

具体规则：

- **表格**：表标题（短）+ 表格必须包进**同一个 `<div align="center">`**，不能只居中标题。GFM 里 markdown 表格默认左对齐，`<div align="center">` 包住整表能让**表格也居中**（实测有效）；只居中标题、表格不包 → 「标题居中悬在左对齐表格上方」的不协调。标题在表上或表下都和表格同包：

  ```markdown
  <div align="center">

  **表 X-Y　标题**

  | 列 | 列 |
  | --- | --- |
  | a | b |

  </div>
  ```

- **表格与标题间必须留一个空行**（GFM 表格后无空行会把紧跟标题吞进表格最后一行——实测踩过）。
- **块级公式 `$$…$$`**：居中（含 `.katex-display` 本就居中）。若有紧邻短标题同理同包。
- **图片**：`![](...)` 包 `<div align="center">`。
- **短标题以外的说明段落一律不居中**（上表第三行）——这是最容易误判的：别因为一段以「图/表/公式 X-Y」开头就居中它。
- **题注关键词集 = `图 表 代码 清单 公式`**：`代码 X-Y`/`清单 X-Y` 是 SingleFile 常见的代码题注，此前关键词只认 `图 表`，代码题注既不居中也不加粗（bug，实测 `代码 8-2` 命中）。
- **统一加粗所有题注**（用户决策）：SingleFile 里表题/代码题是 `data-slate-type=bold` span（转出带 `**`），图题却是纯 `<div>`（转出裸文本无 `**`）。为视觉一致，命中题注后**一律加粗**，不管源有无加粗 mark。
- **题注用多行块级形态，内部 Markdown 标记（间距 + 加粗 + 行内代码一次解决）**。图/代码题注这类**独立成段**的题注（非与表格同包的那种），输出为上下空行分隔的多行 `<div>` 块，内部用 `**…**` 和 `` `code` ``：

  ```markdown
  <div align="center">

  **图 8-1　时间序列标准化代码路径关系图**

  </div>
  ```

  **为什么多行块不用单行 `<div align="center"><strong>…</strong></div>`**（`gh api /markdown` 实测）：
  - **间距**：单行裸 div 内是 inline 内容，GitHub 输出的 `<div>` **不含内部 `<p>`**、CSS 无段落 margin，紧跟的正文 `<p>` 贴上来——题注和后段视觉粘连（用户反馈）。多行块内空行让 GitHub 解析成 `<div><p>…</p></div>`，`<p>` 自带上下 margin，与前后正文分开。
  - **加粗/行内代码**：多行块内 GitHub **会**解析 Markdown，所以内部用 `**…**`/`` `code` `` 即可，不需要单行块被迫用的 `<strong>`/`<code>`。整题注用**一对** `**` 包住、行内代码 `` ` `` 留在内，混排代码题注（`代码 8-2　业务源码：`normalize_candle`…`）不再有 `**` 被 `` ` `` 断开的坏接缝。

  `markdown_postprocess.py::_normalize_captions` 是块级扫描，把三种输入形态——裸题注行、上一轮单行 `<div>`（含 `<strong>`/`<code>`）、已是多行块——全部归一到上面形态。幂等。这修了上一轮"单行 HTML tag"版遗留的粘连问题。
- **顺手修 `****` 拼接 bug**：加黑段相邻拼接产生 `**表 1-4****置信度****…**` 四连星，GitHub 渲染错乱。整行 `**` 去掉后重包一层 `**…**`。
- 编号识别：`X-Y` 中 X 可为数字或字母（如 `D-15`、`0-1`）。
- **验证必须在 GitHub 端**：本地渲染器对 `<div>` 包表格、表格边界的处理与 GitHub 不同，本地看着对不代表 GitHub 对。

题注候选只能来自已验证结构（防止把正文/UI 误当题注）：

- `<figure>` 的直接 `<figcaption>`；
- `<table>` 的直接 `<caption>`；
- Slate `image` 容器内与 `<img>` 已验证同级、非 UI 的文本节点。

不得抓取内容块外部任意 sibling。每个 confirmed caption 建立 ledger 并保证 `emitted_count == 1`。

## 图片与资源

基础规则：

- `data:` 图片（base64 或百分号编码）解码到 `files/<zip-name>/`，并接受合法的媒体类型参数（例如 `charset=utf-8`）；
- Markdown 使用相对路径；
- 评论说明图使用 `comment_` 前缀；
- lazy-load 源缺失时按 notebook 规则回填或标注；
- 每张源图片建立稳定 `source_id`，调用 `decide_image()` 并生成 image ledger；
- 交付前调用 `assert_valid_image_ledger(entries, source_ids=source_ids)`。

### 二维码

二维码不是默认噪声：

- 正文步骤、下载、联系方式、报名、认证、支付等内容相关二维码必须保留；
- 分享/关注/登录 UI 中且与正文无关的二维码可标记 `remove_as_ui`；
- 无法判断时标记 `manual_review`，原图仍输出一次；
- 能可靠解析目标 URL 时，同时输出可点击链接；解析失败不构成删除理由。

### 去站点水印（默认执行）

**默认行为：默认执行去站点水印。** 只有用户明确要求保留原始水印时才跳过。去水印仍是破坏性处理，破坏性护栏一条都不能省——默认执行不等于放松验证。

fast pipeline 已把这套合同下沉为确定性像素层 `@image_processing.py`（fail-closed，编排/验证/压缩）+ 检测与填充模块 `@watermark.py`（Pillow + numpy 手写连通块 + cv2.inpaint），对每张 data-URI 图自动执行，处理结果写入 `report.json.image_ledger`，无需 strict sub-agent 逐张现写脚本。检测不写死颜色：按“与局部背景的半透明偏离带”识别站点叠加（任意色命中，强对比的真内容不命中）。

强制护栏（默认执行时同样适用）：

1. 保留未修改原图副本；
2. 报告处理文件、方法和 bbox；
3. 检测和验证都用原图，不用缩略图（否则漏检）；
4. 命中区域按连通块合并邻近块成单一水印框，只取最右下的那个，不误擦正文；
5. bbox 紧框水印，禁止一盖到角（否则擦掉内容）；
6. 逐图原尺寸/放大验证正文未被擦除（inpaint mask 外零容差全等 + bbox 外扩环带内 mask 外强对比占比阈值 + inpaint 残留检查）；水印框紧贴 mark，碰撞的正文（图表线/轴标）常落在框外一圈，故占比在按框高外扩的环带上量，才看得见框外的正文冲突；
7. 宁可保留不确定水印，也不能擦除正文——无法安全去除（或环境缺 cv2）时降级为保留原图并标注。

### 图片压缩

压缩时同步扩展名和 Markdown 引用，宽图等比缩放，图表/代码截图保守处理，并抽检文字可读性。去水印和压缩均默认执行，固定顺序为“原图备份 → 去水印 → 压缩”。fast pipeline 的确定性参数：宽 > 1600px 等比缩放（不放大），webp 质量 82；webp 编码反而变大时保留原格式（`format_note=webp_larger_kept_original`）；svg/gif 不转码、按原样透传。原图副本存于打包树**外**的 `<output>/<package>__images_orig/`（离线审计用，**不进最终交付 ZIP**）。

## 代码块语言与 fence

无 `language-*` 时至少两个独立信号才标具体语言；不确定时标 `text`。代码内部 NBSP 替换为普通空格。

**代码行换行**：Slate/hljs 代码块把每行渲染成独立的块级 `<div>`（子节点全是 `<span>`），换行由块边界表示、**不存在** `\n` 文本节点。裸 `get_text()` 会把各行糊成一行（`a.jsonb.py`）。提取时检测这种「每行一个块级 div」布局：多于一行时按行 `\n` join，否则退回整体 `get_text()`。实现见 `fast_converter.py::_code_text`；回归 `tests/test_pipeline.py::test_slate_code_block_preserves_line_breaks`。

结构计数前必须调用：

```python
scan_fenced_blocks(markdown)
no_code = strip_fenced_blocks(markdown)
```

不得使用 fence 行数奇偶或跨行正则代替 scanner。

## 文本清理

- 删除 PUA U+E000–U+F8FF；
- 删除 zero-width U+200B/U+200C/U+200D/U+FEFF/U+2060；
- 代码内 NBSP 替换为空格；普通段落仅在确认无语义时处理。

## 加粗/斜体

保留 `<strong>`、`<b>`、font-weight、Slate bold/italic。GitHub 强调边界需区分字母、数字、CJK 和标点，禁止使用 `\S` 宽泛匹配；扫描相邻强调产生的 `****`，按语义重包而非机械替换。

## BeautifulSoup 解析器

必须使用 `lxml`。SingleFile HTML 可能存在未闭合表格标签，`html.parser` 容易错误嵌套。

## 输出结构

```text
dist/
├── <name>/
│   ├── <name>.md
│   └── files/<name>/
└── <name>.zip

<name>.zip
├── <name>.md
└── files/<name>/
```

### 确定性命名

- `<name>` 只能来自 pipeline 的 `report.json.output_name`，默认由输入文件 stem 机械规范化；用户可用 `--output-name` 明确指定。
- 空白、下划线、点号和其他标点/路径分隔符统一转为 `-`；例如 `report v1.2` 固定为 `report-v1-2`。
- 目录名、Markdown stem、资源目录和 ZIP stem 必须完全相同，禁止各自起名。
- 标题文字保留在 Markdown 正文中，不得翻译、摘要或改写成另一套文件 slug。
- strict 多文档输出按渲染 DOM 稳定顺序调用 `numbered_document_name(exact_title, ordinal)`；例如 `01 | AI 量化研究` 固定为 `01-AI-量化研究`，对应 `01-AI-量化研究.md` 和 `files/01-AI-量化研究/`。该 helper 有意由 agent-driven strict handoff 调用；单文档 pipeline 不调用它。
- dispatch 前由主 agent 固化 naming manifest。重名只能通过稳定序号消解；禁止时间戳、随机数、hash 短码或临时后缀。

## 删除与保留速查

**保留：** 正文、标题层级、列表、引用、代码、表格、公式、正文图片、内容相关二维码、关键链接、题注、有价值评论和原有对齐语义。

**可删除：** 导航、侧栏、页脚、弹窗、分享/点赞控件、广告、推荐、头像、Cookie 提示、脚本、CSS、tracking 参数及有明确证据的纯 UI 图片、**作者开头/结尾寒暄**。二维码只有在 `remove_as_ui` 证据成立时才删除。

---

## 作者寒暄去除（课程/专栏类文章）

课程、专栏、公众号类文章常有作者的开场白和结束语，属社交套话非正文，去掉：

- **开头寒暄**：`你好，我是XXX。` / `你好，我是XXX，欢迎来到《课程名》。` / `大家好！` 等自我介绍、欢迎语。删该行。
- **结尾寒暄**：`我们下节课再见！` / `期待你的分享` / `欢迎转发给有需要的朋友` 等**明确的课程道别/求转发/求互动**语。删该行。
- **边界（重要）**：正文首段（讲本讲内容的）、思考题、正文性质的结语（有信息量的总结）都保留。寒暄若与实质内容**混在同一行**（如 `重要结论：算法收敛。我们下节课再见！`），**按句剥离**——只删纯寒暄句，保留带信息量的句子。

**仓库已有实现**：`html-to-markdown/markdown_postprocess.py` 的 `_strip_author_greetings()` 做**保守机械化**（宁漏勿误删），只处理**首个/末个非空行**，**按句剥离**行首开场白句 / 行尾结束语句：

- **按句判定，不整行删**：先把 `\r\n`/`\r` 归一化成 `\n`，逐行拆句（以 `。！？` 切分保留标点），行首连续的纯开场白句 / 行尾连续的纯结束语句删掉，**保留同一行里其余带实质内容的句子**。绝不因为一行以道别收尾就删掉整行正文（曾出现的静默丢正文坑：`重要结论：算法收敛。我们下节课再见！` 被整行删空）。
- **opener 逗号必需**（`你好，我是`）：排除反问句「你好我是谁？…」；且以 `？/?` 收尾的句一律不当开场白。
- **closer 句尾锚定**（强道别短语出现在**句尾** `$`，非子串命中）：正文里出现「敬请期待」「转发」但句子没以道别收尾不会误删。裸「点赞/收藏/转发/敬请期待」正文太常见，**不作为独立信号**（否则「新版本开发中，敬请期待。」这类正文会被误删）。

路径无关，fast/strict 共用。回归见 `tests/test_markdown_postprocess.py`（规则4，含误删反例：正文含道别词、反问 opener、单 `\n` 分段、CRLF）。历史教训：此规则最初由 commit `1e6ab40` 引入却只停在文档层、从未落代码，文档精简后连措辞都丢失——所以线上又冒出寒暄。规则必须落代码 + 测试才算生效。

---

## 代码块首尾空行

Slate 代码块把每行源码渲染成独立 `<div>`，首/尾若有空 `<div>`（布局填充，非代码）会在 fence 内产生多余空行（```` ```text ```` 后紧跟空行才到内容）。转换时去掉代码块首尾空行，**保留内部空行**（代码内部空行有意义）。实现见 `fast_converter.py` 的 `_strip_blank_edges()`；回归见 `tests/test_fast_converter_codeblock.py`。
