"""Tests for local-KaTeX validation document + runtime copy (改进3).

Run: python3 tests/test_validation_document.py   (from skill dir)
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("h2m_formula_batch", _SKILL / "formula_batch.py")
_fb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _fb
_spec.loader.exec_module(_fb)

ITEMS = [
    {"source_id": "formula-0001", "dom_hash": "abc", "latex": r"\frac{a}{b}"},
]


def test_document_references_local_katex_js():
    html = _fb.validation_document(ITEMS)
    assert 'src="katex.min.js"' in html  # 相对同目录,离线
    assert "cdn" not in html.lower()  # 不引 CDN


def test_document_has_dom_content_loaded_autorun():
    html = _fb.validation_document(ITEMS)
    assert "DOMContentLoaded" in html
    assert "runFormulaValidation()" in html  # auto-run 真调了


def test_autorun_handles_already_loaded_page():
    # 竞态:页面在 DOMContentLoaded 已触发后才被打开(driver navigate 等 load)
    # → 事件不再来,必须靠 readyState 分支立即跑,否则 auto-run 永不 fire
    html = _fb.validation_document(ITEMS)
    assert "readyState" in html
    assert "'loading'" in html  # loading 才挂监听,否则立即执行


def test_document_keeps_existing_validation_functions():
    html = _fb.validation_document(ITEMS)
    # 旧验证语义原样保留
    assert "window.runFormulaValidation" in html
    assert "window.githubMathUnescape" in html
    assert "throwOnError" in html


def test_autorun_fails_closed_on_missing_runtime():
    html = _fb.validation_document(ITEMS)
    # KaTeX 没加载时 auto-run 应保持 completed:false(不伪装成功)
    assert "completed = false" in html
    assert "load_error" in html


def test_validator_version_unchanged():
    # 版本锚:变更解析/验证语义时必须 bump(否则旧缓存/旧报告失效不被察觉)。
    # v4:validator 增 identifier-as-subscript 门;parser 增 math-mode 字面 `_`/特殊符转义。
    assert _fb.VALIDATOR_VERSION == "formula-batch-v4"
    assert _fb.PARSER_VERSION == "katex-html-v4"


# --- math-mode 字面特殊符转义(gap #18/#21:field_coverage 被当下标) -----------

def test_map_text_escapes_literal_underscore_per_char():
    # _map_text 逐字符转义(KaTeX HTML mord 是逐字符叶子):字面 _ → \_,
    # 装配后 field\_coverage。这是 parser 的忠实输出。
    assert _fb._map_text("field_coverage") == r"field\_coverage"


def test_underscore_identifier_still_fails_github_guard():
    # 硬事实回归:带下划线标识符即使 \_ 转义,GitHub 也会反转义成下标 → validator
    # 的 identifier-as-subscript 门必须继续判失败(fail-closed 交 strict/manual)。
    assert _fb.has_identifier_subscript(r"field\_coverage")


def test_map_text_escapes_other_math_specials():
    assert _fb._map_text("a%b") == r"a\%b"
    assert _fb._map_text("x#y") == r"x\#y"
    assert _fb._map_text("p&q") == r"p\&q"


def test_map_text_greek_and_operators_unaffected():
    # 转义不能误伤希腊字母/运算符映射
    assert _fb._map_text("α") == r"\alpha"
    assert _fb._map_text("max") == r"\max"


def test_map_text_text_mode_still_escapes_underscore():
    # text mode 分支(\text{} 内)行为不变
    assert _fb._map_text("valid_at", text_mode=True) == r"valid\_at"


def test_copy_katex_runtime_places_asset():
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        ok = _fb.copy_katex_runtime(dest)
        assert ok is True
        asset = dest / "katex.min.js"
        assert asset.is_file()
        assert asset.stat().st_size > 100_000  # 真 bundle,非空占位


def test_copy_katex_runtime_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        _fb.copy_katex_runtime(dest)
        first = (dest / "katex.min.js").read_bytes()
        _fb.copy_katex_runtime(dest)  # 二次不应损坏
        assert (dest / "katex.min.js").read_bytes() == first


def test_copy_katex_runtime_fails_closed_when_dest_is_dir():
    # 反例:dest 路径已是目录 → read_bytes 会抛,须 fail closed 返回 False
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        (dest / "katex.min.js").mkdir()  # 占位成目录
        assert _fb.copy_katex_runtime(dest) is False


def test_copy_katex_runtime_fails_closed_when_source_missing(monkeypatch=None):
    # 反例:源 asset 不存在时返回 False,不抛异常
    real = _fb.MODULE_DIR
    try:
        _fb.MODULE_DIR = Path("/no/such/skill/dir")
        with tempfile.TemporaryDirectory() as d:
            assert _fb.copy_katex_runtime(Path(d)) is False
            assert not (Path(d) / "katex.min.js").exists()
    finally:
        _fb.MODULE_DIR = real


def test_bundled_asset_exists_and_is_pinned():
    asset = _fb.MODULE_DIR / "assets" / _fb.KATEX_ASSET_NAME
    assert asset.is_file()
    assert _fb.KATEX_VERSION == "0.16.9"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
