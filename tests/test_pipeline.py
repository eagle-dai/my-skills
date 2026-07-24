from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "pipeline_article.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class PipelineTests(unittest.TestCase):
    def test_fast_path_converts_and_packages_static_article(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            outcome = pipeline.run_pipeline(FIXTURE_PATH, output, mode="auto")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            assert outcome.zip_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("# Fast path article", markdown)
            self.assertIn("- First item", markdown)
            self.assertIn("```python", markdown)
            self.assertIn("| Name | Value |", markdown)
            self.assertIn("$x^2$", markdown)
            self.assertIn("![pixel](files/pipeline_article/asset-0001.png)", markdown)
            self.assertTrue(
                (
                    outcome.markdown_path.parent
                    / "files"
                    / "pipeline_article"
                    / "asset-0001.png"
                ).exists()
            )
            self.assertEqual(outcome.report["count_errors"], [])
            self.assertEqual(outcome.report["unresolved_formulas"], [])

            with zipfile.ZipFile(outcome.zip_path) as archive:
                self.assertIn("Fast path article.md", archive.namelist())
                self.assertIn(
                    "files/pipeline_article/asset-0001.png", archive.namelist()
                )

    def test_virtualized_page_routes_to_strict_without_markdown(self) -> None:
        html = """
        <html><body><main>
          <p>This substantial page contains enough text for selection but also
          includes a Monaco editor, so the deterministic fast path must stop.</p>
          <div class="monaco-editor"><div class="view-lines">code</div></div>
        </main></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "virtualized.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIsNone(outcome.markdown_path)
            self.assertTrue(outcome.report["strict_reasons"])

    def test_complex_table_routes_to_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long and contains a complex table
          whose spanning cell cannot be represented safely by the fast path.</p>
          <table><tr><th colspan="2">Header</th></tr><tr><td>A</td><td>B</td></tr></table>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "complex.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIn("rowspan/colspan", outcome.report["strict_reasons"][0])

    def test_external_image_routes_to_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long but its image remains remote,
          so an offline fast-path package must not be reported as complete.</p>
          <img src="https://example.invalid/chart.png" alt="chart">
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "external.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIsNone(outcome.zip_path)
            self.assertIn("must be localized", outcome.report["strict_reasons"][0])

    def test_unknown_semantic_element_routes_to_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long but contains an interactive
          disclosure whose semantics cannot be safely flattened by the fast path.</p>
          <details><summary>Hidden section</summary><p>Important hidden content.</p></details>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "details.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIn("unsupported semantic element <details>", outcome.report["strict_reasons"][0])

    def test_katex_html_only_formula_blocks_final_package(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and contains one formula without an original semantic source.</p>
          <span class="katex"><span class="mord mathnormal">x</span></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "formula.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "blocked")
            self.assertIsNone(outcome.zip_path)
            self.assertEqual(len(outcome.report["unresolved_formulas"]), 1)
            assert outcome.markdown_path is not None
            self.assertIn(
                "{{FORMULA:formula-0001}}",
                outcome.markdown_path.read_text(encoding="utf-8"),
            )

    def test_blocked_run_removes_previous_successful_zip(self) -> None:
        blocked_html = """
        <html><body><article>
          <p>This replacement article is long enough for selection but includes a
          KaTeX HTML-only formula that deliberately blocks final packaging.</p>
          <span class="katex"><span class="mord">x</span></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            first = pipeline.run_pipeline(FIXTURE_PATH, output, mode="fast")
            assert first.zip_path is not None
            self.assertTrue(first.zip_path.exists())

            replacement = root / "pipeline_article.html"
            replacement.write_text(blocked_html, encoding="utf-8")
            second = pipeline.run_pipeline(replacement, output, mode="fast")

            self.assertEqual(second.status, "blocked")
            self.assertFalse((output / "pipeline_article.zip").exists())

    def test_zip_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_outcome = pipeline.run_pipeline(FIXTURE_PATH, Path(first), mode="fast")
            second_outcome = pipeline.run_pipeline(FIXTURE_PATH, Path(second), mode="fast")
            assert first_outcome.zip_path is not None
            assert second_outcome.zip_path is not None
            self.assertEqual(
                first_outcome.zip_path.read_bytes(), second_outcome.zip_path.read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
