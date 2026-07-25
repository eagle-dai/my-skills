from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_benchmark", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_synthetic_benchmark_covers_original_and_two_stage_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = benchmark.run_benchmark(
                iterations=2,
                workdir=Path(directory),
                style_blocks=120,
                style_payload_bytes=768,
                formula_count=12,
                unique_formulas=3,
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["schema_version"], "1.1")
        self.assertEqual(
            set(result["scenarios"]),
            {"original_latex", "katex_html_only"},
        )

        original = result["scenarios"]["original_latex"]
        self.assertGreaterEqual(original["snapshot_reduction_percent"], 80.0)
        self.assertEqual(original["formula_total"], 12)
        self.assertEqual(original["formula_unique"], 3)
        self.assertEqual(original["formula_cache_hits_warm"], 3)
        self.assertEqual(original["passes"]["cold"]["status"], "converted")
        self.assertEqual(original["passes"]["warm"]["status"], "converted")

        html_only = result["scenarios"]["katex_html_only"]
        self.assertGreaterEqual(html_only["snapshot_reduction_percent"], 80.0)
        self.assertEqual(html_only["formula_total"], 12)
        self.assertEqual(html_only["formula_unique"], 3)
        self.assertEqual(html_only["validation_jobs"], 3)
        self.assertEqual(html_only["validation_nodes_saved"], 9)
        self.assertEqual(html_only["validation_source_counts"], [4, 4, 4])
        self.assertEqual(html_only["formula_cache_hits_validation"], 3)
        self.assertEqual(html_only["formula_cache_hits_warm"], 3)
        self.assertEqual(html_only["passes"]["cold"]["status"], "blocked")
        self.assertEqual(html_only["passes"]["validation"]["status"], "converted")
        self.assertEqual(html_only["passes"]["warm"]["status"], "converted")

        for scenario in (original, html_only):
            pass_records = scenario["passes"]
            measured = [pass_records["cold"], pass_records["warm"]]
            if "validation" in pass_records:
                measured.append(pass_records["validation"])
            for item in measured:
                timings = item.get("timings_ms") or item["median_timings_ms"]
                self.assertEqual(
                    set(timings),
                    set(benchmark.pipeline.TIMING_FIELDS),
                )
                self.assertGreater(timings["total"], 0.0)

        # PR 1 locks in measurable current behavior. PR 2 will deliberately
        # update this regression from five parses to two.
        self.assertEqual(
            original["passes"]["cold"]["parse_counts"],
            {
                "full_document": 2,
                "detached_body": 1,
                "compact_snapshot": 2,
            },
        )
        self.assertEqual(original["passes"]["cold"]["parse_total"], 5)
        self.assertEqual(html_only["passes"]["cold"]["parse_total"], 5)
        self.assertEqual(html_only["passes"]["validation"]["parse_total"], 5)
        self.assertEqual(
            html_only["passes"]["warm"]["median_parse_total"],
            5,
        )

        # PR 1 measures the current unconditional cache write. PR 3 will
        # change warm/validation passes to zero when no entry changed.
        self.assertEqual(original["passes"]["cold"]["formula_cache_writes"], 1)
        self.assertEqual(
            original["passes"]["warm"]["median_formula_cache_writes"],
            1,
        )
        self.assertEqual(html_only["passes"]["cold"]["formula_cache_writes"], 1)
        self.assertEqual(
            html_only["passes"]["validation"]["formula_cache_writes"],
            1,
        )
        self.assertEqual(
            html_only["passes"]["warm"]["median_formula_cache_writes"],
            1,
        )

    def test_benchmark_requires_a_warm_iteration(self) -> None:
        with self.assertRaisesRegex(ValueError, "iterations must be >= 2"):
            benchmark.run_benchmark(iterations=1)


if __name__ == "__main__":
    unittest.main()
