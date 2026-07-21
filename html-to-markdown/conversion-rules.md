# 转换规则参考（非公式部分）

本文档覆盖 HTML → Markdown 转换中除公式外的所有内容类型规则。公式相关规则见 `formula-extraction` skill。

---

## 识别主体内容

SingleFile HTML 包含完整页面（导航栏、侧边栏、广告、评论区等），需要定位正文容器。

**SingleFile 特征：** 所有 CSS 内联、图片 base64 编码、字体嵌入——文件体积大但结构与原始 DOM 一致。

**定位正文容器策略：**
1. 用 Playwright 检查 DOM，搜索语义容器（`<article>`, `<main>`, `[role="main"]`）或富文本编辑器标记（`[data-slate-editor]`）
2. 无法通过选择器确定时，用 Playwright 截图对照 DOM 定位文本密度最高的区域

**选择器歧义防范：** 同一 CSS class pattern 可能在页面不同区域出现。提取标题、作者等元信息时，**必须限定在正文容器内搜索**。

---

## DOM 完整性审计

提取前必须建立**原始计数基线**（用 Playwright 对主体容器做完整 DOM 审计）：

| 审计项 | 查询方式 | 记录值 |
|--------|---------|--------|
| 块级公式 | `.katex-display` 或 `[data-slate-type="block-katex"]` | N_formula_block |
| 行内公式 | `.katex`（非 display 子代） | N_formula_inline |
| 列表容器 | `ol/ul` 或 `[data-slate-type="list"]` | N_list |
| 列表项 | `li` 或 `[data-slate-type="list-line"]` | N_list_item |
| 图片 | `img`（排除装饰图后） | N_image |
| 代码块 | `pre>code` 或富文本代码容器 | N_codeblock |
| 标题 | `h1-h6` | N_heading |
| 评论 | 评论区顶层容器内评论条目 | N_comment |

**列表项计数是强制的**——仅统计容器数量无法发现"多项被合并成一段"的问题。

**容器嵌套穿透规则**：遍历主体容器直接子节点时，无内容类型标记的中间 div/section 必须递归搜索后代。

---

## 富文本编辑器适配

检测方法：在主体容器中搜索 `[data-slate-type]`、`[data-slate-editor]` 等特征属性。

**Slate 编辑器映射（极客时间等）：**

| 标准 HTML | Slate `data-slate-type` | 提取要点 |
|-----------|-------------------------|----------|
| `<p>` | `paragraph` | 普通段落 |
| `<h1>`-`<h6>` | `heading` | 标题层级从 HTML 标签名获取 |
| `<ul>/<ol>` | `list`（容器） | list 容器子节点可能有 list-line、paragraph、block-katex、嵌套 list |
| `<li>` | `list-line` | 每个输出为一个 bullet/编号 |
| `<table>` | 外层 `data-slate-type="table"` 容器（内含 simplebar 滚动层）→ 内部为**标准 `<table><thead><tr><td>`**（带 `slate-element="table"`） | 定位用外层 `data-slate-type="table"`，抽取行列用内部标准 `<table>` 标签。Phase 1 探测须同时数 `[data-slate-type="table"]` 和 `<table>`（实测：极客时间 table 内部是标准标签，但探测清单里漏列 table 项本身，导致整类被忽略） |
| `<pre><code>` | `pre` + `code-line` | 用 `data-slate-type="pre"` 定位容器，子树查找 `code-line` |
| `<code>` | `code` | 行内代码 |
| `<strong>` | `bold` | 加粗 |
| `<em>` | `italic` | 斜体 |
| `<blockquote>` | `block-quote` + `quote-line` | 引用 |
| `<a>` | `link` | 链接 |
| `<img>` | `image` | 图片块 |
| 高亮 | `mark-class` | 仅标记样式，递归处理子节点 |

---

## 列表处理

### 有序/无序判定

| 证据 | 输出 |
|------|------|
| `<ol>` / `data-list-type="ordered"` / CSS counter 数字 / `content: attr(data-code-line-number) "."` | 有序列表 |
| `<ul>` / CSS `content:"•"` / `"·"` / `"-"` / `"●"` | 无序列表 |
| 仅 `data-slate-type="list-line"` 无其他证据 | 无序列表 |
| 无法确认 | 无序列表 |

**注意：** 有序列表的判定证据（属性、CSS class）不一定在列表项元素本身上，可能在其子元素上。判定时应搜索列表项的**子树**，而非仅检查列表项自身。

### 禁止规则

- 禁止双 marker（`-- item` / `- 1. item` / `1. - item`）
- 不得仅根据"内容像步骤"把 bullet 改成 `1. 2. 3.`
- 不允许改变原文 marker 类型

### Marker 提取通用算法

```text
① 找到 list 容器
② 找到 list item
③ 对每个 list item，搜索子树中的编号属性或 CSS marker
④ 拆分 marker 区域和正文区域
⑤ 读取 marker 类型
⑥ 生成 Markdown，正文去掉原始 marker
⑦ 源码扫描双 marker
```

---

## 评论区处理

**不得默认删除评论区。**

### 识别

匹配：`comment` / `reply` / `discussion` / `评论` / `回复` / `精选留言` 等线索。

**关键：只匹配顶层评论容器**（含完整用户名+正文+时间的元素），不能用 `[class*="CommentItem"]` 宽泛选择器。

### 结构辨别原则

评论容器内部通常有多个子区域（用户名、正文、回复、时间等）。提取前必须用 Playwright 确认各区域的实际用途，不能仅凭 class 名中的 `content`、`body`、`text` 等通用词猜测。

**常见陷阱：** "回复"容器内部可能嵌套一个 class 含 `content` 的子元素（用于回复文本），如果误将其当作用户评论正文来提取，会导致用户评论丢失 + 回复重复。

### 保留/删除判定

**保留：** 技术问题、纠错、补充、实践经验、作者/讲师/官方回复、长评论、含代码/公式/链接评论。

**删除：** 纯"打卡""学习了""666"、纯表情、广告、头像/点赞/UI控件。

**无法判断 → 保留并标注"评论价值待人工复核"。**

### 格式

```markdown
### 评论 N
**用户名**（2025-10-16）

评论正文内容...

> **作者回复**
>
> 回复内容...
```

- 每条评论 `### 评论 N`
- 评论中代码/日志/报错必须 fenced code block
- 作者回复用 blockquote（`>`）紧跟评论

---

## 块级居中

原网页居中的公式块/图片/图表/图注/署名 → Markdown 也必须居中：

```markdown
<div align="center">

$$
V_\pi(s)=\mathbb{E}_\pi\left[R_t+\gamma V_\pi(S_{t+1})\mid S_t=s\right]
$$

</div>
```

**居中证据：** `text-align:center` / `align="center"` / `display:flex; justify-content:center` / `margin:auto` / `.katex-display` / 截图。

无证据不得擅自居中。块级公式不能降级成行内 `$...$`。

---

## 图片与资源（SingleFile 特有）

- base64 `data:image/xxx;base64,...` → 解码保存为 `files/<zip-同名>/image_NN.ext`
- 不直接把 base64 写进 Markdown
- 删除 Logo/广告图/二维码/装饰图（width/height < 50px 过滤）
- 删除头像：class 含 `avatar` 的 img 一律跳过（不论尺寸）
- 评论区不保留头像，只保留用户上传的说明性截图，命名带 `comment_` 前缀
- SingleFile 有时无法捕获动态加载内容，BS4 和 Playwright 看到的 DOM 可能有差异

### 去站点水印（用户要求时）

付费专栏/课程站点常在正文图**固定角落**（多为右下角）嵌 logo+文字水印（如"极客时间"）。用户要求去水印时：

1. **定位（必须逐图、用原尺寸）**：水印是站点 logo，各图位置大体一致。检测——在角落区域（如右下 x>0.80、y>0.82）搜 logo 特征色（品牌色，高饱和橙/红/蓝）。**两个已踩的坑**：
   - **特征色会命中正文里的同色**（如橙色边框/高亮块）。必须只取**最靠右下的连通块**作 logo，不能把全图橙像素一起框（会得到跨半张图的错误 bbox）。
   - **检测/验证必须在原图上做，不能用拼接缩略图**——缩放会错位，导致漏检（把有水印判成无）。逐张开原图看角落。
2. **框定 bbox（紧贴水印，禁止"一盖到角"）**：水印 = logo（左）+ 文字（右），bbox 要**紧框这两者整体**——上下只含水印高度、左到 logo 左缘、右到文字右缘（文字常延到近图右缘，右边界取到图右缘避免残字，但**上边界不要越过水印顶**）。**绝不能**从 logo 左上直接拉到图右下角：那会盖掉水印外的正文/边框（已踩，把内容擦成白块）。
3. **清除**：
   - 水印压在**纯色/浅色背景** → 盖背景色矩形。背景色取**水印框正下方或正左方紧邻的背景像素**（多为纯白），别取到框线/内容色。
   - 水印压在**内容**上 → inpaint（opencv `cv2.inpaint`），盖矩形会遮内容。
4. **不是所有图都有水印**（内容图、UI 截图、图表常无）——逐图检测，无命中跳过，别误盖。
5. **验证（原尺寸，放大角落）**：去后裁角落**放大 2x** 看：水印全消失（无残字/残 logo 弧）、背景融合、水印外的边框/内容未被盖。有残留→调 bbox 重来。

### 图片压缩（用户要求时）

- **限宽**：宽 > 阈值（默认 1600px，密集数字图表可保守到 2000）的等比缩到阈值，小图不动。1600px 对流程图/UI 截图完全可读。
- **格式**：统一转 **webp**（quality 80）体积最小。PNG/JPEG 皆可转。
- **同步引用**：改扩展名（如 `.jpg`→`.webp`）后，**必须同步更新 Markdown 里的图片引用路径**，否则断链。

---

## 代码块语言标注

富文本编辑器的代码块通常无 `language-*` class。通过内容启发式检测语言（至少 2 个信号才标注）：

| 语言 | 信号（≥2 个匹配，除非注明单信号即可） |
|------|-------------------|
| Go | `package \w+`, `func \w+`, `import (`, `fmt.\w+`, `:=` |
| Python | `from \w+ import`, `def \w+(`, `self.`, `class \w+.*:` |
| JavaScript/TS | `const \w+ =`, `let \w+ =`, `=>`, `require(`, `export` |
| Java | `public class`, `public void`, `public static` |
| Bash/Shell | `mkdir`, `cd`, `go run/mod/build`, `npm`, `pip`, `docker`, `git`、`python xxx.py --flag`（行首） |
| PowerShell | `$env:`, `Get-\w+`/`Set-\w+`（cmdlet 动词-名词）, `-ErrorAction`, 行首 `.\` |
| JSON | 整体被 `{}`/`[]` 包裹 + `"key":` 键值对（单信号+括号闭合即可标） |
| YAML | 行首 `key:` 缩进层级 + `- ` 列表项，无花括号 |
| SQL | `SELECT`/`INSERT`/`CREATE TABLE`/`WHERE`（不区分大小写，≥1 强关键词） |
| Text（非代码） | 目录树字符 `├└│─`；emoji 开头行；**中文占比高的清单/模板/说明**（如 `允许：… 审批：…`、`【主假设行】…` 这类中文字段块）；**中文判定伪代码**（`if 收益≤基准: 不支持` 这类非可运行逻辑，标 text 不标 python，避免误导可运行） |

**判不准时**：信号不足 2 个、或像多语言混合 → 标 `text`（保守），不要猜一个可运行语言。宁可 text 也不误标——误标 python 会让读者以为可直接运行。**所有代码块最终都要有语言标注**（含 `text`），不留裸 ` ``` `。

## 文本清理（SingleFile 特有）

- **PUA 字符**（U+E000-U+F8FF）：`re.sub(r'[-]', '', text)`
- **零宽字符**（U+200B, U+200C, U+200D, U+FEFF, U+2060）：删除
- **NBSP（U+00A0）在代码中要替换为普通空格**：富文本编辑器（Monaco/CodeMirror）渲染缩进时常用 `\xa0`，提取出的代码看起来正常但 Python/shell 会因不可见字符报错。仅对代码 cell/代码块内部做替换（普通段落里的 NBSP 保留语义）

---

## 加粗/斜体

识别 `<strong>` / `<b>` / `font-weight:bold/600-900` / `data-slate-type="bold"` 等，保留格式。

**强调定界符闭合后紧贴非空白 → 加空格（GitHub 目标平台）：** 闭合 `**`/`*`/`_` 右侧紧跟英文/数字/`<`（如 `**标签：**https://...`），CommonMark 把该定界符判为"想开新强调"（右 flanking 失败），配对失败 → 星号字面显示，加粗失效。本地 KaTeX/VS Code 宽容，GitHub 严格。修：闭合定界符与后随非空白间插一个空格 → `**标签：** https://...`。检测 `(\*\*[^*\n]+?\*\*)([A-Za-z0-9<])`。同族坑=markdown 特殊符与内容边界冲突（另见公式的 `$` 边界、数学块裸 `*`）。实测：`**专栏配套代码：**https://...`。

---

## 交互式组件处理

| 交互组件类型 | Markdown 表达方式 | 识别线索 |
|-------------|------------------|---------|
| 手风琴/折叠面板 | H3/H4 标题 + 展开内容直接跟随 | `accordion`/`collapse`/`toggle` 类名 |
| 决策树/流程判断 | code block 内 ASCII art | 嵌套 branch/node 结构 |
| Tab 切换面板 | 所有 Tab 内容按顺序输出，各 Tab 用标题分隔 | `tab`/`panel` 类名 |
| 提示/高亮框 | blockquote（可加 emoji 前缀） | `alert`/`callout`/`tip`/`warning` 类名 |

**原则：** 所有被隐藏的内容都必须在 Markdown 中可见。

---

## BeautifulSoup 解析器选择

**必须使用 `lxml` 解析器**，不得使用 `html.parser`。

原因：SingleFile HTML 经常包含未闭合的 `<th>`/`<td>` 标签，`html.parser` 会嵌套处理，`lxml` 能正确识别同级兄弟关系。

---

## 同源批量处理

多个 HTML 来自同一站点时：

1. 先分析一篇确定 DOM 结构
2. 编写 Python 脚本（BeautifulSoup + lxml）
3. 内置审计计数（DOM 基线 vs Markdown 输出自动对比）
4. 统一打包为一个 zip

---

## 输出结构

```text
<zip-英文名>.zip
└── 文章标题目录/
    ├── 文章标题.md
    └── files/
        └── <zip-英文名>/
            ├── image_01.png
            └── comment_image_01.png
```

ZIP 文件名：英文/数字/下划线/短横线，保留原始数字序号，不用中文。

---

## 删除与保留速查

**保留：** 文章标题/作者/时间、正文段落、各级标题、列表、引用、加粗/斜体、行内代码、代码块、表格、公式、正文图片/图表、关键链接、脚注、有价值评论、块级居中语义

**删除：** 导航栏、侧边栏、页脚、登录弹窗、购买提示、分享/点赞/收藏按钮、广告、推荐阅读、头像、Logo、二维码、Cookie 提示、脚本、CSS、tracking 参数、无价值评论、评论区 UI 控件、**作者开头/结尾寒暄**

---

## 作者寒暄去除（课程/专栏类文章）

课程、专栏、公众号类文章常有作者的开场白和结束语，属社交套话非正文，去掉：

- **开头寒暄**：`你好，我是XXX。` / `你好，我是XXX，欢迎来到《课程名》。` / `大家好` 等自我介绍、欢迎语。删整行。
- **结尾寒暄**：`我们下节课再见！` / `敬请期待！` / `期待你的分享` / `欢迎转发给有需要的朋友` / `点赞在看` 等预告、求转发、道别语。删整行/整句。
- **边界（重要）**：寒暄常与实质内容**混在同一句**。如 `好，我们的导读篇就到这里。最后强调一下：<知识总结…>` —— 只删寒暄引子（`好，我们的导读篇就到这里。最后强调一下：`），**保留后面的实质总结**。不要因为一句里有寒暄就删掉整段内容。
- 正文首段（讲本讲内容的）、思考题、正文性质的结语（有信息量的总结）都保留。
