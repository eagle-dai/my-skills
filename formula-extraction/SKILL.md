---
name: formula-extraction
description: Extract and validate LaTeX from KaTeX, MathJax, or MathML formula DOM. Use for either one formula node or a page-level formula batch. Single-node work returns structured success/failure; the html-to-markdown batch integration deduplicates, caches, and validates supported sources. Do not claim a source type is supported by the deterministic fast path unless formula_batch.py implements it.
---

# 公式提取（Formula Extraction）

从公式 DOM 中恢复语义正确的 LaTeX。既支持分析单个公式节点，也支持由页面转换流程批量解析多个公式。

> **改这个 skill 本身？** 先读 `../_meta/skill-self-improvement.md` 和 @self-improvement.md。可确定的规则必须与可执行实现和测试一致；不得把设计目标写成已经落地的能力。

## 两种执行模式

### 单节点模式

- **输入**：一个公式 DOM 节点，以及调用方可选提供的页面上下文。
- **输出**：LaTeX 成功结果，或包含原因和诊断信息的结构化失败结果。
- **不负责**：在整页中定位公式节点、决定 block/inline 定界符、处理上下文正文。
- 页面 hydration JSON、Slate 邻近字段等不在节点内部的证据，只有调用方显式提供页面上下文时才能使用。

### 批量模式

`html-to-markdown` 的确定性路径调用 `html-to-markdown/formula_batch.py::resolve_formulas()`：

- 输入 compact HTML 和按 DOM 顺序排列的 FormulaRecord；
- 按 `dom_hash` 去重；
- 缓存解析结果，但缓存不代表已经通过浏览器验证；
- 为需要验证的重建结果生成一个批量验证页面；
- 输出 resolved、pending_validation 和 failures，而不是特殊占位字符串。

公式数量阈值、是否编写可复用 parser、是否切换 strict 流程，属于页面级调用方决策，不属于单节点 extractor 自己可判断的信息。

## 当前 fast pipeline 的真实能力边界

以 `html-to-markdown/formula_batch.py` 为权威实现：

- `annotation`、`data-tex`、`data-latex`、`data-math`、`alttext`、`math/tex script` 等由 preflight 写入 `original_latex`，batch resolver 可直接使用；
- `katex-html-only` 由现有 KaTeX HTML parser 重建，并且必须通过匹配的浏览器验证报告后才能解锁；
- `mathml` 会被 preflight 正确识别，但当前 deterministic batch resolver **尚未实现 MathML parser**，必须 fail closed，转 strict 流程或由后续专门实现处理；
- 未知来源必须返回结构化失败，不得退化为 `textContent` 成功结果。

因此，文档中的 MathML 映射表是 strict/manual parser 的实现指南，不表示 fast pipeline 已经支持 MathML 自动转换。

## 核心原则

**公式能渲染不等于公式语义正确。** 只有 DOM、MathML、annotation 或调用方提供的原始字段才能证明结构。

- 上下标方向必须忠实原文；不得把下标改成上标或反向。
- 修复连续下标只能补分组，不能改变方向。
- 缺乏结构证据时保持原样并标记人工复核，不能按领域常识猜公式。
- 未知语义节点必须 fail closed，不能把渲染文字当作完整公式。

## 来源优先级

在可用证据范围内按顺序尝试，成功即停：

1. `annotation[encoding="application/x-tex"]`；
2. `data-tex`、`data-latex`、`data-math`、`alttext`；
3. `<script type="math/tex">`；
4. 调用方显式提供的 hydration JSON 或富文本原始字段；
5. MathML 结构重建；
6. KaTeX HTML 系统性重建，详见 @katex-html-parser.md；
7. 结构证据不足时返回结构化失败，由调用方截图或人工复核。

**禁止手动逐公式从渲染文字拼接。** 要么使用可复用 parser，要么 fail closed。

## MathML strict/manual parser 要点

以下是实现 parser 时的结构映射，不是当前 fast resolver 的能力声明：

| MathML 元素 | LaTeX 结构 |
|---|---|
| `<msub>` | `_{...}` |
| `<msup>` | `^{...}` |
| `<msubsup>` | `_{...}^{...}` |
| `<mfrac>` | `\frac{...}{...}` |
| `<msqrt>` | `\sqrt{...}` |
| `<mroot>` | `\sqrt[n]{...}` |
| `<mover>` / `<munder>` | 根据实际 accent/annotation 结构选择命令 |
| `<mtable>` | 根据结构选择 array、matrix 或 cases；无法确认时失败 |
| `<mrow>` | 递归分组容器 |

## 确定错误与结构警告

### 确定错误

- replacement character、无法解释的占位符；
- 括号或环境不平衡；
- 渲染器确认的 undefined control sequence；
- 命令被双反斜杠转义成普通文本；
- 原结构明确含分式、上下标、根号、矩阵或 limits，而输出对应结构消失。

### 需要结构证据的警告

以下字符串本身可能合法，不得自动改写：

- `\pi\theta`、`\mu\theta` 等相邻符号；
- `V^\pi_\theta`、`Q^\pi_\theta` 等同时含上下标的表达式；
- `sumt`、`maxa`、`e\phi` 等可能是普通变量或乘积的字符串；
- 看起来像命令粘连、但无法证明来自两个独立 parser part 的字符串。

## parser join 边界

命令边界修复只能发生在 parser token/part 的 join 阶段。以下反例都以 parser parts 表示：

```text
parts = ["\sim", "p"]      -> "\sim p"
parts = ["\simeq"]         -> "\simeq"
parts = ["\simneqq"]       -> "\simneqq"
parts = ["\sim", "\nu"]  -> "\sim \nu"
```

**禁止**在最终字符串执行：

```text
\\sim([a-zA-Zα-ωΑ-Ω]) -> \\sim \1
```

该规则会把合法命令 `\simeq`、`\simneqq` 等拆坏。不得在最终 LaTeX 字符串上用宽泛正则拆“命令前缀 + 字母”。

KaTeX HTML 的详细 join、`.mspace`、多 `.base` 和 fail-closed 规则以 @katex-html-parser.md 与 `html-to-markdown/formula_batch.py` 为准。

## 后处理

后处理只能修复有机械证据的问题：

- prime、重复 caret、大括号平衡；
- Unicode 数学字符、NBSP、zero-width/PUA；
- 裸 CJK 的 text-mode 包装；
- GitHub 平台上的数学裸星号；
- `\text{}` 内需要转义的特殊字符；
- 已由 parser part 边界证明的命令分隔。

不得全局执行 `\mid → \vert`。`\mid` 是关系符号，`\vert` 更接近竖线或定界符；替换会改变间距或语义，而且不能解决 Markdown 表格分隔符冲突。不得借 Unicode 映射改变上下标关系。

## 验证

### 单公式验证

1. 使用固定版本渲染器创建最小页面；
2. `.katex-error` 必须为 0；
3. MathML 红色错误节点必须为 0；
4. 捕获 unknown-symbol 与 Unicode-in-math warning；
5. 对照原 DOM 验证上下标、分式、limits、字体和矩阵结构。

### 批量验证

- 保持 source_id、dom_hash、LaTeX 一一对应；
- 验证报告的 schema、parser version、validator version、总数和通过数必须与 pending batch 完全匹配；
- cache hit 仍需满足当前批次的验证要求；
- 任一 mismatch、失败或未完成报告都不能解锁最终公式。

## 参考

- @katex-html-parser.md — KaTeX HTML 重建规则
- @self-improvement.md — 公式回归用例
- `html-to-markdown/formula_batch.py` — 当前确定性 batch resolver
- `html-to-markdown/preflight.py` — source_kind 与 FormulaRecord 生成
