from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "pipeline_article.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline_timings", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class PipelineTimingTests(unittest.TestCase):
    def assert_timing_contract(self, report: dict[str, object]) -> None:
        timings = report["timings_ms"]
        assert isinstance(timings, dict)
        self.assertEqual(set(timings), set(pipeline.TIMING_FIELDS))
        self.assertTrue(all(float(value) >= 0.0 for value in timings.values()))
        self.assertGreater(float(timings["total"]), 0.0)

    def test_converted_report_contains_all_timing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outcome = pipeline.run_pipeline(
                FIXTURE_PATH,
                Path(directory),
                mode="auto",
                allow_unprocessed_images=True,
            )

        self.assertEqual(outcome.status, "converted")
        self.assert_timing_contract(outcome.report)
        self.assertGreater(outcome.report["timings_ms"]["formula"], 0.0)
        self.assertEqual(outcome.report["timings_ms"]["validation"], 0.0)

    def test_strict_report_contains_preflight_and_snapshot_timings(self) -> None:
        # A virtualized editor is detected during preflight, so the pipeline
        # routes to strict before ever entering formula resolution — the
        # strict-report timing contract with formula == 0.
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
        self.assert_timing_contract(outcome.report)
        self.assertGreater(outcome.report["timings_ms"]["preflight"], 0.0)
        self.assertGreaterEqual(outcome.report["timings_ms"]["snapshot"], 0.0)
        self.assertEqual(outcome.report["timings_ms"]["formula"], 0.0)

    def test_blocked_report_contains_timing_fields(self) -> None:
        html = """
        <html><body><article>
          <p>This article is sufficiently long for deterministic body selection and
          contains one KaTeX HTML-only formula that awaits browser validation.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord mathnormal">x</span></span></span></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "blocked.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

        self.assertEqual(outcome.status, "blocked")
        self.assert_timing_contract(outcome.report)
        self.assertGreater(outcome.report["timings_ms"]["formula"], 0.0)
        self.assertEqual(outcome.report["timings_ms"]["validation"], 0.0)


if __name__ == "__main__":
    unittest.main()
