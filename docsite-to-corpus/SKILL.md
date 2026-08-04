---
name: docsite-to-corpus
description: Use when copying/mirroring a documentation website (VitePress best-supported; other SSG docs like Docusaurus/MkDocs via --selector) into local markdown for AI querying, RAG, or offline corpus — batch-converting many doc pages to clean text, not archiving a single rich page.
---

# docsite-to-corpus

## Overview

把**静态文档站**(SSG 预渲染)批量转成干净 markdown 语料,喂 AI 查询/RAG。

核心原则:**先探测,再批量**。文档站不是单页 —— 页面清单、渲染方式、正文容器、站点特有噪声,每个都得先确认,否则整批爬歪。

**这不是 `html-to-markdown`。** 那个转单个 SingleFile HTML,做高保真归档(公式/图片/评论)。这里转整站,只要文本,砍图片。二者内核(HTML→md)重叠,场景相反。

## When to Use

- 要把某文档站(几十~几百页)变成本地 md 语料库喂 AI
- 触发词:copy docs、mirror site、爬文档、doc corpus、RAG 语料、offline docs
- **不要用**:单页高保真归档(用 `html-to-markdown`);站点是纯 SPA 且无预渲染(需浏览器,本 skill 的 curl 路径不适用)

## 四步流程(顺序不能乱)

```
1. 发现页面清单  → sitemap 优先,没有再 BFS 内链
2. 探测渲染方式  → 用确认 200 的页判静态/SPA
3. 定正文容器    → 确认选哪个 selector
4. 批量转换+清洗 → 跑 docsite_to_md.py
```

### 1. 发现页面清单

**先找 sitemap** —— 但别只试根路径。sitemap 常在子路径:

```bash
for u in /sitemap.xml /docs/sitemap.xml /sitemap_index.xml; do
  curl -s -o /dev/null -w "%{http_code} $u\n" "https://SITE$u"
done
```

⚠️ **根 sitemap 404 ≠ 没有 sitemap**。文档站部署在子路径(`/docs/`)时,sitemap 也在子路径。baseline 测试里 agent 只试根 sitemap、判"无 sitemap"就去猜 URL、全 404 —— 而 `/docs/sitemap.xml` 其实存在。

没有 sitemap 才 BFS:从入口页抓 HTML,正则提同域内链,过滤 assets,收敛成清单。

⚠️ **别逐页猜 URL** —— 猜必错(404)。用 sitemap 或 HTML 里的**原始 href 形式**(尾斜杠敏感:叶子页 `/a/b` 200,`/a/b/` 可能 404;目录页反之)。

### 2. 探测静态还是 SPA

```bash
# 必须用确认 200 的页,不能用可能 404 的
curl -s "https://SITE/KNOWN-200-PAGE" | grep -oE '<h1[^>]*>|class="vp-doc"|<article' | head
```

正文关键词/标题在 HTML 里 → SSG 静态,curl 够。空 `<div id="app">` → 可能 SPA。

⚠️ **404 页会骗你**。SPA 式 404 页是空壳,拿它判会误判整站是 SPA。**只用确认 200 的页判断**。

静态 → 继续。纯 SPA 无预渲染 → 本 skill 不适用,需浏览器(参考 `html-to-markdown` 的 Playwright 路径)。

### 3. 定正文容器

VitePress → `.vp-doc`。Docusaurus → `article` / `.markdown`。MkDocs → `.md-content article`。

选**只含正文**的容器,别选 `<main>`(带侧栏/页脚噪声)。脚本按 `BODY_SELECTORS` 自动试,拿不准用 `--selector` 覆盖。

### 4. 批量转换

```bash
# 有 sitemap
docsite_to_md.py --sitemap https://SITE/docs/sitemap.xml \
    --base-url https://SITE/docs --out-dir OUT --skip '/releases/' --delay 0.3
# 无 sitemap,自备 URL 列表
docsite_to_md.py --url-list urls.txt --base-url https://SITE/docs --out-dir OUT
# 单页调试
python3 docsite_to_md.py --url https://SITE/docs/foo --out /tmp/foo.md
```

脚本细节 `--help`。它已内置这些坑的处理(见下)。

## 站点特有噪声(脚本已处理,验收时核对)

| 噪声 | 来源 | 脚本处理 |
|---|---|---|
| 代码块丢语言 | VitePress/Shiki 语言在外层 `div.language-xxx`,不在 `<pre>` | 向上找 `language-*` 补 fence 标签 |
| 裸语言角标行 | `<span class="lang">cds</span>` | 删 `span.lang` |
| 复制按钮文字 | `<button class="copy">` | 删 button/.copy |
| 标题锚点噪声 | `[​](#anchor)` header-anchor + 零宽字符 | 删空文本锚点 + 去零宽 |
| 页内 TOC 目录 | 自动生成的 outline | 删 nav/.table-of-contents |
| 图片 | 文本语料不需要 | 砍 img,清只包一图的父 `<a>` 死链 |
| code-group tab 标签 | `vp-code-group > .tabs > label`(如 `Java`/`Node.js`,单 tab 时是语言名 `sh`)泄漏成裸文本行 | 删整条 `.tabs`(含 radio input) |
| 表格单元格裸 HTML | VitePress 属性表把 `<wbr>`/`<i>`/`&lt;key&gt;` 以转义文本塞进单元格,markdownify 转 table 不递归转 | DOM 层【只在 `<td>`/`<th>` 文本节点】清:删 `<wbr>`、`<br>`→空格、解包 `<i>` 等强调标签。不碰正文/行内代码里的标签字面量 |
| 空 heading | 图砍后剩壳,或源里就空(`<h4 id=""><a>​</a></h4>` 只含锚点+零宽) | 剥零宽后判空则删(含 img 的不删) |

## Common Mistakes

- **只试根 sitemap 就判无 sitemap** → 子路径也要试(`/docs/sitemap.xml`)
- **拿 404 页判 SPA** → 必用确认 200 的页
- **逐页猜 URL** → 用 sitemap/href 原始形式,尾斜杠敏感
- **pandoc 转** → 不如 markdownify:pandoc 漏 shiki 类名、header-anchor 残留 HTML
- **fence 不隔离清洗** → CJK/空格清洗会误改代码块内空格;清洗必须 fence-aware

## 已知限制

- **VitePress custom-block(`::: tip` / `::: warning`)降级**:标题+内容会压平成裸文本,`tip/warning` 语义标记丢失。对纯文本语料通常可接受,若需保留提示类型请后处理。
- **非 VitePress 站**:Docusaurus/MkDocs 等正文容器不同,需 `--selector` 指定;custom container 处理未针对性适配。
- **编码**:硬编码 utf-8,非 utf-8 站点(罕见)会出现替换字符。
- **code-group 内容合并**:多 tab 代码块(如 Java/Node.js 切换)的 tab 标签已删,但各 tab 的代码本体会顺序拼接输出(无 tab 分隔),读者需自行判断哪段属哪个 tab。
- **链接 URL 里的脏 HTML**:极少数源页在 `<a href>` 属性值里嵌了 `&lt;br&gt;`(源数据本身错),单元格清理只处理文本节点、不动属性,故这类坏 URL 会原样留在 md。罕见(CAP 全站 2 处),不值得为它加属性清洗。

## 工具

- `docsite_to_md.py` — 转换脚本(抓取/选容器/转换/清洗/URL→路径映射)
- 依赖 `requirements.txt`:beautifulsoup4、markdownify
- `tests/` — 固化 VitePress 关键行为(代码块语言、角标砍除、图片砍除、表格保留、fence-aware 清洗、code-group tab 标签砍除、表格单元格裸 HTML 清理、空 heading 砍除、正文/行内代码里标签字面量不误清),防退化
