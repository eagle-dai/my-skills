---
name: html-to-markdown
description: Use when converting SingleFile-saved HTML pages into clean offline Markdown packages. Triggers on requests involving SingleFile HTML-to-Markdown conversion. Adopts a sub-agent dispatch model for conversion with main-agent quality verification.
---

# SingleFile HTML 转离线 Markdown 包（调度模式）

将 SingleFile 保存的网页 HTML 转换为结构清晰、可离线阅读的 Markdown 文档包。

**架构：** 主 agent 负责分析、定义审计基线和独立验收；sub agent 负责执行转换。

> **改这个 skill 本身？** 先读 `../_meta/skill-self-improvement.md` + @self-improvement.md。相同规则不得在多个文件中以不同选择器或不同默认行为存在。

## 工作流概览

```text
Phase 1  主 agent：识别页面类型 + 建立 DOM 基线
Phase 2  sub agent：按明确参数执行转换
Phase 3  主 agent：独立计数、渲染和截图验收
Phase 4  修复循环
Phase 5  输出 zip + 报告
```

## Phase 1：初步分析

### 1.1 打开 HTML

用 Playwright 打开 SingleFile HTML，确认页面结构。计数必须基于**渲染后的 DOM**，不能只依赖静态 lxml。

### 1.2 按语义容器探测

富文本编辑器常不用标准标签。探测一律走“语义属性 OR 标准标签”双轨：

| 探测项 | 权威查询 |
|--------|----------|
| 代码块 | `[data-slate-type="pre"]` OR `pre > code` |
| 表格 | `[data-slate-type="table"]` OR `table` |
| 列表 | `[data-slate-type="list"]` OR `ul, ol` |
| 列表项 | `[data-slate-type="list-line"]` OR `li` |
| 公式 | `[data-slate-type*="katex"]` OR `.katex` OR `math` |
| 图片 | `img`（排除装饰图后） |
| 标题 | heading slate type OR `h1-h6` |
| 评论 | 评论区顶层评论容器 |

**不得**在其他文档改用 `[data-slate-type="code-block"]` 作为 Slate 代码块基线；本 skill 的 Slate 映射是 `pre`。

### 1.3 强制 DOM 基线

提取前至少记录：

```text
N_formula_block
N_formula_inline
N_table
N_list
N_list_item
N_image
N_codeblock
N_heading
N_comment
```

表格和代码块均为阻断项：HTML 基线大于 Markdown 实际数量时，必须定位丢失元素。

### 1.4 复杂度分级

| 级别 | 条件 | 公式处理 | 验证深度 |
|------|------|---------|---------|
| Level 0 | 无公式、正文图片、代码块、表格和评论 | 跳过公式流程 | 整页对比 |
| Level 1 | 无公式 | 跳过公式流程 | 整页 + 列表/表格/评论局部 |
| Level 2 | 有公式，有原始 LaTeX | 提取 + 渲染验证 | 整页 + 公式局部 |
| Level 3 | 有公式，无原始 LaTeX | 结构重建或截图 | 整页 + 逐公式局部 |

### 1.5 页面类型分流

| 类型 | 信号 | 追加规则 |
|------|------|---------|
| 文章/博客 | `<article>` / `<main>` / Slate | @conversion-rules.md |
| Notebook | Jupyter/Databricks/Colab/cell 信号 | @notebook-and-virtualized.md |
| 虚拟化容器 | Monaco/CodeMirror/react-virtualized | @notebook-and-virtualized.md |
| lazy-load 空占位 | 空 `src` + `data-src` 等 | @notebook-and-virtualized.md |

类型可叠加。

### 1.6 确定参数

- 正文容器选择器
- 编辑器类型
- 评论区顶层选择器
- 公式类型和来源
- DOM 基线计数
- Notebook 的 cell/output/代码提取参数

## Phase 2：Dispatch Sub Agent

Prompt 必须包含明确参数，不得让 sub agent 重新猜测已确认的选择器。

```text
## 任务
将 [文件路径] 的 SingleFile HTML 转换为离线 Markdown 包。

复杂度：[Level N]
正文容器：[selector]
编辑器：[standard / Slate / other]
DOM 基线：
- formula block / inline:
- tables:
- lists / list items:
- images:
- code blocks:
- headings:
- comments:

## 输出结构
<zip-name>.zip
└── 文章标题/
    ├── 文章标题.md
    └── files/<zip-name>/
```

### 打包

- 使用 Python `zipfile`，不要假设存在 `zip`
- 打包和 `pkill`/清理命令分开执行
- 修改 Markdown 后必须重打 zip
- 重打后读取 zip 内文件验证关键修改，不能只看时间戳

### DOM 提取

- 无语义中间 wrapper 必须递归穿透
- 表格、代码块、列表项计数必须与基线对齐
- Slate 代码块使用 `[data-slate-type="pre"]`
- Slate 表格外层可为 `[data-slate-type="table"]`，内部再找标准 `<table>`

### 列表

- 有序证据来自 `<ol>`、属性、CSS counter 等
- 证据可能在 list item 子树
- 无法确认时默认无序
- 禁止双 marker
- 不得根据内容“像步骤”改变 marker

### 评论

- 不得整体默认删除
- 只匹配顶层评论容器
- 保留技术问题、纠错、作者回复、长评论
- 过滤结果必须进入报告，不能用 Markdown 实际评论数直接等同源评论数

### 图片

- base64 图片保存为相对文件
- 删除头像、广告和纯 UI 装饰图
- 评论说明图使用 `comment_` 前缀
- **默认保留水印和原始像素内容**
- **去站点水印仅在用户明确要求时执行（opt-in）**
- 去水印时必须保留原图副本，记录处理文件和 bbox，并逐图原尺寸验证
- 图片压缩按 @conversion-rules.md；若同时 opt-in 去水印，顺序为“原图备份 → 去水印 → 压缩”

### 代码块

- 无语言 class 时至少两个信号才标为具体语言
- 不确定时标 `text`
- 代码块内部 NBSP 转普通空格

### 解析器

- BeautifulSoup 必须用 `lxml`
- Notebook/虚拟化容器按专属双源协议处理

## 公式处理（Level 2-3）

提取优先级：

1. annotation
2. data-tex/data-latex/data-math/alttext
3. math/tex script
4. hydration JSON
5. MathML
6. KaTeX HTML 系统性重建
7. 失败 → 截图

后处理要求：

- Prime、Unicode、PUA/zero-width 等机械修复
- 命令粘连只在 parser token/part 的 join 边界处理
- `["\sim", "p"]` → `\sim p`
- 单一 token `["\simeq"]` / `["\simneqq"]` 保持不变
- **禁止**在最终字符串上运行 `\\sim([A-Za-z...])` 全局替换
- 上下标方向必须忠实原 DOM
- KaTeX parser 遇到未知语义结构必须 fail-closed，不得以 `textContent` 作为成功结果

权威规则见 `formula-extraction` skill。

## Phase 3：主 agent 独立验收

### 强制计数

| 项目 | 要求 |
|------|------|
| 表格 | HTML 基线 == Markdown 实际；少一个即阻断 |
| 代码块 | 使用与 Phase 1 相同选择器；少一个即阻断 |
| 列表项 | 总数和 marker 类型对齐 |
| 图片 | 排除装饰图后对齐 |
| 块级公式 | 少一个即阻断 |
| 评论 | 使用“保留/过滤/失败 ledger”解释差异 |

所有结构 grep 前必须排除 fenced code block；复杂 fence 按 @notebook-and-virtualized.md。

### Markdown/GitHub 边界

所有 level 均检查：

- 强调定界符紧贴字母/数字/CJK 字符
- 不得把紧贴 CJK 标点误判为违规
- 行内 `$` 紧贴 CJK/全角标点
- 数学段裸 `*`
- PUA、zero-width、代码块 NBSP

### Playwright

1. 使用统一 `render.html`
2. `.katex-error == 0`
3. `mstyle[mathcolor="#cc0000"] == 0`
4. 捕获 KaTeX warning
5. 渲染后公式数与基线对比
6. 整页截图 + 公式、列表、表格、评论等高风险区域局部截图

### 主/子分工

| 验证项 | sub agent | 主 agent |
|--------|:---:|:---:|
| DOM vs Markdown 计数 | 必跑 | 独立抽验 |
| 表格/代码块基线 | 必跑 | **使用同一选择器独立复验** |
| KaTeX error/warning | 必跑 | **独立复验** |
| GitHub 边界 | 必跑 | **独立复验** |
| 图片破坏性处理 | 如 opt-in 执行 | **逐图抽检 + 原图存在性** |
| 截图语义对比 | 高风险区 | 高风险区抽检 |

## Phase 4：修复循环

- 个别问题：主 agent 局部修复
- 系统性问题：重新 dispatch，并明确失败计数、选择器和修复要求
- 每次修复后重新执行相关阻断项

## Phase 5：输出

提供 zip 下载路径和报告。报告至少包含：

```text
复杂度：
DOM 基线 / Markdown 实际：
- formulas:
- tables:
- lists / list items:
- images:
- code blocks:
- headings:
- comments ledger:

图片：
- 是否执行去水印（默认否）：
- 用户是否明确要求：
- 原图副本：
- 压缩情况：

公式：
- 来源：
- 失败/截图数量：
- error/warning：
- 语义退化/方向问题：

人工复核：
```

## 参考文档

- @conversion-rules.md — 非公式转换规则
- @notebook-and-virtualized.md — Notebook/虚拟化/lazy-load
- @blocking-rules.md — 阻断规则
- @checklist.md — 主 agent 验收
- `../_meta/skill-self-improvement.md` — 通用改进规则
- @self-improvement.md — 本 skill 回归用例
- `formula-extraction` skill — 公式提取权威规则
