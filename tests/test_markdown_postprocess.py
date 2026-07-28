"""Unit tests for the path-independent Markdown post-processor.

These test the module directly (not through the pipeline) so the shared rules
are pinned regardless of which path — fast or strict — produced the Markdown.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
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


class CaptionCentering(unittest.TestCase):
    def test_table_caption_centered(self) -> None:
        # 全角空格锚点：表 N-N　标题 → 居中包裹。
        self.assertEqual(
            pp.postprocess_markdown("表 6-1　行情数据的证据边界\n"),
            '<div align="center">表 6-1　行情数据的证据边界</div>\n',
        )

    def test_figure_caption_centered(self) -> None:
        self.assertEqual(
            pp.postprocess_markdown("图 6-2　市场数据地图实战路径\n"),
            '<div align="center">图 6-2　市场数据地图实战路径</div>\n',
        )

    def test_prose_mention_not_centered(self) -> None:
        # 反例：正文提及是半角空格 + 动词，无全角空格锚点，不该居中。
        line = "图 6-1 把四类数据进入结论前的检查门画出来。\n"
        self.assertEqual(pp.postprocess_markdown(line), line)

    def test_already_centered_untouched(self) -> None:
        # 反例：已经是 <div> 包裹的不重复包。
        line = '<div align="center">表 6-1　标题</div>\n'
        self.assertEqual(pp.postprocess_markdown(line), line)

    def test_caption_like_line_inside_fence_untouched(self) -> None:
        # 反例：代码块内长得像题注的行不动。
        text = "说明\n\n```\n表 6-1　伪装成题注的代码行\n```\n"
        self.assertEqual(pp.postprocess_markdown(text), text)

    def test_letter_numbered_caption_centered(self) -> None:
        # 附录常见字母编号题注（图 D-1、表 A-2），conversion-rules.md「编号识别」
        # 明确 X-Y 的 X 可为字母。纯 \d+ 会漏掉，这里钉住字母编号也居中。
        self.assertEqual(
            pp.postprocess_markdown("图 D-1　附录数据地图\n"),
            '<div align="center">图 D-1　附录数据地图</div>\n',
        )
        self.assertEqual(
            pp.postprocess_markdown("表 A-2　字母编号来源卡\n"),
            '<div align="center">表 A-2　字母编号来源卡</div>\n',
        )

    def test_letter_numbered_prose_mention_not_centered(self) -> None:
        # 反例：字母编号的正文提及仍是半角空格 + 讲解长句，无全角空格锚点，不居中。
        line = "图 D-1 给出本讲核心知识地图。它不是要求每次都画图，而是提醒复核者。\n"
        self.assertEqual(pp.postprocess_markdown(line), line)


class CommandLineInterface(unittest.TestCase):
    """strict Phase 3 用 CLI 跑机械后处理门；三态锚定 exit code 契约。"""

    def _write(self, text: str) -> Path:
        directory = tempfile.mkdtemp()
        path = Path(directory) / "delivery.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_check_compliant_exits_zero_and_leaves_file(self) -> None:
        path = self._write('<div align="center">表 6-1　标题</div>\n')
        original = path.read_text(encoding="utf-8")
        self.assertEqual(pp.main([str(path), "--check"]), 0)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_check_noncompliant_exits_one_and_leaves_file(self) -> None:
        # 退化产物：CJK 紧贴 $ + 未居中题注。--check 不改文件，只报退出 1。
        path = self._write("表 6-1　标题\n收益率$r_t$表示\n")
        original = path.read_text(encoding="utf-8")
        self.assertEqual(pp.main([str(path), "--check"]), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_fix_rewrites_file_in_place(self) -> None:
        path = self._write("表 6-1　标题\n收益率$r_t$表示\n")
        self.assertEqual(pp.main([str(path)]), 0)
        fixed = path.read_text(encoding="utf-8")
        self.assertIn('<div align="center">表 6-1　标题</div>', fixed)
        self.assertIn("收益率 $r_t$ 表示", fixed)

    def test_missing_file_exits_two(self) -> None:
        self.assertEqual(pp.main(["/no/such/file.md", "--check"]), 2)


if __name__ == "__main__":
    unittest.main()
