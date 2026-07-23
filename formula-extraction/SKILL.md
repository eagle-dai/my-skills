---
name: formula-extraction
description: Extract LaTeX from a single formula DOM node (KaTeX/MathJax/MathML). Input: one formula node. Output: one LaTeX string. Covers annotation extraction, MathML parsing, KaTeX HTML systematic reconstruction, post-processing pipeline, and Playwright render verification.
---

# 公式提取 (Formula Extraction)

从单个公式 DOM 节点中提取语义正确的 LaTeX 字符串。

> **改这个 skill 本身？** 先读 `../_meta/skill-self-improvement.md`（通用两道闸）+ @self-improvement.md（本 skill 专属回归用例表）。尤其是命令边界修正：不得从最终字符串表面猜测 token 边界，改前构造合法命令反例，改后跑全表。

## 职责边界

- **输入**：单个公式 DOM 节点（`.katex` / `<math>` / `<annotation>` / `.MathJax` 等）
- **输出**：一个 LaTeX 字符串（如 `\pi_\theta(a|s)`）
- **不负责**：定位公式节点、决定 block/inline 分界符、上下文文本处理
- **失败原则**：缺乏结构证据时返回失败，不通过“看起来像某领域公式”来猜测或改写

## 核心原则

**公式能渲染 ≠ 公式语义正确。** 只有原始 DOM/MathML/annotation 等结构证据才能判定语义退化。例如原 DOM 明确含 `<msub>` 时，输出缺少 `_` 才能判错；仅看到 `\pi\theta` 这一字符串，不能推断它一定应为 `\pi_\theta`。

**上下标方向必须忠实原文：** 不得把 `V_\pi` 改成 `V^\pi`，也不得反向。修复 Double subscript 只能补分组（如 `d_{\pi_\theta}`），不能改变方向。

## 提取优先级

按优先级依次尝试，成功即停：

1. **`annotation[encoding="application/x-tex"]`** — KaTeX/MathJax 语义层原始 LaTeX
2. **`data-tex` / `data-latex` / `data-math` / `alttext`** — 属性中的原始 LaTeX
3. **`<script type="math/tex">`** — MathJax v2 内嵌脚本
4. **页面 JSON / hydration 数据** — SSR 框架序列化数据中的原始公式
5. **富文本节点附近原始公式字段** — Slate 等编辑器节点数据
6. **MathML 结构重建**
7. **KaTeX HTML 系统性重建** — 详见 @katex-html-parser.md
8. **无法提取** → 返回 `__FORMULA_EXTRACTION_FAILED__`，由调用方截图保存

### 策略选择（优先级 1-5 均不可用时）

| 情况 | 策略 |
|------|------|
| 有 MathML（含 `<msub>` 等语义元素） | MathML 结构重建 |
| 无 MathML，公式数量多（>10） | 编写可复用的 KaTeX HTML 解析器 |
| 无 MathML，公式数量少（≤10） | 返回失败，调用方截图 |

**禁止手动逐公式从渲染层拼接。** 要么编写可复用解析器，要么截图。

### MathML 结构重建要点

| MathML 元素 | LaTeX 等价 |
|-------------|-----------|
| `<msub>` | `_{...}` |
| `<msup>` | `^{...}` |
| `<msubsup>` | `_{...}^{...}` |
| `<mfrac>` | `\frac{...}{...}` |
| `<msqrt>` | `\sqrt{...}` |
| `<mroot>` | `\sqrt[n]{...}` |
| `<mover>` | `\hat{}` / `\bar{}` / `\overline{}` 等 |
| `<munder>` | `\underbrace{}` / 下方注释 |
| `<mtable>` | `\begin{array/matrix/cases}` |
| `<mrow>` | 分组容器，递归处理子节点 |

## 公式源码异常检测

提取完成后扫描异常模式。检查分为“确定错误”和“需要结构证据的警告”，二者不得混用。

### 确定错误（必须修复）

- Unicode replacement character `�`、无法解释的占位符 `□`
- 括号或环境不平衡
- 渲染器确认的 `Undefined control sequence`
- LaTeX 命令被双反斜杠转义为普通文本

```text
�  □  \approxrt  \gammaV  \sumk  \deltat
\\mathcal  \\mathbb  \\mathrm  \\operatorname  \\frac  \\dfrac
\\sum  \\prod  \\max  \\min  \\arg  \\left  \\right  \\begin  \\end
\\pi  \\theta  \\mu  \\sigma  \\alpha  \\gamma  \\epsilon  \\phi
```

### 需要结构证据的警告（不得自动改写）

以下形态本身可以是合法数学表达式。只有原始 DOM/MathML 明确表明结构丢失时，才可修复：

- `\pi\theta`、`\mu\theta` 等相邻符号
- `V^\pi_\theta`、`Q^\pi_\theta` 等同时含上下标的表达式
- `sumt`、`maxa`、`e\phi` 等可能是普通变量或乘积的字符串

### 通用规则

- `^` / `_` 后不能直接结束
- 未分组的连续下标（如 `d_\pi_\theta`）只有在原始结构证明第二个下标属于第一个下标时，才补成 `d_{\pi_\theta}`
- Unicode 希腊字母可按字符映射转为 LaTeX 命令，但不得借机改变上下标关系
- `^'` / `^{'}` → `'`
- `^^` → `^`
- 行内公式中 `\\[A-Za-z]+` 一律阻断；多行环境中的 `\\` 换行除外

## 语义退化检测

即使 LaTeX 能渲染，以下“原始结构 → 输出结构”不一致也视为提取失败：

1. 原公式有分式 → 输出无 `\frac` / `\dfrac`
2. 原公式有上下标 → 输出摊平
3. 上下标方向反转
4. 原公式有指数 → 指数内容变成普通文本
5. 原公式有带 limits 的运算符 → limits 丢失
6. `\mathcal{N}` / `\mathbb{E}` → 普通 `N` / `E`
7. 矩阵、cases、根号、嵌套分式 → 一行扁平字符
8. LaTeX 命令被双反斜杠转义

## 后处理管道

从 KaTeX HTML 或 MathML 重建的结果必须统一执行后处理。后处理只能修复有机械证据的问题，不能进行领域猜测。

| 问题 | 模式 | 修正 | 原因 |
|------|------|------|------|
| Prime | `^'` 或 `^{'}` | `'` | 非法 prime 形态 |
| Double caret | `^^` | `^` | 重复 caret |
| `\sim` 与后续 token 粘连 | 解析节点序列中，前一独立 token 恰为 `\sim`，后一独立 token 为变量 | join 时插空格 | 必须依据 token 边界；禁止在最终字符串上全局拆分 |
| Unicode ϵ | `ϵ` | `\epsilon` | KaTeX 兼容 |
| Unicode ∗ | `∗` | `*` | 之后按目标平台决定是否转 `\ast` |
| Unicode ∥ | `∥` | `\|` | 规范化 |
| Unicode 上标/下标 | `⁻¹`、`₀` 等 | `^{-1}`、`_{0}` | Unicode 规范化 |
| NBSP | U+00A0 | 普通空格 | 避免 unknownSymbol |
| 裸 CJK in math mode | 排除 `\text{}` 后仍有连续 CJK | 包进 `\text{...}` | KaTeX warning |
| `\text{}` 内 `_` / `^` | `\text{signal_source}` | 拆到 `\text{}` 外 | 兼容 GitHub MathJax |
| `\text{}` 内 `# % &` | 未转义字符 | `\# \% \&` | text mode 转义 |
| 数学段内裸 `*`（GitHub） | 未转义 `*` | `\ast` | 避免 GFM emphasis 破坏 |
| LaTeX token 拼接 | parser parts 中，前一 token 是完整命令、后一 token 是独立字母 token | join 时插空格 | 依据 parser token，而不是最终字符串正则 |
| `\text{}` 后粘连 | `\text{probability}1` | `\text{probability} 1` | 视觉粘连 |
| `\mid` 间距 | `\mid` 后无空格 | `\mid ` | 条件概率排版 |
| PUA / zero-width | 对应 Unicode 范围 | 删除 | 干扰匹配 |
| Prime inside frac | 已确认的大括号错位 | 修复平衡 | 语法错误 |

### `\sim` token 边界规则

**禁止**对最终字符串执行：

```text
\\sim([a-zA-Zα-ωΑ-Ω]) → \\sim \1
```

该规则会把合法命令 `\simeq`、`\simneqq` 等拆坏。

正确做法只发生在 parser 的 join 阶段：

```text
parts = ["\sim", "p"]  → "\sim p"
parts = ["\simeq"]     → "\simeq"
parts = ["\sim", "\nu"] → "\sim \nu"
```

若无法证明 `\sim` 与后续字符来自两个独立节点，保持原样并标记人工复核。

### LaTeX 命令边界

同样只在解析器的 token/part 边界上插空格。不得在已经拼成的 LaTeX 字符串中用“命令名前缀 + 字母”的宽泛正则拆分，因为无法区分合法长命令与粘连 token。

## 验证

### 单公式 Playwright 渲染验证

1. 创建最小 HTML 页面，引入固定版本 KaTeX
2. 渲染提取结果
3. `.katex-error` 数量必须为 0
4. `mstyle[mathcolor="#cc0000"]` 数量必须为 0
5. 捕获 `unicodeTextInMathMode` / `unknownSymbol` warning
6. 任一异常 → 定位、修复、重新验证

### 批量验证

可将所有公式写入一个 HTML 页面批量渲染，并保留公式序号到 DOM 节点的映射。

### 上下标方向验证

对每个含上下标的公式：

- 记录原始 DOM 中的方向（`<msub>` / `<msup>` / vlist 结构）
- 对比输出中的 `_` / `^`
- 方向不一致 → 阻断
