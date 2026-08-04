#!/usr/bin/env python3
"""docsite_to_md — 把静态文档站(SSG 预渲染 HTML)批量转成干净 markdown 语料。

目标场景:喂 AI 查询的纯文本语料。不保留图片、不做公式高保真、不做站点归档。
当前支持:VitePress(Shiki 高亮)。其它 SSG 靠 --selector 覆盖正文容器。

用法:
  # 单页
  docsite_to_md.py --url https://cap.cloud.sap/docs/cds/cdl --out /tmp/cdl.md
  # 批量(sitemap 或 URL 列表文件)
  docsite_to_md.py --sitemap https://cap.cloud.sap/docs/sitemap.xml \
      --base-url https://cap.cloud.sap/docs --out-dir cap --skip '/releases/'
  docsite_to_md.py --url-list urls.txt --base-url ... --out-dir cap

设计要点(借鉴 html-to-markdown skill 的转换核,按本场景裁剪):
  - 无语义 wrapper 穿透:div/section/article/main 无块子→当行内,有块子→递归(不抛错)
  - 代码块:Shiki 语言在外层 <div class="language-xxx">;code.get_text() 换行已正确
  - fence:动态长度 max(3, 内部最长连续反引号+1),避开正文反引号
  - 图片全砍:遇 img 返空,顺手丢只包一张图的父 <a> 死链
  - 清洗:去零宽字符、VitePress 锚点 [​](#…)、收紧多余空行
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from xml.etree import ElementTree

try:
    from bs4 import BeautifulSoup, Tag, NavigableString
except ImportError:
    sys.exit("需要 bs4: pip install beautifulsoup4")
import markdownify

# ── 正文容器候选(按序尝试) ───────────────────────────────────────────
BODY_SELECTORS = [".vp-doc", "main .content", "article", "main", ".markdown-body"]

# 正文里要删的噪声(导航/侧栏/编辑链接/脚本等)
NOISE_SELECTORS = [
    "script", "style", ".aside", ".VPDocAsideOutline",
    ".edit-info", ".prev-next", ".VPDocFooter", ".pager",
    ".table-of-contents", ".vp-doc-footer",
    # VitePress code-group(tab 组)的 tab 栏:<label> 文本(如 "Java"/"Node.js",
    # 单 tab 时甚至是语言名 "sh")会泄漏成裸文本行。整条 .tabs 删掉(含 radio input)。
    ".vp-code-group .tabs",
    # 以下收窄到代码块内,避免误删正文 UI 词(如 <button>Save</button>、
    # i18n 文档正文里的 <span class="lang">zh-CN</span>):
    "div[class*=language] button",       # 复制按钮(裸 button 会吞正文)
    "div[class*=language] span.lang",    # 代码块语言角标(否则转成裸行)
    ".copy", ".copied",                  # 复制按钮类名(通用兜底)
    # VitePress home layout 的 feature 卡片图标容器:<div class="icon"> 里是
    # 装饰性 emoji(⭕️🍀🏆💯)或图标,会泄漏成正文裸行。收窄到 VitePress feature
    # 卡片的确切结构(article.box / .VPFeature),不裸删 .icon,也不用宽泛的
    # ".box .icon"(会误伤第三方主题里任何 class 含 box 的容器内的 .icon)。
    "article.box .icon", ".VPFeature .icon",
]

# 零宽/PUA 字符(SingleFile、复制粘贴常带)
_ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿-]")
# VitePress 标题锚点: [​](#anchor) 或 [#](#anchor) —— markdownify 产出的锚点链接
_ANCHOR_LINK = re.compile(r"\[[​#\s]*\]\(#[^)]*\)")
# 3+ 连续空行 → 2 行
_MULTI_BLANK = re.compile(r"\n{3,}")
# VitePress 属性表把软换行 <wbr> / 断行 <br> / 强调 <i> 等以【转义文本】塞进
# 单元格(源码 &lt;wbr&gt;),markdownify 转 <table> 时不递归转,还原成裸标签文本
# 混进 md。只在【表格单元格文本节点】里清,不碰正文/行内代码里的标签字面量。
_CELL_DROP = re.compile(r"<wbr\s*/?>")                        # 软换行占位,删
_CELL_SPACE = re.compile(r"<br\s*/?>")                        # 断行 → 空格
_CELL_UNWRAP = re.compile(r"</?(?:i|b|em|strong|sub|sup|nobr)\b[^>]*>")  # 强调标签,留文本


def fetch(url: str, timeout: int = 30, retries: int = 3) -> str:
    """抓 HTML。静态 SSG 站正文已在 HTML 里,无需浏览器。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "docsite-to-md/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            # 4xx(404 等)是确定性失败,重试无意义,立即抛
            if 400 <= e.code < 500:
                raise RuntimeError(f"fetch failed {url}: HTTP {e.code}") from e
            last = e
            time.sleep(1.5 * (i + 1))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def pick_body(soup: BeautifulSoup, selector: str | None):
    """选正文容器。指定 selector 优先,否则按候选表试。"""
    if selector:
        el = soup.select_one(selector)
        if el:
            return el
        raise RuntimeError(f"selector {selector!r} 未命中")
    # VitePress home layout(layout: home)特判:整页正文在 .VPHome(hero +
    # feature 卡片 + 导航),而 .vp-doc 是空壳。此时页面里可能还散落局部
    # <article>/<main> 卡片(如 CAP 首页的 <article class="box">,仅 113 字符),
    # 排在候选表前面会抢先命中、只抽到残片。故在 .vp-doc 空/缺 且 .VPHome
    # 有内容时,直接优先返回 .VPHome。doc layout 页 .vp-doc 必有内容,不进此路。
    vp_doc = soup.select_one(".vp-doc")
    if vp_doc is None or not vp_doc.get_text(strip=True):
        vp_home = soup.select_one(".VPHome")
        if vp_home and vp_home.get_text(strip=True):
            return vp_home
    # 常规:命中但为空容器要跳过,继续试下一候选。
    for sel in BODY_SELECTORS:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el
    raise RuntimeError("找不到正文容器,用 --selector 指定")


def strip_noise_and_images(body: Tag) -> None:
    """删噪声节点 + 全砍图片(含只包一张图的父 <a> 死链)。"""
    for sel in NOISE_SELECTORS:
        for t in body.select(sel):
            t.decompose()
    # 表格单元格里的裸标签文本(<wbr>/<br>/<i> 等,VitePress 属性表以转义文本塞入,
    # markdownify 不递归转 <td>)。只清单元格内的【文本节点】,且跳过 code/pre/kbd/samp
    # 内的文本 —— 属性表值列常放行内代码,里面的 <br>/<wbr> 是要展示的标签字面量,不能动。
    for cell in body.find_all(["td", "th"]):
        for s in cell.find_all(string=True):
            if s.find_parent(["code", "pre", "kbd", "samp"]):
                continue
            new = _CELL_DROP.sub("", str(s))
            new = _CELL_SPACE.sub(" ", new)
            new = _CELL_UNWRAP.sub("", new)
            if new != str(s):
                s.replace_with(new)
    for img in body.find_all("img"):
        parent = img.parent
        # 父 <a> 只包这一张图 → 整个链接丢弃,否则只删 img
        if (isinstance(parent, Tag) and parent.name == "a"
                and not parent.get_text(strip=True)
                and len(parent.find_all("img")) == 1):
            parent.decompose()
        else:
            img.decompose()
    # 空 figure(图删光后剩壳)
    for fig in body.find_all("figure"):
        if not fig.get_text(strip=True):
            fig.decompose()
    # 空 heading:两种来源 —— ①图砍后剩壳(img 上面已删) ②源里就空(只含 header-anchor
    # + 零宽字符,如 VitePress <h4 id=""><a href="#">​</a></h4>)。零宽 strip 不掉,先剥再判。
    # (img 在上面已 decompose,故不必再判 h.find("img");纯图 heading 图删后即空,该删。)
    for h in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if not _ZERO_WIDTH.sub("", h.get_text()).strip():
            h.decompose()


def _href_link_text(href: str | None) -> str:
    """从 href 抽一段可读的链接文字(路径尾段)。只对像样的路径 href 生效;
    退化 href(空 / 根 "/" / 纯锚点 "#x" / 纯 query "?x")没有有意义的文字,
    返回 "" —— 上游据此把无 CTA/无标题的空壳卡片链接直接删掉,而非塞垃圾文字。"""
    if not href:
        return ""
    # 剥 query / hash,只看路径部分
    path = href.split("#", 1)[0].split("?", 1)[0]
    seg = path.rstrip("/").rsplit("/", 1)[-1]
    return seg


def unwrap_feature_links(body: Tag) -> None:
    """VitePress home layout 的 feature 卡片是整块可点的 <a>(class VPFeature),
    内含 <h2 标题>/<p 详情>/<div link-text CTA>。markdownify 遇 <a> 包块级元素时
    会把标题、列表全塞进链接文本 [## 标题 ...](url),渲染出来标题在方括号里、乱。

    改法:把 a 内的块级内容(标题/详情)提到 a 之前当正文,a 只留底部 CTA 文字
    (如 "Getting Started")+ href,转成正常的行尾链接 [Getting Started](url)。
    只认 VitePress 官方 feature 结构(a.VPFeature),不碰普通链接。
    """
    for a in body.select("a.VPFeature"):
        href = a.get("href")
        # 底部 CTA 文字(.link-text)。CTA 是 VitePress schema 里的可选元素,
        # 缺失时不能直接删链接(会丢导航目标),按 标题 → href 尾段 依次兜底。
        cta = a.select_one(".link-text")
        cta_text = cta.get_text(strip=True) if cta else ""
        # 把块级内容(除 CTA 外)逐个提到 a 之前
        card = a.select_one("article.box") or a
        # 卡片标题是 card 的直接子 heading(VitePress 是 <h2 class="title">)。
        # 只找直接子,不用深度搜索 —— 否则 details 里嵌套的 heading 会被误当标题。
        title_text = ""
        for c in card.children:
            if isinstance(c, Tag) and c.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                title_text = c.get_text(strip=True)
                break
        for child in list(card.children):
            if not isinstance(child, Tag):
                continue
            if cta is not None and (child is cta or cta in child.descendants):
                continue
            a.insert_before(child.extract())
        # a 清空,只放链接文字(保留 href → markdownify 转正常行内链接)。
        # 文字优先级:CTA > 卡片标题 > href 的路径尾段。
        a.clear()
        link_text = cta_text or title_text or _href_link_text(href)
        if link_text:
            a.string = link_text
        else:
            a.decompose()  # 无好文字的空壳链接(CTA/标题都没、href 也不像路径),删


def code_language(pre: Tag) -> str:
    """Shiki 语言在外层 <div class="language-xxx">;code/pre class 兜底。"""
    node = pre
    for _ in range(6):  # 向上找 6 层(有些主题多包 line-numbers-wrapper 等)
        if not isinstance(node, Tag):
            break
        for cls in node.get("class", ()) or ():
            m = re.match(r"language-([A-Za-z0-9_+-]+)$", cls)
            if m and m.group(1) not in ("shiki",):
                return m.group(1)
        node = node.parent
    return ""


def max_backticks(s: str) -> int:
    return max((len(m) for m in re.findall(r"`+", s)), default=0)


class DocConverter(markdownify.MarkdownConverter):
    """markdownify 定制:代码块用 Shiki 语言+动态 fence;正文 pre 换行已对。"""

    def convert_pre(self, el, text, parent_tags=None, **kw):
        code_el = el.find("code") or el
        code = code_el.get_text()
        code = code.rstrip("\n")
        lang = code_language(el)
        fence = "`" * max(3, max_backticks(code) + 1)
        return f"\n\n{fence}{lang}\n{code}\n{fence}\n\n"


def html_to_md(html: str, selector: str | None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = pick_body(soup, selector)
    strip_noise_and_images(body)
    unwrap_feature_links(body)
    md = DocConverter(heading_style="ATX", bullets="-").convert_soup(body)
    return clean(md)


def clean(md: str) -> str:
    """机械清洗(fence-aware:代码块内不动)。"""
    md = _ZERO_WIDTH.sub("", md)
    # 按 fence 切段,只清洗非代码段
    out, in_fence, fence_tok = [], False, ""
    for line in md.split("\n"):
        m = re.match(r"^(\s*)(`{3,}|~{3,})", line)
        if m:
            tok = m.group(2)
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif tok[0] == fence_tok[0] and len(tok) >= len(fence_tok):
                in_fence, fence_tok = False, ""
            out.append(line)
            continue
        if in_fence:
            out.append(line)  # 代码内原样
        else:
            line = _ANCHOR_LINK.sub("", line)
            line = re.sub(r"[ \t]+$", "", line)  # 行尾空白
            out.append(line)
    md = "\n".join(out)
    md = _MULTI_BLANK.sub("\n\n", md)
    return md.strip() + "\n"


# ── URL → 输出路径映射 ────────────────────────────────────────────────
def url_to_path(url: str, base_url: str, out_dir: Path) -> Path:
    """https://.../docs/cds/cdl → out_dir/cds/cdl.md; 尾斜杠→index.md

    base_url 不匹配抛 ValueError(批量循环捕获后跳过并报错),不硬拼垃圾路径。
    """
    clean_url = url.split("#")[0].split("?")[0]  # 先剥 query/hash 再判尾斜杠
    base = base_url.rstrip("/")
    # 前缀匹配需边界对齐:base 之后是 / 或结束,避免 /docs 误配 /docs-old
    if clean_url == base:
        rel = ""
    elif clean_url.startswith(base + "/"):
        rel = clean_url[len(base) + 1:]
    else:
        raise ValueError(f"URL {url!r} 不在 base_url {base_url!r} 前缀下")
    trailing_slash = rel.endswith("/")
    rel = rel.strip("/")
    if not rel:
        rel = "index"
    elif trailing_slash:
        rel = rel + "/index"
    return out_dir / f"{rel}.md"


def read_sitemap(url: str) -> list[str]:
    xml = fetch(url)
    root = ElementTree.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in root.findall(".//s:loc", ns) if loc.text]


def main():
    ap = argparse.ArgumentParser(description="静态文档站 → markdown 语料")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="单页 URL")
    src.add_argument("--sitemap", help="sitemap.xml URL")
    src.add_argument("--url-list", help="URL 列表文件(每行一个)")
    ap.add_argument("--out", help="单页输出文件(配 --url)")
    ap.add_argument("--out-dir", help="批量输出根目录")
    ap.add_argument("--base-url", help="URL 前缀,用于算相对路径(批量必填)")
    ap.add_argument("--selector", help="正文容器 CSS selector(覆盖自动探测)")
    ap.add_argument("--skip", action="append", default=[], help="跳过含此子串的 URL(可多次)")
    ap.add_argument("--delay", type=float, default=0.3, help="每页间隔秒")
    ap.add_argument("--limit", type=int, help="最多处理 N 页(调试)")
    args = ap.parse_args()

    if args.url:
        md = html_to_md(fetch(args.url), args.selector)
        if args.out:
            Path(args.out).write_text(md, encoding="utf-8")
            print(f"✓ {args.out} ({len(md)} chars)")
        else:
            print(md)
        return

    # 批量
    if not args.base_url or not args.out_dir:
        ap.error("批量模式需 --base-url 和 --out-dir")
    urls = read_sitemap(args.sitemap) if args.sitemap else \
        [l.strip() for l in Path(args.url_list).read_text().splitlines() if l.strip()]
    urls = [u for u in urls if not any(s in u for s in args.skip)]
    if args.limit:
        urls = urls[:args.limit]
    out_dir = Path(args.out_dir)
    ok = fail = 0
    for i, url in enumerate(urls, 1):
        try:
            md = html_to_md(fetch(url), args.selector)
            path = url_to_path(url, args.base_url, out_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(md, encoding="utf-8")
            ok += 1
            print(f"[{i}/{len(urls)}] ✓ {path}")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(urls)}] ✗ {url}: {e}", file=sys.stderr)
        time.sleep(args.delay)
    print(f"\ndone: {ok} ok, {fail} fail")


if __name__ == "__main__":
    main()
