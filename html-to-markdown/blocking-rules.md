# 阻断规则详细参考

输出 `.zip` 前，必须执行以下阻断检查。任何一项命中都必须修复或标注人工复核。

---

## §0.0 DOM 遍历完整性阻断

**此规则优先级最高——在所有内容提取之前执行。**

### §0.0.1 容器嵌套穿透

遍历主体容器的子节点提取内容时，**不得仅检查直接子节点的类型属性**。如果某个直接子节点没有内容类型标记，必须递归搜索其后代中的内容块。

**典型的无标记中间层容器（示例，非穷举）：**
- 滚动容器（`simplebar`、`overflow:auto` wrapper 等）
- 纯 CSS class 的 layout wrapper（无语义 data 属性）
- `<section>` / `<div>` / `<article>` 中间层
- 富文本编辑器的内部包装层

**阻断条件（通用）：**
- 原 HTML 中公式元素数量 > Markdown 中公式数量
- 原 HTML 中代码块元素数量 > Markdown 中代码块数量
- 原 HTML 中图片数量（排除装饰图后）> Markdown 中图片引用数量

**任何内容块数量减少都意味着提取遗漏，必须定位并修复。**

### §0.0.2 强制计数对比

提取完成后，必须将 DOM 基线计数（见 checklist §自动结构检查）与 Markdown 输出做逐项对比。计数对比表必须包含在工作过程中（不需要包含在最终用户报告中），任何差异 > 0 的阻断项必须修复。

---

## §0.1 Markdown 渲染错误阻断

**程序化验证（强制）：** 使用 Playwright 加载包含 KaTeX 的渲染页面，执行 `document.querySelectorAll('.katex-error').length`，结果必须为 **0**。任何 > 0 都必须修复。

渲染 Markdown 为 HTML，读取 `document.body.innerText`。

**渲染文本中不得出现：**

```text
KaTeX parse error
ParseError
Expected group after
Expected 'EOF'
Undefined control sequence
No such environment
MathJax error
Double subscript
Double superscript
```

**渲染文本中不得裸露 LaTeX 命令名：**

```text
mathcalN  mathbbE  mathbb  mathcal  mathrm  operatorname
frac  theta  sigma  gamma  epsilon  pitheta  mutheta  sigmatheta
```

特别注意 `\mathcal{N}` 被错误输出为 `\\mathcal{N}` 导致渲染成 `mathcalN` 的情况。

---

## §0.2 公式源码异常阻断

Markdown 公式源码中不得出现以下异常：

```text
\{\|\|  ⎧  ⎪  ⎨  ⎩  \approxrt  \gammaV  \sumk  \deltat  s□=g  �  γ0  γ1
theta -  \theta -  maxa  max a  sumk  sumt  sum t  g ^  g^
\pi\theta  \mu\theta  \sigma\theta  \sigma\theta2  e\phi  T\theta
d_\pi_\theta  V^\pi_\theta  Q^\pi_\theta  J_\pi_\theta
\\mathcal  \\mathbb  \\mathrm  \\operatorname  \\frac  \\dfrac
\\sum  \\prod  \\max  \\min  \\arg  \\left  \\right  \\begin  \\end
\\pi  \\theta  \\mu  \\sigma  \\alpha  \\gamma  \\epsilon  \\phi
```

**额外规则：**

- `^` 后不能直接结束、不能只跟空格/标点/中文
- `_` 后不能直接结束
- `_` 后又出现未分组的 `_`（如 `d_\pi_\theta`）→ 必须补分组，不能改方向
- `\theta+α` → 改成 `\theta + \alpha`
- `g ^` / `g^` 后无内容 → 可能应为 `\hat{g}`
- Unicode 希腊字母在 LaTeX 公式中优先转 `\alpha` `\gamma` `\theta` `\pi` `\epsilon` `\mu` `\sigma`
- `sum t` / `sumt` → 可能应为 `\sum_t` 或 `\sum_{t=0}^{T-1}`
- `maxa` / `max a` → 可能应为 `\max_a` / `\arg\max_a`
- `\sim` 后紧跟字母（`\simp` / `\simq` / `\simν` 等）→ 缺少空格，应为 `\sim p` / `\sim q` / `\sim \nu`
- `^'` 或 `^{'}` → KaTeX 不接受，应直接用 `'`（prime 记号）
- `^^` → double caret（accent+superscript 叠加），应简化为 `^`
- **行内公式中 `\\[A-Za-z]+` 一律阻断**（除非在 aligned/cases/matrix/split 等多行环境中表示换行）
- 块级公式中 `\\[A-Za-z]+` 也必须复核

---

## §0.3 公式语义退化阻断

即使 Markdown 能正常渲染，以下情况也视为转换失败：

1. 原公式有分式结构 → Markdown 无 `\frac` / `\dfrac`
2. 原公式有上下标 → Markdown 下标/上标被摊平（`\pi_\theta` → `\pi\theta`）
3. 原公式上下标方向反转
4. 原公式有 `e^{...}` → Markdown 变成 `e...` 或普通文本
5. 原公式有 `\sum_{a'}` → Markdown 变成 `\sum a'` / `sum a'`
6. 原公式有 `\max_{...}` / `\arg\max_{...}` → Markdown 变成 `maxa` / `max a`
7. 原公式有 `\mathcal{N}` / `\mathbb{E}` → Markdown 降级成普通 `N` / `E`
8. 原公式有矩阵/分段/根号/分式嵌套 → Markdown 变成一行扁平字符
9. 原公式视觉复杂 → Markdown 只是字母/希腊字母/运算符拼接
10. 嵌套上下标产生 Double subscript（`d_\pi_\theta`、`V^\pi_\theta`）
11. LaTeX 命令被双反斜杠转义导致命令名以普通文本显示

---

## §0.4 KaTeX / MathJax / MathML 公式提取

检测 HTML 中是否存在：`.katex` / `.katex-html` / `.katex-mathml` / `.MathJax` / `annotation[encoding="application/x-tex"]` / `math` / `semantics` / `msub` / `msup` / `msubsup` / `munder` / `mover` / `data-slate-type="block-katex"` / `data-slate-type="inline-katex"` / `data-slate-type="math"`

**提取优先级：**

1. `annotation[encoding="application/x-tex"]`
2. `data-tex` / `data-latex` / `data-math` / `alttext`
3. `<script type="math/tex">`
4. 页面 JSON / hydration 数据
5. 富文本节点附近原始公式字段
6. MathML 结构：`<msub>`=下标, `<msup>`=上标, `<msubsup>`=同时
7. **系统性 KaTeX HTML 重建**（见 §0.4.2）——当上述方式全部不可用时
8. 上述全部不可行 → 截图保存为图片

**不得** 根据领域惯例改变上下标方向。

### §0.4.1 无原始 LaTeX 时的策略选择

当整个页面的 KaTeX 都没有原始 LaTeX（无 annotation、无 data-tex、无 MathML），根据公式数量选择策略：

| 情况 | 策略 |
|------|------|
| 公式数量少（≤10） | 逐个截图保存为图片 |
| 公式数量多（>10） | 编写 KaTeX HTML 解析器，系统性重建（见 §0.4.2） |

**禁止手动逐公式从渲染层拼接。** 要么编写可复用的解析器，要么截图。

### §0.4.2 KaTeX HTML 系统性重建（解析器方案）

当页面无原始 LaTeX 且公式密集时，编写 KaTeX `.katex-html` DOM 解析器是可行的。

**前提条件（全部满足才可使用）：**
1. 编写**可复用的程序化解析器**（Python/JS），非手动逐公式提取
2. 解析器覆盖 KaTeX HTML 的关键结构（见下文参考）
3. 通过 Playwright 渲染验证达到 **0 KaTeX error**
4. 批量处理后执行完整后处理管道（§0.4.3）

**KaTeX HTML 关键结构参考：**

KaTeX 的 HTML 渲染层 CSS 类是 KaTeX 库定义的，与宿主网站无关——任何使用 KaTeX 的网站都使用相同的 `.katex-html` 结构。

```text
结构                 | CSS 类 / 模式                          | 解析要点
---------------------|----------------------------------------|------------------------------------------
普通字符             | .mord (text node)                      | Unicode → LaTeX 映射（θ→\theta 等）
上下标               | .msupsub > .vlist-t / .vlist-t2        | 见下方 vlist 方向规则
分式                 | .mfrac > .vlist                        | top 最小 = 分子, top 最大 = 分母
运算符(无 limits)    | .mop (无 .msupsub 子节点)              | textContent → OP_MAP (max→\max 等)
运算符(有 limits)    | .mop > .msupsub                        | 先提取 op 文本, 再解析 supsub
运算符(op-limits)    | .mop.op-limits > .vlist                | 3部分: sup/op/sub (按 CSS top 排列)
根号                 | .msqrt                                 | \sqrt{内容}
重音                 | .accent > .accent-body + .mord         | ˆ→\hat, ~→\tilde, ¯→\bar, ˙→\dot, →→\vec
上划线               | .overline                              | \overline{内容}
括号 + 上下标        | .mclose/.mopen + .msupsub 子节点       | 必须递归进子节点, 如 (γλ)^l
数学字体             | .mord.mathbb                           | \mathbb{内容}
数学字体(花体)       | .mord.mathcal                          | \mathcal{内容}（如 \mathcal{S}、\mathcal{A}）
文本模式             | .mord.text                             | \text{内容}（如 "with probability"）
矩阵/分段/cases     | .mtable > .col-align-* > .vlist        | 见下方 mtable 解析规则
分段函数包装         | .minner > .mopen + .mtable + .mclose   | 外层 minner 含 { 和 nulldelimiter → \begin{cases}
数组列间距           | .arraycolsep                           | 忽略（纯间距）
空分隔符             | .mclose.nulldelimiter                  | 忽略（cases 右侧不可见分隔符）
空格                 | .mspace                                | 空格
忽略                 | .strut / .vlist-s / .frac-line / .rule | 渲染辅助, 无语义
```

**mtable 解析规则（cases / array 环境）：**

```text
.mtable 结构:
  .col-align-l / .col-align-r / .col-align-c  (每个对应一列)
    .vlist-t > .vlist-r > .vlist > span[style="top:..."]  (每个 span 对应一行)
      .mord  (行内容)

识别 cases 环境:
  .minner 的直接子节点中:
    - .mopen.delimcenter 文本为 "{"
    - .mclose.nulldelimiter（右侧无可见分隔符）
  满足条件 → \begin{cases} ... \end{cases}
  否则 → \begin{array}{} ... \end{array}

注意: 检测 .mopen / .mclose 时必须用 recursive=False，
  否则会命中 mtable 内部行中的 ( ) 等括号。

行内 \text{} 后紧跟数字/变量时需要空格:
  \text{with probability}1 → 渲染时 "probability" 和 "1" 会粘连
  建议: \text{内容 } 或 \text{内容}~
```

**vlist 方向规则（核心，方向错误导致上下标反转）：**

```text
.vlist-t2 + 1个 content span → 下标 (subscript)
.vlist-t (非 t2) + 1个 content span → 上标 (superscript)
任何 vlist + 2个 content spans → 按 CSS top 排序:
  top 值最小(最负) = 上标
  top 值最大(最正) = 下标
```

**op-limits 结构（如 \sum_{i=1}^{N}, \max_{\theta'}）：**

```text
.mop.op-limits 内的 .vlist 可能有 2 或 3 个 content span:
  3 个 span (按 top 排序): 上标, 运算符本体, 下标
  2 个 span (按 top 排序): 运算符本体, 下标
注意: _pc(span) 返回的可能已经是 LaTeX 命令（如 \max），
  需先查 SYM_MAP/OP_MAP, 无匹配则直接使用
```

### §0.4.3 KaTeX 重建后处理管道（post-processing）

从 KaTeX HTML 重建的 LaTeX 必须经过以下后处理修正，否则会导致 KaTeX 渲染错误：

| 问题 | 模式 | 修正 | 原因 |
|------|------|------|------|
| Prime 记号 | `^'` 或 `^{'}` | `'` | KaTeX 不接受 `^'` 语法 |
| Double caret | `^^` | `^` | accent(hat) + superscript 叠加 |
| `\sim` 后粘连 | `\simp`, `\simq`, `\simν` | `\sim p`, `\sim q`, `\sim \nu` | \sim 后紧跟字母会被解析为未定义命令 |
| Unicode ϵ | `ϵ` (U+03F5) | `\epsilon` | KaTeX 不识别此 Unicode |
| Unicode ∗ | `∗` (U+2217) | `*` | |
| Unicode ∥ | `∥` (U+2225) | `\|` | |
| Unicode 上标序列 | `⁻¹`, `²`, `ⁿ` 等 | `^{-1}`, `^{2}`, `^{n}` | KaTeX HTML 有时用 Unicode 上标字符（U+207x, U+00Bx）代替 msupsub 结构 |
| Unicode 下标序列 | `₀`, `₁`, `ₙ` 等 | `_{0}`, `_{1}`, `_{n}` | 同上，Unicode 下标字符（U+208x） |
| NBSP | `\xa0` (U+00A0) | 普通空格 | KaTeX 对 NBSP 发出 unknownSymbol warning |
| LaTeX 命令粘连 | `\gammaV`, `\thetax` | `\gamma V`, `\theta x` | 命令后紧跟字母会被当作命令名的一部分 |
| `\text{}` 后粘连 | `\text{with probability}1` | `\text{with probability} 1` | 文本模式后紧跟数字/变量视觉上会粘连 |
| `\mid` 间距 | `\mid` 后无空格 | `\mid ` | 条件概率分隔符需要空格 |
| `\mid` vs `\vert` | `\mid` 含 `\|` 字符 | `\vert` | Markdown 解析器可能把 `\|` 当表格分隔符，`\vert` 更安全 |
| PUA 字符 | U+E000-U+F8FF | 删除 | SingleFile 保留的 Private Use Area 字符对人不可见但导致 KaTeX 报 "Unexpected character" |
| Prime inside `\frac` | `\frac{f'}(1)}{2}` | `\frac{f'(1)}{2}` | prime cleanup 把 `'` 移出 `{}` 导致大括号不平衡 |
| 空 block-katex | `$$\n$$` 或 lone `$$` | 删除 | KaTeX HTML 解析返回空字符串时，产生的空 `$$` 块会造成后续所有 `$$` 配对错位 |
| Zero-width spaces | U+200B, U+FEFF, U+200D, U+200C | 删除 | 原始 HTML 中的零宽字符嵌入公式或 `$` 分界符附近，干扰正则匹配 |

**`\sim` 后粘连修正的完整规则：** `\sim` 后紧跟任何字母（包括 a-z, A-Z 和 Unicode 希腊字母）都必须插入空格。regex: `\\sim([a-zA-Zα-ωΑ-Ω])` → `\\sim \1`（其中希腊字母还需转换为 LaTeX 命令）。

**LaTeX 命令粘连的系统性修正：** 解析器拼接 LaTeX parts 时，必须检测前一部分是否以 `\command` 结尾（regex: `\\[a-zA-Z]+$`）且后一部分以字母开头——若是则插入空格。这是最高频的静默错误来源（`\theta` + `J` → `\thetaJ`，`\gamma` + `V` → `\gammaV` 等），逐个修正不可靠，必须在 join 阶段统一处理。

**空 block-katex 防护：** block-katex 处理函数返回 `$$...$$` 前必须检查 latex 内容是否为空。一个多余的 `$$` 会导致后续所有块级公式分界符错位，产生级联失败——单个 stray `$$` 可引发 7+ 个渲染错误，因为整段文本被吞入"公式"中。最终 cleanup 也应移除空 `$$` 块。

**残留 `$$` 文本段落防护：** 部分 Slate 编辑器页面中，块级公式（尤其是无 `data-slate-type` 的 wrapper div 模式）后面紧跟一个 `paragraph` 节点，内容仅为字面字符串 `$$`（KaTeX 渲染前的残留标记）。必须在 paragraph 处理中过滤掉纯 `$$` 段落——效果与空 block-katex 完全相同：一个多余的 `$$` 行导致级联配对错位。

**这些后处理规则必须在解析器输出后统一应用，不得遗漏。**

---

## §0.5 列表结构阻断

**通用规则（适用于所有 HTML 来源）：**

1. 没有明确编号证据 → 不得输出有序列表
2. CSS 圆点/短横线/黑点/bullet → 必须输出无序列表
3. 不允许仅根据"内容像步骤"把 bullet 改成 `1. 2. 3.`
4. 原文视觉 bullet → Markdown 有序列表 = 结构错误
5. 原文视觉有序编号 → Markdown bullet = 结构错误
6. 自动检查发现"HTML 有序 → Markdown bullet"→ 阻断

**有序列表判定证据（任一满足即可）：**
- 标准 `<ol>` 标签
- `data-list-type="ordered"` 或等价属性
- CSS `counter(...)` + 连续数字编号
- CSS `content: attr(...)` + 连续数字编号
- `::before` / `::after` 伪元素渲染出连续数字

**无序列表判定证据：**
- 标准 `<ul>` 标签
- CSS `content:"•"` / `"-"` / `"·"` / `"●"` 等 bullet marker
- 无法确认类型 → 默认无序

**Marker 提取通用算法：**

```text
① 找到 list 容器（ol/ul / role="list" / 富文本特定标记）
② 找到 list item（li / role="listitem" / 富文本特定标记）
③ 对每个 list item，搜索子树中的编号属性或 CSS marker
④ 拆分 marker 区域和正文区域
⑤ 读取 marker 类型
⑥ 生成 Markdown，正文去掉原始 marker
⑦ 源码扫描双 marker
```

**Slate 编辑器列表模式（极客时间等）：**

| 列表容器 | 列表项 | 有序编号证据 |
|----------|--------|-------------|
| `data-slate-type="list"` | `data-slate-type="list-line"` | 子 div 上的 `data-code-line-number` + CSS `content:attr(...)` |

遇到未见过的富文本列表结构时，用 Playwright 截图看视觉效果，再决定有序/无序。

**有序/无序列表项计数阻断（marker 类型退化检测）：**

截图对比无法可靠发现 marker 类型退化（有序→无序或反向），因为视觉差异仅为单字符（`1.` vs `-`），内容和布局完全相同。必须通过程序化计数检测。

在 DOM 审计阶段，对每个列表容器调用有序列表判定逻辑，将其中的列表项分别计入 `dom_ordered_items` 和 `dom_unordered_items`。Markdown 侧同样分别统计 `^\d+\.\s` 和 `^[-*]\s` 行数。

**阻断条件：**
- `dom_ordered_items != md_ordered_items` → **阻断**（有序列表项数量不匹配，可能有序→无序退化）
- `dom_unordered_items != md_unordered_items` → **阻断**（无序列表项数量不匹配，可能无序→有序误判）

**注意：** 仅统计列表项总数不足以发现此问题——如果一个有序列表被错误输出为无序列表，总数仍然相等，但有序/无序的分类计数会不一致。

---

## §0.6 评论区保留阻断

存在评论区线索（`comment` / `reply` / `discussion` / `评论` / `回复` / `精选留言` / `作者回复` / `讲师回复` 等）时，不得默认删除。

**阻断错误：**

1. HTML 有评论区 → Markdown 无评论且无说明
2. 作者/讲师/官方/编辑回复被删除
3. 对正文的提问/纠错被删除
4. 长评论/代码评论/报错评论/实践经验被删除
5. 因 UI 噪声就整体删除评论区
6. 无法判断价值时直接删除，未标注人工复核
7. 评论中代码/日志被误渲染为普通段落或标题
8. 回复与原评论挤在同一段
9. 训练 log / Episode/Score/Loss 被挤成普通长段落

### §0.6.1 评论数量一致性阻断

**评论数量必须与 HTML 中的评论条目一一对应。**

**阻断条件：**
- Markdown 中评论数量 > HTML 中顶层评论容器数量 → **评论被错误拆分**（碎片化）
- Markdown 中评论数量 < HTML 中顶层评论容器数量 → 评论丢失

**评论碎片化检测（Markdown 源码扫描）：**

出现以下模式时阻断，因为它们通常是一条评论被拆成多条的症状：
- 连续评论中出现只有日期的条目
- 连续评论中出现只有用户名的条目
- 评论正文完全重复用户名
- 评论正文 < 3 个字符（日期、地理位置、UI 残留）

**常见根因与修复：**

提取评论时，必须只匹配**顶层评论容器**——包含完整用户名+正文+时间的外层 wrapper。不能用 `[class*="Comment"]` 之类的宽泛 CSS 选择器——它会同时命中评论内部的子元素（用户名 div、正文 div、时间 span），把一条评论拆成 N 条。

**正确方法：** 先用 Playwright/DOM 检查确定评论的**顶层容器**的 class pattern（通常含 `wrapper`、`item`、`entry` 等），再只选择该层级。

遇到未知评论结构时，先用 Playwright 截图确认评论区外观，再用 DOM inspector 定位顶层容器。

### §0.6.2 评论结构完整性

每条 Markdown 评论必须包含：
1. 用户名（如果原始 HTML 中有）
2. 评论正文
3. 时间（如果原始 HTML 中有，放在用户名后括号内）

作者/讲师回复必须使用 blockquote 格式（`>` 前缀）紧跟在对应评论下方，不能作为独立评论。blockquote 比 `#### 回复` 在视觉上更明显地与评论正文区分开。

---

## §0.7 评论排版阻断

- 不得出现 `**回复：** 作者回复：...`
- 每条回复必须用 blockquote（`>` 前缀）格式，`> **作者回复**` 开头
- 多个回复必须拆成多个 blockquote 块
- 评论中 `# 注释` / `Traceback` / `Error` / `Episode` / `Loss` / `Score` 等 → 代码/日志上下文
- 连续训练日志 → fenced code block + 保留换行

---

## §0.8 图片和 ZIP 阻断

- 图片路径必须是相对路径，指向 `files/<zip 同名>/`
- 资源文件必须真实存在
- ZIP 解压后必须能离线阅读
- 不得把 base64 直接写进 Markdown
- 不得误保留头像/Logo/广告图/二维码
- 有价值评论中的说明图片/截图应保留

---

## §0.9 Playwright 渲染验证阻断

**Playwright MCP 始终可用，不存在"无浏览器"的借口。** 以下验证步骤为强制阻断项：

1. **KaTeX 程序化验证**：用 Playwright 加载渲染页面，执行 `document.querySelectorAll('.katex-error').length === 0`。任何 > 0 阻断。**同时必须检测 `document.querySelectorAll('mstyle[mathcolor="#cc0000"]').length === 0`**——当 `throwOnError: false` 时，部分解析错误不产生 `.katex-error` 元素，而是用红色 `<mstyle>` 内联渲染（如 `\gammaV` 被拆成 `\gamm` + 红色 `a`）。只查 `.katex-error` 会漏掉这类静默错误。
2. **渲染后公式数量验证**：执行 `document.querySelectorAll('.katex').length`，与 DOM 基线 `N_formula_block + N_formula_inline` 对比。**渲染数量显著低于基线 → 阻断**（意味着部分公式的 `$` 分界符被 Markdown 解析器破坏，KaTeX 未能处理到）。注意：0 error + 公式数量不足 = 静默丢失，比 error > 0 更危险。
3. **截图对比**：原 HTML vs Markdown 渲染的整页截图 + 高风险区域局部截图。
4. 核对失败 → 最终说明必须写失败，不得声称"已完成核对"。

**render.html 验证页面模板：**

创建一个 HTML 页面，引入 CDN KaTeX + marked.js，通过 `?file=` query 加载 Markdown 文件。页面自动渲染所有 `$...$`（行内）和 `$$...$$`（块级）公式。失败的公式自动添加 `.katex-error` class（红色边框），便于程序化统计。

---

## §0.10 列表源码形态阻断

Markdown 源码中不得出现：

```text
-- 列表项
- - 列表项
* * 列表项
+ + 列表项
- 1. 列表项
1. - 列表项
1. 1. 列表项
```

---

## §0.11 上下标方向一致性阻断

对每个公式建立对应关系：

```text
公式序号 / 原始来源 / 原始下标 / 原始上标 / msub / msup / msubsup
→ Markdown 下标 / Markdown 上标 / 方向是否一致 / 是否需要人工复核
```

**阻断：**

1. 原始 `_` → Markdown 变 `^`
2. 原始 `^` → Markdown 变 `_`
3. MathML `<msub>` → 上标
4. MathML `<msup>` → 下标
5. 为避免 Double subscript 改变方向但无原始证据
6. 根据领域惯例改变 `V_\pi` ↔ `V^\pi`

---

## §0.12 块级居中元素保真阻断

**居中证据：** `text-align:center` / `align="center"` / CSS class 含 `text-align:center` / `display:flex; justify-content:center` / `margin:auto` / `.katex-display` / `data-slate-type="block-katex"` / 截图

**阻断：**

1. 原网页公式块居中 → Markdown 靠左
2. 原网页图片/图表居中 → Markdown 靠左
3. 原网页图注居中 → Markdown 靠左
4. 原网页独立短句/署名居中 → Markdown 靠左
5. 块级公式被输出成行内 `$...$` 导致靠左
6. 只提取公式源码丢弃外层居中样式
7. Markdown 渲染器 `$$...$$` 不默认居中时未用 HTML wrapper

**修复方式：**

```markdown
<div align="center">

$$
公式内容
$$

</div>
```
