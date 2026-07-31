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

### NBSP 紧贴 `$`（缺陷 37，GitHub 平台，微信 mmbiz 真机验证）

规则：`\xa0(?=\$)` / `(?<=\$)\xa0` → 换成半角空格（`_space_cjk_inline_math_line` 里在 CJK 规则**之前**跑）。机制：GitHub 行内数学要求 `$…$` 两侧是 ASCII 空白或行首尾边界，**U+00A0 NBSP 不算合法边界** → 公式字面显示。微信 mmbiz SingleFile 页用 NBSP 分隔公式与中文（`有\xa0$n$\xa0个`）。CJK 规则的字符类 `一-鿿　-〿＀-￯` 含全角空格 U+3000 但**不含** NBSP U+00A0，是两个不同码点，必须单独处理。真机（推真 GitHub 私库看渲染，非本地 KaTeX/MathJax，缺陷 25 铁律）验证：`有\xa0$n$\xa0个` 字面不渲染 → 换空格后 91 数学节点全渲染。

| 输入（`\xa0`=NBSP） | 期望 | 类别 | 理由 |
|------|:---:|------|------|
| `有\xa0$n$\xa0个` | 换成 `有 $n$ 个` | 正例 | NBSP 两侧紧贴 $，GitHub 不认边界 |
| `见 $r_t$ 公式`（半角空格） | 原样不动 | 反例 | 已是 ASCII 空格，合法边界 |
| `价格\xa0上涨了`（NBSP 不贴 $） | 原样保留 NBSP | 反例 | 只归一紧贴 $ 的 NBSP，正文 NBSP 不动 |
| fence 内 `价格\xa0$USD` | 原样不动 | 反例 | fenced code 内不处理 |

### `$` 相邻多空格折叠（缺陷 37 续，courses-md 存量修复真机发现）

规则：`" {2,}(?=\$)"` / `"(?<=\$) {2,}"` → 单个半角空格（`_space_cjk_inline_math_line` 里在 NBSP 归一**之后**、CJK 补空格之前跑）。机制：源里常见 `半角空格 + NBSP + $`（微信 mmbiz 在已有半角空格后又插 NBSP 分隔），NBSP 归一成半角空格后成 `  $` 两个连续空格。GitHub 渲染折叠多空格、`$` 边界仍合法（公式照常渲染），但源码留冗余双空格不干净。真机（`gh api /markdown`，courses-md 25 文件存量修复）证实：双空格处 math-renderer 正常、0 泄漏，折叠纯为源码整洁。**只折叠紧贴 `$` 的**多空格，不碰正文其它多空格（避免泛化过宽误伤对齐/缩进）；折叠后仍留一个空格 = 合法边界，绝不把 `$` 重新贴回 CJK。CJK 补空格规则只在单侧紧贴时补一个、不产生双空格，所以双空格的唯一来源是 NBSP 归一，折叠放其后即可。

| 输入（`\xa0`=NBSP） | 期望 | 类别 | 理由 |
|------|:---:|------|------|
| `期望 \xa0$x$ 表示` | 换成 `期望 $x$ 表示` | 正例 | 半角空格+NBSP → 双空格 → 折叠成单空格 |
| `见 $x$\xa0 表示` | 换成 `见 $x$ 表示` | 正例 | $ 后侧 NBSP+半角空格同理 |
| `见 $x$ 表示`（单个半角空格） | 原样不动 | 反例 | 已是单空格合法边界 |
| `状态   $s$   下`（三空格） | 换成 `状态 $s$ 下` | 边界 | 折叠留一个空格，不贴 CJK（否则又坏边界） |
| 已知副作用：`价格  $5`（散文双空格贴货币号） | 折成 `价格 $5` | 已接受 | 折叠任何 `$` 相邻多空格；散文冗余双空格被顺手清=无害，接受此轻微越界换实现简单 |

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

## 数学段反斜杠加倍（缺陷 38，GitHub 平台，共享后处理侧，`markdown_postprocess.py`）

判定项：GitHub GFM 在 `$…$` / `$$…$$` 内会把 `\`+一个 CommonMark ASCII 标点的反斜杠**剥掉一层**再喂 MathJax（剥离正则 `\\([!-/:-@\[-`{-~])`，与 `formula_batch.py::_GFM_MATH_UNESCAPE_RE` 同源，全局非重叠，`\`+字母不动）。所以 verbatim LaTeX（`data-formula`/结构，**绕过 gap #31 的 `_map_text`**）里的**矩阵/cases 换行 `\\`**、`\,` `\;` `\%` `\{` 等 `\`+标点，都被吃掉一层：换行 `\\`（k=2）→ GitHub 吐 1 个 `\` → MathJax 收不到换行 → **矩阵所有行塌成一行**（用户报的 6.5 协方差矩阵 bug）。

这是 **gap #31 的共享后处理侧对偶**：gap #31 在提取器侧（`_map_text`）为字面下划线产出 `\\_`；本规则在 `markdown_postprocess.py::_double_math_backslashes` 覆盖**所有** `\`+标点（含换行 `\\`），fast/strict 两路径都经过，且与 gap #31 的 `\\_` **幂等兼容**（不把 `\\_` 翻成 `\\\\_`）。

transform（极大反斜杠 run，长 k，follow=run 后紧接字符）：① follow 字母且 k 奇 → 不动（命令 `\sigma`）；② follow 非反斜杠标点 → k 奇翻倍/k 偶不动（`\,`→`\\,`；gap#31 `\\_` 保持）；③ 其它（换行/非字母/EOL）→ `2k if (k 奇 or k//2 奇) else k`（换行 `\\` k2→4；再跑 k4 不动=幂等）。**follow 字符区分「换行 `\\` 需双写」与「`\\_` 不能动」**（都 k=2，follow 不同）。块级用状态机（`$$`-only 行 toggle，块内整行施 transform，fence 跳过）。

实证（`gh api /markdown`，`$$…$$`）：

| 源 md 形态 | GitHub 剥离后喂 MathJax | 类别 | 理由 |
|------|------|------|------|
| 换行 `\\`（单层，转换器产出） | `\`（掉换行，矩阵塌一行） | 反例（bug 现状） | k=2 → floor(2/2)=1 |
| 换行 `\\\\`（本规则修后） | `\\`（换行保住） | 正例 | k=4 → floor(4/2)=2 = MathJax 换行 |
| `\,`（单）→ 修成 `\\,` | `\,`（thin space 保住） | 正例 | k=1→2，GFM 剥一层 |
| `\%`（单）→ 修成 `\\%` | `\%` | 正例 | 同上 |
| gap#31 `\\_`（双，follow=`_`） | `\_`（字面下划线） | 正例（不干扰） | k=2 follow 标点 → 不动，本规则不碰 |
| `\sigma` `\frac`（`\`+字母） | `\sigma` `\frac` | 反例（不误伤命令） | follow 字母 → 不动 |
| 数学 span 外 `C:\Users` `\*` | 原样 | 反例（不碰 prose） | 只作用于 span 内 |

回归 `tests/test_markdown_postprocess.py` 规则9（`test_block_matrix_rowbreak_doubled`、`test_gap31_double_underscore_not_requadrupled`、`test_backslash_doubling_idempotent`、`test_backslash_before_letter_untouched`、`test_prose_backslash_untouched` 等）。真实用例：`02｜量化概率论基础` 的 6.5 协方差矩阵 pmatrix + 期望 cases 块（就地 `markdown_postprocess.py` 修 + 真机 GitHub 渲染验证换行保住）。

---

## 微信公众号 (mmbiz) 页面支持（结构规则，非正则）

判定项分布在 `preflight.py`（1-3、8）与 `fast_converter.py`（4-7），回归 `tests/test_preflight.py::WeChatMmbizTests` + `tests/test_pipeline.py::WeChatMmbizPipelineTests`（结构穿透用例在 `PipelineTests`）：

1. **正文 selector**：`BODY_SELECTORS` 追加 `#js_content` / `.rich_media_content`，排在语义 selector（`data-slate-editor`/`article`/`main`/`[role=main]`）之后。保持 `select_body` 的「首个有 substantial 命中的优先级必须唯一，否则 ambiguous 失败」语义。
2. **MathJax-SVG 公式源**：`FORMULA_SELECTOR` 加 `[data-formula]`；`_formula_source` 在 `data-tex/data-latex/data-math/alttext` 循环里加 `data-formula`（verbatim LaTeX，无需 KaTeX HTML 重建）；`_formula_display` 认 `data-formula` 节点**自身** style 含 `display:block` → block（收紧到 wrapper 节点，避免任意居中祖先误判行内为块级）。`fast_converter.formula` 复用既有 `original_latex` 分支，无需改。
3. **data-URI 图优先于残留 data-src**：`_asset_source` 在 lazy 检查**之前**加判——`_substantial_data_uri(src)`（data-URI 且解码 ≥512B）为真即 `data-uri`（authoritative），忽略 `data-src`。512B 门槛坐在 1px 占位（解码 <100B）和真内联图（观测最小 ~9KiB）之间；小于门槛的 data-URI + 不同 data-src 仍 fail-close 判 lazy。
4. **块位置 `<span>` 透明穿透**：`fast_converter.py::block` 加分支——`<span>` 且 `not slate` 时，`has_block_child` 为真则 `self.blocks(node)`（等价 BLOCK_TRANSPARENT_TAGS），否则 `self.inline_children(node)`（作一段行内文本发出，内容保留）。微信用 `<span data-tool style="display:block"><section>…` 包裹块级内容，旧代码到 `block()` 落 `unsupported <span>` → strict。带 `data-slate-type` 的 span 走 `not slate` 守卫仍 fail-close（不当透明 wrapper）。
5. **原生 `<p>` 尾部块 wrapper 拆分**：`fast_converter.py::block` 的 p 分支——仅 `node.name == "p" and not slate` 时，若 p 含块 wrapper（`section/div` 无 slate 且 `has_block_child`）且**块全在尾部**（最后块之后无非空白行内），拆成「前导行内→段落」+「尾部块 wrapper→`self.block` 穿透」（返回 `list[str]`）。前导 `.strip()` 空则跳过。mdnice 把「导语句 + 表格」塞进一个 p：`<p><span>导语</span><section><table>…</table></section></p>`。块夹中间 / 块后有行内 / Slate 段落 / 带 slate 属性子 wrapper → 维持 `inline_children`，遇块子 fail-close。
6. **`<li>` 内 section 裹段落穿透**：`fast_converter.py::_li_inline_passthrough_target`——li 内容遇「块 wrapper（`section/div`，无 slate，`has_block_child`）裹单个可行内段落（`<p>`/`<div>` 无更深块子）」时穿透取内层段落的 `inline_children`；裹 table/list/pre/多段落/更深块 → 维持 `self.inline`，fail-close。mdnice 把有序列表项包成 `<li><section><p>提出假设</p></section></li>`。
7. **游离嵌套 list 不吞**：`fast_converter.py::list_block` 遍历所有直接子而非只 `find_all("li")`——`<li>` 输出项并递增序号，游离 `<ul>`/`<ol>`（直接挂父 list 下，非 li 内）当嵌套递归缩进 `level+1`。微信产出 `<ol><li>…</li><ul>…</ul><li>…</li></ol>`，旧代码整块吞掉游离 ul（连同其中公式、列表项）。
8. **双层相同 data-formula 去重**：`preflight.py::_top_level_formula_nodes` 的 nested 检查补——祖先**自身** data 属性（`_own_attr_latex`，不搜后代）带相同 LaTeX 时判 nested。mdnice 把公式包成两层相同 `data-formula` span（外层 `cursor:pointer`）；`FORMULA_SELECTOR` 匹配两层但 `_matches_formula` 不认 `data-formula` → 父子都 top-level → `formula_total` 翻倍 → 守恒 blocked。LaTeX 不同的祖先公式是合法嵌套（块内嵌行内），不判 nested。**关键**：比较必须用 `_own_attr_latex`（只读自身属性），不能用 `_formula_source`（`select_one` 后代搜 annotation，对祖先会误命中后代 LaTeX，误杀相邻/嵌套 katex 公式——已被回归测试烧到）。

**为什么这么定**（真机诊断）：微信公众号 SingleFile 页无 `article`/`main` 语义，正文固定 `#js_content.rich_media_content`；公式是 MathJax→SVG，原始 LaTeX 存 `<section|span data-formula="...">`（块级 section 带 `display:block`，行内 span 无）；图片 `src` 已内联为完整 webp/png data-URI，`data-src` 只是残留 CDN 地址（图其实完整存在，非 lazy）。无 `data-formula` 的 `<svg>` 是真插图，不当公式，到 `fast_converter.block()` 落 `unsupported <svg>` → strict（用 Playwright 截图，cairosvg 渲 CJK 出豆腐块不可用）。

| 输入结构 | 期望 | 类别 | 理由 |
|------|------|------|------|
| `#js_content.rich_media_content` 内足够长正文 | 选中，selector=`#js_content` | 正例 | 微信正文容器 |
| 同时有 `<article>` 语义容器 | 选中 `article` | 反例 | 语义 selector 优先级更高，微信不抢 |
| 两个 substantial `.rich_media_content` | ambiguous 失败 | 反例 | 不因新增 selector 放松 fail-closed |
| `<section data-formula='R_t=\frac{...}' style='...display:block'>` | source=`data-formula`、display=`block`、latex verbatim | 正例 | 块级公式 |
| `<span data-formula='n'>` | source=`data-formula`、display=`inline` | 正例 | 行内公式 |
| `<svg viewBox='0 0 720 480'>`（无 data-formula） | 不进公式清单；pipeline→strict | 反例 | 真插图非公式，保守路由 |
| `<span class='katex'><annotation encoding='application/x-tex'>a+b</annotation></span>` | source=`annotation` | 反例 | 旧 KaTeX 源不受 data-formula 新增影响 |
| 完整 data-URI src（解码 ≥512B）+ 残留 data-src | `data-uri`、非 lazy、mode=fast | 正例 | 真图已内联，data-src 是残留 |
| 1px 占位 data-URI（解码 43B）+ 真 data-src | `lazy:data-src`、lazy | 反例 | 真 lazy，门槛拦住占位 |
| 空 src + data-src | `lazy:data-src`、lazy | 反例 | 经典 lazy，data-URI 规则不误放 |
| `<span data-tool style='display:block'><section><p>…</p><h2>…</h2></section></span>` | converted，穿透出正文 + 标题 | 正例 | 块位置 span 含块子=透明 wrapper |
| `<span data-slate-type='mystery-block'><section>…</section></span>` | strict_required | 反例 | `not slate` 守卫，slate span 不当透明 wrapper |
| 无 block 子的块位置 span（纯文本/inline） | 作行内文本发出，内容保留 | 反例 | 不 fail-close，也不吞内容 |
| `<p><span>导语</span><section><table>…</table></section></p>` | converted，导语段落 + 表格 | 正例 | 原生 p 尾部块 wrapper 拆分 |
| `<p><span>lead</span><section><table></section><span>trailing</span></p>` | strict_required | 反例 | 块后有行内，非尾部，fail-close |
| `<div data-slate-type='paragraph'>lead<section><table></section></div>` | strict_required | 反例 | Slate 段落不进拆分 |
| `<li><section data-tool><p>提出假设</p></section></li>` | converted，普通列表项 | 正例 | li 内 section 裹段落穿透 |
| `<li><section><table></section></li>` | strict_required | 反例 | li 裹真块，GFM 表达受限，fail-close |
| `<ol><li>a</li><ul><li>b</li></ul><li>c</li></ol>` | converted，嵌套项缩进不吞 | 正例 | 游离嵌套 list 遍历所有直接子 |
| `<span data-formula='X' style='cursor:pointer'><span data-formula='X'>…</span></span>` | 计 1 个公式 | 正例 | 双层相同 LaTeX 去重 |
| `<section data-formula='A'><span data-formula='n'>…</span></section>` | 计 2 个公式（A block、n inline） | 反例 | 不同 LaTeX 是合法嵌套，不去重 |

---

新增规则请按同样格式加小节 + 用例（≥1 正例 + ≥2 反例）。用例是本 skill 的回归测试套件，价值随行数增长。
