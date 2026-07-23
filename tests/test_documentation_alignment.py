from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationAlignmentTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_qr_codes_are_not_blanket_deleted(self) -> None:
        conversion = self.read("html-to-markdown/conversion-rules.md")

        self.assertIn("@image_disposition.py", conversion)
        self.assertIn("assert_valid_image_ledger", conversion)
        self.assertIn("manual_review", conversion)
        self.assertNotIn("删除头像、广告、二维码", conversion)
        self.assertNotIn("头像、二维码、Cookie", conversion)

    def test_notebook_docs_use_fence_scanner(self) -> None:
        notebook = self.read("html-to-markdown/notebook-and-virtualized.md")

        self.assertIn("@markdown_fences.py", notebook)
        self.assertIn("scan_fenced_blocks", notebook)
        self.assertIn("strip_fenced_blocks", notebook)
        # The docs may quote a bad expression as a prohibited example. What must
        # not return is the old affirmative algorithm and its claimed proof.
        self.assertNotIn("assert n3 % 2 == 0 and n4 % 2 == 0", notebook)
        self.assertNotIn("偶数 = 配对完整即可", notebook)
        self.assertNotIn("re.sub(r'```.*?\n.*?```'", notebook)

    def test_checklist_uses_deterministic_conservation_rules(self) -> None:
        checklist = self.read("html-to-markdown/checklist.md")

        self.assertIn("assert_valid_image_ledger", checklist)
        self.assertIn("scan_fenced_blocks", checklist)
        self.assertIn("段落 ledger", checklist)
        self.assertNotIn("显著减少", checklist)
        self.assertNotIn("大幅减少", checklist)

    def test_meta_guidance_matches_current_ci(self) -> None:
        meta = self.read("_meta/skill-self-improvement.md")

        self.assertIn("GitHub Actions", meta)
        self.assertIn("完整测试集", meta)
        self.assertNotIn("本质是无 CI", meta)
        self.assertNotIn("无 hook/CI", meta)


if __name__ == "__main__":
    unittest.main()
