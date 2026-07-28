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

    def test_escape_text_mode_covers_all_special_chars(self) -> None:
        f = formula_batch._escape_text_mode
        self.assertEqual(f("observed_at"), r"observed\_at")
        self.assertEqual(f("a%b"), r"a\%b")
        self.assertEqual(f("c#d"), r"c\#d")
        self.assertEqual(f("e&f"), r"e\&f")
        self.assertEqual(f("p$q"), r"p\$q")
        self.assertEqual(f("g^h"), r"g\textasciicircum{}h")
        self.assertEqual(f("i~j"), r"i\textasciitilde{}j")
        self.assertEqual(f("m{n}o"), r"m\{n\}o")

    def test_escape_text_mode_backslash_not_double_escaped(self) -> None:
        # 单趟替换:插入的 \textbackslash{} 里的反斜杠不得被再次转义
        self.assertEqual(formula_batch._escape_text_mode("k\\l"), r"k\textbackslash{}l")

    def test_escape_text_mode_leaves_safe_chars(self) -> None:
        self.assertEqual(formula_batch._escape_text_mode("abc AB 12 <>|[]"), "abc AB 12 <>|[]")

    def test_text_node_escapes_underscore(self) -> None:
        # KaTeX 对 \text{observed_at} 渲染出的最小结构:mord text 包裹文本
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord text"><span class="mord">observed_at</span></span>'
            '</span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None
        result = formula_batch.parse_katex(node)
        self.assertTrue(result.success)
        self.assertEqual(result.latex, r"\text{observed\_at}")

    def test_math_mode_subscript_underscore_unchanged(self) -> None:
        # 下标结构(msupsub)生成的 _ 是合法 math-mode 结构字符,不得转义
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord"><span class="mord mathnormal">t</span>'
            '<span class="msupsub"><span class="vlist-t vlist-t2"><span class="vlist-r">'
            '<span class="vlist" style="height:0.3361em;">'
            '<span style="top:-2.55em;"><span class="pstrut"></span>'
            '<span class="sizing reset-size6 size3 mtight">'
            '<span class="mord mtight"><span class="mord mathnormal mtight">n</span></span>'
            '</span></span></span></span></span></span></span>'
            '</span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None
        result = formula_batch.parse_katex(node)
        self.assertTrue(result.success)
        self.assertIn("_{", result.latex)          # 下标结构保留
        self.assertNotIn(r"\_", result.latex)       # 未被误转义

    def test_text_mode_with_nested_math_structure_fails_closed(self) -> None:
        # \text{$t_n$} 的真实结构:msupsub 是 .mord.text 的后代。裸拼会得非法
        # \text{t_{n}}(text mode 报 '_' allowed only in math mode)→ 须 fail-close 交 strict。
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord text"><span class="mord">'
            '<span class="mord mathnormal">t</span>'
            '<span class="msupsub"><span class="vlist-t vlist-t2"><span class="vlist-r">'
            '<span class="vlist" style="height:0.15em;"><span style="top:-2.55em;">'
            '<span class="pstrut"></span>'
            '<span class="sizing reset-size6 size3 mtight">'
            '<span class="mord mathnormal mtight">n</span></span></span></span></span></span></span>'
            '</span></span></span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None
        result = formula_batch.parse_katex(node)
        self.assertFalse(result.success)
        # 绝不能静默产出裸下标的非法 \text{}
        self.assertNotIn("t_{", result.latex or "")

    def test_mathbb_subscript_stays_math_mode(self) -> None:
        # \mathbb 内的下标是合法 math,_ 不应被转义成 \_
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord mathbb">'
            '<span class="mord mathbb">R</span>'
            '<span class="msupsub"><span class="vlist-t vlist-t2"><span class="vlist-r">'
            '<span class="vlist" style="height:0.15em;"><span style="top:-2.55em;">'
            '<span class="pstrut"></span>'
            '<span class="sizing reset-size6 size3 mtight">'
            '<span class="mord mathnormal mtight">n</span></span></span></span></span></span></span>'
            '</span></span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None
        result = formula_batch.parse_katex(node)
        self.assertTrue(result.success)
        self.assertIn("_{", result.latex)
        self.assertNotIn(r"\_", result.latex)

    # --- gap #20: 验证要模拟 GitHub 的 $…$ 内反转义 -----------------------------
    # GitHub GFM 会把 $…$ 内 CommonMark 可转义标点前的反斜杠剥掉再喂 KaTeX,所以
    # gap #18 的 \text{a\_b} 转义在 GitHub 上被还原成裸 _ → 渲染报错。validation
    # 文档必须先做同样的反转义再验,才能 fail-close 抓到这类公式。
    # 与 validation_document 内 JS 正则同义的 Python 复刻,供测试直接判定。
    import re as _re

    _GITHUB_MATH_UNESCAPE = _re.compile(r"\\([!-/:-@\[-`{-~])")

    @classmethod
    def _github_math_unescape(cls, s: str) -> str:
        return cls._GITHUB_MATH_UNESCAPE.sub(r"\1", s)

    def test_validation_document_simulates_github_unescape(self) -> None:
        # validation HTML 必须注入 githubMathUnescape,并在 render 前用它变换 latex。
        html = formula_batch.validation_document(
            [{"source_id": "f1", "dom_hash": "h1", "latex": r"\text{a\_b}"}]
        )
        self.assertIn("githubMathUnescape", html)
        # render 的是反转义后的 target,不是原始 item.latex
        self.assertIn("githubMathUnescape(item.latex)", html)
        self.assertIn("katex.render(target", html)

    def test_github_unescape_catches_text_mode_underscore(self) -> None:
        # gap #18 产出的 \text{observed\_at} 在 GitHub 会变成裸 _,这正是要 fail 的输入。
        got = self._github_math_unescape(r"t_{obs} \leftarrow \text{observed\_at}")
        self.assertEqual(got, r"t_{obs} \leftarrow \text{observed_at}")
        # 反转义后含 text mode 裸下划线 → 交给 KaTeX 必失败(此处只断言字符串形态,
        # 端到端 KaTeX 失败由浏览器验证阶段保证)。
        self.assertIn(r"\text{observed_at}", got)
        self.assertNotIn(r"\_", got)

    def test_github_unescape_preserves_command_backslash(self) -> None:
        # 命令反斜杠(\ 后接字母)不得被吃,否则会破坏合法公式。
        for latex in (r"\leftarrow", r"\frac{a}{b}", r"\text{x}", r"A \leq B"):
            self.assertEqual(self._github_math_unescape(latex), latex)
        # 但转义标点仍被还原(全 ASCII 标点集,不止 _)。
        self.assertEqual(self._github_math_unescape(r"a\_b\%c\#d\&e\,f"), r"a_b%c#d&e,f")

    def test_reusing_preflight_root_does_not_mutate_compact_snapshot(self) -> None:
        html = """
        <article>
          <p>This article is long enough for deterministic selection and contains
          a simple KaTeX HTML-only formula for root reuse validation.</p>
          <span class="katex"><span class="katex-html"><span class="base"><span class="mord">x</span></span></span></span>
        </article>
        """
        preflight = formula_batch.preflight.build_preflight(html)
        before = preflight.compact_root.decode(formatter="minimal")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation.html",
                results_path=root / "results.json",
                root=preflight.compact_root,
            )

        self.assertEqual(
            preflight.compact_root.decode(formatter="minimal"),
            before,
        )

    def test_duplicate_formulas_parse_and_validate_once_then_hit_cache(self) -> None:
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
            self.assertTrue(first.stats["cache_written"])
            self.assertTrue(first.stats["validation_html_written"])
            self.assertEqual(first.stats["resolved"], 0)
            self.assertEqual(first.stats["pending_validation"], 2)
            self.assertEqual(first.stats["validation_jobs"], 1)
            self.assertEqual(first.stats["validation_nodes_saved"], 1)
            self.assertEqual(second.stats["cache_hits"], 1)
            self.assertFalse(second.stats["cache_written"])
            self.assertEqual(len(first.pending_validation), 2)
            self.assertEqual(len(first.validation_jobs), 1)
            self.assertEqual(
                first.validation_jobs[0]["source_ids"],
                ["formula-0001", "formula-0002"],
            )
            self.assertIn('data-source-id="formula-0001"', first.validation_html)
            self.assertNotIn('data-source-id="formula-0002"', first.validation_html)
            self.assertIn('data-source-count="2"', first.validation_html)
            self.assertIn("KaTeX runtime is missing", first.validation_html)
            self.assertIn("runFormulaValidation", first.validation_html)

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
                                "source_id": first.validation_jobs[0]["source_id"],
                                "dom_hash": first.validation_jobs[0]["dom_hash"],
                                "latex": first.validation_jobs[0]["latex"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            resolved = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation-3.html",
                results_path=root / "results-3.json",
                validation_report_path=report_path,
            )

            self.assertEqual(resolved.stats["resolved"], 2)
            self.assertEqual(resolved.stats["pending_validation"], 0)
            self.assertEqual(resolved.stats["validation_nodes_saved"], 1)
            self.assertEqual([record.original_latex for record in resolved.records], ["x", "x"])

            results = json.loads((root / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(len(results["validation_jobs"]), 1)
            self.assertEqual(
                results["validation_jobs"][0]["source_ids"],
                ["formula-0001", "formula-0002"],
            )

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
                        "items": [
                            {
                                "source_id": pending.validation_jobs[0]["source_id"],
                                "dom_hash": pending.validation_jobs[0]["dom_hash"],
                                "latex": pending.validation_jobs[0]["latex"],
                            }
                        ],
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

    def test_duplicate_source_ids_in_validation_report_fail_closed(self) -> None:
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
            item = {
                "source_id": pending.validation_jobs[0]["source_id"],
                "dom_hash": pending.validation_jobs[0]["dom_hash"],
                "latex": pending.validation_jobs[0]["latex"],
            }
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
                        "total": 2,
                        "passed": 2,
                        "failures": [],
                        "items": [item, item],
                    }
                ),
                encoding="utf-8",
            )

            result = formula_batch.resolve_formulas(
                preflight.compact_html,
                preflight.formulas,
                cache_path=root / "cache.json",
                validation_path=root / "validation-2.html",
                results_path=root / "results-2.json",
                validation_report_path=report_path,
            )

            self.assertEqual(result.stats["pending_validation"], 1)
            self.assertIn("duplicate source IDs", result.validation_error)

    def test_validation_document_is_byte_deterministic(self) -> None:
        jobs = [
            {
                "source_id": "formula-0001",
                "source_ids": ["formula-0001", "formula-0003"],
                "dom_hash": "hash-a",
                "latex": "x+1",
            },
            {
                "source_id": "formula-0002",
                "source_ids": ["formula-0002"],
                "dom_hash": "hash-b",
                "latex": "y^2",
            },
        ]

        first = formula_batch.validation_document(jobs)
        second = formula_batch.validation_document(jobs)

        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_formula_cache_skips_unchanged_save(self) -> None:
        parsed = formula_batch.ParseResult("x+1", True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            first = formula_batch.FormulaCache(path)
            self.assertTrue(first.put("hash-a", "github", parsed))
            self.assertTrue(first.save())
            before = path.read_bytes()

            warm = formula_batch.FormulaCache(path)
            self.assertFalse(warm.put("hash-a", "github", parsed))
            self.assertFalse(warm.save())

            self.assertEqual(path.read_bytes(), before)

    def test_validation_html_write_is_skipped_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.html"
            self.assertTrue(formula_batch._write_text_if_changed(path, "stable\n"))
            before = path.read_bytes()
            self.assertFalse(formula_batch._write_text_if_changed(path, "stable\n"))
            self.assertEqual(path.read_bytes(), before)

    def test_cache_key_changes_with_parser_version(self) -> None:
        key = formula_batch.FormulaCache.key("abc", "github")
        self.assertIn(formula_batch.PARSER_VERSION, key)
        self.assertTrue(key.endswith("|github"))


if __name__ == "__main__":
    unittest.main()
