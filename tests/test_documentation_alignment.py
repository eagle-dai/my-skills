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
        qr_section = self.section(disposition, "QR code 默认规则")
        ledger_section = self.section(disposition, "Ledger")

        self.assertIn("@image_disposition.py", conversion)
        self.assertIn("decide_image()", image_section)
        self.assertIn("assert_valid_image_ledger", image_section)
        for decision in ("keep", "remove_as_ui", "manual_review"):
            self.assertIn(decision, qr_section)
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

    def test_output_naming_contract_is_consistent_across_execution_docs(self) -> None:
        skill = self.read("html-to-markdown/SKILL.md")
        pipeline = self.read("html-to-markdown/pipeline.md")
        conversion = self.read("html-to-markdown/conversion-rules.md")
        blocking = self.read("html-to-markdown/blocking-rules.md")
        checklist = self.read("html-to-markdown/checklist.md")

        for text in (skill, pipeline, conversion, blocking, checklist):
            self.assertIn("output_name", text)
            self.assertIn("Markdown stem", text)
            self.assertIn("资源目录", text)
        self.assertIn("numbered_document_name", skill)
        self.assertIn("numbered_document_name", conversion)
        self.assertIn("--output-name", pipeline)
        self.assertIn("随机后缀", blocking)

    def test_meta_guidance_matches_current_ci(self) -> None:
        meta = self.read("_meta/skill-self-improvement.md")

        self.assertIn("GitHub Actions", meta)
        self.assertIn("完整测试集", meta)
        self.assertNotRegex(meta, r"本质.{0,4}无\s*CI")
        self.assertNotRegex(meta, r"无\s*(?:hook\s*/\s*)?CI\s*强制")

    def test_formula_skill_scopes_single_node_and_batch_capabilities(self) -> None:
        skill = self.read("formula-extraction/SKILL.md")
        fast_boundary = self.section(skill, "当前 fast pipeline 的真实能力边界")

        self.assertIn("单节点模式", skill)
        self.assertIn("批量模式", skill)
        self.assertIn("formula_batch.py::resolve_formulas()", skill)
        self.assertIn("结构化失败", skill)
        self.assertNotIn("__FORMULA_EXTRACTION_FAILED__", skill)
        self.assertIn("尚未实现 MathML parser", fast_boundary)
        self.assertIn("必须 fail closed", fast_boundary)
        self.assertIn("不表示 fast pipeline 已经支持 MathML 自动转换", skill)

    def test_formula_validation_is_deduplicated_by_dom_hash(self) -> None:
        skill = self.read("formula-extraction/SKILL.md")
        pipeline = self.read("html-to-markdown/pipeline.md")
        formula_batch = self.read("html-to-markdown/formula-batch.md")
        batch_section = self.section(skill, "两种执行模式")
        validation_section = self.section(skill, "验证")
        pipeline_formula_section = self.section(pipeline, "公式批处理与验证")
        formula_batch_mapping = self.section(formula_batch, "Validation job 与 source 映射")
        formula_batch_validation = self.section(formula_batch, "批量验证")

        for text in (
            batch_section,
            validation_section,
            pipeline_formula_section,
            formula_batch_mapping,
            formula_batch_validation,
        ):
            self.assertIn("dom_hash", text)
            self.assertIn("source_ids", text)
        self.assertIn("只生成一个 browser validation job", batch_section)
        self.assertIn("重复 source node 不得重复渲染", validation_section)
        self.assertIn("validation_nodes_saved", pipeline_formula_section)
        self.assertIn("首个来源的稳定代表", formula_batch_mapping)
        self.assertIn("total == passed == validation_jobs", formula_batch_validation)
        self.assertIn("不应", formula_batch_validation)
        self.assertNotIn(
            "与 pending batch 完全一致的 `source_id`、`dom_hash` 和 `latex`",
            formula_batch_validation,
        )


if __name__ == "__main__":
    unittest.main()
