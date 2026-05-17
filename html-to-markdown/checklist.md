# 验证 Checklist 与输出报告

## 自动结构检查（强制量化对比）

### 基线建立（提取前）

在提取内容之前，必须通过 DOM 查询建立原始 HTML 的结构基线计数。查询时**必须在整个主体容器中搜索**（`querySelectorAll`），不能仅遍历直接子节点——因为内容块可能嵌套在无标记容器（simplebar wrapper、layout div 等）中。

### 强制计数对比表（提取后）

| 检查项 | DOM 查询方式 | HTML 基线 | Markdown 实际 | 差异 | 阻断? |
|--------|-------------|-----------|---------------|------|-------|
| 块级公式 | `[data-slate-type="block-katex"]` 或 `.katex-display` | N | M | N-M | **差异>0 阻断** |
| 行内公式 | `[data-slate-type="inline-katex"]` 或 `.katex:not(.katex-display *)` | N | M | N-M | 差异>2 警告 |
| 有序列表容器 | 见有序列表判定规则 | N | M | N-M | **差异>0 阻断** |
| 无序列表容器 | 列表总数 - 有序列表数 | N | M | N-M | 差异>0 警告 |
| 列表项（总计） | `li` 或 `[data-slate-type="list-line"]` | N | M | N-M | **差异>0 阻断** |
| 有序列表项 | 有序列表容器内的 list-line 数量 | N | M | N-M | **差异>0 阻断** |
| 无序列表项 | 无序列表容器内的 list-line 数量 | N | M | N-M | **差异>0 阻断** |
| 图片 | `img`（排除装饰图后） | N | M | N-M | **差异>0 阻断** |
| 代码块 | `[data-slate-type="code-block"]` 或 `pre > code` | N | M | N-M | **差异>0 阻断** |
| 标题 | `h1-h6` 或 heading slate types | N | M | N-M | 差异>0 警告 |
| 段落 | paragraph slate types 或 `<p>` | N | M | N-M | 差异>3 警告 |
| 评论 | 评论容器内评论节点 | N | M | N-M | 差异>0 警告 |

**阻断项差异>0 时，必须逐一定位丢失的元素并修复或标注人工复核，不得继续输出。**

**Markdown 计数注意事项：**
- 计数必须**排除评论区和代码块内部**——评论中的 `- ` 开头行或代码块输出中的 `1. ` 编号不是正文列表项
- 列表项正则应精确匹配行首 `^(?:- |\d+\. )`，而非宽泛的 `^[-\d]+[.)]\s`
- 如果段落内容恰好以列表标记开头（如引用的 AI 输出 `1. **Go 版本检查**：...`），会导致计数偏高——这是**误报**，不影响转换质量，但需要人工确认

### 有序列表判定规则

`data-code-line-number` 属性可能出现在以下位置（按优先级）：
1. `list-line` 元素自身
2. `list-line` 的**直接子 div**（极客时间/Slate 常见模式）
3. `list-line` 子树中的任意后代节点

判定方法：
```text
对每个 list 容器：
  遍历其 list-line 子节点
    对每个 list-line，执行 querySelector('[data-code-line-number]')
    如果找到 → 记录编号值
    如果全部 list-line 都有连续编号 → 有序列表
  同时检查 CSS 规则：
    遍历 document.styleSheets 查找 content: attr(data-code-line-number)"."
    如果该 CSS class 出现在当前 list-line 的 class 列表中 → 有序列表
```

### 原有检查项（仍需执行）

| 检查项 | 说明 |
|--------|------|
| 嵌套列表数量/最大层级 | 不能被压平 |
| CSS marker 类型 | `::before` / `::after` 生成的编号或 bullet |
| 表格数量 | |
| 原始 LaTeX 数量 | annotation / data-tex 等 |
| 上下标方向一致性 | 逐个公式检查 |
| 加粗/强调 | 不能丢失 |
| 链接数量 | 关键链接保留 |
| 居中块数量 | 公式块/图片/图表/图注 |

## 专项检查清单

### 评论区专项
- 原 HTML 是否存在评论区
- **HTML 中顶层评论容器数量**（不是所有含 "Comment" 的元素数量）
- Markdown 中评论数量是否与顶层容器数量一致（多了=碎片化，少了=丢失）
- 作者/讲师/官方回复数量
- 评论中代码/日志/公式/图片/链接
- 回复是否独立成块（`#### 回复`）
- 训练日志是否 fenced code block
- **碎片化扫描**：是否存在只有日期/只有用户名/只有归属地的独立"评论"

### 评论排版专项
- 不得出现 `**回复：** 作者回复：...`
- 回复必须用 blockquote 格式（`>` 前缀），使其与评论正文在视觉上明确区分
- 多回复拆成多个 blockquote 块
- 评论 `# 注释` 不误渲染为标题
- 连续训练日志为 fenced code block

### 列表结构专项
- 有序/无序/嵌套列表数量对比
- `data-code-line-number` + CSS 证据
- CSS bullet marker 类型
- 双 marker 扫描
- 代码块行号不误作列表

### 列表 marker 专项
对每个富文本伪列表记录：父节点类型、列表项数量、marker 来源、原始值、是否连续、判定结果、Markdown 输出 marker、是否双 marker、是否需要人工复核

### 公式异常扫描
扫描 `\{\|\|` / `⎧` / `\approxrt` / `\gammaV` / `\sumk` / `\deltat` / `theta -` / `maxa` / `\pi\theta` / `\\mathcal` / `\\theta` / `\simp` / `\simq` / `\sim[a-z]` / `^'` / `^^` / `ϵ` 等

### 公式结构语义专项
检查 `\frac` / `_` / `^` / `msub` / `msup` / `\sum` / `\max` / `e^{...}` / `\mathcal` / `\mathbb` / cases / matrix / sqrt / 嵌套上下标

### LaTeX 命令转义专项
- 行内公式中 `\\[A-Za-z]+` → 一律阻断
- 块级公式中 `\\[A-Za-z]+` → 复核（多行换行 `\\` 除外）

### 上下标方向专项
对每个公式：原始源码、Markdown 源码、原始下/上标 token、Markdown 下/上标 token、方向一致性、修复方式

### 块级居中专项
对每个可能居中的块级元素：

```text
块序号 / 元素类型（公式块/图片/图表/图注/短句/署名）
原始居中证据 / 是否居中
Markdown 输出方式 / 渲染是否居中
是否原文居中但输出靠左 / 是否需要人工复核
```

### Markdown 渲染错误文本检查
渲染 → 读取 innerText → 扫描 ParseError / Double subscript / mathcalN / mathbbE 等

### 图片路径检查
相对路径 / 指向 `files/<zip-同名>/` / 文件存在 / 无无关图片 / 图注紧跟图片 / 顺序一致 / 居中图片保留居中

### 代码块检查
- 疑似代码/日志/命令/配置/堆栈/训练日志是否裸露在普通段落（含评论区）
- 代码块是否标注了语言（如 ```` ```python ````）——富文本编辑器通常不提供 `language-*` class，需通过内容启发式检测

## Playwright 渲染验证（强制，不可跳过）

Playwright MCP 始终可用。此步骤是**强制的，不得以任何理由跳过**。

### Step 1: 程序化 KaTeX 错误检测

1. 创建 `render.html` 验证页面（KaTeX CDN + marked.js，通过 `?file=` 加载 Markdown）
2. 用 Playwright 打开渲染页面
3. 执行 `document.querySelectorAll('.katex-error').length`
4. **目标：0 error**
5. 若 > 0，获取每个错误公式的 `.textContent`，定位 Markdown 源码中对应位置，修复后重新验证
6. 常见错误模式与修复：
   - `Undefined control sequence: \simp` → `\sim p`（`\sim` 后缺空格）
   - `Undefined control sequence: \simq` → `\sim q`
   - `Expected group after '^'` → `^'` 应改为 `'`（prime 记号）
   - `Double subscript` → 补分组 `_{...}`
   - `Undefined control sequence: \gammaV` → `\gamma V`（命令后缺空格）

### Step 1.5: 渲染后公式数量验证（紧随 error 检查之后）

1. 执行 `document.querySelectorAll('.katex').length` 统计实际渲染的公式数量
2. 与 DOM 基线 `N_formula_block + N_formula_inline` 对比
3. **如果渲染后公式数量显著少于基线 → 阻断**
4. 此类缺失不会产生 `.katex-error`——KaTeX 根本没处理到这些公式（`$` 分界符被 Markdown 解析器破坏），只能通过数量对比发现

**常见根因：**
- Markdown 解析器（如 marked.js）将公式内的 `_` 解析为 `<em>`、`|` 解析为表格分隔符，导致 `$...$` 边界被破坏。render.html 必须在调用 `marked.parse()` 前保护数学公式块（占位符替换）。
- **`$$` 配对错位（级联失败）：** Markdown 中存在一个多余的 lone `$$`（如空 block-katex 产物）会导致后续所有 `$$` 配对移位。症状：Playwright 报告多个 katex-error，错误内容包含大段中文正文和 Markdown 标题——这说明整段文本被吞入了公式区间。修复方法：搜索 Markdown 中 prev 和 next 都为空行的 lone `$$`，删除后重新验证。

### Step 2: 截图对比

1. 分别打开原 HTML 和 Markdown 渲染 HTML
2. 对比：标题、正文顺序、段落、列表编号/bullet/嵌套、图片位置/图注、代码块、表格、公式渲染/数学含义/上下标方向、加粗/斜体、评论区保留与排版、UI 噪声、块级居中
3. 整页截图：原 HTML 主体 + Markdown 主体
4. 评论区截图：原 HTML + Markdown
5. **高风险区域必须逐一截图**：每个块级公式、inline 公式密集段、有序列表（验证编号）、**无序列表（验证 bullet 数量与列表项是否被合并成段落）**、代码块前后上下文、居中块
6. 视觉语义对比（不做像素匹配）
7. **列表区域重点关注**：列表项被合并成段落在全页截图中不易发现（文字内容仍在，只是结构丢失），必须对列表区域做局部截图并逐项对比

## 修复循环

发现问题 → 只修改局部 → 重新渲染检查 → 必要时重新截图 → 直到无结构性错误或标注人工复核

---

## 最终输出报告模板

根据复杂度分级（见 SKILL.md §0）选择对应模板。

### 通用部分（所有级别必填）

```text
复杂度级别：Level [1/2/3]
是否识别到正文：
保留资源文件数量：
其中正文图片数量：
其中评论图片数量：
是否识别到评论区：
评论数量（DOM 基线 / Markdown 实际）：
保留有价值评论数量：
删除无价值评论数量：
保留作者/讲师/官方回复数量：
是否发现评论排版问题（内联回复/日志未 code block）：
是否已修复：
列表项数量（DOM 基线 / Markdown 实际）：
代码块数量（DOM 基线 / Markdown 实际）：
标题数量（DOM 基线 / Markdown 实际）：
图片数量（DOM 基线 / Markdown 实际）：
是否处理并保留加粗、斜体、强调、高亮：
是否进行了浏览器渲染核对（截图对比）：
核对后是否发现差异：
发现的差异是否已经修正：
是否还有需要人工复核的内容：
```

### 公式部分（Level 2-3 追加）

```text
公式总数（块级 / 行内）：
公式来源：[annotation / data-tex / MathML / KaTeX HTML 重建 / 截图]
成功提取原始 LaTeX 数量：
KaTeX 渲染错误数量（.katex-error / mstyle[mathcolor]）：
渲染后公式数量 vs DOM 基线：
是否发现公式语义退化（上下标摊平/分式丢失/命令裸露）：
是否发现上下标方向反转：
是否发现 LaTeX 命令双反斜杠转义：
是否已修复所有公式问题：
是否存在需要人工复核的公式：
```

### 居中部分（有居中块时追加）

```text
原 HTML 居中块数量：
是否发现原文居中但 Markdown 靠左：
是否已修复居中丢失问题：
```

### 批量处理汇总表（同源多文件时使用）

```text
| 序号 | 文件名 | 标题 | 图片 | 代码块 | 列表项 | 评论 | 公式 | 问题 |
|------|--------|------|------|--------|--------|------|------|------|
| 1    | ...    | ...  | N/M  | N/M    | N/M    | N/M  | N/M  | 无/描述 |
```
