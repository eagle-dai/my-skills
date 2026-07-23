from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationAlignmentTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def section(self, text: str, heading: str) -> str:
        match = re.search(
            rf"^## {re.escape(heading)}\s*$",
            text,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(match, f"missing section: {heading}")
        assert match is not None
        next_heading = re.search(r"^## ", text[match.end() :], flags=re.MULTILINE)
        end = match.end() + next_heading.start() if next_heading else len(text)
        return text[match.end() : end]

    def assert_bad_rule_is_explicitly_negated(
        self,
        text: str,
        *,
        trigger: re.Pattern[str],
    ) -> None:
        negation = re.compile(r"不得|不能|禁止|无效|不是|不构成|只有.+才")
        for line in text.splitlines():
            if trigger.search(line):
                self.assertRegex(
                    line,
                    negation,
                    f"bad rule is not explicitly negated: {line}",
                )

    def test_qr_section_uses_executable_disposition_and_link_contract(self) -> None:
        conversion = self.read("html-to-markdown/conversion-rules.md")
        image_section = self.section(conversion, "图片与资源")
        disposition = self.read("html-to-markdown/image-disposition.md")
        ledger_section = self.section(disposition, "Ledger")

        self.assertIn("@image_disposition.py", conversion)
        self.assertIn("decide_image()", image_section)
        self.assertIn("assert_valid_image_ledger", image_section)
        for decision in ("keep", "remove_as_ui", "manual_review"):
            self.assertIn(decision, image_section)
        self.assertIn("decoded_link_emitted", ledger_section)
        self.assertIn("decoded_url", ledger_section)
        self.assertIn("可点击链接", disposition)

        blanket_delete = re.compile(
            r"(?:二维码|QR\s*code).{0,24}(?:默认|一律|全部|直接).{0,12}(?:删除|移除)"
            r"|(?:默认|一律|全部|直接).{0,12}(?:删除|移除).{0,24}(?:二维码|QR\s*code)",
            flags=re.IGNORECASE,
        )
        self.assert_bad_rule_is_explicitly_negated(
            image_section,
            trigger=blanket_delete,
        )

    def test_notebook_fence_section_uses_scanner_and_negates_old_algorithms(self) -> None:
        notebook = self.read("html-to-markdown/notebook-and-virtualized.md")
        fence_section = self.section(notebook, "6. Fence 扫描与结构计数")

        self.assertIn("@markdown_fences.py", notebook)
        self.assertIn("scan_fenced_blocks", fence_section)
        self.assertIn("strip_fenced_blocks", fence_section)
        self.assertIn("以下做法无效并禁止", fence_section)

        affirmative_shortcuts = re.compile(
            r"(?:%\s*2|奇偶).{0,24}(?:配对完整|通过)"
            r"|(?:跨行正则|re\.sub).{0,24}(?:验证|替代|通过)"
        )
        self.assert_bad_rule_is_explicitly_negated(
            fence_section,
            trigger=affirmative_shortcuts,
        )

    def test_checklist_sections_use_deterministic_conservation_rules(self) -> None:
        checklist = self.read("html-to-markdown/checklist.md")
        image_section = self.section(checklist, "7. 图片与二维码")
        scan_section = self.section(checklist, "2. Markdown 侧结构扫描")

        self.assertIn("assert_valid_image_ledger", image_section)
        self.assertIn("decoded_url", image_section)
        self.assertIn("decoded_link_emitted", image_section)
        self.assertIn("scan_fenced_blocks", scan_section)
        self.assertIn("strip_fenced_blocks", scan_section)
        self.assertIn("段落 ledger", checklist)
        self.assertIsNone(
            re.search(r"(?:显著|明显|大幅|大量)\s*(?:减少|降低)", checklist)
        )

    def test_meta_guidance_matches_current_ci(self) -> None:
        meta = self.read("_meta/skill-self-improvement.md")

        self.assertIn("GitHub Actions", meta)
        self.assertIn("完整测试集", meta)
        self.assertNotRegex(meta, r"本质.{0,4}无\s*CI")
        self.assertNotRegex(meta, r"无\s*(?:hook\s*/\s*)?CI\s*强制")


if __name__ == "__main__":
    unittest.main()
