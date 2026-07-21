# 验证 Checklist 与输出报告

本 checklist 供主 agent 在 sub agent 返回结果后执行最终质量验证。

## 自动结构检查（强制量化对比）

### 基线建立（提取前）

在提取内容之前，必须通过 DOM 查询建立原始 HTML 的结构基线计数。查询时**必须在整个主体容器中搜索**（`querySelectorAll`），不能仅遍历直接子节点。

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

**阻断项差异>0 时，必须逐一定位丢失的元素并修复或标注人工复核。**

**Markdown 计数注意事项：**
- 计数必须**排除评论区和代码块内部**——所有 grep 验证脚本必须先剥离 fenced code block：
  ```python
  no_code = re.sub(r'```.*?\n.*?```', '', text, flags=re.DOTALL)
  ```
  否则代码注释 `# foo` 会被当作 H1 命中，得到虚高的标题计数。
- 列表项正则应精确匹配行首 `^(?:- |\d+\. )`
- 段落内容恰好以列表标记开头时为误报，需人工确认

### 有序列表判定规则

`data-code-line-number` 属性可能出现在以下位置：
1. `list-line` 元素自身
2. `list-line` 的直接子 div
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
    如果该 CSS class 出现在当前 list-line 子树中 → 有序列表
```

**注意：** 有序证据（属性和 CSS class）可能在列表项的子元素上而非列表项本身。判定时须搜索子树。

---

## 专项检查清单

### 评论区专项
- 原 HTML 是否存在评论区
- HTML 中顶层评论容器数量
- Markdown 中评论数量是否与顶层容器数量一致
- 作者/讲师/官方回复数量
- 评论中代码/日志/公式/图片/链接
- 回复是否 blockquote 格式
- 训练日志是否 fenced code block
- 碎片化扫描：是否存在只有日期/只有用户名/只有归属地的独立"评论"

### 评论排版专项
- 不得出现 `**回复：** 作者回复：...`
- 回复必须用 blockquote 格式（`>` 前缀）
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

### 公式验证专项（引用 formula-extraction skill）
- KaTeX 程序化错误检测（`.katex-error` + `mstyle[mathcolor]` 均为 0）
- 渲染后公式数量 vs DOM 基线
- 公式源码异常扫描（见 formula-extraction skill）
- 语义退化检测（见 formula-extraction skill）
- 上下标方向一致性

### LaTeX 命令转义专项
- 行内公式中 `\\[A-Za-z]+` → 一律阻断
- 块级公式中 `\\[A-Za-z]+` → 复核（多行换行 `\\` 除外）

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
- 代码块是否标注了语言

### Notebook 类专项（仅 notebook 类页面）
详见 @notebook-and-virtualized.md。验证要点：

- **Cell 总数对齐**：DOM cell 容器数 == markdown_count + code_count，差异>0 阻断
- **Code cell 完整性**：每个 code cell 都成功提取代码（无空 cell、无 ⚠️ 标记），任一空 cell 阻断
- **NBSP 残留**：markdown 中不得出现 `\xa0`，否则代码不可执行 → 阻断
- **fence 配对**：3-反引号和 4-反引号分两路统计，各自必须为偶数（奇偶配对校验为准；4-反引号 outer 升级会包住 inner 3-反引号，使总数等式不可解，详见 notebook-and-virtualized.md §3.2 / §5）
- **Output blockquote 渲染**：含 inner ` ``` ` 的 Output 必须用 4-反引号 outer fence，否则会被截断（Playwright 抽查含 inner fence 的 cell：blockquote 内单一 `<pre>` + 末尾文本到位）
- **空 IFrame/img 回填**：从 cell 源代码或 `data-src` 反推 URL；未回填的需在报告标注
- **Output 处理报告**：输出保留数 / 跳过数 / 回填数 三项必须明示

---

## Playwright 渲染验证（强制，不可跳过）

> **主/子分工**：Step 1（`.katex-error`）、Step 1.6（GitHub 边界）主 agent **必须独立复验，不采信 sub agent 自报结论**——实测出现过 sub 报 error=0、主复验 error=1。分工契约见 SKILL.md「主/子 agent 验证分工契约」。主/子共用同一 render.html 模板。

### Step 1: 程序化 KaTeX 错误检测

1. 创建 `render.html` 验证页面（KaTeX CDN + marked.js，通过 `?file=` 加载 Markdown）
2. **render.html 必须在 Markdown 解析前保护数学公式**（占位符替换）
3. 用 Playwright 打开渲染页面
4. 执行 `document.querySelectorAll('.katex-error').length` — 目标 0
5. 执行 `document.querySelectorAll('mstyle[mathcolor="#cc0000"]').length` — 目标 0
6. 若 > 0，获取错误公式 `.textContent`，定位修复

### Step 1.5: 渲染后公式数量验证

1. 执行 `document.querySelectorAll('.katex').length`
2. 与 DOM 基线 `N_formula_block + N_formula_inline` 对比
3. 渲染数量显著少于基线 → 阻断（`$` 分界符被 Markdown 解析器破坏）

### Step 1.6: GitHub GFM 兼容检查（目标平台含 GitHub 时强制）

**本地 KaTeX 比 GitHub（GFM/MathJax）宽松。** GitHub 要求行内 `$...$` 定界符外侧是 ASCII 边界；紧贴中文/全角标点（如 `，$q=1-p$，`）时 GitHub **不渲染**，留字面 `$`，但本地 KaTeX 照渲染 → 验证漏过。

1. 扫描 md（先剥离 fenced code + `$$` 块）：找行内 `$...$` 定界符**外侧紧贴 CJK 汉字或全角标点**的实例。
   - 正则：开界 `([一-鿿　-〿＀-￯])\$(?!\$)`、闭界 `(?<!\$)\$([一-鿿　-〿＀-￯])`
2. 命中 > 0 → 修：在 CJK 与 `$` 之间插一个 **ASCII 空格**（方案 A）→ `， $q=1-p$ ，`。
3. **实测依据**（2026-07）：方案 A（插空格，标准 `$` 语法）GitHub + VS Code 都渲染；方案 B（backtick `` $`...`$ ``）GitHub 渲染但 VS Code 不认，弃用。块级 `$$...$$` 独立成行，不受此限。
4. 有条件时，push 到公开 repo + Playwright 打开 `blob/main/xxx.md` 实地确认渲染（看是否成数学斜体字符而非字面 `$`）。

### Step 2: 截图对比

1. 分别打开原 HTML 和 Markdown 渲染 HTML
2. 整页截图 + 高风险区域局部截图
3. 视觉语义对比（不做像素匹配）
4. **列表区域重点关注**：列表项被合并成段落在全页截图中不易发现

---

## 修复循环

发现问题 → 只修改局部 → 重新渲染检查 → 直到无结构性错误或标注人工复核

---

## 最终输出报告模板

### 通用部分（所有级别必填）

```text
复杂度级别：Level [0/1/2/3]
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
是否发现公式语义退化：
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
