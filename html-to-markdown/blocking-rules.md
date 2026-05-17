# 阻断规则详细参考

输出 `.zip` 前，必须执行以下阻断检查。任何一项命中都必须修复或标注人工复核。

> **公式相关阻断规则**（源码异常 §0.2、语义退化 §0.3、提取策略 §0.4）已移至 `formula-extraction` skill。本文档仅保留非公式部分的阻断规则。

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

提取完成后，必须将 DOM 基线计数与 Markdown 输出做逐项对比。计数对比表必须包含在工作过程中，任何差异 > 0 的阻断项必须修复。

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

**有序/无序列表项计数阻断（marker 类型退化检测）：**

截图对比无法可靠发现 marker 类型退化（有序→无序或反向）。必须通过程序化计数检测。

在 DOM 审计阶段，对每个列表容器调用有序列表判定逻辑，将其中的列表项分别计入 `dom_ordered_items` 和 `dom_unordered_items`。Markdown 侧同样分别统计 `^\d+\.\s` 和 `^[-*]\s` 行数。

**阻断条件：**
- `dom_ordered_items != md_ordered_items` → **阻断**
- `dom_unordered_items != md_unordered_items` → **阻断**

---

## §0.6 评论区保留阻断

存在评论区线索时，不得默认删除。

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

出现以下模式时阻断：
- 连续评论中出现只有日期的条目
- 连续评论中出现只有用户名的条目
- 评论正文完全重复用户名
- 评论正文 < 3 个字符

**常见根因：** 匹配了评论内部子元素而非顶层容器。

### §0.6.2 评论结构完整性

每条 Markdown 评论必须包含：
1. 用户名（如果原始 HTML 中有）
2. 评论正文
3. 时间（如果原始 HTML 中有）

作者/讲师回复必须使用 blockquote 格式紧跟对应评论下方。

---

## §0.7 评论排版阻断

- 不得出现 `**回复：** 作者回复：...`
- 每条回复必须用 blockquote（`>` 前缀）格式
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

1. **KaTeX 程序化验证**：用 Playwright 加载渲染页面，执行 `document.querySelectorAll('.katex-error').length === 0`。任何 > 0 阻断。**同时必须检测 `document.querySelectorAll('mstyle[mathcolor="#cc0000"]').length === 0`**。
2. **渲染后公式数量验证**：执行 `document.querySelectorAll('.katex').length`，与 DOM 基线对比。渲染数量显著低于基线 → 阻断。
3. **截图对比**：原 HTML vs Markdown 渲染的整页截图 + 高风险区域局部截图。
4. 核对失败 → 最终说明必须写失败。

**render.html 验证页面要求：**
- 引入 CDN KaTeX + marked.js
- 通过 `?file=` 参数加载 Markdown 文件
- **必须在 Markdown 解析前保护数学公式**（占位符替换）
- 页面自动渲染所有 `$...$`（行内）和 `$$...$$`（块级）

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
→ Markdown 下标 / Markdown 上标 / 方向是否一致
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

**居中证据：** `text-align:center` / `align="center"` / `display:flex; justify-content:center` / `margin:auto` / `.katex-display` / `data-slate-type="block-katex"` / 截图

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
