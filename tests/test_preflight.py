from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "preflight.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "preflight_article.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_preflight", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_compacts_article_and_deduplicates_equivalent_formula_hashes(self) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8")

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["body"]["selector"], "article")
        self.assertEqual(result.manifest["recommended_mode"], "fast")
        self.assertLess(
            result.manifest["sizes"]["compact_bytes"],
            result.manifest["sizes"]["input_bytes"],
        )
        self.assertNotIn("<style", result.compact_html)
        self.assertNotIn("<script", result.compact_html)
        self.assertNotIn("Navigation", result.compact_html)
        self.assertIn('class="katex"', result.compact_html)
        self.assertIn("display", result.compact_html)
        self.assertEqual(result.manifest["counts"]["tables"], 1)
        self.assertEqual(result.manifest["counts"]["images"], 1)
        self.assertEqual(result.manifest["counts"]["formula_total"], 2)
        self.assertEqual(result.manifest["counts"]["formula_unique"], 1)
        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].source_kind, "data-uri")

    def test_virtualized_editor_recommends_strict(self) -> None:
        html = """
        <html><body><main>
          <p>This substantial article body has enough text to pass selection and
          contains a virtualized editor marker that requires strict inspection.</p>
          <div class="monaco-editor"><div class="view-lines">code</div></div>
        </main></body></html>
        """

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["recommended_mode"], "strict")
        self.assertTrue(result.manifest["signals"]["virtualized_editor"])
        self.assertIn(
            "virtualized editor markers detected",
            result.manifest["signals"]["strict_reasons"],
        )

    def test_ambiguous_body_fails_closed(self) -> None:
        body = (
            "This is substantial article text that deliberately exceeds the "
            "minimum body threshold so ambiguity cannot be ignored by preflight."
        )
        html = f"<html><body><article>{body}</article><article>{body}</article></body></html>"

        with self.assertRaisesRegex(preflight.BodySelectionError, "ambiguous"):
            preflight.build_preflight(html)

    def test_writes_deterministic_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            first_result = preflight.run_preflight(FIXTURE_PATH, first_dir)
            second_result = preflight.run_preflight(FIXTURE_PATH, second_dir)

            self.assertEqual(first_result.manifest, second_result.manifest)
            for name in ("content.html", "manifest.json", "formulas.json", "assets.json"):
                self.assertEqual(
                    (first_dir / name).read_bytes(),
                    (second_dir / name).read_bytes(),
                )

            manifest = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.0")


if __name__ == "__main__":
    unittest.main()
