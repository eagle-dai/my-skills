"""formula-extraction 规则表的兜底测试（闸 2）。

`formula-extraction/self-improvement.md` 是本 skill 的回归用例表，但它的**实现**住在
兄弟 skill `html-to-markdown`（`formula_batch.py` / `markdown_postprocess.py`）里——skill
目录名带连字符不可直接 import，所以按路径加载，沿用 html-to-markdown 自己测试的惯例。

这样规则表里**有实现**的每一条都被本 skill 名下的测试钉住：谁把规则改坏或删掉，这里变红。

表里另有一批**只写了文档、两个模块都没有实现函数**的规则（Prime、double caret、Unicode
上下标、`\text{}` 后粘连、`∗`、裸 CJK 检测、double subscript 检测、`SR^{*}`→`SR^{\\ast}`
重写）。它们不能 import-and-call 测试。`UnimplementedRulesAreMarkedTests` 守卫这些行必须在
表里带 `[未实现-仅设计]` 标记，防止有人误当已落地能力——正是 skill 自己写的
"不得把设计目标写成已经落地的能力"。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from bs4 import BeautifulSoup


SKILL = Path(__file__).resolve().parent.parent
HTML_TO_MARKDOWN = SKILL.parent / "html-to-markdown"


def _load(module_name: str, filename: str):
    """按路径加载 html-to-markdown 的实现模块。

    用带 skill 前缀的唯一 sys.modules 名，避免与 html-to-markdown 自己的测试
    在同名 key 上互相覆盖（各 skill 测试跑在独立子进程，此处再加一层保险）。
    """
    path = HTML_TO_MARKDOWN / filename
    spec = importlib.util.spec_from_file_location(f"formula_extraction_ref_{module_name}", path)
    assert spec is not None and spec.loader is not None, f"无法定位实现模块: {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


formula_batch = _load("formula_batch", "formula_batch.py")


def _katex(inner_html: str) -> BeautifulSoup:
    """包一个最小 .katex > .katex-html > .base 外壳，返回可 select 的 soup 节点。"""
    return BeautifulSoup(
        f'<span class="katex"><span class="katex-html"><span class="base">{inner_html}</span></span></span>',
        "lxml",
    )


class JoinBoundaryTests(unittest.TestCase):
    """parser part join 边界（表：`\\sim` 边界、token 拼接、跨 base 命令边界等）。

    这些规则都作用在 parser part 阶段，实现是 `formula_batch._join`。测试输入必须表达
    part 边界，不能只给最终字符串（见表末注释：禁止在最终串上用 `\\sim([A-Za-z])` 拆分）。
    """

    def test_sim_token_boundary_inserts_space(self) -> None:
        self.assertEqual(formula_batch._join(["\\sim", "p"]), "\\sim p")

    def test_sim_greek_token_boundary_inserts_space(self) -> None:
        self.assertEqual(formula_batch._join(["\\sim", "\\nu"]), "\\sim \\nu")

    def test_single_part_legal_command_untouched(self) -> None:
        # 反例：\simeq / \simneqq 是合法单 part，不得被拆
        self.assertEqual(formula_batch._join(["\\simeq"]), "\\simeq")
        self.assertEqual(formula_batch._join(["\\simneqq"]), "\\simneqq")

    def test_existing_space_not_doubled(self) -> None:
        # 反例：已含空格的单 part 不重复插空格（末尾非命令字母，边界正则不匹配）
        self.assertEqual(formula_batch._join(["\\sim p"]), "\\sim p")

    def test_latex_token_glue_inserts_space(self) -> None:
        self.assertEqual(formula_batch._join(["\\gamma", "V"]), "\\gamma V")

    def test_single_greek_command_untouched(self) -> None:
        # 反例：\Gamma 单 part 不变
        self.assertEqual(formula_batch._join(["\\Gamma"]), "\\Gamma")

    def test_command_followed_by_letter_gets_space(self) -> None:
        # 跨 base 命令边界：\leq + L → \leq L
        self.assertEqual(formula_batch._join(["\\leq", "L"]), "\\leq L")

    def test_command_followed_by_digit_no_space(self) -> None:
        # 反例：数字不进命令名，\leq + 1 → \leq1（不插空格）
        self.assertEqual(formula_batch._join(["\\leq", "1"]), "\\leq1")

    def test_group_end_not_treated_as_command(self) -> None:
        # 反例：\text{prob} 以 } 收尾非控制字，+ x → \text{prob}x（不插空格）
        self.assertEqual(formula_batch._join(["\\text{prob}", "x"]), "\\text{prob}x")

    def test_non_command_tail_no_space(self) -> None:
        # 跨 base 非命令：E_{t} + = → E_{t}=；= + L → =L（收尾非命令，不插空格）
        self.assertEqual(formula_batch._join(["E_{t}", "="]), "E_{t}=")
        self.assertEqual(formula_batch._join(["=", "L"]), "=L")

    def test_mspace_space_part_between_commands(self) -> None:
        # .mspace 产出的空格 part：["\leq", " ", "L"] → "\leq L"
        # 中间空格 part 使 result 以空格收尾，边界正则不再匹配，故不重复插 → 恰好一个空格
        self.assertEqual(formula_batch._join(["\\leq", " ", "L"]), "\\leq L")

    def test_mspace_between_plain_tokens(self) -> None:
        # 反例：["x", " ", "y"] → "x y"（普通 token 间的空格 part 原样保留，不加也不去）
        self.assertEqual(formula_batch._join(["x", " ", "y"]), "x y")


class TextModeEscapeTests(unittest.TestCase):
    """`\\text{}` 内特殊字符转义（表：`\\text{}` 内下标符 / `\\text{a_b}` 检测；gap #18）。

    实现 `formula_batch._escape_text_mode`。产出单反斜杠 `\\_`（text mode），区别于
    math mode 的双反斜杠（gap #31）。
    """

    def test_text_mode_escapes_underscore(self) -> None:
        # \text{signal_source} 的下标符 _ 必须转义（GitHub MathJax 兼容）
        self.assertEqual(formula_batch._escape_text_mode("signal_source"), r"signal\_source")

    def test_text_mode_flags_special_char(self) -> None:
        # 表检测规则：\text{a_b} 内的 _ 命中 → 被转义（转义即命中的机器证据）
        self.assertEqual(formula_batch._escape_text_mode("a_b"), r"a\_b")

    def test_text_mode_leaves_safe_chars(self) -> None:
        # 反例：无特殊符的文本不动
        self.assertEqual(formula_batch._escape_text_mode("signal source 12"), "signal source 12")

    def test_map_text_delegates_to_text_escape_in_text_mode(self) -> None:
        self.assertEqual(formula_batch._map_text("a_b", text_mode=True), r"a\_b")


class MathModeUnderscoreTests(unittest.TestCase):
    """math-mode 字面下划线用双反斜杠 `\\\\_`（gap #31，GitHub 平台，提取器产出）。

    实现 `formula_batch._map_text`（默认 math mode 走 `_MATH_MODE_ESCAPES`）。
    """

    def test_math_mode_literal_underscore_double_backslash(self) -> None:
        self.assertEqual(formula_batch._map_text("a_b"), "a\\\\_b")

    def test_math_mode_underscore_differs_from_text_mode(self) -> None:
        # 双闸对比：math mode 双反斜杠，text mode 单反斜杠——两种转义不得混淆
        self.assertNotEqual(
            formula_batch._map_text("a_b"),
            formula_batch._map_text("a_b", text_mode=True),
        )


class UnicodeSymbolMapTests(unittest.TestCase):
    """Unicode 数学字符映射（表：Unicode ϵ → `\\epsilon`）。

    实现 `formula_batch.SYMBOLS`（经 `_map_text` math mode 分支）。
    仅 SYMBOLS 收录的字符可测；上标/下标/`∗`/prime 未收录，见未实现守卫。
    """

    def test_epsilon_lunate_maps(self) -> None:
        self.assertEqual(formula_batch._map_text("ϵ"), r"\epsilon")

    def test_varepsilon_maps(self) -> None:
        self.assertEqual(formula_batch._map_text("ε"), r"\varepsilon")

    def test_existing_command_untouched(self) -> None:
        # 反例：已是 \epsilon 的不重复映射（无 ϵ 字符，逐字符原样输出）
        self.assertEqual(formula_batch._map_text("\\epsilon"), "\\epsilon")


class IdentifierSubscriptGuardTests(unittest.TestCase):
    """裸标识符误当下标检测（gap #21，表 double subscript / 合法上下标 反例的近邻护栏）。

    实现 `formula_batch.has_identifier_subscript`，返回 bool。
    """

    def test_flags_bare_identifier_subscript(self) -> None:
        self.assertTrue(formula_batch.has_identifier_subscript("field_coverage"))
        self.assertTrue(formula_batch.has_identifier_subscript("a^abc"))

    def test_allows_real_math_subscripts(self) -> None:
        # 反例：单字母/数字/花括号下标都是合法数学，不命中
        for latex in ("x_i", "x_2", "x_{ij}", r"\sum_{i=1}^{n}", r"\frac{a}{b}"):
            self.assertFalse(
                formula_batch.has_identifier_subscript(latex),
                f"合法数学不该命中: {latex}",
            )

    def test_text_mode_underscore_not_flagged(self) -> None:
        # 反例：\text{...} 内的 _ 是 text mode（gap #18 管），先剥离不误判
        self.assertFalse(formula_batch.has_identifier_subscript(r"\text{observed_at}"))


class MspaceViaParseTests(unittest.TestCase):
    """`.mspace` 端到端：经 parse_katex 的公开入口验证空格 part 落到 join。

    补 `_join` 单测之外的一层：确认 .mspace 节点真的被 `_parse` 转成空格 part。
    """

    def test_mspace_node_becomes_space(self) -> None:
        node = _katex(
            '<span class="mord mathnormal">a</span>'
            '<span class="mspace"></span>'
            '<span class="mord mathnormal">b</span>'
        ).select_one(".katex")
        assert node is not None
        result = formula_batch.parse_katex(node)
        self.assertTrue(result.success)
        # a、b 之间保留恰好一个空格（mspace → 空格 part）
        self.assertEqual(result.latex, "a b")


class UnimplementedRulesAreMarkedTests(unittest.TestCase):
    """守卫：表里没有实现函数的规则，必须显式标注 `[未实现-仅设计]`。

    防止"文档写了功能、代码里根本没有"的坑（_meta 第三种坑）被当成已落地能力。
    这些规则在 formula_batch.py / markdown_postprocess.py 里都查不到实现函数：
    Prime、double caret、Unicode 上标/下标、Unicode ∗、`\\text{}` 后粘连、
    公式内裸 CJK 检测、double subscript 检测、数学块内裸 `*` 重写。

    若将来给某条补了实现，请：给它写上面那样的 import-and-call 测试，
    并从 self-improvement.md 去掉该行的 `[未实现-仅设计]` 标记——本守卫会随之要求改动，
    形成"实现↔标记↔测试"三者同步的闭环。
    """

    UNIMPLEMENTED_MARKERS = (
        "Prime",
        "double caret",
        "Unicode ∗",
        "Unicode 上标",
        "Unicode 下标",
        "`\\text{}` 后粘连",
        "公式内裸 CJK",
        "double subscript",
        "数学块内裸 `*`",
    )

    def setUp(self) -> None:
        self.table = (SKILL / "self-improvement.md").read_text(encoding="utf-8")

    def test_unimplemented_rows_carry_marker(self) -> None:
        for row_key in self.UNIMPLEMENTED_MARKERS:
            with self.subTest(rule=row_key):
                # 找到含该规则关键字的行
                lines = [ln for ln in self.table.splitlines() if row_key in ln]
                self.assertTrue(lines, f"规则表里找不到规则行: {row_key}")
                self.assertTrue(
                    any("[未实现-仅设计]" in ln for ln in lines),
                    f"未实现规则 '{row_key}' 必须标 [未实现-仅设计]；"
                    f"若已补实现，请去标记并加对应测试。",
                )


if __name__ == "__main__":
    unittest.main()
