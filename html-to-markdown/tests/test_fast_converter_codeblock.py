"""Regression tests for code-block blank-line trimming (defect A).

Slate lays out each code line as its own <div>; empty leading/trailing rows
surface as blank lines just inside the fence. `_strip_blank_edges` drops the
edge blanks while preserving interior blank lines.

Loads the sibling module by path (skill dir is not a package).
Run: .venv/bin/python tests/test_fast_converter_codeblock.py
"""
import importlib.util
import sys
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))  # fast_converter imports sibling pipeline_utils
_spec = importlib.util.spec_from_file_location(
    "fast_converter", _SKILL / "fast_converter.py"
)
fc = importlib.util.module_from_spec(_spec)
sys.modules["fast_converter"] = fc  # dataclass __module__ lookup needs this
_spec.loader.exec_module(fc)

strip = fc._strip_blank_edges


# --- 首尾空行去除 ---------------------------------------------------------

def test_strip_leading_blank_lines():
    assert strip("\n\nTest-Path x\nTest-Path y") == "Test-Path x\nTest-Path y"


def test_strip_leading_whitespace_only_line():
    # Slate 首行是纯空格 div → get_text() 得 " "，也要去掉
    assert strip(" \n\nTest-Path x") == "Test-Path x"


def test_strip_trailing_blank_lines():
    assert strip("a\nb\n\n ") == "a\nb"


def test_strip_both_edges():
    assert strip("\n \na\nb\n \n") == "a\nb"


def test_preserve_interior_blank_lines():
    # 代码内部空行有意义，必须保留
    assert strip("a\n\nb") == "a\n\nb"
    assert strip("\na\n\n\nb\n") == "a\n\n\nb"


def test_no_blank_edges_unchanged():
    assert strip("a\nb\nc") == "a\nb\nc"


def test_all_blank_becomes_empty():
    assert strip("\n \n\n") == ""


def test_single_line_unchanged():
    assert strip("Test-Path x") == "Test-Path x"


# --- 端到端：code_block 输出的 fence 内无首尾空行 -------------------------

def _code_block_from_slate(rows):
    """构造 Slate 每行 div 布局的容器，返回 code_block() 的输出。"""
    from bs4 import BeautifulSoup

    inner = "".join(f"<div><span>{r}</span></div>" for r in rows)
    soup = BeautifulSoup(f'<div class="code">{inner}</div>', "lxml")
    node = soup.find("div", class_="code")
    conv = fc.MarkdownConverter.__new__(fc.MarkdownConverter)
    conv.counts = fc.EmittedCounts()
    return conv.code_block(node)


def test_code_block_no_blank_after_opening_fence():
    out = _code_block_from_slate(
        [" ", "", "Test-Path data/x.json", "Test-Path src/y.py", ""]
    )
    lines = out.split("\n")
    assert lines[0].startswith("```"), lines[0]
    # fence 后第一行必须是真内容，不是空行
    assert lines[1] == "Test-Path data/x.json", lines
    assert lines[-1] == "```", lines
    # 倒数第二行是最后一行代码，不是空行
    assert lines[-2] == "Test-Path src/y.py", lines


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
