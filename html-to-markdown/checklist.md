# 验证 Checklist 与输出报告

本 checklist 供主 agent 在 sub agent 返回后执行独立验收。

## 自动结构检查

### 基线建立

在提取前通过 Playwright 对整个主体容器执行 `querySelectorAll`。不要只遍历直接子节点。

### 强制计数对比

| 检查项 | DOM 查询方式 | 阻断条件 |
|--------|-------------|----------|
| 块级公式 | `[data-slate-type="block-katex"]` OR `.katex-display` | HTML > Markdown |
| 行内公式 | inline-katex OR 非 display `.katex` | 显著减少 |
| 表格 | `[data-slate-type="table"]` OR `table` | HTML > Markdown |
| 有序/无序列表 | 有序判定规则 | marker 类型或数量不一致 |
| 列表项 | `[data-slate-type="list-line"]` OR `li` | HTML > Markdown |
| 图片 | `img`（排除装饰图后） | HTML > Markdown |
| 代码块 | `[data-slate-type="pre"]` OR `pre > code` | HTML > Markdown |
| 标题 | heading slate type OR `h1-h6` | 差异需解释 |
| 段落 | paragraph slate type OR `p` | 大幅减少 |
| 评论 | 顶层评论容器 | ledger 不守恒 |

**权威约束：** Slate 代码块使用 `[data-slate-type="pre"]`。不得在验收阶段改用 `[data-slate-type="code-block"]`，否则会把真实代码块基线算成 0。

### Markdown 侧计数

结构扫描前排除 fenced code block，避免代码注释或示例被误算为标题/列表。

简单三反引号正则只适用于无嵌套场景；存在 4+ 反引号或 blockquote/list 嵌套时，按 @notebook-and-virtualized.md 的 fence 规则或使用 Markdown parser。

## 专项检查

### 表格

- HTML 表格基线与 Markdown/HTML table 输出数量一致
- Slate 外层 table wrapper 与内部标准 `<table>` 不得重复计数
- 行数、列数、表头、顺序一致
- rowspan/colspan 无法等价表达时使用 fenced HTML 或人工复核
- 表标题与表格之间保留空行
- 截图抽检至少一张复杂表格

### 代码块

- 基线选择器与 Phase 1 相同
- 代码块数量一致
- 语言标签合理；不确定时为 `text`
- 代码内部 NBSP 已清理
- 代码注释未被误算为标题
- Notebook code cell 与 markdown 内嵌 code block 分开计数

### 列表

- 有序/无序/嵌套列表数量对比
- 编号证据可能在 item 子树
- 双 marker 扫描
- 代码块行号不误作列表
- 列表项总数一致

### 评论

为每条源评论记录：

```text
source_id
kept
removed_as_noise
failed
manual_review
reason
```

守恒条件：

```text
kept + removed_as_noise + failed + manual_review == source_total
```

检查作者回复、代码、日志、公式、图片、链接和 blockquote 排版。

### 图片

- 相对路径有效
- 文件真实存在
- 无 base64 直接嵌入
- 顺序和图注对应
- 删除的图片确为头像/广告/装饰图
- 压缩后文字可读

#### 去水印

- 默认应为“未执行”
- 只有用户明确要求时才允许执行
- 必须存在原图副本
- 报告列出处理文件、方法和 bbox
- 原尺寸/放大抽检，确认水印外内容未被擦除
- 未满足任一条件 → 阻断交付处理图，改用原图

### 公式

引用 `formula-extraction` skill：

- `.katex-error == 0`
- `mstyle[mathcolor="#cc0000"] == 0`
- 捕获 warning
- 渲染后公式数与基线对比
- 原始结构与输出的分式、上下标、矩阵等语义一致
- 上下标方向一致
- 双反斜杠命令未裸露

#### 命令边界

- `\simeq`、`\simneqq` 等合法命令不得被拆分
- 只有 parser parts 明确为 `["\sim", "p"]` 时才输出 `\sim p`
- 禁止在最终字符串上运行 `\\sim([A-Za-z...])`
- 未知 KaTeX 结构必须 fail-closed；`textContent` 只能用于诊断

### 块级居中

记录每个候选块的：

```text
类型
原始居中证据
Markdown 输出方式
渲染结果
```

短题注可与内容块同组；长说明段落保持正文对齐。

- 短题注示例：`图 D-1　系统架构`，紧邻图片且仅用于命名，可与图片同组居中。
- 说明段落示例：`图 D-1 给出了系统架构。它展示了……`，后续包含多句解释，即使以“图 D-1”开头也保持正文左对齐。
- 历史样例中曾出现 200–267 字的“图/公式开头说明段落”；长度只是辅助信号，最终以“命名性题注”还是“解释性正文”的功能判断。

### Markdown 渲染错误文本

渲染后扫描：

```text
KaTeX parse error
ParseError
Undefined control sequence
Double subscript
Double superscript
'_' allowed only in math mode
mathcalN
mathbbE
```

### Notebook 类

详见 @notebook-and-virtualized.md：

- cell 总数对齐
- 每个 code cell 都能提取代码
- NBSP 无残留
- fence 真正配对，不只看总数
- output 未被 inner fence 截断
- 空 iframe/img 已回填或标注
- output 保留/跳过/回填统计完整

## Playwright 渲染验证

### Step 1：公式错误

1. 使用统一、固定版本的 `render.html`
2. Markdown 解析前保护数学段
3. `.katex-error == 0`
4. `mstyle[mathcolor="#cc0000"] == 0`
5. 捕获 KaTeX console warning
6. 定位错误公式并循环修复

### Step 1.5：公式数量

渲染后 `.katex` 数量与 `N_formula_block + N_formula_inline` 对比。显著减少 → 阻断。

### Step 1.6：GitHub GFM

目标平台含 GitHub 时检查：

- 行内 `$` 外侧紧贴 CJK/全角标点
- 数学段未转义 `*`
- `\text{}` 内 `_`
- 双反斜杠命令

**行内 `$` 的首选修法：** 在 CJK/全角标点与 `$` 之间插入 ASCII 空格。实测该方案在 GitHub 与 VS Code 都能渲染；backtick 数学变体虽然可在 GitHub 工作，但 VS Code 不识别，因此不采用，避免为一个平台修复后破坏另一个平台。

### Step 1.7：强调边界

所有 level 强制：

- 闭合 `**/*/_` 后紧贴字母、数字、CJK 字符 → 检查
- 紧贴 punctuation 的合法场景不得误修
- 禁用 `\S` 宽类
- 清理 `**结论** 。` 这类误插空格
- 扫描 `****` 拼接
- 命中相邻加粗产生的 `****` 时，先移除该行已有加粗定界符，再按语义段重新包一层 `**...**`；不要把四个星号机械替换成两个，否则仍可能错误合并两段强调内容

### Step 2：截图对比

- 原 HTML 与 Markdown 渲染整页截图
- 公式、列表、**表格**、评论、处理过的图片做局部截图
- 做语义对比，不要求像素一致
- 表格/列表结构在整页图中不明显，必须局部检查

## 修复循环

发现问题 → 局部修复 → 重新执行受影响的计数、渲染和截图检查。

## 最终报告模板

### 通用部分

```text
复杂度级别：
正文容器：
编辑器类型：

DOM 基线 / Markdown 实际：
- 块级公式：
- 行内公式：
- 表格：
- 列表 / 列表项：
- 图片：
- 代码块：
- 标题：
- 评论 ledger：

图片处理：
- 去水印是否执行（默认否）：
- 用户明确要求：
- 原图副本：
- 压缩：
- 人工抽检：

浏览器渲染：
- 是否执行：
- 发现差异：
- 是否修复：
- 人工复核项：
```

### 公式部分（Level 2-3）

```text
公式来源：
成功提取：
截图 fallback：
KaTeX error / warning：
渲染数量 vs 基线：
语义退化：
上下标方向：
未知结构 fail-closed：
合法命令误拆检查：
```

### 批量汇总

```text
| 序号 | 文件名 | 标题 | 表格 | 图片 | 代码块 | 列表项 | 评论 | 公式 | 问题 |
|------|--------|------|------|------|--------|--------|------|------|------|
| 1    | ...    | ...  | N/M  | N/M  | N/M    | N/M    | ledger | N/M | ... |
```