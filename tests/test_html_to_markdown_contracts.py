from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "contracts.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_contracts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
contracts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contracts
SPEC.loader.exec_module(contracts)


class SelectorContractTests(unittest.TestCase):
    def test_selectors_are_executable_css_lists(self) -> None:
        for name, selector in contracts.CSS_SELECTORS.items():
            self.assertNotIn(" OR ", selector, name)
            self.assertNotIn(" OR", selector, name)
            self.assertTrue(selector.strip(), name)

    def test_slate_and_native_table_candidates_count_once(self) -> None:
        candidates = [
            contracts.SemanticCandidate(
                semantic_id="table-1",
                source_dom_id="wrapper-1",
                representation="slate-wrapper",
                priority=10,
            ),
            contracts.SemanticCandidate(
                semantic_id="table-2",
                source_dom_id="native-table-2",
                representation="native-table",
                priority=0,
            ),
            contracts.SemanticCandidate(
                semantic_id="table-1",
                source_dom_id="native-table-1",
                representation="native-table",
                priority=0,
            ),
        ]

        result = contracts.canonicalize_candidates(candidates)

        self.assertEqual([item.semantic_id for item in result], ["table-1", "table-2"])
        self.assertEqual(result[0].source_dom_id, "native-table-1")


class ComplexityContractTests(unittest.TestCase):
    def test_level_zero_requires_all_rich_block_counts_to_be_zero(self) -> None:
        empty = contracts.DomCounts()
        self.assertEqual(
            contracts.classify_complexity(empty, has_original_latex=False), 0
        )

        for field in ("image", "codeblock", "table", "comment"):
            counts = contracts.DomCounts(**{field: 1})
            with self.subTest(field=field):
                self.assertEqual(
                    contracts.classify_complexity(
                        counts, has_original_latex=False
                    ),
                    1,
                )

    def test_formula_levels_depend_on_original_latex(self) -> None:
        counts = contracts.DomCounts(formula_inline=1)
        self.assertEqual(
            contracts.classify_complexity(counts, has_original_latex=True), 2
        )
        self.assertEqual(
            contracts.classify_complexity(counts, has_original_latex=False), 3
        )


class CommentLedgerContractTests(unittest.TestCase):
    def test_valid_filtering_does_not_require_markdown_count_equality(self) -> None:
        entries = [
            contracts.CommentLedgerEntry("c1", "kept", 1),
            contracts.CommentLedgerEntry(
                "c2", "removed_as_noise", 0, "pure check-in"
            ),
        ]

        self.assertEqual(
            contracts.validate_comment_ledger(entries, source_ids=["c1", "c2"]), ()
        )

    def test_filtered_comment_requires_reason(self) -> None:
        entries = [
            contracts.CommentLedgerEntry("c1", "removed_as_noise", 0),
        ]

        errors = contracts.validate_comment_ledger(entries, source_ids=["c1"])

        self.assertTrue(any("requires a reason" in error for error in errors))

    def test_kept_comment_must_be_emitted_exactly_once(self) -> None:
        entries = [contracts.CommentLedgerEntry("c1", "kept", 2)]

        errors = contracts.validate_comment_ledger(entries, source_ids=["c1"])

        self.assertTrue(any("emitted_count == 1" in error for error in errors))

    def test_duplicate_source_id_is_rejected(self) -> None:
        entries = [
            contracts.CommentLedgerEntry("c1", "kept", 1),
            contracts.CommentLedgerEntry("c1", "manual_review", 0, "ambiguous"),
        ]

        errors = contracts.validate_comment_ledger(entries, source_ids=["c1", "c2"])

        self.assertTrue(any("duplicate comment source_id" in error for error in errors))

    def test_missing_and_unexpected_source_ids_are_rejected(self) -> None:
        entries = [contracts.CommentLedgerEntry("invented", "kept", 1)]

        errors = contracts.validate_comment_ledger(entries, source_ids=["actual"])

        self.assertTrue(any("missing source comment ids" in error for error in errors))
        self.assertTrue(any("unexpected source comment ids" in error for error in errors))


class DocumentationContractTests(unittest.TestCase):
    def test_skill_references_executable_contracts(self) -> None:
        skill = (ROOT / "html-to-markdown" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("@contracts.py", skill)
        self.assertIn("classify_complexity()", skill)
        self.assertIn("canonicalize_candidates()", skill)
        self.assertNotIn("无公式、正文图片、代码块、表格和评论", skill)

    def test_blocking_rules_use_ledger_conservation(self) -> None:
        rules = (ROOT / "html-to-markdown" / "blocking-rules.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("validate_comment_ledger(entries, source_ids=source_ids)", rules)
        self.assertIn("完整 `source_ids`", rules)
        self.assertNotIn("评论数量必须与 HTML 中的评论条目一一对应", rules)


if __name__ == "__main__":
    unittest.main()
