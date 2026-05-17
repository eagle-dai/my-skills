---
name: html-to-markdown
description: Use when converting SingleFile-saved HTML pages into clean offline Markdown packages. Triggers on requests involving SingleFile HTML-to-Markdown conversion. Adopts a sub-agent dispatch model for conversion with main-agent quality verification.
---

# SingleFile HTML 转离线 Markdown 包（调度模式）

将 SingleFile 保存的网页 HTML 转换为干净、结构清晰、可离线阅读的 Markdown 文档包。

**架构：** 主 agent 负责分析和质量验证，sub agent 负责实际转换工作。

## 工作流概览

```text
Phase 1: 初步分析（主 agent）
    ↓
Phase 2: Dispatch sub agent（执行转换）
    ↓
Phase 3: 质量验证（主 agent）
    ↓ 如有问题
Phase 4: 修复循环（再次 dispatch 或手动修复）
    ↓
Phase 5: 输出
```

---

## Phase 1: 初步分析（主 agent 执行）

### 1.1 打开 HTML 文件

用 Playwright 打开 SingleFile HTML，确认页面结构。

### 1.2 复杂度分级

| 级别 | 条件 | 公式处理 | 验证深度 |
|------|------|---------|---------|
| Level 0 | 无公式、无正文图片、无代码块、无评论 | 跳过 | 整页对比即可 |
| Level 1 | 无公式（N_formula = 0） | 跳过 | 整页 + 列表/评论局部 |
| Level 2 | 有公式，有原始 LaTeX | 提取 + 渲染验证 | 整页 + 公式区域局部 |
| Level 3 | 有公式，无原始 LaTeX，需重建 | 完整公式处理 | 整页 + 逐公式局部 |

### 1.3 同源批量检测

多个 HTML 来自同一站点时，DOM 结构一致，应指导 sub agent 采用脚本化批量处理。

### 1.4 确定关键参数

- 正文容器选择器
- 富文本编辑器类型（标准 HTML / Slate / 其他）
- 评论区选择器
- 公式类型和来源

---

## Phase 2: Dispatch Sub Agent

使用 Agent tool 派出 sub agent 执行转换。根据复杂度级别选择对应的 prompt 模板。

### Prompt 模板结构

```
## 任务
将 [文件路径] 的 SingleFile HTML 转换为离线 Markdown 包。
复杂度级别：Level [N]
正文容器：[选择器]
编辑器类型：[标准 HTML / Slate / 其他]
[同源批量：是/否，共 N 个文件]

## 输出要求
输出 zip 包，结构：
<zip-英文名>.zip
└── 文章标题目录/
    ├── 文章标题.md
    └── files/<zip-英文名>/ (图片)

## 转换规则

### DOM 审计（提取前必须执行）
[从 conversion-rules.md 精简关键规则]
- 建立计数基线：公式、列表项、图片、代码块、标题、评论
- 容器嵌套穿透：无标记中间层必须递归搜索
- 列表项计数是强制的

### 列表处理
- 有序证据：<ol> / data-list-type="ordered" / CSS counter / content:attr(...)
- 判定证据可能在列表项子树中而非列表项自身，搜索时须遍历子树
- 无序证据：<ul> / CSS bullet / 无法确认→默认无序
- 禁止双 marker
- 不得根据"内容像步骤"改变 marker 类型
[如果是 Slate 编辑器，补充 Slate 列表映射]

### 评论区
- 不得默认删除
- 只匹配顶层评论容器
- 用 Playwright 确认各子区域（正文 vs 回复）的实际用途，不凭 class 名猜测
- 保留：技术问题、纠错、作者回复、长评论
- 删除：打卡、纯表情、广告、头像
- 格式：### 评论 N + blockquote 回复

### 图片
- base64 → 解码保存为 files/<zip-同名>/image_NN.ext
- 删除装饰图（<50px）
- 评论图片带 comment_ 前缀

### 块级居中
- 居中证据 → Markdown 也必须居中（<div align="center">）

### 代码块
- 无 language class 时启发式检测语言（≥2 信号）

### 文本清理
- PUA 字符删除
- 零宽字符删除

### 解析器
- 必须使用 lxml，不得使用 html.parser

## 公式处理（Level 2-3 时包含）
[按复杂度级别从 formula-extraction skill 精简]

### 提取优先级
1. annotation[encoding="application/x-tex"]
2. data-tex / data-latex / data-math / alttext
3. <script type="math/tex">
4. 页面 JSON / hydration 数据
5. MathML 结构
6. KaTeX HTML 系统性重建（编写解析器）
7. 无法提取 → 截图保存

### 后处理管道（必须统一应用）
- Prime: ^' → '
- 命令粘连: \gammaV → \gamma V（join 阶段统一）
- \sim 后粘连: \simp → \sim p
- Unicode 希腊字母 → LaTeX 命令
- PUA/零宽字符删除
- 空 block-katex 防护（空 $$ 删除）

### 上下标方向
- 忠实原文，不得根据领域惯例改变
- Double subscript 只能补分组，不能改方向

## 验证要求

### 强制计数对比
提取完成后，将 DOM 基线与 Markdown 逐项对比，差异>0 的阻断项必须修复。

### Playwright 渲染验证（Level 1+）
1. 创建 render.html（KaTeX + marked.js，保护数学公式后再解析）
2. .katex-error 数量 = 0
3. mstyle[mathcolor="#cc0000"] 数量 = 0
4. 渲染后 .katex 数量 ≈ DOM 基线
5. 整页截图对比 + 高风险区域局部截图

### 修复循环
发现问题 → 局部修复 → 重新验证 → 循环直到通过

## 输出
返回 zip 文件路径 + 简短处理报告。
```

### 同源批量的 prompt 变体

增加以下段落：

```
## 批量处理策略
共 [N] 个文件来自同一站点，DOM 结构一致。
1. 先分析第一篇确定选择器和结构
2. 编写 Python 脚本（BeautifulSoup + lxml）统一处理
3. 内置审计计数
4. 所有文章输出到一个 zip，每篇一个子目录
```

---

## Phase 3: 质量验证（主 agent 执行）

Sub agent 返回结果后，主 agent 执行最终质量验证。参考 @checklist.md。

### 必须验证的项目

1. **计数对比**：确认 sub agent 报告的 DOM 基线 vs Markdown 实际数量无阻断差异
2. **Playwright 渲染**：打开 sub agent 创建的 render.html，独立验证 KaTeX error = 0
3. **截图抽检**：对高风险区域（公式密集段、列表、评论区）做局部截图对比
4. **zip 完整性**：确认 zip 解压后图片路径正确、文件存在

### 最终输出报告

参考 @checklist.md 中的报告模板，向用户提供：
- 复杂度级别
- 各项计数对比结果
- 是否有人工复核标注
- zip 下载路径

---

## Phase 4: 修复循环

如果 Phase 3 发现问题：

- **小问题**（个别公式错误、单个列表 marker 错误）：主 agent 直接修复
- **系统性问题**（大量公式失败、列表结构全部错误）：再次 dispatch sub agent，prompt 中包含具体问题描述和修复指导

---

## Phase 5: 输出

提供 `.zip` 下载链接 + 最终报告。

---

## 关键决策点

```dot
digraph dispatch_decision {
    rankdir=TB;
    "用户提供 HTML" [shape=doublecircle];
    "打开 HTML 判断复杂度" [shape=box];
    "Level 0-1" [shape=diamond];
    "Level 2-3" [shape=diamond];
    "同源批量?" [shape=diamond];
    "Dispatch: 基础转换 prompt" [shape=box];
    "Dispatch: 含公式处理 prompt" [shape=box];
    "Dispatch: 批量脚本 prompt" [shape=box];
    "验证 + 输出" [shape=doublecircle];

    "用户提供 HTML" -> "打开 HTML 判断复杂度";
    "打开 HTML 判断复杂度" -> "Level 0-1" [label="无公式"];
    "打开 HTML 判断复杂度" -> "Level 2-3" [label="有公式"];
    "Level 0-1" -> "同源批量?";
    "Level 2-3" -> "同源批量?";
    "同源批量?" -> "Dispatch: 批量脚本 prompt" [label="是"];
    "同源批量?" -> "Dispatch: 基础转换 prompt" [label="否, Level 0-1"];
    "同源批量?" -> "Dispatch: 含公式处理 prompt" [label="否, Level 2-3"];
    "Dispatch: 基础转换 prompt" -> "验证 + 输出";
    "Dispatch: 含公式处理 prompt" -> "验证 + 输出";
    "Dispatch: 批量脚本 prompt" -> "验证 + 输出";
}
```

## 参考文档

- @conversion-rules.md — 完整转换规则（列表、评论、图片、居中、代码块等）
- @blocking-rules.md — 阻断规则（验证阶段使用）
- @checklist.md — 验证 checklist 和报告模板
- `formula-extraction` skill — 公式提取的权威参考（独立 skill）
