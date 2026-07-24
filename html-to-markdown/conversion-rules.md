# 转换规则参考（非公式部分）

本文档覆盖 HTML → Markdown 转换中除公式外的内容规则。公式见 `formula-extraction` skill。selector、复杂度分级、语义候选发现与去重、评论 ledger 的可执行合同以 @contracts.py 为准；图片保留/删除以 @image_disposition.py 为准；fence 验证以 @markdown_fences.py 为准。

## 识别主体内容

SingleFile HTML 包含导航、侧边栏、弹窗、评论等完整页面内容。

1. 在渲染后的 DOM 中优先查 `<article>`、`<main>`、`[role="main"]`、`[data-slate-editor]`。
2. 无唯一选择器时，用截图和文本密度确认正文范围。
3. 标题、作者、时间等元信息必须限定在正文容器内查询。

## DOM 完整性审计

提取前用 Playwright 对主体容器建立基线。原始 selector 命中必须先分配 `semantic_id` 并调用 `canonicalize_candidates()`，不得直接作为基线。

| 审计项 | 权威查询/分类 | 记录值 |
|---|---|---|
| 块级公式 | `CSS_SELECTORS["formula"]` 后按 display/Slate 类型分类 | `N_formula_block` |
| 行内公式 | canonical 公式候选排除 display 后分类 | `N_formula_inline` |
| 表格 | `[data-slate-type="table"], table` 后 canonicalize | `N_table` |
| 列表 | `[data-slate-type="list"], ul, ol` 后 canonicalize | `N_list` |
| 列表项 | `[data-slate-type="list-line"], li` 后 canonicalize | `N_list_item` |
| 图片 | `img`，每张建立 image ledger | `N_image` |
| 题注 | `figure > figcaption, table > caption` 与已验证 Slate 关系 | `N_caption` |
| 代码块 | `[data-slate-type="pre"], pre > code` 后 canonicalize | `N_codeblock` |
| 标题 | `[data-slate-type^="heading"], h1, h2, h3, h4, h5, h6` | `N_heading` |
| 评论 | 顶层评论容器与完整稳定 `source_ids` | `N_comment` |

规则：

- 表格、代码块、列表项、正文图片和块级公式减少均为阻断。
- 审计和验收使用相同 selector、`semantic_id` 与 canonicalization。
- Slate 代码块的权威映射是 `[data-slate-type="pre"]`；不得改成 `code-block`。
- selector list 使用逗号，不得把自然语言 `OR` 拼进 `querySelectorAll()`。

## 富文本编辑器适配

先枚举实际 `[data-slate-type]`，再建立映射。

| 标准语义 | Slate 标记 | 提取要点 |
|---|---|---|
| 段落 | `paragraph` | 普通段落 |
| 标题 | `heading` 或标准 h 标签 | 保留层级 |
| 列表 | `list` | wrapper/native 共享身份，嵌套列表独立 |
| 列表项 | `list-line` | wrapper/native 共享身份 |
| 表格 | 外层 `table` + 内部 `<table>` | 原生节点优先 |
| 代码块 | `pre` + `code-line` | 使用 `[data-slate-type="pre"]` |
| 引用 | `block-quote` + `quote-line` | 输出 blockquote |
| 图片 | `image` | 图片、题注和 image ledger 一起处理 |
| 加粗/斜体 | `bold` / `italic` | 保留语义 |

## 列表处理

有序证据来自 `<ol>`、`data-list-type="ordered"`、CSS counter 或连续编号属性； `<ul>`/bullet 为无序证据。无法确认时默认无序并标记复核。

禁止：

- 双 marker，如 `- 1. item` 或 `1. - item`；
- 根据内容“像步骤”擅自改变 marker；
- 把代码块行号当列表编号；
- 把嵌套 `ul/ol` 与父列表合并为同一 `semantic_id`。

## 表格处理

- DOM 基线计 canonical 表格，不计 selector 原始命中数。
- Slate wrapper 与内部标准 `<table>` 使用同一 `semantic_id`。
- canonical candidate 优先原生 `<table>`，wrapper 只作 fallback。
- 保留行列、表头和顺序；rowspan/colspan 无法等价表达时使用 fenced HTML 或人工复核。
- 表标题与表格之间保留空行。

## 评论区处理

不得默认整体删除评论区。只匹配顶层评论容器，转换前记录完整稳定 `source_ids`。

保留技术问题、纠错、补充、作者回复、代码、公式、链接和说明图；纯打卡、纯表情、广告和 UI 控件可有理由过滤。

每条源评论建立 ledger：

```text
source_id | status | emitted_count | reason
```

`status` 只能为 `kept / removed_as_noise / failed / manual_review`。交付前调用：

```python
assert_valid_comment_ledger(entries, source_ids=source_ids)
```

- `kept` 必须输出一次；
- 其他状态输出 0 次且必须有原因；
- ledger ID 集合与源 ID 集合完全一致。

## 相邻行内公式（避免 `$$` 定界符碰撞）

两个行内公式在源 DOM 中相邻（中间无文字）时，逐个按 `$...$` 拼接会产生定界符碰撞：`$D_t=P_t/P_0-1$` 紧跟 `$T_t=D_t≤-S$` 拼成 `...-1$$T_t...`，中间的 `$$` 被 GitHub/KaTeX 当成块公式定界符，渲染破坏。

规则：

- 在相邻行内公式之间**插入一个空格分隔符**，输出 `$a$ $b$`。这保持二者仍是行内公式，**不改 display 类型**：`formula_inline` 计数不变、无审计不一致、排版语义不变。
- **不要**把行内公式改成 `$$ ... $$` display 块——那会改变源 DOM 的排版语义，并造成报告按 `formula_inline` 计数、输出却是块公式的审计不一致。
- 只有**前一片段以 `$` 结尾且后一片段以 `$` 开头**才需分隔；公式与文字、文字与公式、行内 code 与公式等其它边界不插空格。

**仓库已有实现**：`html-to-markdown/fast_converter.py` 的 `_join_inline()` 在 `inline_children` 拼接时执行此分隔（前片段 `$` 结尾 + 后片段 `$` 开头 → 插空格）；回归见 `tests/test_pipeline.py::test_adjacent_inline_formulas_are_separated`。strict 路径的临时转换器同样须在相邻行内公式间保留分隔符。

## 块级居中与题注

有明确居中证据的公式块、图片、图表、短题注和署名可保留居中语义；解释性长段落保持正文左对齐。不得仅凭“图/表/公式”开头就居中整段。

题注候选只能来自已验证结构：

- `<figure>` 的直接 `<figcaption>`；
- `<table>` 的直接 `<caption>`；
- Slate `image` 容器内与 `<img>` 已验证同级、非 UI 的文本节点。

不得抓取内容块外部任意 sibling。每个 confirmed caption 建立 ledger 并保证 `emitted_count == 1`。

## 图片与资源

基础规则：

- base64 图片解码到 `files/<zip-name>/`；
- Markdown 使用相对路径；
- 评论说明图使用 `comment_` 前缀；
- lazy-load 源缺失时按 notebook 规则回填或标注；
- 每张源图片建立稳定 `source_id`，调用 `decide_image()` 并生成 image ledger；
- 交付前调用 `assert_valid_image_ledger(entries, source_ids=source_ids)`。

### 二维码

二维码不是默认噪声：

- 正文步骤、下载、联系方式、报名、认证、支付等内容相关二维码必须保留；
- 分享/关注/登录 UI 中且与正文无关的二维码可标记 `remove_as_ui`；
- 无法判断时标记 `manual_review`，原图仍输出一次；
- 能可靠解析目标 URL 时，同时输出可点击链接；解析失败不构成删除理由。

### 去站点水印（默认执行）

**默认行为：默认执行去站点水印。** 只有用户明确要求保留原始水印时才跳过。去水印仍是破坏性处理，破坏性护栏一条都不能省——默认执行不等于放松验证。

强制护栏（默认执行时同样适用）：

1. 保留未修改原图副本；
2. 报告处理文件、方法和 bbox；
3. 检测和验证都用原图，不用缩略图（否则漏检）；
4. 特征色命中正文同色区域时，只取最右下连通块，不误擦正文；
5. bbox 紧框水印，禁止一盖到角（否则擦掉内容）；
6. 逐图原尺寸/放大验证正文未被擦除；
7. 宁可保留不确定水印，也不能擦除正文——无法安全去除时降级为保留原图并标注。

### 图片压缩

压缩时同步扩展名和 Markdown 引用，宽图等比缩放，图表/代码截图保守处理，并抽检文字可读性。去水印和压缩均默认执行，固定顺序为“原图备份 → 去水印 → 压缩”。

## 代码块语言与 fence

无 `language-*` 时至少两个独立信号才标具体语言；不确定时标 `text`。代码内部 NBSP 替换为普通空格。

结构计数前必须调用：

```python
scan_fenced_blocks(markdown)
no_code = strip_fenced_blocks(markdown)
```

不得使用 fence 行数奇偶或跨行正则代替 scanner。

## 文本清理

- 删除 PUA U+E000–U+F8FF；
- 删除 zero-width U+200B/U+200C/U+200D/U+FEFF/U+2060；
- 代码内 NBSP 替换为空格；普通段落仅在确认无语义时处理。

## 加粗/斜体

保留 `<strong>`、`<b>`、font-weight、Slate bold/italic。GitHub 强调边界需区分字母、数字、CJK 和标点，禁止使用 `\S` 宽泛匹配；扫描相邻强调产生的 `****`，按语义重包而非机械替换。

## BeautifulSoup 解析器

必须使用 `lxml`。SingleFile HTML 可能存在未闭合表格标签，`html.parser` 容易错误嵌套。

## 输出结构

```text
<zip-name>.zip
└── 文章标题/
    ├── 文章标题.md
    └── files/<zip-name>/
```

## 删除与保留速查

**保留：** 正文、标题层级、列表、引用、代码、表格、公式、正文图片、内容相关二维码、关键链接、题注、有价值评论和原有对齐语义。

**可删除：** 导航、侧栏、页脚、弹窗、分享/点赞控件、广告、推荐、头像、Cookie 提示、脚本、CSS、tracking 参数及有明确证据的纯 UI 图片。二维码只有在 `remove_as_ui` 证据成立时才删除。
