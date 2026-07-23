# 转换规则参考（非公式部分）

本文档覆盖 HTML → Markdown 转换中除公式外的内容规则。公式见 `formula-extraction` skill。selector、复杂度分级、语义候选去重和评论 ledger 的可执行合同以 @contracts.py 为准。

## 识别主体内容

SingleFile HTML 包含导航、侧边栏、弹窗、评论等完整页面内容。

定位正文：

1. 在渲染后的 DOM 中优先查 `<article>`、`<main>`、`[role="main"]`、`[data-slate-editor]`
2. 无唯一选择器时，用截图和文本密度辅助确认
3. 标题、作者、时间等元信息必须限定在正文容器内查询，避免侧栏同名 class

## DOM 完整性审计

提取前必须用 Playwright 对主体容器建立基线。候选发现使用 @contracts.py 的合法 CSS selector list；原始 selector 命中必须先按 `semantic_id` 调用 `canonicalize_candidates()`，不得直接作为基线：

| 审计项 | 权威查询/分类 | 记录值 |
|--------|---------------|--------|
| 块级公式 | `CSS_SELECTORS["formula"]` 发现 canonical 公式候选，再按 display 容器/Slate 类型分类 | N_formula_block |
| 行内公式 | `CSS_SELECTORS["formula"]` 发现 canonical 公式候选，再排除 display 后分类 | N_formula_inline |
| 表格 | `[data-slate-type="table"], table`，随后 canonicalize wrapper/native | N_table |
| 列表容器 | `[data-slate-type="list"], ul, ol`，随后 canonicalize | N_list |
| 列表项 | `[data-slate-type="list-line"], li`，随后 canonicalize | N_list_item |
| 图片 | `img`（排除装饰图后） | N_image |
| 题注 | `figure > figcaption, table > caption`；Slate image 题注按已验证容器关系发现并按 DOM 身份去重 | N_caption |
| 代码块 | `[data-slate-type="pre"], pre > code`，随后 canonicalize wrapper/native | N_codeblock |
| 标题 | `[data-slate-type^="heading"], h1, h2, h3, h4, h5, h6` | N_heading |
| 评论 | 评论区顶层评论条目，并记录完整稳定 `source_ids` | N_comment |

规则：

- 表格、代码块、列表项、图片和块级公式减少均为阻断
- 只遍历直接子节点不够；无语义 wrapper 必须递归穿透
- 审计和验收必须使用相同 selector、相同 `semantic_id` 生成方式和相同 canonicalization
- 不得在 checklist 中把 Slate 代码块改写为 `[data-slate-type="code-block"]`
- selector 表中的逗号是 CSS selector list 语法；不得把自然语言 `OR` 拼进 `querySelectorAll()`

## 富文本编辑器适配

检测 `[data-slate-type]`、`[data-slate-editor]` 等属性，先枚举实际类型再建立映射。

### Slate 常见映射

| 标准语义 | Slate 标记 | 提取要点 |
|----------|------------|----------|
| 段落 | `paragraph` | 普通段落 |
| 标题 | `heading` 或标准 h 标签 | 层级取实际标签/属性 |
| 列表 | `list` | 子节点可混合 list-line、paragraph、公式、嵌套 list |
| 列表项 | `list-line` | 每项单独输出 |
| 表格 | 外层 `table` + 内部标准 `<table>` | 外层定位，内部抽行列；两者共享 `semantic_id` |
| 代码块 | `pre` + `code-line` | 用 `[data-slate-type="pre"]` 定位 |
| 行内代码 | `code` | 保留 inline code |
| 引用 | `block-quote` + `quote-line` | 输出 blockquote |
| 图片 | `image` | 提取内部 img **+ 已验证同级题注**（范围严格限定，见「题注提取」） |
| 加粗/斜体 | `bold` / `italic` | 保留语义 |
| 高亮 | `mark-class` | 递归处理子节点 |

## 列表处理

### 有序/无序证据

| 证据 | 输出 |
|------|------|
| `<ol>`、`data-list-type="ordered"`、CSS counter、连续编号属性 | 有序 |
| `<ul>`、CSS bullet marker | 无序 |
| 仅 list-line 且无编号证据 | 无序 |
| 无法确认 | 无序并标记复核 |

编号证据可能位于 list item 子树而非自身。

禁止：

- `-- item`
- `- 1. item`
- `1. - item`
- 根据内容“像步骤”擅自改变 marker
- 把代码块行号当列表编号

算法：

```text
找到 list 容器
→ 找 list item
→ 搜索 item 子树中的 marker 证据
→ 拆掉视觉 marker
→ 输出对应 Markdown marker
→ 扫描双 marker
```

## 表格处理

- DOM 基线必须计 canonical 表格，不计 selector 原始命中数
- Slate 表格先定位 `[data-slate-type="table"]`，再在其子树找标准 `<table>`；wrapper/native 使用同一 `semantic_id`
- canonical candidate 优先选择原生 `<table>`，wrapper 仅在无原生节点时兜底
- 保留行列数、表头和单元格顺序
- Markdown 无法表达 rowspan/colspan 时，优先 fenced HTML 或标记人工复核
- 表格基线大于 Markdown 实际表格数 → 阻断
- 表标题和表格之间保留空行，避免 GFM 把标题吞进最后一行

## 评论区处理

**不得默认整体删除评论区。**

识别时只匹配顶层评论容器，不能宽泛匹配内部 `content/body/text` 子节点。转换前先记录源顶层评论的完整稳定 `source_ids`。

保留：

- 技术问题、纠错、补充、实践经验
- 作者/讲师/官方回复
- 含代码、公式、链接、说明图的评论
- 无法判断价值的评论（标记待复核）

可过滤：

- 纯打卡、纯表情、广告
- 头像、点赞、展开按钮等 UI

每个源评论必须建立一条 identity ledger：

```text
source_id | status | emitted_count | reason
```

其中 `status` 只能是：

```text
kept | removed_as_noise | failed | manual_review
```

交付前必须调用：

```python
assert_valid_comment_ledger(entries, source_ids=source_ids)
```

约束：

- ledger 的 `source_id` 集合与源 `source_ids` 完全相等
- `kept` 必须 `emitted_count == 1`
- 非 `kept` 必须 `emitted_count == 0`
- `removed_as_noise / failed / manual_review` 必须有非空 `reason`
- 允许有理由地过滤噪声，不要求 Markdown 评论数量等于源评论数量

格式：

```markdown
### 评论 N
**用户名**（日期）

正文
> **作者回复**
>
> 回复内容
```

## 块级居中

有明确居中证据的公式块、图片、图表、短题注、署名应保留居中语义。

区分：

| 元素 | 特征 | 处理 |
|------|------|------|
| 内容块 | 表格、图片、块级公式 | 按原文证据居中 |
| 短题注 | 紧邻内容块、命名性、通常一行 | 与内容块同一 `<div align="center">` |
| 说明段落 | 多句、解释性、较长 | 正文左对齐 |

不得仅凭“图/表/公式”开头就居中整段说明。

公式编号如 `$D - 6$` 若只是编号标签，应改为正体文本并与公式块同组；必须有相邻公式证据。

## 题注提取

富文本编辑器常把题注（figcaption）放进**内容块容器内的已验证直接结构关系**里，而非独立段落。提取图片/表格块时必须一并抽出题注，否则题注静默丢失。

处理闭环：**候选发现 → 语义分类 → DOM 身份去重 → 一次输出 → ledger 验收**。不得把"发现候选"和"确认题注"混为一步。

### 候选发现（范围严格限定，禁止泛化）

只在内容块**父容器内的已确认结构关系**里找候选，**不得**跨出父容器抓下一段，**不得**泛化为"任意同级 `<div>` / 任意紧邻 sibling"：

| 形态 | 题注唯一合法位置 |
|------|------------------|
| 标准 figure | `<figure>` 直接子 `<figcaption>` |
| 标准表格 | `<table>` 直接子 `<caption>` |
| Slate `image` block | `data-slate-type="image"` 容器内、`<img>` 的**已验证同级** `<div>`（同一容器内、非嵌套 UI 层） |

候选必须**排除**：

- 含 `img/button/input/svg` 的 wrapper、toolbar、resize handle
- `contenteditable="false"` 的 UI 节点
- 空文本节点、纯 UI class 节点
- 内容块父容器**之外**的任何 sibling（含"紧随图片的下一段正文"、解释性长段落）

"表格容器**外部** sibling 题注"不是通用规则——只能在已识别的站点专属 adapter 里启用，默认关闭。

### 语义分类

候选发现后再分类，命名性 ≠ 解释性：

- **短题注**（命名性、通常一行、形如 `图 4-5　权益峰值...`、`表 4-3　...`，常含全角空格 U+3000）：按「块级居中」节与内容块同组
- **解释性长说明段落**（多句、以"图 X 给出/展示了…"开头）：**不分类为题注**，仍作正文左对齐保留，**不重复抽**

### DOM 身份去重 + 一次输出

- 每个候选按稳定标识记录（DOM path/index 或 source id）
- 同一 DOM 节点若已被普通段落遍历输出过，题注 pass 必须**复用/移动**而非再次输出
- 目标：每个 confirmed caption `emitted_count == 1`

### ledger 验收

Markdown 无标准 caption 节点，验收不能只写 `N_caption == Markdown caption count`。需建 caption ledger：

```text
每条：source_dom_id/path | 分类(caption/正文) | 输出位置 | emitted_count
```

要求：

- 每个 confirmed caption `emitted_count == 1`（不丢、不重复）
- 误分类为正文的候选仍须作为正文保留，`emitted_count == 1`
- `N_caption`（源侧 confirmed caption 数）== Markdown 侧 caption 输出数

## 图片与资源

基础规则：

- base64 图片解码到 `files/<zip-name>/`
- Markdown 使用相对路径
- 删除头像、广告、二维码和纯装饰图
- 评论说明图以 `comment_` 前缀命名
- 动态加载导致源缺失时，按 notebook/lazy-load 规则回填或标注

### 去站点水印（仅用户明确要求时执行）

**默认行为：保留水印和原始图片。** 去水印是破坏性处理，不属于普通格式转换的默认步骤。

执行前提：

1. 用户明确要求去水印
2. 保留未修改原图副本
3. 报告列出处理文件、方法和 bbox
4. 逐图原尺寸验证，不能只看缩略图
5. 宁可保留不确定水印，也不能擦除正文

执行护栏：

- 特征色可能命中正文，只取角落中与水印形态相符的连通块
- bbox 紧框水印，禁止从 logo 一直覆盖到图角
- 纯色背景可背景填充；压在内容上才考虑 inpaint
- 每张图片独立判断，不批量套固定 bbox
- 修改后放大检查残留、背景融合和正文完整性

目录建议：

```text
files/<zip-name>/original/   # 原图
files/<zip-name>/processed/  # opt-in 处理图
```

### 图片压缩

默认可按用户目标压缩，但必须：

- 修改扩展名后同步 Markdown 引用
- 宽图等比缩放
- 图表/代码截图保守处理
- 转换后抽检文字可读性和体积
- 若用户同时 opt-in 去水印：原图备份 → 去水印 → 压缩

## 代码块语言标注

无 `language-*` 时至少两个独立信号才标具体语言。

| 语言 | 示例信号 |
|------|----------|
| Go | `package`、`func`、`:=` |
| Python | `def`、`from ... import`、`self.` |
| JS/TS | `const/let`、`=>`、`export` |
| Java | `public class`、`public static` |
| Shell | `mkdir`、`npm`、`pip`、`docker`、`git` |
| PowerShell | `$env:`、`Get-*`、`-ErrorAction` |
| JSON | 完整 `{}`/`[]` + `"key":` |
| YAML | 缩进 `key:` + `- ` |
| SQL | `SELECT/INSERT/CREATE TABLE/WHERE` |
| Text | 中文模板、目录树、不可运行伪代码 |

判不准时标 `text`，不要误导为可运行代码。所有 fenced code block 都应有语言标签。

## 文本清理

- PUA U+E000-U+F8FF：删除
- zero-width U+200B/U+200C/U+200D/U+FEFF/U+2060：删除
- 代码 cell/代码块内 NBSP：替换为普通空格
- 普通段落中的 NBSP 仅在确认无语义时处理

## 加粗/斜体

保留 `<strong>`、`<b>`、font-weight、Slate bold/italic。

GitHub 强调边界：

- 闭合 `**/*/_` 后紧贴字母、数字、CJK 汉字可能导致配对失败
- 紧贴 CJK/ASCII 标点通常是合法 right-flanking，不得用 `\S` 宽泛匹配
- 闭合前是标点时优先把标点移出强调
- 其他真违规才插空格
- 反向清理 `**结论** 。` 这类过度修复
- 扫描 `****` 相邻强调拼接

## 交互式组件

| 类型 | Markdown 表达 |
|------|---------------|
| 折叠面板 | 标题 + 展开内容 |
| 决策树 | ASCII/code block |
| Tabs | 各 tab 按顺序展开 |
| callout | blockquote |

隐藏内容应在离线 Markdown 中可见。

## BeautifulSoup 解析器

必须使用 `lxml`，不得使用 `html.parser`。SingleFile HTML 可能存在未闭合表格标签，`html.parser` 容易错误嵌套。

## 同源批量处理

1. 先分析一篇并确认基线
2. 编写 Python + BeautifulSoup(lxml) 通用脚本
3. 内置 DOM vs Markdown 审计
4. 统一打包
5. 每篇输出独立计数报告

## 输出结构

```text
<zip-name>.zip
└── 文章标题/
    ├── 文章标题.md
    └── files/<zip-name>/
```

ZIP 文件名使用英文、数字、下划线或短横线。

## 删除与保留速查

**保留：** 标题、作者、时间、正文、标题层级、列表、引用、强调、代码、表格、公式、正文图片、关键链接、脚注、有价值评论、原有对齐语义。

**删除：** 导航、侧栏、页脚、登录/购买弹窗、分享/点赞按钮、广告、推荐、头像、二维码、Cookie 提示、脚本、CSS、tracking 参数、纯 UI 控件。

作者寒暄可删除，但若与实质总结在同一句，只删除寒暄引子，保留内容。
