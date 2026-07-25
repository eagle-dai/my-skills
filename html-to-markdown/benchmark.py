"""Repeatable synthetic benchmark for the deterministic SingleFile pipeline.

The benchmark deliberately uses generated content rather than a paid/private page.
It covers both formulas that already contain original LaTeX and the real two-stage
KaTeX HTML-only workflow: blocked cold pass, validation-report ingestion, and a
warm cache pass. Instrumentation stays benchmark-local so implementation costs can
be measured without expanding the stable pipeline report schema.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any, Iterator, Sequence

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import formula_batch
import pipeline
import pipeline_utils

DEFAULT_MIN_REDUCTION_PERCENT = 80.0
FORMULA_MODES = ("original-latex", "katex-html-only")


def _formula_html(index: int, unique_formulas: int, mode: str) -> str:
    formula_index = index % unique_formulas
    semantic_source = (
        (
            '<span class="katex-mathml"><math>'
            '<annotation encoding="application/x-tex">'
            f"x_{{{formula_index}}}+1"
            "</annotation></math></span>"
        )
        if mode == "original-latex"
        else ""
    )
    return (
        '<span class="katex">'
        f"{semantic_source}"
        '<span class="katex-html"><span class="base">'
        f'<span class="mord mathnormal">x{formula_index}</span>'
        '<span class="mbin">+</span><span class="mord">1</span>'
        "</span></span></span>"
    )


def build_synthetic_singlefile(
    *,
    style_blocks: int = 600,
    style_payload_bytes: int = 1024,
    formula_count: int = 168,
    unique_formulas: int = 12,
    formula_mode: str = "original-latex",
) -> str:
    """Build a deterministic, CSS-heavy article with repeated formulas."""

    if style_blocks < 1 or style_payload_bytes < 64:
        raise ValueError("style_blocks must be positive and style_payload_bytes >= 64")
    if formula_count < 1 or unique_formulas < 1 or unique_formulas > formula_count:
        raise ValueError("require 1 <= unique_formulas <= formula_count")
    if formula_mode not in FORMULA_MODES:
        raise ValueError(f"unsupported formula_mode: {formula_mode}")

    padding = "x" * style_payload_bytes
    styles = "\n".join(
        f"<style>.singlefile-{index}{{--payload:{padding};}}</style>"
        for index in range(style_blocks)
    )
    formulas = "\n".join(
        _formula_html(index, unique_formulas, formula_mode)
        for index in range(formula_count)
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Synthetic SingleFile benchmark</title>
{styles}
<script>window.__singlefile_noise__ = true;</script>
</head>
<body>
<nav>Navigation and page chrome that must not enter the compact snapshot.</nav>
<article>
<h1>Synthetic SingleFile benchmark</h1>
<p>This generated article is intentionally long enough for deterministic body
selection. It contains repeated formulas and ordinary semantic structures, while
large page-level styles simulate the inlined resources found in SingleFile pages.</p>
<h2>Structures</h2>
<ul><li>First item</li><li>Second item</li></ul>
<table><tr><th>Name</th><th>Value</th></tr><tr><td>alpha</td><td>1</td></tr></table>
<pre><code>print("benchmark")</code></pre>
<p>{formulas}</p>
</article>
<footer>Footer chrome outside the selected article.</footer>
</body>
</html>
"""


class _Instrumentation:
    def __init__(self) -> None:
        self.parse_counts: Counter[str] = Counter()
        self.formula_cache_writes = 0

    def reset(self) -> None:
        self.parse_counts.clear()
        self.formula_cache_writes = 0

    def snapshot(self) -> dict[str, Any]:
        counts = {
            name: int(self.parse_counts.get(name, 0))
            for name in ("full_document", "detached_body", "compact_snapshot")
        }
        return {
            "parse_counts": counts,
            "parse_total": sum(counts.values()),
            "formula_cache_writes": self.formula_cache_writes,
        }


@contextmanager
def _instrument_pipeline(metrics: _Instrumentation) -> Iterator[None]:
    """Count parser and formula-cache writes without changing production schemas."""

    original_pipeline_soup = getattr(pipeline, "BeautifulSoup", None)
    original_preflight_soup = pipeline.preflight.BeautifulSoup
    original_utils_soup = pipeline_utils.BeautifulSoup
    original_formula_write_json = formula_batch.write_json

    def pipeline_soup(markup: Any, *args: Any, **kwargs: Any) -> Any:
        metrics.parse_counts["full_document"] += 1
        return original_pipeline_soup(markup, *args, **kwargs)

    def preflight_soup(markup: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(markup).lstrip().lower()
        category = (
            "full_document"
            if text.startswith("<!doctype") or "<head" in text or text.startswith("<html")
            else "detached_body"
        )
        metrics.parse_counts[category] += 1
        return original_preflight_soup(markup, *args, **kwargs)

    def utils_soup(markup: Any, *args: Any, **kwargs: Any) -> Any:
        metrics.parse_counts["compact_snapshot"] += 1
        return original_utils_soup(markup, *args, **kwargs)

    def measured_write_json(path: Path, payload: Any) -> None:
        if Path(path).name == ".formula-cache.json":
            metrics.formula_cache_writes += 1
        original_formula_write_json(path, payload)

    if original_pipeline_soup is not None:
        pipeline.BeautifulSoup = pipeline_soup
    pipeline.preflight.BeautifulSoup = preflight_soup
    pipeline_utils.BeautifulSoup = utils_soup
    formula_batch.write_json = measured_write_json
    try:
        yield
    finally:
        if original_pipeline_soup is not None:
            pipeline.BeautifulSoup = original_pipeline_soup
        pipeline.preflight.BeautifulSoup = original_preflight_soup
        pipeline_utils.BeautifulSoup = original_utils_soup
        formula_batch.write_json = original_formula_write_json


def _median_timings(reports: Sequence[dict[str, Any]]) -> dict[str, float]:
    fields = pipeline.TIMING_FIELDS
    return {
        field: round(
            statistics.median(
                float(report["timings_ms"].get(field, 0.0)) for report in reports
            ),
            3,
        )
        for field in fields
    }


def _median_integer_metrics(
    values: Sequence[dict[str, Any]],
    field: str,
) -> dict[str, int] | int:
    if field == "parse_counts":
        names = ("full_document", "detached_body", "compact_snapshot")
        return {
            name: int(statistics.median(item[field][name] for item in values))
            for name in names
        }
    return int(statistics.median(int(item[field]) for item in values))


def _pass_record(outcome: Any, metrics: _Instrumentation) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "timings_ms": dict(outcome.report["timings_ms"]),
        **metrics.snapshot(),
    }


def _warm_summary(
    outcomes: Sequence[Any],
    metric_snapshots: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "iterations": len(outcomes),
        "status": "converted",
        "median_timings_ms": _median_timings(
            [outcome.report for outcome in outcomes]
        ),
        "median_parse_counts": _median_integer_metrics(
            metric_snapshots, "parse_counts"
        ),
        "median_parse_total": _median_integer_metrics(
            metric_snapshots, "parse_total"
        ),
        "median_formula_cache_writes": _median_integer_metrics(
            metric_snapshots, "formula_cache_writes"
        ),
    }


def _validation_jobs_from_pending(
    pending: Sequence[dict[str, str]],
) -> list[dict[str, Any]]:
    jobs_by_hash: dict[str, dict[str, Any]] = {}
    for item in pending:
        job = jobs_by_hash.setdefault(
            item["dom_hash"],
            {
                "source_id": item["source_id"],
                "source_ids": [],
                "dom_hash": item["dom_hash"],
                "latex": item["latex"],
            },
        )
        job["source_ids"].append(item["source_id"])
    return list(jobs_by_hash.values())


def _write_validation_report(path: Path, jobs: Sequence[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": formula_batch.VALIDATION_SCHEMA_VERSION,
                "parser_version": formula_batch.PARSER_VERSION,
                "validator_version": formula_batch.VALIDATOR_VERSION,
                "runtime_loaded": True,
                "completed": True,
                "katex_version": "synthetic-benchmark-runtime",
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
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _scenario_sizes(report: dict[str, Any]) -> dict[str, Any]:
    sizes = report["preflight"]["sizes"]
    return {
        "snapshot_reduction_percent": round(
            (1.0 - float(sizes["reduction_ratio"])) * 100.0,
            3,
        ),
        "input_bytes": int(sizes["input_bytes"]),
        "compact_bytes": int(sizes["compact_bytes"]),
        "visible_text_bytes": int(sizes["visible_text_bytes"]),
    }


def _assert_formula_conservation(
    report: dict[str, Any],
    *,
    formula_count: int,
    unique_formulas: int,
) -> dict[str, int]:
    stats = report["formula_batch"]
    actual_total = int(stats["formula_total"])
    actual_unique = int(stats["formula_unique"])
    if actual_total != formula_count or actual_unique != unique_formulas:
        raise RuntimeError(
            "formula conservation failed: "
            f"expected total/unique {formula_count}/{unique_formulas}, "
            f"got {actual_total}/{actual_unique}"
        )
    return {
        "formula_total": actual_total,
        "formula_unique": actual_unique,
    }


def _run_original_latex_scenario(
    *,
    source: Path,
    output: Path,
    warm_iterations: int,
    metrics: _Instrumentation,
    formula_count: int,
    unique_formulas: int,
) -> dict[str, Any]:
    metrics.reset()
    cold = pipeline.run_pipeline(source, output, mode="auto")
    cold_pass = _pass_record(cold, metrics)
    if cold.status != "converted" or cold.zip_path is None:
        raise RuntimeError(
            "original-LaTeX cold pass did not convert: "
            f"{cold.status} {cold.report.get('strict_reasons') or cold.report.get('blockers')}"
        )

    warm_outcomes: list[Any] = []
    warm_metrics: list[dict[str, Any]] = []
    for _ in range(warm_iterations):
        metrics.reset()
        outcome = pipeline.run_pipeline(source, output, mode="auto")
        if outcome.status != "converted" or outcome.zip_path is None:
            raise RuntimeError(
                "original-LaTeX warm pass did not convert: "
                f"{outcome.status} {outcome.report.get('strict_reasons') or outcome.report.get('blockers')}"
            )
        warm_outcomes.append(outcome)
        warm_metrics.append(metrics.snapshot())

    cache_hits = int(warm_outcomes[-1].report["formula_batch"]["cache_hits"])
    if cache_hits != unique_formulas:
        raise RuntimeError(
            f"formula cache reuse failed: expected {unique_formulas} hits, got {cache_hits}"
        )

    return {
        "status": "passed",
        **_scenario_sizes(cold.report),
        **_assert_formula_conservation(
            cold.report,
            formula_count=formula_count,
            unique_formulas=unique_formulas,
        ),
        "formula_cache_hits_warm": cache_hits,
        "passes": {
            "cold": cold_pass,
            "warm": _warm_summary(warm_outcomes, warm_metrics),
        },
    }


def _run_html_only_scenario(
    *,
    source: Path,
    output: Path,
    validation_report: Path,
    warm_iterations: int,
    metrics: _Instrumentation,
    formula_count: int,
    unique_formulas: int,
) -> dict[str, Any]:
    metrics.reset()
    cold = pipeline.run_pipeline(source, output, mode="fast")
    cold_pass = _pass_record(cold, metrics)
    if cold.status != "blocked" or cold.zip_path is not None:
        raise RuntimeError(
            "KaTeX HTML-only cold pass must block before validation: "
            f"{cold.status} {cold.report.get('strict_reasons') or cold.report.get('blockers')}"
        )

    conservation = _assert_formula_conservation(
        cold.report,
        formula_count=formula_count,
        unique_formulas=unique_formulas,
    )
    jobs = _validation_jobs_from_pending(cold.report["formula_pending_validation"])
    stats = cold.report["formula_batch"]
    if len(jobs) != unique_formulas:
        raise RuntimeError(
            f"validation deduplication failed: expected {unique_formulas} jobs, got {len(jobs)}"
        )
    if int(stats["validation_jobs"]) != len(jobs):
        raise RuntimeError("formula stats validation_jobs do not match pending job groups")
    if sum(len(item["source_ids"]) for item in jobs) != formula_count:
        raise RuntimeError("validation job source mapping does not conserve formula nodes")

    _write_validation_report(validation_report, jobs)

    metrics.reset()
    validated = pipeline.run_pipeline(
        source,
        output,
        mode="fast",
        formula_validation_report=validation_report,
    )
    validation_pass = _pass_record(validated, metrics)
    if validated.status != "converted" or validated.zip_path is None:
        raise RuntimeError(
            "KaTeX HTML-only validation pass did not convert: "
            f"{validated.status} {validated.report.get('strict_reasons') or validated.report.get('blockers')}"
        )

    warm_outcomes: list[Any] = []
    warm_metrics: list[dict[str, Any]] = []
    for _ in range(warm_iterations):
        metrics.reset()
        outcome = pipeline.run_pipeline(
            source,
            output,
            mode="fast",
            formula_validation_report=validation_report,
        )
        if outcome.status != "converted" or outcome.zip_path is None:
            raise RuntimeError(
                "KaTeX HTML-only warm pass did not convert: "
                f"{outcome.status} {outcome.report.get('strict_reasons') or outcome.report.get('blockers')}"
            )
        warm_outcomes.append(outcome)
        warm_metrics.append(metrics.snapshot())

    cache_hits = int(warm_outcomes[-1].report["formula_batch"]["cache_hits"])
    if cache_hits != unique_formulas:
        raise RuntimeError(
            f"HTML-only cache reuse failed: expected {unique_formulas} hits, got {cache_hits}"
        )

    return {
        "status": "passed",
        **_scenario_sizes(cold.report),
        **conservation,
        "validation_jobs": len(jobs),
        "validation_nodes_saved": formula_count - len(jobs),
        "validation_source_counts": [len(item["source_ids"]) for item in jobs],
        "formula_cache_hits_validation": int(
            validated.report["formula_batch"]["cache_hits"]
        ),
        "formula_cache_hits_warm": cache_hits,
        "passes": {
            "cold": cold_pass,
            "validation": validation_pass,
            "warm": _warm_summary(warm_outcomes, warm_metrics),
        },
    }


def run_benchmark(
    *,
    iterations: int = 3,
    workdir: Path | None = None,
    style_blocks: int = 600,
    style_payload_bytes: int = 1024,
    formula_count: int = 168,
    unique_formulas: int = 12,
    min_reduction_percent: float = DEFAULT_MIN_REDUCTION_PERCENT,
) -> dict[str, Any]:
    """Run original-LaTeX and KaTeX HTML-only benchmark scenarios."""

    if iterations < 2:
        raise ValueError("iterations must be >= 2 so every scenario has a warm pass")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if workdir is None:
        temporary = tempfile.TemporaryDirectory(prefix="html-to-markdown-benchmark-")
        root = Path(temporary.name)
    else:
        root = workdir
        root.mkdir(parents=True, exist_ok=True)

    warm_iterations = iterations - 1
    metrics = _Instrumentation()
    try:
        original_source = root / "synthetic-original-latex.html"
        html_only_source = root / "synthetic-katex-html-only.html"
        original_source.write_text(
            build_synthetic_singlefile(
                style_blocks=style_blocks,
                style_payload_bytes=style_payload_bytes,
                formula_count=formula_count,
                unique_formulas=unique_formulas,
                formula_mode="original-latex",
            ),
            encoding="utf-8",
        )
        html_only_source.write_text(
            build_synthetic_singlefile(
                style_blocks=style_blocks,
                style_payload_bytes=style_payload_bytes,
                formula_count=formula_count,
                unique_formulas=unique_formulas,
                formula_mode="katex-html-only",
            ),
            encoding="utf-8",
        )

        with _instrument_pipeline(metrics):
            original = _run_original_latex_scenario(
                source=original_source,
                output=root / "original-output",
                warm_iterations=warm_iterations,
                metrics=metrics,
                formula_count=formula_count,
                unique_formulas=unique_formulas,
            )
            html_only = _run_html_only_scenario(
                source=html_only_source,
                output=root / "html-only-output",
                validation_report=root / "synthetic-validation-report.json",
                warm_iterations=warm_iterations,
                metrics=metrics,
                formula_count=formula_count,
                unique_formulas=unique_formulas,
            )

        scenarios = {
            "original_latex": original,
            "katex_html_only": html_only,
        }
        below_threshold = [
            name
            for name, scenario in scenarios.items()
            if float(scenario["snapshot_reduction_percent"]) < min_reduction_percent
        ]
        if below_threshold:
            raise RuntimeError(
                "snapshot reduction is below the required "
                f"{min_reduction_percent}% for: {', '.join(below_threshold)}"
            )

        return {
            "schema_version": "1.1",
            "iterations": iterations,
            "warm_iterations": warm_iterations,
            "status": "passed",
            "minimum_reduction_percent": min_reduction_percent,
            "scenarios": scenarios,
            # Compatibility summary for existing consumers: original-LaTeX scenario.
            "snapshot_reduction_percent": original["snapshot_reduction_percent"],
            "input_bytes": original["input_bytes"],
            "compact_bytes": original["compact_bytes"],
            "visible_text_bytes": original["visible_text_bytes"],
            "formula_total": original["formula_total"],
            "formula_unique": original["formula_unique"],
            "formula_cache_hits_last_run": original["formula_cache_hits_warm"],
            "median_timings_ms": original["passes"]["warm"]["median_timings_ms"],
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Benchmark original-LaTeX and two-stage KaTeX HTML-only "
            "SingleFile conversion"
        )
    )
    value.add_argument("--iterations", type=int, default=3)
    value.add_argument("--workdir", type=Path, help="Keep generated inputs and outputs here")
    value.add_argument("--style-blocks", type=int, default=600)
    value.add_argument("--style-payload-bytes", type=int, default=1024)
    value.add_argument("--formula-count", type=int, default=168)
    value.add_argument("--unique-formulas", type=int, default=12)
    value.add_argument(
        "--min-reduction-percent",
        type=float,
        default=DEFAULT_MIN_REDUCTION_PERCENT,
    )
    value.add_argument("--json-output", type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = run_benchmark(
            iterations=args.iterations,
            workdir=args.workdir,
            style_blocks=args.style_blocks,
            style_payload_bytes=args.style_payload_bytes,
            formula_count=args.formula_count,
            unique_formulas=args.unique_formulas,
            min_reduction_percent=args.min_reduction_percent,
        )
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
