from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "contracts.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "selector_contract.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_contracts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
contracts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contracts
SPEC.loader.exec_module(contracts)


EXPECTED_SELECTOR_TAGS = {
    "codeblock": ["section", "code", "section"],
    "table": ["section", "table", "section"],
    "list": ["div", "ul"],
    "list_item": ["div", "li"],
    "formula": ["div", "span", "math"],
    "caption": ["caption", "figcaption"],
    "heading": ["h2", "div"],
}


class SelectorExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.soup = BeautifulSoup(html, "lxml")
        cls.normal = cls.soup.select_one("#normal")
        assert cls.normal is not None

    def test_every_contract_selector_matches_expected_fixture_nodes(self) -> None:
        self.assertEqual(set(contracts.CSS_SELECTORS), set(EXPECTED_SELECTOR_TAGS))

        for name, selector in contracts.CSS_SELECTORS.items():
            with self.subTest(name=name, selector=selector):
                matches = self.normal.select(selector)
                self.assertEqual(
                    [match.name for match in matches],
                    EXPECTED_SELECTOR_TAGS[name],
                )

    def test_table_wrapper_and_native_node_share_identity(self) -> None:
        candidates = contracts.discover_semantic_candidates(self.normal, kind="table")
        result = contracts.canonicalize_candidates(candidates)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            [candidate.representation for candidate in result],
            ["native-table", "slate-table-wrapper"],
        )
        native = next(item for item in candidates if item.representation == "native-table")
        wrapper = next(
            item
            for item in candidates
            if item.source_dom_id.endswith("section[0]")
        )
        self.assertEqual(wrapper.semantic_id, native.semantic_id)

    def test_code_wrapper_and_native_node_share_identity(self) -> None:
        candidates = contracts.discover_semantic_candidates(
            self.normal,
            kind="codeblock",
        )
        result = contracts.canonicalize_candidates(candidates)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            [candidate.representation for candidate in result],
            ["native-code", "slate-pre-wrapper"],
        )

    def test_ambiguous_table_wrapper_fails_closed(self) -> None:
        root = self.soup.select_one("#ambiguous-table")
        assert root is not None

        with self.assertRaisesRegex(ValueError, "contains 2 native nodes"):
            contracts.discover_semantic_candidates(root, kind="table")

    def test_ambiguous_code_wrapper_fails_closed(self) -> None:
        root = self.soup.select_one("#ambiguous-code")
        assert root is not None

        with self.assertRaisesRegex(ValueError, "contains 2 native nodes"):
            contracts.discover_semantic_candidates(root, kind="codeblock")

    def test_unsupported_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported semantic candidate kind"):
            contracts.discover_semantic_candidates(self.normal, kind="image")


if __name__ == "__main__":
    unittest.main()
