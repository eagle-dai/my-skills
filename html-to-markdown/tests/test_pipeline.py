from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


SKILL = Path(__file__).resolve().parent.parent
MODULE_PATH = SKILL / "pipeline.py"
FORMULA_MODULE_PATH = SKILL / "formula_batch.py"
FIXTURE_PATH = SKILL / "tests" / "fixtures" / "pipeline_article.html"
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

    def test_slate_code_block_preserves_line_breaks(self) -> None:
        """Slate code blocks store each line as its own block-level <div>.

        The hljs/simplebar wrapper emits one ``<div>`` per source line and lets
        the block boundary carry the newline; there is no ``\\n`` text node
        between lines. ``get_text()`` therefore glues the lines together
        (``a.jsonb.py``). The fast path must join the per-line divs with ``\\n``
        so a three-line snippet stays three lines.
        """

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a multi-line Slate code block rendered by highlight.js.</p>
          <pre data-slate-type="pre"><div class="simplebar-content"><div class="se-line"><span>Test-Path a.json</span></div><div class="se-line"><span>Test-Path b.py</span></div><div class="se-line"><span>echo done</span></div></div></pre>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "slate-code.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Test-Path a.json\nTest-Path b.py\necho done", markdown)
            self.assertNotIn("Test-Path a.jsonTest-Path b.py", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["codeblocks"], 1)

    def test_inline_div_wrapper_is_transparent_on_fast_path(self) -> None:
        """An inline-only <div> wrapper inside a paragraph must be transparent.

        Some editors wrap inline runs in a bare ``<div>`` that carries no block
        child. The block context already flattens such wrappers via
        ``has_block_child``; the inline context must do the same instead of
        forcing the whole page to strict.
        """

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a Slate paragraph wrapping an inline div run.</p>
          <div data-slate-type="paragraph">lead <div>wrapped <strong>text</strong> and <span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">x=1</annotation></math></span></span></div></div>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inline-div.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("lead wrapped **text** and $x=1$", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["formula_inline"], 1)

    def test_inline_div_with_block_child_still_routes_to_strict(self) -> None:
        """A wrapper div hiding a block child must still route to strict."""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a Slate paragraph hiding a block element inside a div.</p>
          <div data-slate-type="paragraph">lead <div>text <p>nested block</p></div></div>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inline-div-block.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")

    def test_unknown_inline_element_still_routes_to_strict(self) -> None:
        """An unknown inline element must still route to strict, not flatten."""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a paragraph carrying an unknown inline widget.</p>
          <p>before <custom-widget data-x="1">inner</custom-widget> after</p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "unknown-inline.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")

    def test_p_with_tail_block_wrapper_converts_on_fast_path(self) -> None:
        """mdnice: <p><span>导语</span><section><table></section></p> 拆成段落+表格。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a mdnice-style paragraph wrapping a table.</p>
          <p><span>一个好的估计量应具备以下性质：</span><section data-tool="mdnice"><table><thead><tr><th>性质</th><th>定义</th></tr></thead><tbody><tr><td>无偏性</td><td>期望等于真值</td></tr></tbody></table></section></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mdnice-tail.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("一个好的估计量应具备以下性质：", markdown)
            self.assertIn("| 性质 | 定义 |", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["tables"], 1)

    def test_p_with_multiple_tail_block_wrappers_converts(self) -> None:
        """前导行内 + 两个尾部 section 块 → converted，两块都在。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a paragraph wrapping two tables.</p>
          <p><strong>两张表：</strong><section><table><tr><td>a</td></tr></table></section><section><table><tr><td>b</td></tr></table></section></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mdnice-multi.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            self.assertEqual(outcome.report["emitted_counts"]["tables"], 2)

    def test_p_with_block_wrapper_then_inline_still_strict(self) -> None:
        """块后还有行内文字（混排非尾部）→ 维持 fail-close strict。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a paragraph mixing a block then trailing inline text.</p>
          <p><span>lead</span><section><table><tr><td>x</td></tr></table></section><span>trailing text after block</span></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mdnice-midblock.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")

    def test_slate_paragraph_with_block_wrapper_still_strict(self) -> None:
        """Slate 段落含块 wrapper 不进新拆分逻辑 → 维持 strict。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a Slate paragraph hiding a section-wrapped table.</p>
          <div data-slate-type="paragraph">lead <section><table><tr><td>x</td></tr></table></section></div>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "slate-block.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")

    def test_p_pure_block_wrapper_no_empty_paragraph(self) -> None:
        """无前导行内的纯块 wrapper → converted，无孤立空段落。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a paragraph wrapping only a table, no leading text.</p>
          <p><section><table><thead><tr><th>col</th></tr></thead><tbody><tr><td>val</td></tr></tbody></table></section></p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pure-block.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertNotIn("\n\n\n\n", markdown)  # 无孤立空段落
            self.assertEqual(outcome.report["emitted_counts"]["tables"], 1)

    def test_li_with_mdnice_section_paragraph_converts(self) -> None:
        """mdnice: <li><section><p>文字</p></section></li> → 普通列表项。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with an ordered list whose items are mdnice-wrapped.</p>
          <ol>
            <li><section data-tool="mdnice"><p>提出假设</p></section></li>
            <li><section data-tool="mdnice"><p>选择检验统计量</p></section></li>
          </ol>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "li-mdnice.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("1. 提出假设", markdown)
            self.assertIn("2. 选择检验统计量", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["list_items"], 2)

    def test_li_with_section_wrapping_table_still_strict(self) -> None:
        """li 里 section 裹真块（table）→ 维持 fail-close strict。"""

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with a list item hiding a real table inside a section.</p>
          <ul>
            <li><section><table><tr><td>x</td></tr></table></section></li>
          </ul>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "li-table.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertEqual(outcome.report["recommended_mode"], "strict")

    def test_list_with_floating_nested_list_converts(self) -> None:
        """<ol> 直接含游离 <ul>（非 li 内）→ 嵌套项不被吞，公式守恒。

        WeChat/mdnice 会产出 <ol><li>..</li><ul><li>..</li></ul><li>..</li></ol>，
        嵌套 ul 直接挂在 ol 下而非 li 内。list_block 若只遍历 li 会整块吞掉该 ul。
        """

        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection
          and ends with an ordered list carrying a floating nested list.</p>
          <ol>
            <li>first</li>
            <ul><li>nested item with <span class="katex"><span class="katex-mathml"><math><annotation encoding="application/x-tex">x=1</annotation></math></span></span></li></ul>
            <li>second</li>
          </ol>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "floating-list.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("1. first", markdown)
            self.assertIn("2. second", markdown)
            self.assertIn("nested item with $x=1$", markdown)
            # 3 list items (first, nested, second), formula preserved
            self.assertEqual(outcome.report["emitted_counts"]["list_items"], 3)
            self.assertEqual(outcome.report["emitted_counts"]["formula_inline"], 1)

    def test_image_originals_backed_up_outside_delivery_zip(self) -> None:
        """Original-image backups are auditable but must not ship in the ZIP.

        The untouched originals are kept for offline audit of the dewatermark
        step, but they double the package size and are not part of the
        deliverable. They belong in a sibling ``<package>__images_orig``
        directory outside the packaged tree, never inside ``files/`` or the ZIP.
        """

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            outcome = pipeline.run_pipeline(FIXTURE_PATH, output, mode="fast")

            assert outcome.zip_path is not None
            with zipfile.ZipFile(outcome.zip_path) as archive:
                names = archive.namelist()
            self.assertFalse(
                any("images_orig" in name for name in names),
                f"images_orig leaked into the ZIP: {names}",
            )
            # The backup still exists, outside the packaged article directory.
            backups = list(output.glob("*__images_orig/*"))
            self.assertTrue(backups, "original-image backup was not written")
            # Nothing named images_orig may live inside the packaged tree.
            self.assertEqual(
                list((output / "pipeline-article").glob("**/images_orig")),
                [],
                "images_orig must not live inside the packaged tree",
            )

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


def _substantial_png_data_uri() -> str:
    """A decodable, non-placeholder PNG data-URI (>512B) like SingleFile inlines."""
    import base64
    import io
    import random

    from PIL import Image

    img = Image.new("RGB", (96, 72))
    px = img.load()
    rng = random.Random(42)  # 固定种子=可重复；噪声保证 PNG 不被压到 512B 以下
    for y in range(72):
        for x in range(96):
            px[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class WeChatMmbizPipelineTests(unittest.TestCase):
    """端到端：微信公众号页面（正文 + MathJax-SVG 公式 + data-URI 图）的路由与产出。"""

    def _wechat_html(self, body_inner: str) -> str:
        return (
            "<html><body id='activity-detail'>"
            "<div id='js_article' class='rich_media'>"
            "<div id='js_content' class='rich_media_content'>"
            f"{body_inner}"
            "</div></div></body></html>"
        )

    def test_wechat_article_converts_with_formulas_and_data_uri_image(self) -> None:
        # 正例：微信正文 + 块级/行内 data-formula 公式 + 完整 data-URI 图 → converted。
        html = self._wechat_html(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "随后给出块级与行内公式，并附一张已内联为 data-URI 的图片。</p>"
            "<section data-formula='R_t = \\frac{P_t}{P_{t-1}} - 1' "
            "style='text-align:center;display:block'><svg role='img'></svg></section>"
            "<p>行内公式 <span data-formula='n'><svg role='img'></svg></span> 出现在句中。</p>"
            f"<p><img src='{_substantial_png_data_uri()}' "
            "data-src='https://mmbiz.qpic.cn/leftover.png' alt='图片'></p>"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertIn(outcome.status, {"converted", "blocked"})
            self.assertNotEqual(outcome.status, "strict_required")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            # 块级公式 → $$…$$；行内公式 → $…$（verbatim LaTeX，来自 data-formula）
            self.assertIn("$$\nR_t = \\frac{P_t}{P_{t-1}} - 1\n$$", markdown)
            self.assertIn("$n$", markdown)
            self.assertEqual(outcome.report["emitted_counts"]["formula_block"], 1)
            self.assertEqual(outcome.report["emitted_counts"]["formula_inline"], 1)
            # 图片按 data-URI 处理（未被误判 lazy 推向 strict）
            self.assertIn("files/wechat/", markdown)

    def test_wechat_span_wrapper_with_block_children_passes_through(self) -> None:
        # 正例：WeChat 用 <span data-tool> 包裹块级 <section>，块位置 span 含块子
        # 时应透明穿透（等价 block-transparent），不再 unsupported <span> → strict。
        html = self._wechat_html(
            "<span data-tool='mp' style='display:block'>"
            "<section><p>这是被 span 包裹的一段足够长的微信正文，用来越过 body "
            "选择的最小文本阈值，并验证块位置 span 透明穿透后正文能正常转换，"
            "而不是因为一个包裹用的 span 就把整篇文章保守地推到 strict 处理。</p>"
            "<h2>小节标题</h2></section>"
            "</span>"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat-span.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertIn(outcome.status, {"converted", "blocked"})
            self.assertNotEqual(outcome.status, "strict_required")
            assert outcome.markdown_path is not None
            markdown = outcome.markdown_path.read_text(encoding="utf-8")
            self.assertIn("## 小节标题", markdown)
            self.assertIn("这是被 span 包裹的一段足够长的微信正文", markdown)

    def test_slate_typed_span_still_fails_closed(self) -> None:
        # 反例：带 data-slate-type 的 span 不当透明 wrapper（not slate 守卫），
        # 落到 block() 无匹配分支仍 fail-close → strict。
        html = self._wechat_html(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "随后出现一个带 slate 语义但 fast path 未知的块级 span，"
            "它应当被 not-slate 守卫挡住，保守地把整篇路由到 strict 处理。</p>"
            "<span data-slate-type='mystery-block'><section><p>x</p></section></span>"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat-slate-span.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertEqual(outcome.status, "strict_required")

    def test_wechat_plain_svg_illustration_routes_to_strict(self) -> None:
        # 反例：正文含无 data-formula 的真插图 <svg> → fast path fail-closed → strict。
        html = self._wechat_html(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "随后嵌入一张普通统计图插图（没有 data-formula 的 SVG），"
            "它应当让 fast path 保守失败并把整篇路由到 strict 处理。</p>"
            "<p><svg role='img' viewBox='0 0 720 480'><path d='M0 0L10 10'/>"
            "<text>标签</text></svg></p>"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat-svg.html"
            source.write_text(html, encoding="utf-8")
            outcome = pipeline.run_pipeline(source, root / "out", mode="auto")

            self.assertEqual(outcome.status, "strict_required")


if __name__ == "__main__":
    unittest.main()
