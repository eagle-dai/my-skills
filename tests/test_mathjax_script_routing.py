from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline_mathjax", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class MathJaxScriptRoutingTests(unittest.TestCase):
    def test_standalone_math_tex_script_routes_to_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This article has enough visible prose for deterministic body selection,
          but its MathJax v2 source formula is a standalone script node.</p>
          <script type="math/tex; mode=display">x^2 + y^2</script>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "standalone-mathjax.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIsNone(outcome.markdown_path)
            self.assertIsNone(outcome.zip_path)
            self.assertTrue(
                any(
                    "standalone math/tex script formulas" in reason
                    for reason in outcome.report["strict_reasons"]
                )
            )

    def test_nested_math_tex_script_remains_a_fast_original_latex_source(self) -> None:
        html = """
        <html><body><article>
          <p>This article has enough visible prose for deterministic body selection
          and contains a formula source nested in a recognized KaTeX container.</p>
          <span class="katex"><script type="math/tex">x^2</script></span>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nested-math-script.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            self.assertIn("$x^2$", outcome.markdown_path.read_text(encoding="utf-8"))
            self.assertFalse(
                any(
                    "standalone math/tex script formulas" in reason
                    for reason in outcome.report.get("strict_reasons", [])
                )
            )


if __name__ == "__main__":
    unittest.main()
