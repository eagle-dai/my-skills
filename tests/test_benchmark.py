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
    def test_synthetic_benchmark_meets_reduction_and_reports_timings(self) -> None:
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
        self.assertGreaterEqual(result["snapshot_reduction_percent"], 80.0)
        self.assertEqual(result["formula_total"], 12)
        self.assertEqual(result["formula_unique"], 3)
        self.assertEqual(result["formula_cache_hits_last_run"], 3)
        self.assertEqual(
            set(result["median_timings_ms"]),
            set(benchmark.pipeline.TIMING_FIELDS),
        )
        self.assertGreater(result["median_timings_ms"]["total"], 0.0)


if __name__ == "__main__":
    unittest.main()
