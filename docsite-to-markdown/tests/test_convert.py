"""固化 docsite_to_md 的 VitePress 转换行为,防退化。

离线测试:用内联 HTML 片段(真实 VitePress/Shiki 结构),不碰网络。
跑: python3 -m pytest tests/ -q   或   python3 tests/test_convert.py
"""
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
    自动选择该跳过空 .vp-doc,兜底抽 .VPHome。"""
    page = (
        '<html><body><main class="main">'
        '<div class="vp-doc"></div>'
        '<div class="VPHome"><h1>CAP Docs</h1><p>Build enterprise apps.</p></div>'
        '</main></body></html>'
    )
    md = html_to_md(page, selector=None)
    assert "CAP Docs" in md, "空 .vp-doc 该被跳过,抽到 .VPHome"
    assert "Build enterprise apps" in md


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
