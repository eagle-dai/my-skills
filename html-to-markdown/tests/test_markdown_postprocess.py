"""Regression + new-rule tests for markdown_postprocess.

Loads the sibling module by path (skill dir is not a package).
Run: python3 -m pytest tests/test_markdown_postprocess.py  (from skill dir)
  or: python3 tests/test_markdown_postprocess.py            (plain asserts)
"""
import importlib.util
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "markdown_postprocess", _SKILL / "markdown_postprocess.py"
)
mpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mpp)

pp = mpp.postprocess_markdown


# --- 规则1：题注居中（含加粗表题 bug 修复 + 图题回归） -------------------

def test_bare_figure_caption_centered_regression():
    # 图题无加粗，原有行为不能回归
    out = pp("图 6-1　数据证据门")
    assert out == '<div align="center">图 6-1　数据证据门</div>'


def test_bold_table_caption_centered():
    # bug: **表 …** 被 ** 前缀挡住不居中
    out = pp("**表 6-5　market_tickers 来源卡示例**")
    assert out == '<div align="center">**表 6-5　market_tickers 来源卡示例**</div>'


def test_bold_figure_caption_centered():
    out = pp("**图 6-2　市场数据地图**")
    assert out == '<div align="center">**图 6-2　市场数据地图**</div>'


def test_letter_numbered_bold_caption_centered():
    out = pp("**表 A-2　附录来源卡**")
    assert out == '<div align="center">**表 A-2　附录来源卡**</div>'


def test_prose_mention_not_centered():
    # 正文提及用半角空格，无 U+3000 锚点，不居中
    line = "图 6-1 把表 6-3 落到四张卡片上。"
    assert pp(line) == line


def test_already_centered_not_double_wrapped():
    line = '<div align="center">图 6-1　数据证据门</div>'
    assert pp(line) == line


# --- 规则2：独立成段公式 → $$ 块级 ---------------------------------------

def test_standalone_formula_becomes_block():
    out = pp(r"$C = \frac{n_{valid}}{n_{expected}}$")
    assert out == r"$$C = \frac{n_{valid}}{n_{expected}}$$"


def test_standalone_formula_with_greek():
    out = pp(r"$Δt = t_{now} - t_{obs}$")
    assert out == r"$$Δt = t_{now} - t_{obs}$$"


def test_inline_formula_in_prose_untouched():
    # $ 开头但不以 $ 结尾（后有中文）→ 不改
    line = "- 时间类变量： $t_{obs}$ 为数据观测时间。"
    assert pp(line) == line


def test_multi_formula_line_untouched():
    # $s_{i}$ 开头但整行不是单个公式 → 不改
    line = "$s_{i}$ 、 $e_{i}$ 分别代表第 i 类数据源观测窗口起止时间："
    # 该行以中文结尾，非 $ 结尾；即便首尾都是 $ 也因中间夹文字排除
    assert pp(line) == line


def test_already_block_formula_untouched():
    line = r"$$C = \frac{a}{b}$$"
    assert pp(line) == line


def test_formula_inside_fence_untouched():
    md = "```\n$C = a$\n```"
    assert pp(md) == md


# --- 规则3：变量↔标识符映射公式拆分（缺陷 #16） -------------------------
import sys as _sys
if str(_SKILL) not in _sys.path:
    _sys.path.insert(0, str(_SKILL))
_fb_spec = importlib.util.spec_from_file_location(
    "formula_batch", _SKILL / "formula_batch.py"
)
_fb = importlib.util.module_from_spec(_fb_spec)
_sys.modules["formula_batch"] = _fb
_fb_spec.loader.exec_module(_fb)
split = _fb.split_text_mapping_formula


def test_split_basic_mapping():
    assert split(r"t_{obs} \leftarrow \text{observed\_at}") == ("t_{obs}", "observed_at")


def test_split_restores_underscore():
    assert split(r"n_{valid} \leftarrow \text{valid\_rows}") == ("n_{valid}", "valid_rows")


def test_split_single_letter_var():
    assert split(r"A \leftarrow \text{windows\_overlap}") == ("A", "windows_overlap")


def test_split_ident_without_underscore():
    assert split(r"x \leftarrow \text{count}") == ("x", "count")


def test_no_split_plain_formula():
    assert split(r"C = \frac{n_{valid}}{n_{expected}}") is None


def test_no_split_rightarrow():
    # 只拆 \leftarrow，不碰 \rightarrow
    assert split(r"a \rightarrow \text{b}") is None


def test_no_split_math_structure_in_text():
    # 右侧 \text{} 内含数学结构 → 不拆（保守）
    assert split(r"a \leftarrow \text{x_{i}}") is None


def test_no_split_missing_text():
    assert split(r"a \leftarrow b") is None


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
