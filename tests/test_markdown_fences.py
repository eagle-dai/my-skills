from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "markdown_fences.py"
SPEC = importlib.util.spec_from_file_location("markdown_fences", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
markdown_fences = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = markdown_fences
SPEC.loader.exec_module(markdown_fences)


class MarkdownFenceScannerTests(unittest.TestCase):
    def test_scans_simple_backtick_block(self) -> None:
        markdown = "```python\n# not a heading\n```\n# Real heading\n"

        blocks = markdown_fences.scan_fenced_blocks(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual((blocks[0].start_line, blocks[0].end_line), (1, 3))
        self.assertEqual(blocks[0].marker_length, 3)

    def test_long_outer_fence_contains_short_inner_fence(self) -> None:
        markdown = (
            "````markdown\n"
            "```python\n"
            "print('inside')\n"
            "```\n"
            "````\n"
        )

        blocks = markdown_fences.scan_fenced_blocks(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual((blocks[0].start_line, blocks[0].end_line), (1, 5))
        self.assertEqual(blocks[0].marker_length, 4)

    def test_scans_blockquote_fence(self) -> None:
        markdown = "> ```text\n> output\n> ```\nparagraph\n"

        block = markdown_fences.scan_fenced_blocks(markdown)[0]

        self.assertEqual(block.blockquote_depth, 1)
        self.assertEqual((block.start_line, block.end_line), (1, 3))

    def test_scans_list_item_fence(self) -> None:
        markdown = "- ```python\n  print('item')\n  ```\n- next\n"

        block = markdown_fences.scan_fenced_blocks(markdown)[0]

        self.assertEqual(block.container_indent, 2)
        self.assertEqual((block.start_line, block.end_line), (1, 3))

    def test_list_item_fence_rejects_column_zero_closer(self) -> None:
        markdown = "- ```python\n  print('item')\n```\n"

        with self.assertRaisesRegex(
            ValueError,
            "outside the list-item content indentation",
        ):
            markdown_fences.scan_fenced_blocks(markdown)

    def test_normally_indented_opener_can_close_at_column_zero(self) -> None:
        markdown = "  ```text\ncontent\n```\n"

        block = markdown_fences.scan_fenced_blocks(markdown)[0]

        self.assertEqual(block.container_indent, 0)
        self.assertEqual((block.start_line, block.end_line), (1, 3))

    def test_tilde_fence_accepts_longer_closer(self) -> None:
        markdown = "~~~text\nvalue\n~~~~\n"

        block = markdown_fences.scan_fenced_blocks(markdown)[0]

        self.assertEqual(block.marker, "~")
        self.assertEqual(block.marker_length, 3)

    def test_shorter_closer_reports_specific_reason(self) -> None:
        markdown = "````markdown\ncontent\n```\n"

        with self.assertRaisesRegex(ValueError, "shorter than the opener"):
            markdown_fences.scan_fenced_blocks(markdown)

    def test_closer_with_trailing_text_reports_specific_reason(self) -> None:
        markdown = "```python\ncode\n``` extra\n"

        with self.assertRaisesRegex(ValueError, "has trailing text"):
            markdown_fences.scan_fenced_blocks(markdown)

    def test_even_marker_counts_can_still_be_malformed(self) -> None:
        # The old n % 2 checks see two backtick lines and two tilde lines.
        # The state machine correctly sees the final tilde opener as unclosed.
        markdown = "```python\ncode\n~~~\n```\n~~~\n"

        with self.assertRaisesRegex(ValueError, "opened at line 5"):
            markdown_fences.scan_fenced_blocks(markdown)

    def test_strip_preserves_line_count_and_outer_structure(self) -> None:
        markdown = (
            "# Before\r\n"
            "> ```text\r\n"
            "> # not a heading\r\n"
            "> ```\r\n"
            "- After\r\n"
        )

        stripped = markdown_fences.strip_fenced_blocks(markdown)

        self.assertEqual(len(stripped.splitlines()), len(markdown.splitlines()))
        self.assertEqual(stripped, "# Before\r\n\r\n\r\n\r\n- After\r\n")

    def test_backtick_in_info_string_is_not_an_opener(self) -> None:
        markdown = "```bad`info\nplain text\n"

        self.assertEqual(markdown_fences.scan_fenced_blocks(markdown), ())


if __name__ == "__main__":
    unittest.main()
