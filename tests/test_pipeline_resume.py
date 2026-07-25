from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
FORMULA_PATH = ROOT / "html-to-markdown" / "formula_batch.py"
PIPELINE_SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_pipeline_resume_tests", PIPELINE_PATH
)
assert PIPELINE_SPEC is not None and PIPELINE_SPEC.loader is not None
pipeline = importlib.util.module_from_spec(PIPELINE_SPEC)
sys.modules[PIPELINE_SPEC.name] = pipeline
PIPELINE_SPEC.loader.exec_module(pipeline)
FORMULA_SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_formula_resume_tests", FORMULA_PATH
)
assert FORMULA_SPEC is not None and FORMULA_SPEC.loader is not None
formula_batch = importlib.util.module_from_spec(FORMULA_SPEC)
sys.modules[FORMULA_SPEC.name] = formula_batch
FORMULA_SPEC.loader.exec_module(formula_batch)


def html_only_source(symbol: str = "x") -> str:
    return f"""
    <html><body><article>
      <p>This article body is sufficiently long for deterministic body selection
      and contains one KaTeX HTML-only formula that requires browser validation.</p>
      <span class="katex"><span class="katex-html"><span class="base">
        <span class="mord mathnormal">{symbol}</span>
      </span></span></span>
    </article></body></html>
    """


def write_validation_report(output: Path, report_path: Path) -> None:
    formula_results = json.loads(
        (output / "formula-results.json").read_text(encoding="utf-8")
    )
    jobs = formula_results["validation_jobs"]
    report_path.write_text(
        json.dumps(
            {
                "schema_version": formula_batch.VALIDATION_SCHEMA_VERSION,
                "parser_version": formula_batch.PARSER_VERSION,
                "validator_version": formula_batch.VALIDATOR_VERSION,
                "runtime_loaded": True,
                "completed": True,
                "katex_version": "resume-test-runtime",
                "total": len(jobs),
                "passed": len(jobs),
                "failures": [],
                "items": [
                    {
                        "source_id": item["source_id"],
                        "dom_hash": item["dom_hash"],
                        "latex": item["latex"],
                    }
                    for item in jobs
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


class PipelineResumeTests(unittest.TestCase):
    def cold_run(self, root: Path, *, symbol: str = "x") -> tuple[Path, Path, object]:
        source = root / "resume.html"
        output = root / "out"
        source.write_text(html_only_source(symbol), encoding="utf-8")
        cold = pipeline.run_pipeline(source, output, mode="fast")
        self.assertEqual(cold.status, "blocked")
        self.assertTrue(cold.report["resume_ledger_written"])
        self.assertTrue((output / pipeline.RESUME_LEDGER_NAME).exists())
        report_path = root / "validation-report.json"
        write_validation_report(output, report_path)
        return source, report_path, cold

    def test_validation_rerun_uses_verified_resume_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"

            with mock.patch.object(
                pipeline.preflight,
                "build_preflight",
                side_effect=AssertionError("full preflight must not run"),
            ):
                resolved = pipeline.run_pipeline(
                    source,
                    output,
                    mode="fast",
                    formula_validation_report=report_path,
                )

            self.assertEqual(resolved.status, "converted")
            self.assertTrue(resolved.report["resume_used"])
            self.assertEqual(resolved.report["resume_fallback_reason"], "")
            self.assertTrue(resolved.report["resume_ledger_written"])
            self.assertEqual(resolved.report["timings_ms"]["preflight"], 0.0)
            self.assertEqual(resolved.report["timings_ms"]["snapshot"], 0.0)
            self.assertGreater(resolved.report["timings_ms"]["resume"], 0.0)
            self.assertIsNotNone(resolved.zip_path)

    def test_resume_ledger_covers_exact_trusted_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _ = self.cold_run(root)
            output = root / "out"
            ledger = json.loads(
                (output / pipeline.RESUME_LEDGER_NAME).read_text(encoding="utf-8")
            )

            self.assertEqual(ledger["schema_version"], pipeline.RESUME_SCHEMA_VERSION)
            self.assertEqual(
                {item["path"] for item in ledger["artifacts"]},
                set(pipeline._RESUME_ARTIFACT_SCHEMAS),
            )
            for item in ledger["artifacts"]:
                artifact = output / item["path"]
                self.assertEqual(item["size"], len(artifact.read_bytes()))
                self.assertEqual(item["sha256"], pipeline._sha256_bytes(artifact.read_bytes()))
            self.assertIn("do not authenticate", ledger["security_scope"])

    def test_corrupt_artifact_falls_back_to_full_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"
            content = output / "preflight" / "content.html"
            content.write_text(content.read_text(encoding="utf-8") + "<!-- corrupt -->", encoding="utf-8")

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn("artifact", resolved.report["resume_fallback_reason"])
            self.assertIn("mismatch", resolved.report["resume_fallback_reason"])
            self.assertGreater(resolved.report["timings_ms"]["preflight"], 0.0)

    def test_malformed_ledger_falls_back_to_full_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"
            (output / pipeline.RESUME_LEDGER_NAME).write_text("{not-json", encoding="utf-8")

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn("invalid resume ledger", resolved.report["resume_fallback_reason"])

    def test_missing_artifact_falls_back_to_full_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"
            (output / ".formula-cache.json").unlink()

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn("missing or unreadable", resolved.report["resume_fallback_reason"])

    def test_source_change_cannot_use_or_unlock_stale_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root, symbol="x")
            output = root / "out"
            source.write_text(html_only_source("y"), encoding="utf-8")

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "blocked")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn("source_sha256", resolved.report["resume_fallback_reason"])
            self.assertIsNone(resolved.zip_path)
            self.assertTrue(resolved.report["formula_validation_error"])

    def test_validation_job_digest_mismatch_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"
            ledger_path = output / pipeline.RESUME_LEDGER_NAME
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["fingerprint"]["validation_job_digest"] = "0" * 64
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="fast",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn(
                "validation job digest", resolved.report["resume_fallback_reason"]
            )

    def test_mode_mismatch_falls_back_to_full_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, report_path, _ = self.cold_run(root)
            output = root / "out"

            resolved = pipeline.run_pipeline(
                source,
                output,
                mode="auto",
                formula_validation_report=report_path,
            )

            self.assertEqual(resolved.status, "converted")
            self.assertFalse(resolved.report["resume_used"])
            self.assertIn("mode", resolved.report["resume_fallback_reason"])

    def test_resume_ledger_write_failure_is_non_blocking_and_cleans_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.html"
            output = root / "out"
            source.write_text(html_only_source(), encoding="utf-8")
            original = pipeline.write_json

            def fail_ledger(path: Path, payload: object) -> None:
                if Path(path).name == pipeline.RESUME_LEDGER_NAME:
                    raise OSError("simulated resume ledger failure")
                original(path, payload)

            with mock.patch.object(pipeline, "write_json", side_effect=fail_ledger):
                cold = pipeline.run_pipeline(source, output, mode="fast")

            self.assertEqual(cold.status, "blocked")
            self.assertFalse(cold.report["resume_ledger_written"])
            self.assertIn("simulated resume ledger failure", cold.report["resume_ledger_error"])
            self.assertFalse((output / pipeline.RESUME_LEDGER_NAME).exists())
            self.assertTrue((output / "report.json").exists())

    def test_resume_ledger_is_written_through_atomic_json_helper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.html"
            output = root / "out"
            source.write_text(html_only_source(), encoding="utf-8")
            original = pipeline.write_json
            destinations: list[Path] = []

            def measured(path: Path, payload: object) -> None:
                destinations.append(Path(path))
                original(path, payload)

            with mock.patch.object(pipeline, "write_json", side_effect=measured):
                cold = pipeline.run_pipeline(source, output, mode="fast")

            self.assertEqual(cold.status, "blocked")
            self.assertIn(output / pipeline.RESUME_LEDGER_NAME, destinations)
            self.assertEqual(
                list(output.glob(f".{pipeline.RESUME_LEDGER_NAME}.*.tmp")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
