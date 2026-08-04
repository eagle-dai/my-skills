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
