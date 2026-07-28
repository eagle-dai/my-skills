"""Unit tests for the path-independent Markdown post-processor.

These test the module directly (not through the pipeline) so the shared rules
are pinned regardless of which path — fast or strict — produced the Markdown.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "markdown_postprocess.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_postprocess_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
pp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pp
SPEC.loader.exec_module(pp)


class CjkInlineMathSpacing(unittest.TestCase):
    def test_cjk_both_sides_get_space(self) -> None:
        self.assertEqual(
            pp.postprocess_markdown("收益率$r_t$表示\n"),
            "收益率 $r_t$ 表示\n",
        )

    def test_fullwidth_paren_gets_space(self) -> None:
        self.assertEqual(
            pp.postprocess_markdown("（$w_t$）\n"),
            "（ $w_t$ ）\n",
        )

    def test_ascii_spaced_is_left_alone(self) -> None:
        self.assertEqual(
            pp.postprocess_markdown("see $r_t$ here\n"),
            "see $r_t$ here\n",
        )

    def test_display_dollar_pair_untouched(self) -> None:
        # $$ display delimiters next to CJK must not be split.
        text = "结论\n\n$$\nx=1\n$$\n"
        self.assertEqual(pp.postprocess_markdown(text), text)

    def test_dollar_inside_fence_untouched(self) -> None:
        text = "前言\n\n```bash\necho 价格$USD 变量\n```\n"
        out = pp.postprocess_markdown(text)
        self.assertIn("价格$USD", out)
        self.assertNotIn("价格 $USD", out)


class QuadStarFix(unittest.TestCase):
    def test_quad_star_seam_removed(self) -> None:
        # Adjacent bold spans concatenated into four stars render wrong on GitHub.
        self.assertEqual(
            pp.postprocess_markdown("**表 1-4****置信度**\n"),
            "**表 1-4置信度**\n",
        )

    def test_normal_bold_untouched(self) -> None:
        self.assertEqual(
            pp.postprocess_markdown("这是**重点**内容\n"),
            "这是**重点**内容\n",
        )

    def test_quad_star_inside_fence_untouched(self) -> None:
        text = "说明\n\n```\na****b\n```\n"
        self.assertEqual(pp.postprocess_markdown(text), text)


if __name__ == "__main__":
    unittest.main()
