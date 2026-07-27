from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
FORMULA_MODULE_PATH = ROOT / "html-to-markdown" / "formula_batch.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "pipeline_article.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)
FORMULA_SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_formula_batch_for_pipeline_tests", FORMULA_MODULE_PATH
)
assert FORMULA_SPEC is not None and FORMULA_SPEC.loader is not None
formula_batch = importlib.util.module_from_spec(FORMULA_SPEC)
sys.modules[FORMULA_SPEC.name] = formula_batch
FORMULA_SPEC.loader.exec_module(formula_batch)


class PipelineTests(unittest.TestCase):
    def test_fast_path_converts_and_packages_static_article(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            outcome = pipeline.run_pipeline(
                FIXTURE_PATH,
                output,
                mode="auto",
                allow_unprocessed_images=True,
            )

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            assert outcome.zip_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("# Fast path article", markdown)
            self.assertIn("- First item", markdown)
            self.assertIn("```python", markdown)
            self.assertIn("| Name | Value |", markdown)
            self.assertIn("$x^2$", markdown)
            self.assertIn("![pixel](files/pipeline-article/asset-0001.png)", markdown)
            self.assertTrue(
                (
                    outcome.markdown_path.parent
                    / "files"
                    / "pipeline-article"
                    / "asset-0001.png"
                ).exists()
            )
            self.assertEqual(outcome.report["count_errors"], [])
            self.assertEqual(outcome.report["unresolved_formulas"], [])
            self.assertTrue(outcome.report["allow_unprocessed_images"])

            with zipfile.ZipFile(outcome.zip_path) as archive:
                self.assertIn("pipeline-article.md", archive.namelist())
                self.assertIn(
                    "files/pipeline-article/asset-0001.png", archive.namelist()
                )

    def test_output_name_is_reused_for_all_delivery_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            outcome = pipeline.run_pipeline(
                FIXTURE_PATH,
                output,
                mode="auto",
                allow_unprocessed_images=True,
                output_name="01 | AI 量化研究",
            )

            self.assertEqual(outcome.status, "converted")
            self.assertEqual(outcome.report["output_name"], "01-AI-量化研究")
            self.assertEqual(
                outcome.markdown_path,
                output / "01-AI-量化研究" / "01-AI-量化研究.md",
            )
            self.assertEqual(outcome.zip_path, output / "01-AI-量化研究.zip")
            assert outcome.markdown_path is not None
            self.assertTrue(
                (
                    outcome.markdown_path.parent
                    / "files"
                    / "01-AI-量化研究"
                    / "asset-0001.png"
                ).exists()
            )
            assert outcome.zip_path is not None
            with zipfile.ZipFile(outcome.zip_path) as archive:
                self.assertIn("01-AI-量化研究.md", archive.namelist())
                self.assertIn(
                    "files/01-AI-量化研究/asset-0001.png",
                    archive.namelist(),
                )

    def test_reused_root_matches_serialize_and_reparse_path_byte_for_byte(self) -> None:
        with (
            tempfile.TemporaryDirectory() as reused_dir,
            tempfile.TemporaryDirectory() as reparsed_dir,
        ):
            reused_root = Path(reused_dir)
            reparsed_root = Path(reparsed_dir)
            reused = pipeline.run_pipeline(
                FIXTURE_PATH,
                reused_root,
                mode="fast",
                allow_unprocessed_images=True,
            )
            reparsed = pipeline.run_pipeline(
                FIXTURE_PATH,
                reparsed_root,
                mode="fast",
                allow_unprocessed_images=True,
                _reuse_compact_root=False,
            )

            self.assertEqual(reused.status, "converted")
            self.assertEqual(reparsed.status, "converted")
            relative_files = (
                "preflight/content.html",
                "preflight/manifest.json",
                "preflight/formulas.json",
                "preflight/assets.json",
                "formula-results.json",
                "formula-validation.html",
                "pipeline-article/pipeline-article.md",
                "pipeline-article.zip",
            )
            for relative in relative_files:
                self.assertEqual(
                    (reused_root / relative).read_bytes(),
                    (reparsed_root / relative).read_bytes(),
                    relative,
                )

            reused_report = dict(reused.report)
            reparsed_report = dict(reparsed.report)
            reused_report.pop("timings_ms", None)
            reparsed_report.pop("timings_ms", None)
            self.assertEqual(reused_report, reparsed_report)

    def test_adjacent_inline_formulas_are_separated(self) -> None:
        """Two adjacent inline formulas must not collide into a ``$$`` delimiter.

        A paragraph whose only content is two neighbouring inline formulas
        would otherwise serialize as ``$D_t=1$$T_t=2$``; the ``$$`` reads as a
        display-math delimiter on GitHub. The fast path must emit ``$a$ $b$``
        while keeping both as inline math (formula_inline stays 2, no block).
        """

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a paragraph that contains only two adjacent formulas.</p>
          <p><span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">D_t=1</annotation></math></span></span><span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">T_t=2</annotation></math></span></span></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "adjacent.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("$D_t=1$ $T_t=2$", markdown)
            self.assertNotIn("$D_t=1$$T_t=2$", markdown)
            self.assertNotIn("$$", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["formula_inline"], 2)
            self.assertEqual(outcome.report["emitted_counts"]["formula_block"], 0)

    def test_adjacent_inline_formulas_separated_inside_transparent_span(self) -> None:
        """Adjacent formulas nested in a transparent <span> must also separate.

        When the two formulas share a wrapping <span>, the outer paragraph sees
        one fragment and the inner transparent span joins them. That join must
        also go through the separator rule, otherwise ``$a$$b$`` still leaks.
        """

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with two formulas wrapped in a single transparent span.</p>
          <p><span><span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">D_t=1</annotation></math></span></span><span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">T_t=2</annotation></math></span></span></span></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "adjacent-span.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("$D_t=1$ $T_t=2$", markdown)
            self.assertNotIn("$D_t=1$$T_t=2$", markdown)
            self.assertNotIn("$$", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["formula_inline"], 2)
            self.assertEqual(outcome.report["emitted_counts"]["formula_block"], 0)

    def test_data_uri_images_processed_in_fast_path(self) -> None:
        # A data-URI image no longer forces strict handling: it is processed
        # deterministically on the fast path. The fixture's fake PNG cannot be
        # decoded, so it fails closed and is packaged as the original bytes.
        with tempfile.TemporaryDirectory() as directory:
            outcome = pipeline.run_pipeline(FIXTURE_PATH, Path(directory), mode="auto")

            # Not routed to strict: the image no longer blocks the fast path.
            self.assertIn(outcome.status, {"converted", "blocked"})
            self.assertNotEqual(outcome.status, "strict_required")
            self.assertFalse(outcome.report["allow_unprocessed_images"])
            ledger = outcome.report["image_ledger"]
            self.assertEqual(len(ledger), 1)
            entry = ledger[0]
            self.assertEqual(entry["decision"], "keep")
            self.assertEqual(entry["emitted_count"], 1)
            # Fake PNG cannot be decoded, so it fails closed to the original.
            self.assertTrue(entry["fallback_to_original"])

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
            self.assertEqual(outcome.report["recommended_mode"], "strict")

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
            self.assertEqual(outcome.report["recommended_mode"], "strict")
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
            outcome = pipeline.run_pipeline(
                source,
                root / "out",
                mode="fast",
                allow_unprocessed_images=True,
            )

            self.assertEqual(outcome.status, "strict_required")
            self.assertIsNone(outcome.zip_path)
            self.assertEqual(outcome.report["recommended_mode"], "strict")
            self.assertTrue(outcome.report["allow_unprocessed_images"])
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
            self.assertEqual(outcome.report["recommended_mode"], "strict")
            self.assertIn("unsupported semantic element <details>", outcome.report["strict_reasons"][0])

    def test_katex_html_only_formula_requires_matching_validation_report(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and contains one simple formula without an original semantic source.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord mathnormal">x</span></span></span></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "formula.html"
            output = root / "out"
            source.write_text(html, encoding="utf-8")

            pending = pipeline.run_pipeline(source, output, mode="fast")

            self.assertEqual(pending.status, "blocked")
            self.assertIsNone(pending.zip_path)
            self.assertEqual(pending.report["formula_batch"]["pending_validation"], 1)
            self.assertIn("validation report is required", pending.report["formula_validation_error"])
            self.assertIn("{{FORMULA:formula-0001}}", pending.markdown_path.read_text(encoding="utf-8"))

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
                        "items": pending.report["formula_pending_validation"],
                    }
                ),
                encoding="utf-8",
            )

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertIsNotNone(resolved.zip_path)
            assert resolved.markdown_path is not None
            self.assertIn("$x$", resolved.markdown_path.read_text(encoding="utf-8"))
            self.assertEqual(resolved.report["formula_batch"]["pending_validation"], 0)

    def test_unknown_katex_structure_blocks_final_package(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and contains an unsupported matrix structure that must fail closed.</p>
          <span class="katex"><span class="katex-html"><span class="mtable">x</span></span></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unknown-formula.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "blocked")
            self.assertIsNone(outcome.zip_path)
            self.assertEqual(outcome.report["formula_batch"]["failures"], 1)

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
            first = pipeline.run_pipeline(
                FIXTURE_PATH,
                output,
                mode="fast",
                allow_unprocessed_images=True,
            )
            assert first.zip_path is not None
            self.assertTrue(first.zip_path.exists())

            replacement = root / "pipeline_article.html"
            replacement.write_text(blocked_html, encoding="utf-8")
            second = pipeline.run_pipeline(replacement, output, mode="fast")

            self.assertEqual(second.status, "blocked")
            self.assertFalse((output / "pipeline-article.zip").exists())

    def test_zip_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_outcome = pipeline.run_pipeline(
                FIXTURE_PATH,
                Path(first),
                mode="fast",
                allow_unprocessed_images=True,
            )
            second_outcome = pipeline.run_pipeline(
                FIXTURE_PATH,
                Path(second),
                mode="fast",
                allow_unprocessed_images=True,
            )
            assert first_outcome.zip_path is not None
            assert second_outcome.zip_path is not None
            self.assertEqual(
                first_outcome.zip_path.read_bytes(), second_outcome.zip_path.read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
