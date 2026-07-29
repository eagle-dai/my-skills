# html-to-markdown 专属回归用例表

> **通用元规则**（泛化检查清单闸 1 + 病根 + 改进流程）见 `../_meta/skill-self-improvement.md`。改本 skill 前先过那份的两道闸。本文件只放 html-to-md 的**专属回归用例表**（闸 2）。

改任何下列检测/清理正则后，把全表喂给临时 Python 跑，`hit != expect` 即 FAIL，全绿才落地。**禁删已有行。**

## 强调定界符边界（缺陷 6/7，已被烧两次，重点保护）

当前正则：`(\*\*[^*\n]+?\*\*)([^\s。，、；：！？）】」』.,;:!?)])`

| 输入 | 期望命中 | 类别 | 理由 |
|------|:---:|------|------|
| `**标签：**https://` | ✅ | 英文字母紧贴 | right-flanking 失败，真违规 |
| `**概念辨析：**为什么` | ✅ | CJK 汉字紧贴 | 真违规 |
| `**结论**。` | ❌ | CJK 句号紧贴 | 标点是有效 right-flanking，GitHub 渲染正常 |
| `**结论**，后面` | ❌ | CJK 逗号紧贴 | 同上 |
| `**记录**：写清` | ❌ | 全角冒号紧贴 | 同上 |
| `**读法**。只看` | ❌ | 句号+汉字 | 句号先紧贴→合法 |
| `**结论** 。` | ❌ | 已插空格 | 不该再命中（此形态另用反向正则清） |

反向清理正则（清缺陷 7 过度修复留下的错误空格）：`\*\*[^*\n]+?\*\* [。，、；：！？）]` —— 命中即删空格。

## 行内公式 `$` 边界（缺陷 3，GitHub 平台）

当前正则：`([一-鿿　-〿＀-￯])\$(?!\$)` / `(?<!\$)\$([一-鿿　-〿＀-￯])`

| 输入 | 期望命中 | 类别 | 理由 |
|------|:---:|------|------|
| `收益率$r_t$表示` | ✅ | CJK 紧贴 $ 两侧 | GitHub 不渲染 |
| `见 $r_t$ 公式` | ❌ | ASCII 空格隔开 | 正常 |
| `（$w_t$）` | ✅ | 全角括号紧贴 | GitHub 不渲染 |

## 数学块内裸 `*`（缺陷 5，GitHub 平台）

检测：数学段内 `(?<!\\)\*` 命中 → 阻断，修 `*`→`\ast`

| 输入 | 期望命中 | 理由 |
|------|:---:|------|
| `$SR^{*}$` | ✅ | 裸 `*` 被当 emphasis，MathJax 报错 |
| `$a \ast b$` | ❌ | 已转义 |

## 题注提取候选发现（缺陷 8，语义规则，非正则）

判定项：给定内容块内一个候选节点，**是否分类为题注并输出**。非正则可跑，靠转换脚本的候选发现逻辑判定；此表是语义回归清单（人工/fixture 验证），改候选发现范围时必须逐条对照。

规则见 conversion-rules「题注提取」：只认 `figure > figcaption` / `table > caption` / Slate image 容器内 img 已验证同级 `<div>`，排除 UI/wrapper/正文。

| 候选节点 | 期望分类 | 理由 |
|----------|:---:|------|
| Slate image 容器内 img 同级 `<div>图 4-5　权益峰值...</div>` | ✅ 题注 | 已验证直接结构关系，命名性短文本 |
| `<figure>` 内 `<figcaption>系统架构</figcaption>` | ✅ 题注 | 标准结构 |
| `<table>` 内 `<caption>量化口径</caption>` | ✅ 题注 | 标准结构 |
| 图片工具栏 `<div class="toolbar"><button/></div>` | ❌ 排除 | 含 button、UI class |
| resize wrapper `<div><img/></div>` | ❌ 排除 | 含 img，是 wrapper 非题注 |
| 图片后紧随的解释性长段落 `图 4-5 给出了…（多句）` | ❌ 排除 | 内容块父容器外/解释性正文，作正文保留不重复抽 |
| 内容块父容器外的下一普通段落 | ❌ 排除 | 跨出父容器，禁止抓取 |

去重项：同一 DOM 节点被普通段落遍历和题注 pass 同时触达 → `emitted_count == 1`（只输出一次，题注 pass 复用/移动而非重复输出）。

---

## 输出命名合同

命名必须由 `canonical_output_name()` / `numbered_document_name()` 机械生成；目录、
Markdown stem、资源目录和 ZIP stem 复用同一个结果。strict 多文档编号取渲染
DOM 稳定顺序，标题取 DOM 原文。

| 输入 | ordinal | 期望 | 反例/理由 |
|------|:---:|------|------|
| `01 \| AI 量化研究` | 1 | `01-AI-量化研究` | 不得双写为 `01-01-...` |
| `LLM 量化：可复现工作区` | 3 | `03-LLM-量化-可复现工作区` | 不得自由改成 `llm-quant-reproducible-workspace` |
| `05_安全边界` | 5 | `05-安全边界` | 下划线和竖线不能随机混用 |
| `report v1.2` | 无 | `report-v1-2` | 点号转 `-` 是明确合同，不得依赖旧的保留行为 |
| `2026 research` | 1 | `01-2026-research` | `2026` 是标题内容，不是第 1 篇的旧序号 |
| `CON` | 无 | `article-CON` | Windows 保留名不能原样作为 basename |
| `｜／：` | 无 | `article` | 纯标点稳定回退，不得追加随机字符 |

反例：同一输入不得在不同运行间选择中文标题/英文 slug；不得用时间戳、
随机数或 hash 解决重名。重名只用 DOM 顺序 ordinal 消解。

---

## 代码块行换行（缺陷 17，结构规则，非正则）

判定项：Slate/hljs 代码块——每行一个块级 `<div>`（子全 `<span>`，无块子）——提取后各行须以 `\n` 分隔，不得糊成一行。`fast_converter.py::_code_text` 判定，回归 `test_slate_code_block_preserves_line_breaks`。

| 输入结构 | 期望输出 | 理由 |
|------|------|------|
| `<pre data-slate-type="pre">` 内 3 个 `.se-line` div，各含 span 一行 | 三行以 `\n` 分隔（`a\nb\nc`） | 块边界即换行，`get_text()` 会漏 |
| 单个 `<code>` 内含真实 `\n` 文本 | 原样 `get_text()`，不改写 | 反例：非 Slate 布局，无多行 div，不触发 join |
| `<pre>` 内仅 1 个 line div | 退回整体 `get_text()` | 反例：`len(lines) > 1` 才 join，单行不特殊处理 |

## 无语义 wrapper 穿透 inline 上下文（缺陷 13，结构规则，非正则）

判定项：inline 上下文遇 `div/section/article/main`——无 `data-slate` 语义且无块子→穿透；否则 fail-close 路由 strict。`fast_converter.py::inline` 判定。

| 输入结构 | 期望 | 理由 |
|------|------|------|
| Slate 段落内嵌 `<div>wrapped <strong>x</strong> <katex></div>`（无块子） | converted，穿透为 `wrapped **x** $...$` | 正例：等价 span，不该 fail-close |
| 段落内 `<div>` 含 `<p>` 块子 | strict_required | 反例：wrapper 藏真块内容，不能扁平化 |
| 段落内未知 inline 元素 `<custom-widget>` | strict_required | 反例：未知语义仍保守 fail-close，穿透只放行无语义 wrapper |
| 带 `data-slate-type` 的 div | 走对应 slate 分支，不进 wrapper 穿透 | 反例：`not slate` 守卫，有语义的 div 不当透明 wrapper |

## text-mode 特殊字符转义（缺陷 18，结构规则，非正则）

判定项：KaTeX HTML → LaTeX 重建时，`\text{}` / `\mathbb{}` / `\mathcal{}` 内的 LaTeX 特殊字符（`_ % $ # & ^ { } \ ~`）必须转义，否则独立 KaTeX 报 `'_' allowed only in math mode` 等。`formula_batch.py::_escape_text_mode` + text-mode 下的 `_map_text` 分支判定；`_parse` 用 `text_mode` 标志区分 math/text 上下文。回归 `test_escape_text_mode_covers_all_special_chars`、`test_text_node_escapes_underscore`、`test_math_mode_subscript_underscore_unchanged`。

> ⚠️ 更正（gap #20）：转义成 `\_` 只对**独立 KaTeX / VS Code** 有效，**对 GitHub 无效**——GitHub GFM 会把 `$…$` 内可转义标点前的反斜杠剥掉再喂 KaTeX，`\text{observed\_at}` 在 GitHub 上还原成裸 `\text{observed_at}` 仍报错。即：含标点标识符（`observed_at` 等）放进 `\text{}` 在 GitHub 上本质不安全。正确产出应改行内代码 `` `observed_at` ``（源语义本就是代码标识符，见 gap #16 backlog），或由验证 fail-close 交 strict/人工。见下方 gap #20。

| 输入结构 | 期望输出 | 理由 |
|------|------|------|
| `<span class="mord text">` 内文本 `observed_at` | `\text{observed\_at}`（KaTeX 通过） | 正例：text mode 下 `_` 是字面字符，必须转义 |
| 重建输出 `\text{observed_at}`（裸下划线） | 禁止 | 反例：GitHub 报 `'_' allowed only in math mode` |
| math-mode 下标 `t_{obs}`（`msupsub`/`vlist` 结构） | 保留 `t_{obs}`，`_` 不转义 | 反例：math mode 的 `_` 是合法结构字符，转成 `\_` 会破坏下标 |
| text mode 内的 `≤` 等 Unicode 符号 | 不映射为 `\leq`（原样或按需处理） | 反例：`\leq` 在 text mode 非法，text_mode 分支关闭 SYMBOLS/OPERATORS 映射 |
| `\text{$t_n$}`（msupsub 嵌在 `.mord.text` 后代） | fail-close 交 strict，不产 `\text{t_{n}}` | 反例：text 内数学子式须 `$...$` 包裹；重建器不自动包裹，检测 `_{`/`^{`/`\frac` 即 `_MATH_ONLY_IN_TEXT_RE` fail-close（回归 `test_text_mode_with_nested_math_structure_fails_closed`） |
| `\mathbb{R}` 内下标 `R_n` | 保留 `_{n}`，`_` 不转义 | 反例：`\mathbb`/`\mathcal` 是 math-mode 命令，内部下标合法，不置 text_mode（回归 `test_mathbb_subscript_stays_math_mode`） |

## 去水印检测：渐变尖 + 复杂背景 logo（缺陷 19，图像规则，真图 fixture 回归）

判定项：右下角实心站点 logo（橙水滴 icon + 灰字）在两种形态下须完整检测并去净。PR #41 换成"饱和锚点 + fill/aspect 形状过滤"后对这两种变脆（commit 已自登记为待修回归）：

- **渐变/反锯齿尖**：水滴尖端分裂成 sub-threshold 小连通块，anchor bbox 底部止步，弧尖残留。修 `watermark.py::_grow_anchor_down`——anchor 定选后沿其列范围向下吸附饱和像素，capped 半个 icon 高。
- **复杂背景粘连**：logo 压在有色边框/填充上，icon 与边框 8-连通成细长块（fill 低、aspect 极端）被拒 → 漏检回退原图。修 `_find_anchor` 两遍：小 kernel 常规找；失败则 ROI 自适应大 kernel（`_ANCHOR_LINE_BREAK_FRAC`）断细线后重找。

回归 `test_real_solid_logo_on_white_leaves_no_orange_residue`、`test_real_logo_on_colored_frame_is_detected_at_bottom_right`（真图 fixture `tests/fixtures/watermark_*.webp`，**必须整图**——裁片改 ROI 比例会掩盖故障）。

| 场景 | 期望 | 理由 |
|------|------|------|
| 白底实心 logo（渐变尖） | 去净，右下 orange(hue 6-22) 残留=0 | 正例：bbox 向下扩覆盖弧尖 |
| logo 压红框粉底 | 检测到右下 logo（bbox 在 w/h 0.55 外）并去净 | 正例：fallback 断线找回 icon |
| 白底孤立橙 icon（合成 size24） | 去净，small kernel 命中，不触发 fallback | 反例：小 icon 不被大 kernel 腐蚀 |
| 细高橙 bar（aspect<0.5 图表） | 不检测 | 反例：形状过滤仍拒图表内容，fallback 不放宽 fill/aspect 判据 |
| 干净图无 logo | 不检测 | 反例：两遍都找不到合格 anchor |

橙 vs 红判据：OpenCV hue，橙 icon hue~8-15，纯红框/字 hue~0；测试用 hue∈[6,22] 排除红，不能用裸 R/G/B box（会把红误判成橙）。

## 公式验证模拟 GitHub `$…$` 反转义（缺陷 20，验证器缺陷）

判定项：GitHub GFM 在 `$…$` 内会剥掉 CommonMark 可转义标点（`` !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ ``）前的反斜杠，再把结果交给 KaTeX。所以 gap #18 转义出的 `\text{observed\_at}` 在 GitHub 上被还原成裸 `\text{observed_at}` → `'_' allowed only in math mode`。旧验证器把**源 md 里的转义形式**（带 `\_`）直接喂本地 KaTeX（通过），与 GitHub 实际渲染不一致 → 漏检。修法：`formula_batch.py::validation_document()` 注入 `githubMathUnescape`（JS 正则 `/\\([!-\/:-@\[-`{-~}])/g` → `$1`），`runFormulaValidation` 在 `katex.render` 前对 `item.latex` 施加，用反转义后的 `target` 验证。命令反斜杠（`\` 后接字母，如 `\leftarrow` `\frac`）不匹配、不受影响。`VALIDATOR_VERSION` bump v2→v3（验证语义变更，旧报告失效）。回归 `test_validation_document_simulates_github_unescape`、`test_github_unescape_catches_text_mode_underscore`、`test_github_unescape_preserves_command_backslash`。这是 fail-close 检测护栏，不自动改写产出（改写需判断"代码标识符 vs 数学文本"意图，属 gap #16 backlog）。

实证（本次用 `gh api /markdown` + Playwright/KaTeX 0.16.11）：`$a \_ b$` → GitHub 喂 `a _ b`；`\, \# \% \& \{ \}` 同样被吃；`\leftarrow` 保留。

| 输入（源 md 里的 latex） | 期望（验证器判定） | 理由 |
|------|------|------|
| `\text{observed\_at}` | fail（反转义成 `\text{observed_at}` → KaTeX 报错） | 正例：模拟 GitHub 后裸 `_` 暴露，护栏抓到，交 strict/人工 |
| `t_{obs}`（math mode 下标） | pass | 正例：`_{` 是合法结构，无标点转义，反转义不动它 |
| `\leftarrow` `\frac{a}{b}` `A \leq B` | 命令反斜杠原样保留 | 反例：`\` 后是字母，不在标点类，不该被吃（否则毁合法公式） |
| `a\_b\%c\#d\&e\,f` | 反转义为 `a_b%c#d&e,f` | 反例：不能只处理 `_`，GitHub 吃全 ASCII 标点集 |
| 只喂原始 `\_` 给本地 KaTeX 判"通过" | 禁止（旧行为） | 反例：本地 KaTeX 与 GitHub 不一致 → 假阴性漏检，正是本缺陷根因 |

## math-mode 字面下划线用双反斜杠 `\\_`（缺陷 31，GitHub 平台，提取器产出规则）

判定项：math mode 里作为**字面字符**出现的下划线（工程标识符 `field_coverage`、`valid_required_fields` 等，渲染文本里的真实 `_`，不是结构下标）——`formula_batch.py::_map_text` 走默认（非 text_mode）分支时，逐字符转义为**双反斜杠** `\\_`，不是单 `\_`。`_MATH_MODE_ESCAPES["_"] = "\\\\_"` 判定。

**为什么双反斜杠**（真机 `gh api /markdown` 实证，块级 `$$…$$`）：

- 单 `\_`：GitHub GFM 把 `$$…$$` 内可转义标点前的反斜杠剥掉 → MathJax 收到裸 `field_coverage` → `_coverage` 被当**下标**渲染（下划线消失、尾巴缩成下标，**错**）。
- 双 `\\_`：GFM 剥一层 → `\_` → MathJax 当**字面下划线**渲染（**对**）。同时过 validator 的 gap #21 门：`githubMathUnescape` 反转义 `\\_` → `\_`，门 `(?<!\\)[_^][A-Za-z]{2,}` 的 lookbehind 看到 `_` 前有反斜杠 → 不误判 identifier-as-subscript。

**边界（关键，防误伤）**：真数学结构下标/上标（`x_i`、`x_{ij}`、`\sum_{i}`）来自 KaTeX HTML 的 `msupsub`/`mfrac` vlist（走 `_parse_vlist`），**根本不经过 `_map_text`**，所以本规则不碰它们；它们以裸 `_{...}` 输出，GitHub 原样保留、MathJax 正常渲染下标。因此改 `_map_text` 只影响"渲染文本里的字面下划线"，不影响结构下标。

**范围**：本规则只管 `_`。字面 `^` 保持 `\string^`（命令形式，反斜杠+字母不被 GFM 吃，已 GitHub-safe，不改）——但 gap #21 门对 `\string^bc` 会过度 fail-close（`^` 前是字母 `g`，lookbehind 不排除），方向安全（安全形态误判为危险 → 走 strict/人工，不产错公式），07/08 无此形态，未在本次收窄。text mode（`\text{}` 内，gap #18/#20）是另一场景，本次不动。

`PARSER_VERSION` bump v4→v5（产出形态变更，旧缓存失效）；`VALIDATOR_VERSION` 保持 v4（门逻辑未变）。回归 `test_map_text_escapes_literal_underscore_double_backslash`、`test_map_text_double_backslash_multiple_underscores`、`test_double_backslash_underscore_passes_github_guard`、`test_single_backslash_underscore_still_fails_github_guard`、`test_real_math_subscript_not_touched_by_map_text`。真实用例：07/08 文章的 `field\\_coverage = \frac{valid\\_required\\_fields}{required\\_fields}`（端到端 pipeline `converted` + 真机 GitHub 渲染验证）。

实证（`gh api /markdown`，`$$…$$`）：单 `\_` → GitHub 喂 `field_coverage`（裸）；双 `\\_` → GitHub 喂 `field\_coverage`（留 `\_`）；`\frac` 两形态都保留。

| 输入（`_map_text` 参数 / 源 md latex） | 期望 | 类别 | 理由 |
|------|------|------|------|
| `_map_text("field_coverage")` | `field\\_coverage`（双反斜杠） | 正例 | 字面下划线标识符，GitHub 剥一层后 MathJax 当字面下划线 |
| `_map_text("valid_required_fields")` | `valid\\_required\\_fields` | 正例（多下划线） | 每个字面 `_` 各自 `\\_` |
| 门判 `field\\_coverage`（双） | pass（`has_identifier_subscript` False） | 正例 | 反转义成 `field\_coverage`，`_` 前有反斜杠，lookbehind 排除 |
| 门判 `field\_coverage`（单） | fail（`has_identifier_subscript` True） | 反例（旧错形态必须仍被拦） | 反转义成裸 `field_coverage` → 门抓到，防产出改回单反斜杠而门失守 |
| 门判 `x_i + y_{ij}`（裸结构下标） | pass | 反例（不误伤真下标） | 结构下标不经 `_map_text`，裸留，MathJax 正常渲染 |
| 门判 `x_i = data\\_count`（结构+字面共存） | pass | 反例 | 结构 `x_i` 裸留 + 字面 `data\\_count` 双反斜杠，两者并行正确 |
| `_map_text("α")` / `_map_text("max")` | `\alpha` / `\max` | 反例 | 希腊字母/运算符映射不受下划线改动影响 |
| `_map_text("valid_at", text_mode=True)` | `valid\_at`（单，text mode 分支不变） | 反例 | text mode 是 gap #18 场景，本规则只改 math mode 默认分支 |

---

新增规则请按同样格式加小节 + 用例（≥1 正例 + ≥2 反例）。用例是本 skill 的回归测试套件，价值随行数增长。
