from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "formula_batch.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_formula_batch", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
formula_batch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = formula_batch
SPEC.loader.exec_module(formula_batch)


class FormulaBatchTests(unittest.TestCase):
    def test_flat_katex_parser_maps_tokens(self) -> None:
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord mathnormal">x</span><span class="mbin">+</span>'
            '<span class="mord">1</span></span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None

        result = formula_batch.parse_katex(node)

        self.assertTrue(result.success)
        self.assertEqual(result.latex, "x+1")

    def test_unknown_semantic_node_fails_without_using_diagnostic_text(self) -> None:
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="mtable">x</span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None

        result = formula_batch.parse_katex(node)

        self.assertFalse(result.success)
        self.assertIsNone(result.latex)
        self.assertEqual(result.diagnostic_text, "x")

    def test_duplicate_formulas_parse_once_and_then_hit_cache(self) -> None:
        html = """
        <article>
          <p>This body is long enough for the normal preflight body selector and formula indexing.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord">x</span></span></span></span>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord">x</span></span></span></span>
        </article>
        """
        preflight = formula_batch.preflight.build_preflight(html)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation.html",
                results_path=root / "results.json",
            )
            second = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation-2.html",
                results_path=root / "results-2.json",
            )

            self.assertEqual(first.stats["formula_total"], 2)
            self.assertEqual(first.stats["formula_unique"], 1)
            self.assertEqual(first.stats["parsed_unique"], 1)
            self.assertEqual(first.stats["resolved"], 0)
            self.assertEqual(first.stats["pending_validation"], 2)
            self.assertEqual(second.stats["cache_hits"], 1)
            self.assertEqual(len(first.pending_validation), 2)
            self.assertIn('data-source-id="formula-0001"', first.validation_html)
            self.assertIn('data-source-id="formula-0002"', first.validation_html)
            self.assertIn("KaTeX runtime is missing", first.validation_html)
            self.assertIn("runFormulaValidation", first.validation_html)

            cache = json.loads((root / "cache.json").read_text(encoding="utf-8"))
            entry = next(iter(cache["entries"].values()))
            self.assertEqual(entry["validation_status"], "not_validated")

    def test_matching_completed_validation_report_unlocks_reconstructed_formulas(self) -> None:
        html = """
        <article>
          <p>This body is long enough for the normal preflight body selector and formula indexing.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord">x</span></span></span></span>
        </article>
        """
        preflight = formula_batch.preflight.build_preflight(html)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation.html",
                results_path=root / "results.json",
            )
            report_path = root / "validation-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "schema_version": formula_batch.VALIDATION_SCHEMA_VERSION,
                        "parser_version": formula_batch.PARSER_VERSION,
                        "validator_version": formula_batch.VALIDATOR_VERSION,
                        "runtime_loaded": True,
                        "completed": True,
                        "katex_version": "test-runtime",
                        "total": 1,
                        "passed": 1,
                        "failures": [],
                        "items": list(pending.pending_validation),
                    }
                ),
                encoding="utf-8",
            )

            resolved = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation-2.html",
                results_path=root / "results-2.json",
                validation_report_path=report_path,
            )

            self.assertEqual(resolved.stats["resolved"], 1)
            self.assertEqual(resolved.stats["pending_validation"], 0)
            self.assertEqual(resolved.validation_error, "")
            self.assertEqual(resolved.records[0].original_latex, "x")

    def test_mismatched_validation_report_remains_pending(self) -> None:
        html = """
        <article>
          <p>This body is long enough for the normal preflight body selector and formula indexing.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord">x</span></span></span></span>
        </article>
        """
        preflight = formula_batch.preflight.build_preflight(html)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "validation-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "schema_version": formula_batch.VALIDATION_SCHEMA_VERSION,
                        "parser_version": formula_batch.PARSER_VERSION,
                        "validator_version": formula_batch.VALIDATOR_VERSION,
                        "runtime_loaded": True,
                        "completed": True,
                        "katex_version": "test-runtime",
                        "total": 1,
                        "passed": 1,
                        "failures": [],
                        "items": [
                            {
                                "source_id": "wrong-id",
                                "dom_hash": "wrong-hash",
                                "latex": "x",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation.html",
                results_path=root / "results.json",
                validation_report_path=report_path,
            )

            self.assertEqual(result.stats["pending_validation"], 1)
            self.assertIn("source IDs", result.validation_error)

    def test_cache_key_changes_with_parser_version(self) -> None:
        key = formula_batch.FormulaCache.key("abc", "github")
        self.assertIn(formula_batch.PARSER_VERSION, key)
        self.assertTrue(key.endswith("|github"))


if __name__ == "__main__":
    unittest.main()
