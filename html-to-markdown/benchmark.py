"""Repeatable synthetic benchmark for the deterministic SingleFile pipeline.

The benchmark deliberately uses generated content rather than a paid/private page.
It validates the measurable contract from issue #15: page-level CSS dominates the
input, the compact snapshot removes at least 80%, duplicate formulas remain
mapped to every source node, and the complete fast path produces a ZIP.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any, Sequence

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import pipeline

DEFAULT_MIN_REDUCTION_PERCENT = 80.0


def build_synthetic_singlefile(
    *,
    style_blocks: int = 600,
    style_payload_bytes: int = 1024,
    formula_count: int = 168,
    unique_formulas: int = 12,
) -> str:
    """Build a deterministic, CSS-heavy static article with repeated formulas."""

    if style_blocks < 1 or style_payload_bytes < 64:
        raise ValueError("style_blocks must be positive and style_payload_bytes >= 64")
    if formula_count < 1 or unique_formulas < 1 or unique_formulas > formula_count:
        raise ValueError("require 1 <= unique_formulas <= formula_count")

    padding = "x" * style_payload_bytes
    styles = "\n".join(
        f"<style>.singlefile-{index}{{--payload:{padding};}}</style>"
        for index in range(style_blocks)
    )
    formulas = "\n".join(
        (
            '<span class="katex">'
            '<span class="katex-mathml"><math>'
            '<annotation encoding="application/x-tex">'
            f"x_{{{index % unique_formulas}}}+1"
            "</annotation></math></span>"
            '<span class="katex-html"><span class="base">'
            f'<span class="mord mathnormal">x{index % unique_formulas}</span>'
            '<span class="mbin">+</span><span class="mord">1</span>'
            "</span></span></span>"
        )
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


def _median_timings(reports: Sequence[dict[str, Any]]) -> dict[str, float]:
    fields = pipeline.TIMING_FIELDS
    return {
        field: round(
            statistics.median(float(report["timings_ms"].get(field, 0.0)) for report in reports),
            3,
        )
        for field in fields
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
    """Run the synthetic pipeline benchmark and return machine-readable metrics."""

    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if workdir is None:
        temporary = tempfile.TemporaryDirectory(prefix="html-to-markdown-benchmark-")
        root = Path(temporary.name)
    else:
        root = workdir
        root.mkdir(parents=True, exist_ok=True)

    try:
        source = root / "synthetic-singlefile.html"
        source.write_text(
            build_synthetic_singlefile(
                style_blocks=style_blocks,
                style_payload_bytes=style_payload_bytes,
                formula_count=formula_count,
                unique_formulas=unique_formulas,
            ),
            encoding="utf-8",
        )

        reports: list[dict[str, Any]] = []
        for index in range(iterations):
            outcome = pipeline.run_pipeline(
                source,
                root / "output",
                mode="auto",
            )
            if outcome.status != "converted" or outcome.zip_path is None:
                raise RuntimeError(
                    f"benchmark iteration {index + 1} did not convert: "
                    f"{outcome.status} {outcome.report.get('strict_reasons') or outcome.report.get('blockers')}"
                )
            reports.append(outcome.report)

        first = reports[0]
        sizes = first["preflight"]["sizes"]
        reduction_percent = round((1.0 - float(sizes["reduction_ratio"])) * 100.0, 3)
        formula_stats = first["formula_batch"]
        actual_formula_total = int(formula_stats["formula_total"])
        actual_formula_unique = int(formula_stats["formula_unique"])
        if actual_formula_total != formula_count or actual_formula_unique != unique_formulas:
            raise RuntimeError(
                "formula conservation failed: "
                f"expected total/unique {formula_count}/{unique_formulas}, "
                f"got {actual_formula_total}/{actual_formula_unique}"
            )

        cache_hits = int(reports[-1]["formula_batch"]["cache_hits"])
        if iterations > 1 and cache_hits != unique_formulas:
            raise RuntimeError(
                f"formula cache reuse failed: expected {unique_formulas} hits, got {cache_hits}"
            )

        result = {
            "schema_version": "1.0",
            "iterations": iterations,
            "status": "passed" if reduction_percent >= min_reduction_percent else "failed",
            "minimum_reduction_percent": min_reduction_percent,
            "snapshot_reduction_percent": reduction_percent,
            "input_bytes": int(sizes["input_bytes"]),
            "compact_bytes": int(sizes["compact_bytes"]),
            "visible_text_bytes": int(sizes["visible_text_bytes"]),
            "formula_total": actual_formula_total,
            "formula_unique": actual_formula_unique,
            "formula_cache_hits_last_run": cache_hits,
            "median_timings_ms": _median_timings(reports),
        }
        if result["status"] != "passed":
            raise RuntimeError(
                f"snapshot reduction {reduction_percent}% is below "
                f"the required {min_reduction_percent}%"
            )
        return result
    finally:
        if temporary is not None:
            temporary.cleanup()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Benchmark the deterministic HTML-to-Markdown pipeline on synthetic SingleFile input"
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
