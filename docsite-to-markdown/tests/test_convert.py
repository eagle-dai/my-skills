"""固化 docsite_to_md 的 VitePress 转换行为,防退化。

离线测试:用内联 HTML 片段(真实 VitePress/Shiki 结构),不碰网络。
跑: python3 -m pytest tests/ -q   或   python3 tests/test_convert.py
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from docsite_to_md import html_to_md, url_to_path  # noqa: E402


def conv(body_html: str) -> str:
    """包成最小 VitePress 页面再转。"""
    page = f'<html><body><main class="main"><div class="vp-doc">{body_html}</div></main></body></html>'
    return html_to_md(page, selector=".vp-doc")


class _Raises:
    """不依赖 pytest 的 assertRaises 上下文管理器。"""
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        assert et is not None and issubclass(et, self.exc), f"未抛 {self.exc.__name__}"
        return True  # 吞掉预期异常


def raises(exc):
    return _Raises(exc)


# ── 代码块:语言在外层 div.language-xxx,Shiki 行结构 ──────────────────
def test_code_block_language_from_wrapper():
    html = '''
    <div class="language-cds">
      <button class="copy"></button>
      <span class="lang">cds</span>
      <pre class="shiki"><code><span class="line"><span>entity Books;</span></span>
<span class="line"><span>entity Authors;</span></span></code></pre>
    </div>'''
    md = conv(html)
    assert "```cds" in md, "代码块该带 cds 语言标签"
    assert "entity Books;" in md
    assert "entity Authors;" in md
    # 语言角标不该变成裸行
    lines = [l for l in md.splitlines() if l.strip() == "cds"]
    assert not lines, f"span.lang 'cds' 不该成裸行: {lines}"


def test_code_block_newlines_preserved():
    """Shiki 行间有真 \\n,get_text 换行正确,不糊成一行。"""
    html = '''
    <div class="language-js">
      <span class="lang">js</span>
      <pre class="shiki"><code><span class="line"><span>const a = 1;</span></span>
<span class="line"><span>const b = 2;</span></span></code></pre>
    </div>'''
    md = conv(html)
    assert "const a = 1;\nconst b = 2;" in md, "代码换行该保留"


def test_code_fence_dynamic_length():
    """代码内含 ``` 时,fence 该用更长的反引号。"""
    html = '''
    <div class="language-md">
      <span class="lang">md</span>
      <pre class="shiki"><code><span class="line"><span>```inner```</span></span></code></pre>
    </div>'''
    md = conv(html)
    assert "````" in md, "内含 ``` 时 fence 该 >=4 反引号"


# ── 图片:全砍,清死链 ─────────────────────────────────────────────────
def test_images_removed():
    html = '<p>text</p><img src="/foo.png" alt="x"><p>more</p>'
    md = conv(html)
    assert "![" not in md, "图片引用该砍掉"
    assert ".png" not in md


def test_image_wrapping_link_removed():
    """只包一张图的 <a> 该整个删,不留空链接。"""
    html = '<a href="/big.png"><img src="/thumb.png"></a><p>after</p>'
    md = conv(html)
    assert "![" not in md
    assert "[](" not in md, "不该留空链接死链"
    assert "big.png" not in md


def test_link_with_text_kept():
    """有文字的链接(含图)不该被误删。"""
    html = '<a href="/page">Read <img src="/i.png"> more</a>'
    md = conv(html)
    assert "/page" in md, "有文字的链接该保留"


# ── 表格保留 ──────────────────────────────────────────────────────────
def test_table_preserved():
    html = '''<table>
      <thead><tr><th>Type</th><th>SQL</th></tr></thead>
      <tbody><tr><td>UUID</td><td>NVARCHAR</td></tr></tbody>
    </table>'''
    md = conv(html)
    assert "| Type" in md and "| SQL" in md, "表头该保留"
    assert "UUID" in md and "NVARCHAR" in md


# ── 噪声清理 ──────────────────────────────────────────────────────────
def test_zero_width_removed():
    html = '<p>a​b﻿c</p>'
    md = conv(html)
    assert "​" not in md and "﻿" not in md


def test_empty_anchor_removed():
    """标题空文本锚点该删,有文字的页内链接保留。"""
    html = '<h2>Title <a class="header-anchor" href="#title">​</a></h2>' \
           '<ul><li><a href="#foo">Foo</a></li></ul>'
    md = conv(html)
    assert "## Title" in md
    assert "[Foo](#foo)" in md, "有文字的目录链接该保留"


# ── 裸标签不误删正文 UI 词(review 回归) ─────────────────────────────
def test_body_button_not_stripped():
    """正文里讲 UI 的 <button>Save</button> 不该被当复制按钮删掉。"""
    html = '<p>Click the <button>Save</button> button.</p>'
    md = conv(html)
    assert "Save" in md, "正文 button 文字该保留"


def test_body_span_lang_not_stripped():
    """正文里 i18n 的 <span class='lang'>zh-CN</span> 不该被当代码角标删。"""
    html = '<p>The <span class="lang">zh-CN</span> locale.</p>'
    md = conv(html)
    assert "zh-CN" in md, "正文 span.lang 文字该保留"


def test_code_copy_button_stripped():
    """代码块内的复制按钮/语言角标仍该删。"""
    html = '''<div class="language-cds">
      <button class="copy"></button><span class="lang">cds</span>
      <pre class="shiki"><code><span class="line"><span>x;</span></span></code></pre>
    </div>'''
    md = conv(html)
    assert not [l for l in md.splitlines() if l.strip() == "cds"], "角标不该成裸行"
    assert "```cds" in md


def test_feature_card_icon_stripped():
    """VitePress home feature 卡片的 <div class='icon'> 装饰 emoji 该删,
    卡片标题/正文保留。"""
    html = (
        '<article class="box">'
        '<div class="icon">⭕️</div>'
        '<h2>Rapid Development</h2><p>Jumpstart & grow.</p>'
        '</article>'
    )
    md = conv(html)
    assert "⭕️" not in md, "feature 卡片图标 emoji 该删"
    assert "Rapid Development" in md, "卡片标题该保留"
    assert "Jumpstart" in md, "卡片正文该保留"


def test_plain_icon_not_in_feature_card_kept():
    """防误伤:正文里不在 .box/.VPFeature 内的 <div class='icon'> 不该被删
    (.icon 是通用类名,只在 feature 卡片内才当装饰删)。"""
    html = '<div class="icon">✅ Done</div><p>Body text.</p>'
    md = conv(html)
    assert "Done" in md, "非 feature 卡片的 .icon 内容该保留"
    assert "Body text" in md


def test_feature_link_unwrapped():
    """VitePress home feature 卡片是整块可点的 <a class='VPFeature'>,内含标题/
    详情/底部 CTA。该拆开:标题成正常 heading、CTA 成行尾链接,而非把整块塞进
    [## 标题 ...](url)。"""
    html = (
        '<a class="VPLink VPFeature" href="/docs/get-started/">'
        '<article class="box">'
        '<div class="icon">⭕️</div>'
        '<h2 class="title">Rapid Development</h2>'
        '<p class="details">Jumpstart and grow.</p>'
        '<div class="link-text"><p class="link-text-value">Getting Started</p></div>'
        '</article></a>'
    )
    md = conv(html)
    # 标题该是独立 heading 行,不在方括号里
    assert any(l.strip() == "## Rapid Development" for l in md.splitlines()), \
        "卡片标题该拆成正常 heading"
    assert "Jumpstart and grow" in md
    # CTA 该是行尾链接
    assert "[Getting Started](/docs/get-started/)" in md, "CTA 该成行尾链接"
    assert "[## Rapid Development" not in md, "标题不该被包进链接文本"


def test_plain_link_not_unwrapped():
    """防误伤:普通行内链接(非 VPFeature)不该被拆。"""
    html = '<p>See <a href="/x">the guide</a> for details.</p>'
    md = conv(html)
    assert "[the guide](/x)" in md, "普通链接该原样保留"


def test_feature_link_no_cta_keeps_link_via_title():
    """VitePress feature 卡片的 .link-text CTA 是可选的。缺 CTA 时不该静默
    丢掉链接 —— 该用卡片标题当链接文字,保住 href 导航目标。"""
    html = (
        '<a class="VPFeature" href="/docs/get-started/">'
        '<article class="box">'
        '<h2 class="title">Rapid Development</h2>'
        '<p class="details">Jumpstart and grow.</p>'
        '</article></a>'
    )
    md = conv(html)
    assert "Jumpstart and grow" in md
    assert "[Rapid Development](/docs/get-started/)" in md, \
        "缺 CTA 时该用标题当链接文字,不丢 href"


def test_feature_link_no_cta_no_title_falls_back_to_href():
    """CTA 和标题都缺时,退到 href 尾段当链接文字,仍不丢导航。"""
    html = (
        '<a class="VPFeature" href="/docs/guides/">'
        '<article class="box"><p class="details">Body only.</p></article></a>'
    )
    md = conv(html)
    assert "Body only" in md
    assert "](/docs/guides/)" in md, "该保留 href 链接,文字用尾段兜底"
    assert "[guides]" in md, "href 尾段 'guides' 该当链接文字"


def test_multiple_feature_cards_order_preserved():
    """多张 feature 卡片:各自拆开,顺序不乱。第一张【无 CTA】走标题兜底,
    第二张有 CTA 走原路径 —— 覆盖两条链接文字路径 + 多卡片顺序。"""
    html = (
        '<a class="VPFeature" href="/a"><article class="box">'
        '<h2>First Card</h2><p>Alpha.</p></article></a>'          # 无 CTA → 标题兜底
        '<a class="VPFeature" href="/b"><article class="box">'
        '<h2>Second Card</h2><p>Beta.</p>'
        '<div class="link-text"><p>Go B</p></div></article></a>'   # 有 CTA
    )
    md = conv(html)
    assert md.index("First Card") < md.index("Second Card"), "卡片顺序该保持"
    assert "[First Card](/a)" in md, "无 CTA 的第一张该用标题当链接文字"
    assert "[Go B](/b)" in md, "有 CTA 的第二张走 CTA"
    assert "Alpha" in md and "Beta" in md


def test_feature_link_degenerate_href_dropped():
    """退化 href(根 / 纯锚点 / 纯 query / 相对 ./ ..)没有有意义的尾段文字。
    无 CTA/标题时该删掉空壳链接,而非塞 '/' '#x' '?x' '.' '..' 这种垃圾。"""
    for bad in ("/", "#section", "?tab=1", "./", "../"):
        html = (
            f'<a class="VPFeature" href="{bad}">'
            '<article class="box"><p class="details">Just body.</p></article></a>'
        )
        md = conv(html)
        assert "Just body" in md, f"正文该保留 (href={bad})"
        assert bad not in md, f"退化 href {bad!r} 不该成链接文字"
        assert "](" not in md, f"不该生成链接 (href={bad})"


def test_degenerate_href_with_title_keeps_link_via_title():
    """隔离 _href_link_text guard:卡片【有标题】但 href 退化(#section)时,
    该用标题当链接文字保住链接 —— 退化的是 href 尾段,标题优先级更高。
    (证明 drop 只发生在 CTA+标题都缺时,不是一见退化 href 就删。)"""
    html = (
        '<a class="VPFeature" href="#section">'
        '<article class="box"><h2>Has Title</h2><p>Body.</p></article></a>'
    )
    md = conv(html)
    assert "[Has Title](#section)" in md, "有标题时该用标题当链接文字,链接保留"


def test_box_icon_scoped_to_article_box():
    """收窄:只删 article.box 内的 .icon,第三方主题普通 <div class='box'>
    (非 article)内的 .icon 不该被误删。两个方向都测。"""
    # 正向:article.box 内的 .icon 该删
    stripped = conv('<article class="box"><div class="icon">🎯</div>'
                    '<h2>Card</h2><p>Detail.</p></article>')
    assert "🎯" not in stripped, "article.box 内的 .icon 该被删"
    assert "Card" in stripped and "Detail" in stripped
    # 负向:非 article 的 .box 内 .icon 该保留
    kept = conv('<div class="box"><span class="icon">📌 keep</span> Note text.</div>')
    assert "keep" in kept, "非 article.box 容器内的 .icon 不该被删"
    assert "Note text" in kept


def test_code_group_tab_labels_stripped():
    """VitePress code-group 的 tab 栏 <label> 文本(Java/Node.js,单 tab 时甚至是
    语言名如 sh)会泄漏成裸文本行 —— 整条 .tabs 该删。"""
    html = '''<div class="vp-code-group">
      <div class="tabs">
        <input type="radio" id="t1" checked><label for="t1">Java</label>
        <input type="radio" id="t2"><label for="t2">Node.js</label>
      </div>
      <div class="blocks">
        <div class="language-sh active"><span class="lang">sh</span>
          <pre class="shiki"><code><span class="line"><span>cf apps</span></span></code></pre>
        </div>
      </div>
    </div>'''
    md = conv(html)
    assert not [l for l in md.splitlines() if l.strip() in ("Java", "Node.js", "sh")], \
        "tab 标签不该成裸行"
    assert "cf apps" in md and "```sh" in md, "代码本体该保留"


def test_table_cell_inline_html_cleaned():
    """VitePress 属性表把 <wbr>(软换行)/<i>(斜体)以转义文本塞进单元格,
    markdownify 转 table 时不递归转,还原成裸标签混进 md。该清成纯文本。"""
    html = '''<table><thead><tr><th>Property</th><th>Desc</th></tr></thead>
      <tbody><tr>
        <td>cds.&lt;wbr&gt;security.&lt;wbr&gt;mock.&lt;wbr&gt;<i>&lt;key&gt;</i>.&lt;wbr&gt;id</td>
        <td>The ID<br>of the user.</td>
      </tr></tbody></table>'''
    md = conv(html)
    assert "<wbr>" not in md, "软换行标记该删"
    assert "<i>" not in md and "</i>" not in md, "斜体标签该解包"
    assert "<br>" not in md, "断行该转空格"
    assert "cds.security.mock" in md, "属性名该连贯"


def test_prose_literal_tags_not_clobbered():
    """单元格 HTML 清理只限【表格内文本节点】,不碰正文里讲 HTML 标签的字面量。
    回归:曾用文本层正则清 <wbr>/<br>/<i>,把正文 'the <b> tag' 里的 <b> 也吞了。"""
    html = '<p>The tag &lt;b&gt; makes text bold, &lt;br&gt; breaks a line.</p>'
    md = conv(html)
    assert "<b>" in md and "<br>" in md, "正文里讲的 HTML 标签字面量该原样保留"


def test_inline_code_tags_not_clobbered():
    """行内代码里的标签字面量(文档讲 <br>/<wbr> 标签)不该被清空。
    回归:文本层正则挡不住单反引号行内代码,曾把 `<br>` 清成空 ``。"""
    html = '<p>Use <code>&lt;br&gt;</code> and <code>&lt;wbr&gt;</code> tags.</p>'
    md = conv(html)
    assert "`<br>`" in md and "`<wbr>`" in md, "行内代码里的标签该保留"


def test_table_cell_inline_code_tags_not_clobbered():
    """单元格清理跳过 code/pre 内文本:属性表值列常放行内代码,里面展示的
    <br>/<wbr> 标签字面量不能当噪声清掉。回归:DOM 遍历曾无差别抓 code 内文本。"""
    html = '<table><tbody><tr><td>lineBreak</td>' \
           '<td>Use <code>&lt;br&gt;</code> or <code>&lt;wbr&gt;</code></td></tr></tbody></table>'
    md = conv(html)
    assert "`<br>`" in md and "`<wbr>`" in md, "单元格内行内代码里的标签该保留"


def test_empty_heading_removed():
    """空 heading 两种来源都该删:①图砍后剩壳 ②源里就空(只含 header-anchor
    + 零宽字符,零宽 strip 不掉需先剥)。含 img 的 heading 不误删。"""
    html = '<h4 id=""><a class="header-anchor" href="#">​</a></h4>' \
           '<h2>Real Title</h2>'
    md = conv(html)
    assert not [l for l in md.splitlines() if l.strip() in ("#", "##", "###", "####")], \
        "空 heading 不该剩裸 # 行"
    assert "## Real Title" in md, "有文字的 heading 保留"


# ── fence-aware 清洗:代码块内空格不动 ─────────────────────────────────
def test_fence_aware_no_trailing_strip_inside_code():
    """代码块内行尾空格(缩进对齐用)不该被清洗动;仅非代码行清行尾。"""
    html = '''
    <div class="language-py">
      <span class="lang">py</span>
      <pre class="shiki"><code><span class="line"><span>def f():    </span></span>
<span class="line"><span>    pass</span></span></code></pre>
    </div>'''
    md = conv(html)
    assert "    pass" in md, "代码块内缩进该保留"


# ── 正文容器自动选择(pick_body,不传 selector) ───────────────────────
def test_home_layout_picks_vphome_when_vpdoc_empty():
    """VitePress home layout:.vp-doc 存在但空,正文在 .VPHome。
    自动选择该跳过空 .vp-doc,抽 .VPHome。"""
    page = (
        '<html><body><main class="main">'
        '<div class="vp-doc"></div>'
        '<div class="VPHome"><h1>CAP Docs</h1><p>Build enterprise apps.</p></div>'
        '</main></body></html>'
    )
    md = html_to_md(page, selector=None)
    assert "CAP Docs" in md, "空 .vp-doc 该被跳过,抽到 .VPHome"
    assert "Build enterprise apps" in md


def test_home_layout_vphome_wins_over_local_article():
    """真实 CAP 首页坑:home layout 里散落局部 <article class="box">(仅一张
    feature 卡片),排在候选表 .VPHome 前面会抢先命中、只抽到残片。
    .vp-doc 空 → 该优先返回完整 .VPHome,而非局部 article。"""
    page = (
        '<html><body>'
        '<div class="vp-doc container"></div>'
        '<div class="VPHome">'
        '<div class="VPHero"><h1><span class="name">Full Hero Title</span></h1>'
        '<p class="tagline">Full hero tagline text.</p></div>'
        '<article class="box"><h2>Rapid Development</h2><p>Local card only.</p></article>'
        '</div>'
        '</body></html>'
    )
    md = html_to_md(page, selector=None)
    assert "Full Hero Title" in md, "该抽完整 .VPHome 的 hero,不被局部 article 抢走"
    assert "Full hero tagline text" in md
    assert "Rapid Development" in md, ".VPHome 内的局部卡片也应一并抽到"


def test_doc_layout_still_picks_nonempty_vpdoc():
    """防回归:正常 doc 页 .vp-doc 有内容,即使 main 也匹配,
    仍优先抽 .vp-doc(空容器跳过逻辑不该带偏正常页)。"""
    page = (
        '<html><body><main class="main">'
        '<div class="vp-doc"><h1>Real Page</h1><p>Doc body here.</p></div>'
        '</main></body></html>'
    )
    md = html_to_md(page, selector=None)
    assert "Real Page" in md
    assert "Doc body here" in md


def test_no_vpdoc_no_vphome_uses_candidate_loop():
    """.vp-doc 和 .VPHome 都缺时,该退回候选表(article/main 等)照常抽。"""
    page = (
        '<html><body>'
        '<article><h1>Article Page</h1><p>Article body.</p></article>'
        '</body></html>'
    )
    md = html_to_md(page, selector=None)
    assert "Article Page" in md
    assert "Article body" in md


def test_all_candidates_empty_raises():
    """所有候选容器都存在但全空 → 该抛 RuntimeError,不返回空壳。"""
    page = (
        '<html><body>'
        '<div class="vp-doc"></div><article></article><main></main>'
        '</body></html>'
    )
    with raises(RuntimeError):
        html_to_md(page, selector=None)


# ── URL → 路径映射 ────────────────────────────────────────────────────
def test_url_to_path():
    base, out = "https://x.com/docs", Path("cap")
    assert url_to_path("https://x.com/docs/cds/cdl", base, out) == out / "cds/cdl.md"
    # 尾斜杠 → index
    assert url_to_path("https://x.com/docs/cds/", base, out) == out / "cds/index.md"
    # 根 → index
    assert url_to_path("https://x.com/docs/", base, out) == out / "index.md"
    assert url_to_path("https://x.com/docs", base, out) == out / "index.md"


def test_url_to_path_base_with_trailing_slash():
    """base_url 带尾斜杠也该正常。"""
    assert url_to_path("https://x.com/docs/a", "https://x.com/docs/", Path("o")) == Path("o/a.md")


def test_url_to_path_prefix_substring_trap():
    """/docs 不该误配 /docs-old(前缀子串陷阱)。"""
    with raises(ValueError):
        url_to_path("https://x.com/docs-old/x", "https://x.com/docs", Path("o"))


def test_url_to_path_base_mismatch_raises():
    """base 不匹配该抛错,不硬拼垃圾路径。"""
    with raises(ValueError):
        url_to_path("https://other.com/a/b", "https://x.com/docs", Path("o"))


def test_url_to_path_query_and_trailing_slash():
    """query/hash 该先剥再判尾斜杠:.../cds/?x=1 → cds/index.md 而非 cds/.md"""
    base, out = "https://x.com/docs", Path("o")
    assert url_to_path("https://x.com/docs/cds/?x=1", base, out) == out / "cds/index.md"
    assert url_to_path("https://x.com/docs/cds/cdl#anchor", base, out) == out / "cds/cdl.md"


# ── keep-images: URL 解析 ─────────────────────────────────────────────
from docsite_to_md import resolve_image_url  # noqa: E402


def test_resolve_image_url_relative():
    r = resolve_image_url("/docs/assets/x.svg", "https://cap.cloud.sap/docs/cds/")
    assert r == "https://cap.cloud.sap/docs/assets/x.svg"


def test_resolve_image_url_absolute_kept():
    r = resolve_image_url("https://cdn.x/y.png", "https://s/p/")
    assert r == "https://cdn.x/y.png"


def test_resolve_image_url_data_uri_kept():
    r = resolve_image_url("data:image/png;base64,AAAA", "https://s/p/")
    assert r == "data:image/png;base64,AAAA"


def test_resolve_image_url_empty_none():
    assert resolve_image_url("", "https://s/p/") is None
    assert resolve_image_url(None, "https://s/p/") is None


# ── keep-images: 本地路径 + 相对引用 ──────────────────────────────────
from docsite_to_md import image_local_path, image_rel_href  # noqa: E402


def test_image_local_path_from_url():
    # 图在 .../assets/ 下:剥到 assets/ 后,存 out/assets/<file>,不带冗余层
    p = image_local_path("https://cap.cloud.sap/docs/assets/csn.svg", Path("cap"))
    assert p == Path("cap/assets/csn.svg")


def test_image_local_path_no_assets_marker_keeps_path():
    # 非 assets 结构:用完整 url path(去域名)防撞名
    p = image_local_path("https://s/docs/a/b/pic.png", Path("out"))
    assert p == Path("out/assets/docs/a/b/pic.png")


def test_image_local_path_nested_under_assets():
    # assets 后还有子目录 → 保留子结构
    p = image_local_path("https://s/docs/assets/img/pic.png", Path("out"))
    assert p == Path("out/assets/img/pic.png")


def test_image_local_path_data_uri_hashed():
    p = image_local_path("data:image/png;base64,iVBORw0AAA", Path("out"))
    assert p.parent == Path("out/assets/inline")
    assert p.suffix == ".png"


def test_image_rel_href_sibling_assets():
    href = image_rel_href(Path("out/assets/csn.svg"), Path("out/cds/index.md"))
    assert href == "../assets/csn.svg"


def test_image_rel_href_top_level_md():
    href = image_rel_href(Path("out/assets/x.svg"), Path("out/index.md"))
    assert href == "assets/x.svg"


def test_image_rel_href_space_encoded():
    """文件按真名(空格)存,但 md 引用里裸空格会截断 URL,须编码成 %20;
    路径分隔 / 保留。"""
    href = image_rel_href(Path("out/assets/remote services.svg"),
                          Path("out/java/p.md"))
    assert href == "../assets/remote%20services.svg", href
    assert " " not in href, "引用里不该有裸空格"


# ── keep-images: 落盘 + 缓存 ──────────────────────────────────────────
import tempfile  # noqa: E402
from docsite_to_md import store_image, ImageContext  # noqa: E402


def _ctx(tmp, downloader, page="https://s/docs/cds/", md_rel="cds/index.md"):
    out = Path(tmp)
    return ImageContext(page_url=page, out_dir=out,
                        md_path=out / md_rel, downloader=downloader)


def test_store_image_http_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, lambda url: b"<svg>ok</svg>")
        p = store_image("https://s/docs/assets/x.svg", ctx)
        assert p is not None and p.exists()
        assert p.read_bytes() == b"<svg>ok</svg>"


def test_store_image_download_fail_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, lambda url: None)
        p = store_image("https://s/docs/assets/bad.png", ctx)
        assert p is None


def test_store_image_cache_hit_no_second_download():
    calls = []

    def dl(url):
        calls.append(url)
        return b"data"

    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, dl)
        p1 = store_image("https://s/docs/assets/x.png", ctx)
        p2 = store_image("https://s/docs/assets/x.png", ctx)
        assert p1 == p2
        assert len(calls) == 1, "同图第二次该走缓存,不重复下载"


def test_store_image_data_uri_decoded():
    raw = b"\x89PNG\r\n"
    data_uri = "data:image/png;base64," + base64.b64encode(raw).decode()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, lambda url: None)  # data uri 不走 downloader
        p = store_image(data_uri, ctx)
        assert p is not None and p.read_bytes() == raw


def test_store_image_collision_raises():
    """两个不同 URL 剥 assets/ 后撞到同一本地路径,报错不静默覆盖。"""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, lambda url: b"data")
        store_image("https://s/a/assets/logo.png", ctx)  # 先落一个
        try:
            store_image("https://s/b/assets/logo.png", ctx)  # 剥后同为 assets/logo.png
        except ValueError as e:
            assert "撞名" in str(e), f"异常消息不含'撞名': {e}"
        else:
            assert False, "未抛 ValueError"


def test_store_image_traversal_skipped():
    """畸形 src 含 ../ 逃出 out_dir 时跳过返 None,不写盘。"""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(tmp, lambda url: b"data")
        # path 无 assets/ 段,用完整 path;含 ../ 逃逸
        p = store_image("https://s/../../../etc/evil.png", ctx)
        assert p is None
        assert ctx.cache == {}, "越界路径不该进缓存"


def test_downloader_oversize_returns_none():
    """超大响应(> 上限)跳过返 None。"""
    from docsite_to_md import _make_downloader, _MAX_IMAGE_BYTES
    import urllib.request
    from unittest import mock

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1):
            return b"x" * (_MAX_IMAGE_BYTES + 1) if n < 0 else b"x" * n

    dl = _make_downloader()
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp()):
        assert dl("https://s/huge.png") is None


# ── keep-images: 端到端(注入 fake downloader) ───────────────────────
def conv_keep(body_html, downloader, page="https://s/docs/cds/", md_rel="cds/index.md"):
    """keep-images 模式转换,注入 fake downloader + tmp out_dir。返 (md, out_dir)。"""
    page_html = (f'<html><body><main class="main"><div class="vp-doc">'
                 f'{body_html}</div></main></body></html>')
    tmp = tempfile.mkdtemp()
    out = Path(tmp)
    ctx = ImageContext(page_url=page, out_dir=out, md_path=out / md_rel,
                       downloader=downloader)
    md = html_to_md(page_html, selector=".vp-doc", image_ctx=ctx)
    return md, out


def test_keep_images_localizes_and_rewrites():
    md, out = conv_keep('<p>t</p><img src="/docs/assets/csn.svg" alt="arch">',
                        lambda url: b"<svg/>")
    assert "![arch](../assets/csn.svg)" in md, "该保留图并重写为相对路径"
    assert (out / "assets/csn.svg").exists(), "图该落盘"


def test_keep_images_download_fail_placeholder():
    md, _ = conv_keep('<img src="/docs/assets/x.png" alt="diagram">',
                      lambda url: None)
    assert "*[图片: diagram]*" in md, "下载失败该降级为占位"
    assert "![" not in md, "失败不该留 md 图引用"


def test_keep_images_fail_no_alt_placeholder():
    md, _ = conv_keep('<img src="/docs/assets/x.png">', lambda url: None)
    assert "*[图片]*" in md, "无 alt 失败占位"


def test_keep_images_default_still_strips():
    """不传 image_ctx 时,现有砍图行为不变。"""
    page = ('<html><body><main class="main"><div class="vp-doc">'
            '<img src="/foo.png" alt="x"><p>t</p></div></main></body></html>')
    md = html_to_md(page, selector=".vp-doc")  # 无 image_ctx
    assert "![" not in md and ".png" not in md


def test_keep_images_single_page_self_contained():
    """单页模式(out_dir=md 父目录):图落 md 同级 assets/,引用 assets/x 自包含。"""
    md, out = conv_keep('<img src="/docs/assets/x.svg" alt="a">',
                        lambda url: b"<svg/>", md_rel="foo.md")
    assert "![a](assets/x.svg)" in md, "md 同级 assets 引用该无 ../ 前缀"
    assert (out / "assets/x.svg").exists()


def test_keep_images_shared_cache_across_pages():
    """批量共享 cache:同图两页只下一次。"""
    calls = []

    def dl(url):
        calls.append(url)
        return b"<svg/>"

    tmp = tempfile.mkdtemp()
    out = Path(tmp)
    cache = {}
    for md_rel in ("cds/a.md", "cds/b.md"):
        ctx = ImageContext(page_url="https://s/docs/cds/", out_dir=out,
                           md_path=out / md_rel, downloader=dl, cache=cache)
        page = ('<html><body><main class="main"><div class="vp-doc">'
                '<img src="/docs/assets/shared.svg" alt="s"></div></main></body></html>')
        html_to_md(page, selector=".vp-doc", image_ctx=ctx)
    assert len(calls) == 1, "同图跨页该走共享缓存只下一次"


# ── 图片文件名:URL 编码要解码,存盘名与引用名一致 ──────────────
from docsite_to_md import read_sitemap  # noqa: E402


def test_image_local_path_url_decoded():
    """URL 里 %20 等编码,存盘用解码后的真名(空格),否则引用侧解码后找不到文件。"""
    p = image_local_path("https://s/docs/assets/remote%20services.svg", Path("out"))
    assert p == Path("out/assets/remote services.svg"), p
    # 编码残留不该出现在文件名里
    assert "%20" not in str(p)


def test_image_encoded_url_roundtrip_file_real_ref_encoded():
    """端到端:src 含 %20 → 文件按空格真名落盘,md 引用用 %20 编码,两侧对得上。"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        ctx = ImageContext(page_url="https://s/docs/java/p", out_dir=out,
                           md_path=out / "java/p.md",
                           downloader=lambda u: b"<svg/>")
        page = ('<html><body><main><div class="vp-doc">'
                '<img src="/docs/assets/remote%20services.svg" alt="a">'
                '</div></main></body></html>')
        md = html_to_md(page, selector=".vp-doc", image_ctx=ctx)
        # 引用侧:%20 编码,无裸空格
        assert "remote%20services.svg" in md, md
        assert "remote services.svg" not in md, "引用不该有裸空格"
        # 文件侧:真名(空格)
        files = [f for _, _, fs in os.walk(out) for f in fs]
        assert "remote services.svg" in files, files


def test_store_image_data_uri_plain_url_decoded(tmp_path=None):
    """非 base64 data-URI 的明文 payload 要 urldecode 后再存,否则存出带 %3C 的坏 SVG。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        ctx = ImageContext(page_url="https://s/docs/p", out_dir=out,
                           md_path=out / "p.md",
                           downloader=lambda u: None)
        data_uri = "data:image/svg+xml,%3Csvg%3E%3C%2Fsvg%3E"
        p = store_image(data_uri, ctx)
        assert p is not None
        content = p.read_bytes()
        assert b"<svg>" in content, f"应解码成真 SVG,实际: {content!r}"
        assert b"%3C" not in content, "不该有编码残留"


# ── 双重转义实体:单元格与代码块里的 &amp;lt;key&amp;gt; / &amp;quot; 要解码 ──
def test_table_cell_double_escaped_entity_decoded():
    """VitePress 属性表把占位符 &amp;lt;key&amp;gt; 双重转义塞单元格,bs4 一层解析后
    剩 &lt;key&gt;,markdownify 不再解码 → md 残留裸实体。清洗要解码成 <key>。"""
    md = conv('<table><tr><th>K</th></tr>'
              '<tr><td>cds.mock.users.&amp;lt;key&amp;gt;.id</td></tr></table>')
    assert "<key>" in md, md
    assert "&lt;" not in md and "&gt;" not in md, f"实体没解码: {md}"


def test_table_cell_double_escaped_quot_decoded():
    md = conv('<table><tr><th>K</th></tr>'
              '<tr><td>say &amp;quot;hi&amp;quot;</td></tr></table>')
    assert 'say "hi"' in md, md
    assert "&quot;" not in md


def test_table_cell_double_escaped_wbr_still_stripped():
    """双重转义的 &amp;lt;wbr&amp;gt; 解码后是 <wbr> 软换行占位,仍要删,不能留在 md。"""
    md = conv('<table><tr><th>K</th></tr>'
              '<tr><td>a.&amp;lt;wbr&amp;gt;b</td></tr></table>')
    assert "<wbr>" not in md, md
    assert "a.b" in md or "a.​b" in md, md


def test_code_block_double_escaped_entity_decoded():
    """代码块(Shiki)里双重转义的 &amp;quot; 该解码成真引号,否则复制出的 XML 不能用。"""
    md = conv('<div class="language-xml"><pre class="shiki"><code>'
              '<span class="line"><span>&lt;formula&gt;&amp;quot;id&amp;quot;&lt;/formula&gt;</span></span>'
              '</code></pre></div>')
    assert '"id"' in md, md
    assert "&quot;" not in md


# ── sitemap index(嵌套 sitemap)要递归展开子 sitemap ──────────────
def test_read_sitemap_index_recurses(monkeypatch=None):
    """sitemapindex 的 <loc> 指向子 sitemap 的 .xml,要递归抓子 sitemap 里的页面 URL,
    而非把子 sitemap 的 .xml 当页面返回。"""
    import docsite_to_md as d
    index_xml = (
        '<?xml version="1.0"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>https://s/sitemap-1.xml</loc></sitemap>'
        '<sitemap><loc>https://s/sitemap-2.xml</loc></sitemap>'
        '</sitemapindex>')
    child1 = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://s/docs/a</loc></url>'
        '<url><loc>https://s/docs/b</loc></url>'
        '</urlset>')
    child2 = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://s/docs/c</loc></url>'
        '</urlset>')
    responses = {
        "https://s/sitemap_index.xml": index_xml,
        "https://s/sitemap-1.xml": child1,
        "https://s/sitemap-2.xml": child2,
    }
    orig = d.fetch
    d.fetch = lambda url: responses[url]
    try:
        urls = read_sitemap("https://s/sitemap_index.xml")
    finally:
        d.fetch = orig
    assert urls == ["https://s/docs/a", "https://s/docs/b", "https://s/docs/c"], urls


def test_read_sitemap_flat_still_works():
    """普通 urlset sitemap 照常返回页面 URL。"""
    import docsite_to_md as d
    flat = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://s/docs/x</loc></url>'
        '</urlset>')
    orig = d.fetch
    d.fetch = lambda url: flat
    try:
        urls = read_sitemap("https://s/sitemap.xml")
    finally:
        d.fetch = orig
    assert urls == ["https://s/docs/x"], urls


# ── 空 language div(code-group 畸形残留)不该产出空围栏 ──────────
def test_empty_language_div_no_empty_fence():
    """<div class="language-"> 空块(VitePress code-group 畸形残留)转出一对空 ```
    围栏,是垃圾。应删空 language 块,不留空围栏。"""
    html = '''
    <p>text before</p>
    <div class="language- active"><button class="copy"></button><span class="lang"></span>
      <pre class="shiki"><code></code></pre>
    </div>
    <p>text after</p>'''
    md = conv(html)
    # 不该出现连续两行空围栏
    import re as _re
    assert not _re.search(r"```\s*\n\s*```", md), f"不该有空围栏对:\n{md}"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
