from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_pipeline_caption_routing", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class PipelineCaptionRoutingTests(unittest.TestCase):
    def test_table_caption_routes_to_strict_instead_of_being_dropped(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          contains a table caption that must not disappear in the fast converter.</p>
          <table>
            <caption>Quarterly revenue by region</caption>
            <tr><th>Region</th><th>Revenue</th></tr>
            <tr><td>APJ</td><td>42</td></tr>
          </table>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "captioned-table.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")
            self.assertIsNone(outcome.markdown_path)
            self.assertIsNone(outcome.zip_path)
            self.assertTrue(
                any(
                    "caption ledger" in reason
                    for reason in outcome.report["strict_reasons"]
                )
            )

    def test_figure_caption_routes_to_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          contains a figure caption whose source identity must remain auditable.</p>
          <figure>
            <figcaption>System architecture</figcaption>
          </figure>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "captioned-figure.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")
            self.assertTrue(
                any(
                    "1 captions require strict handling" in reason
                    for reason in outcome.report["strict_reasons"]
                )
            )


if __name__ == "__main__":
    unittest.main()
