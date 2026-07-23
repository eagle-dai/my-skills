---
name: formula-extraction
description: Extract LaTeX from a single formula DOM node (KaTeX/MathJax/MathML). Input: one formula node. Output: one LaTeX string. Covers annotation extraction, MathML parsing, KaTeX HTML systematic reconstruction, post-processing pipeline, and Playwright render verification.
---

# 公式提取 (Formula Extraction)

从单个公式 DOM 节点中提取语义正确的 LaTeX 字符串。

> **改这个 skill 本身？** 先读 `../_meta/skill-self-improvement.md`（通用两道闸）+ @self-improvement.md（本 skill 专属回归用例表）——尤其后处理粘连修正,改前构造合法命令反例、改后跑全表,防误伤 `\simeq` 这类合法命令。

## 职责边界

- **输入**：单个公式 DOM 节点（`.katex` / `<math>` / `<annotation>` / `.MathJax` 等）
- **输出**：一个 LaTeX 字符串（如 `\pi_\theta(a|s)`）
- **不负责**：定位公式节点（调用方用 DOM 查询完成）、决定 block/inline 分界符（调用方决定 `$...$` 还是 `$$...$$`）、上下文文本处理

## 核心原则

**公式能渲染 ≠ 公式语义正确。** `\pi\theta(a|s)` 能渲染但不是 `\pi_\theta(a|s)`。

**上下标方向必须忠实原文：** 不得把 `V_\pi` 改成 `V^\pi`，也不得反向。修复 Double subscript 只能补分组（`d_{\pi_\theta}`），不能改方向。不得根据领域惯例改变上下标方向。

## 提取优先级

按优先级依次尝试，成功即停：

1. **`annotation[encoding="application/x-tex"]`** — KaTeX/MathJax 语义层原始 LaTeX
2. **`data-tex` / `data-latex` / `data-math` / `alttext`** — 属性中的原始 LaTeX
3. **`<script type="math/tex">`** — MathJax v2 内嵌脚本
4. **页面 JSON / hydration 数据** — SSR 框架的序列化数据中可能含原始公式
5. **富文本节点附近原始公式字段** — Slate 等编辑器节点数据
6. **MathML 结构重建** — 从 `<msub>/<msup>/<msubsup>/<mfrac>/<msqrt>` 等语义标签提取
7. **KaTeX HTML 系统性重建** — 解析 `.katex-html` 渲染层 DOM（详见 @katex-html-parser.md）
8. **无法提取** → 返回失败标记（如 `__FORMULA_EXTRACTION_FAILED__`），由调用方决定截图保存

### 策略选择（当优先级 1-5 均不可用时）

| 情况 | 策略 |
|------|------|
| 有 MathML（`<semantics>/<math>` 含 `<msub>` 等） | 优先级 6：MathML 结构重建 |
| 无 MathML，公式数量多（>10） | 优先级 7：编写 KaTeX HTML 解析器 |
| 无 MathML，公式数量少（≤10） | 优先级 8：返回失败，调用方截图 |

**禁止手动逐公式从渲染层拼接。** 要么编写可复用的解析器，要么截图。

### MathML 结构重建要点

| MathML 元素 | LaTeX 等价 |
|-------------|-----------|
| `<msub>` | `_{...}` |
| `<msup>` | `^{...}` |
| `<msubsup>` | `_{...}^{...}` |
| `<mfrac>` | `\frac{...}{...}` |
| `<msqrt>` | `\sqrt{...}` |
| `<mroot>` | `\sqrt[n]{...}` |
| `<mover>` | `\hat{}`/`\bar{}`/`\overline{}` 等（取决于上方符号） |
| `<munder>` | `\underbrace{}`/下方注释 |
| `<mtable>` | `\begin{array/matrix/cases}` |
| `<mrow>` | 分组容器，递归处理子节点 |

## 公式源码异常检测

提取完成后，必须扫描结果中的异常模式。以下任一命中必须修复：

### 明确错误（必须修复）

```text
\{\|\|  ⎧  ⎪  ⎨  ⎩  \approxrt  \gammaV  \sumk  \deltat  s□=g  �  γ0  γ1
\pi\theta  \mu\theta  \sigma\theta  \sigma\theta2  e\phi  T\theta
d_\pi_\theta  V^\pi_\theta  Q^\pi_\theta  J_\pi_\theta
\\mathcal  \\mathbb  \\mathrm  \\operatorname  \\frac  \\dfrac
\\sum  \\prod  \\max  \\min  \\arg  \\left  \\right  \\begin  \\end
\\pi  \\theta  \\mu  \\sigma  \\alpha  \\gamma  \\epsilon  \\phi
```

### 规则

- `^` 后不能直接结束、不能只跟空格/标点/中文
- `_` 后不能直接结束
- `_` 后又出现未分组的 `_`（如 `d_\pi_\theta`）→ 必须补分组为 `d_{\pi_\theta}`
- `\theta+α` → `\theta + \alpha`（Unicode 希腊字母转 LaTeX 命令）
- `g ^` / `g^` 后无内容 → 可能应为 `\hat{g}`
- `sum t` / `sumt` → 可能应为 `\sum_t`
- `maxa` / `max a` → 可能应为 `\max_a` / `\arg\max_a`
- `\sim` 后紧跟字母（`\simp` / `\simq` / `\simν`）→ 缺少空格，应为 `\sim p`
- `^'` 或 `^{'}` → KaTeX 不接受，应直接用 `'`（prime 记号）
- `^^` → double caret，应简化为 `^`
- **行内公式中 `\\[A-Za-z]+` 一律阻断**（除非在 aligned/cases/matrix/split 等多行环境中表示换行）

## 语义退化检测

即使 LaTeX 能正常渲染，以下情况也视为提取失败：

1. 原公式有分式结构 → 结果无 `\frac` / `\dfrac`
2. 原公式有上下标 → 下标/上标被摊平（`\pi_\theta` → `\pi\theta`）
3. 上下标方向反转
4. `e^{...}` → `e...` 或普通文本
5. `\sum_{a'}` → `\sum a'` / `sum a'`
6. `\max_{...}` / `\arg\max_{...}` → `maxa` / `max a`
7. `\mathcal{N}` / `\mathbb{E}` → 降级成普通 `N` / `E`
8. 矩阵/分段/根号/分式嵌套 → 一行扁平字符
9. 视觉复杂公式 → 字母/希腊字母/运算符简单拼接
10. 嵌套上下标产生 Double subscript
11. LaTeX 命令被双反斜杠转义导致命令名以普通文本显示

## 后处理管道

从 KaTeX HTML 重建或 MathML 提取的 LaTeX 必须经过以下后处理。**这些规则在解析器输出后统一应用，不得遗漏。**

| 问题 | 模式 | 修正 | 原因 |
|------|------|------|------|
| Prime 记号 | `^'` 或 `^{'}` | `'` | KaTeX 不接受 `^'` |
| Double caret | `^^` | `^` | accent+superscript 叠加 |
| `\sim` 后粘连 | `\simp`, `\simq`, `\simν` | `\sim p`, `\sim q`, `\sim \nu` | 未定义命令 |
| Unicode ϵ | `ϵ` (U+03F5) | `\epsilon` | KaTeX 不识别 |
| Unicode ∗ | `∗` (U+2217) | `*` | |
| Unicode ∥ | `∥` (U+2225) | `\|` | |
| Unicode 上标序列 | `⁻¹`, `²`, `ⁿ` 等 | `^{-1}`, `^{2}`, `^{n}` | U+207x/U+00Bx |
| Unicode 下标序列 | `₀`, `₁`, `ₙ` 等 | `_{0}`, `_{1}`, `_{n}` | U+208x |
| NBSP | `\xa0` (U+00A0) | 普通空格 | unknownSymbol warning |
| 裸 CJK in math mode | math mode 内 `[一-鿿]`（先剥离 `\text{}` 内容再判） | 连续 CJK 段包 `\text{...}` | `unicodeTextInMathMode` warning，`.katex-error` 检测漏网（是 warning 非 error）。实测：`\frac{平均盈利}{平均亏损}` |
| `\text{}` 内 `_` / `^`（**下标符**） | `\text{signal_source}` 或 `\text{signal\_source}` | 拆到 `\text{}` 外：`\text{signal}\_\text{source}` | **KaTeX 与 GitHub MathJax 行为不同**：KaTeX 接受 `\text{signal\_source}`，但 **GitHub MathJax 报 `'_' allowed only in math mode`**（`\text{}` 内即使 `\_` 也非法）。两端通吃的唯一写法是把 `_` 移到 `\text{}` 外用 `\_` 连接。实测：`\text{signal_source}`→`\text{signal}\_\text{source}`。次选：`\text{}` 内下划线换空格 `\text{signal source}`，或整体改行内代码 `` `signal_source` ``（非公式语义时） |
| `\text{}` 内 `# % &` | `\text{...}` 内未转义的 `# % &` | `\# \% \&` | text mode 下这三个转义可行（不同于 `_`） |
| 数学块内裸 `*`（GitHub 目标平台） | 数学段（`$...$`/`$$...$$`）内未转义的 `*` | `\ast` | 成对 `*`（如 `SR^{*}` 多次出现）被 GitHub markdown 当 emphasis 吃掉，`{*}`→`{_}`，MathJax 报 `Extra close brace`。VS Code 先保护数学块不受影响。实测：PSR/DSR 公式 |
| LaTeX 命令粘连 | `\gammaV`, `\thetax` | `\gamma V`, `\theta x` | 命令名延伸 |
| `\text{}` 后粘连 | `\text{with probability}1` | `\text{with probability} 1` | 视觉粘连 |
| `\mid` 间距 | `\mid` 后无空格 | `\mid ` | 条件概率 |
| `\mid` vs `\vert` | `\mid` | `\vert` | 避免 Markdown `\|` 表格冲突 |
| PUA 字符 | U+E000-U+F8FF | 删除 | Unexpected character |
| Zero-width | U+200B, U+FEFF, U+200D, U+200C | 删除 | 干扰匹配 |
| Prime inside frac | `\frac{f'}(1)}{2}` | `\frac{f'(1)}{2}` | 大括号不平衡 |

### `\sim` 后粘连完整规则

`\sim` 后紧跟任何字母（a-z, A-Z, Unicode 希腊字母）都必须插入空格。

Regex: `\\sim([a-zA-Zα-ωΑ-Ω])` → `\\sim \1`（其中希腊字母还需转换为 LaTeX 命令）

### LaTeX 命令粘连系统性修正

解析器拼接 LaTeX parts 时，必须检测：
- 前一部分以 `\command` 结尾（regex: `\\[a-zA-Z]+$`）
- 后一部分以字母开头

若是则插入空格。这是最高频的静默错误来源，逐个修正不可靠，必须在 join 阶段统一处理。

## 验证

### 单公式 Playwright 渲染验证

对每个提取结果：

1. 创建最小 HTML 页面，引入 KaTeX CDN
2. 渲染提取的 LaTeX
3. 检查 `document.querySelectorAll('.katex-error').length === 0`
4. 检查 `document.querySelectorAll('mstyle[mathcolor="#cc0000"]').length === 0`
5. 任一 > 0 → 定位错误、修复、重新验证

### 批量验证（调用方提取多个公式时）

可将所有公式写入一个 HTML 页面批量渲染，一次性统计所有错误，效率更高。

### 上下标方向验证

对每个含上下标的公式：
- 记录原始 DOM 中的方向（`<msub>` = 下标, `<msup>` = 上标, vlist 结构方向）
- 对比提取结果中的 `_` / `^`
- 方向不一致 → 阻断
