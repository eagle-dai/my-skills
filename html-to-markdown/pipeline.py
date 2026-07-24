"""CLI and orchestration for deterministic SingleFile fast/auto conversion."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import sys
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from fast_converter import EmittedCounts, FastPathUnsupported, MarkdownConverter
from formula_batch import resolve_formulas
from pipeline_utils import (
    canonicalize_manifest_counts,
    deterministic_zip,
    preflight,
    root_from_html,
    safe_file_name,
    safe_package_name,
    title_from_root,
    write_json,
)

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PipelineOutcome:
    status: str
    report: dict[str, Any]
    markdown_path: Path | None = None
    zip_path: Path | None = None


def validate_counts(expected: dict[str, int], emitted: EmittedCounts) -> list[str]:
    actual = emitted.as_dict()
    return [
        f"{field}: expected {expected.get(field, 0)}, emitted {value}"
        for field, value in actual.items()
        if int(expected.get(field, 0)) != value
    ]


def clear_previous_delivery(output: Path, package: str) -> None:
    """Remove stale deliverables before starting a new run."""

    article_dir = output / package
    zip_path = output / f"{package}.zip"
    if article_dir.exists():
        shutil.rmtree(article_dir)
    if zip_path.exists():
        zip_path.unlink()


def strict_outcome(
    output: Path,
    mode: str,
    manifest: dict[str, Any],
    reasons: list[str],
) -> PipelineOutcome:
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "strict_required",
        "requested_mode": mode,
        "recommended_mode": manifest["recommended_mode"],
        "strict_reasons": reasons,
        "preflight": manifest,
    }
    write_json(output / "report.json", report)
    return PipelineOutcome("strict_required", report)


def run_pipeline(
    input_path: Path,
    output: Path,
    *,
    mode: str = "auto",
    formula_validation_report: Path | None = None,
) -> PipelineOutcome:
    if mode not in {"auto", "fast", "strict"}:
        raise ValueError(f"unsupported mode: {mode}")

    package = safe_package_name(input_path.stem)
    output.mkdir(parents=True, exist_ok=True)
    clear_previous_delivery(output, package)

    result = preflight.build_preflight(input_path.read_text(encoding="utf-8"))
    root = root_from_html(result.compact_html)
    canonical_error = ""
    try:
        canonicalize_manifest_counts(root, result.manifest)
    except ValueError as error:
        canonical_error = str(error)

    preflight.write_preflight(result, output / "preflight")
    reasons = list(result.manifest["signals"]["strict_reasons"])
    if canonical_error:
        reasons.append(canonical_error)
    if mode == "strict":
        reasons.append("strict mode explicitly requested")
    if reasons:
        return strict_outcome(output, mode, result.manifest, reasons)

    article_dir = output / package
    title = title_from_root(root, input_path.stem)
    batch = resolve_formulas(
        result.compact_html,
        result.formulas,
        cache_path=output / ".formula-cache.json",
        validation_path=output / "formula-validation.html",
        results_path=output / "formula-results.json",
        validation_report_path=formula_validation_report,
    )
    converter = MarkdownConverter(
        root,
        batch.records,
        result.assets,
        article_dir / "files" / package,
        f"files/{package}",
    )
    try:
        conversion = converter.convert()
    except FastPathUnsupported as error:
        clear_previous_delivery(output, package)
        return strict_outcome(output, mode, result.manifest, [str(error)])

    count_errors = validate_counts(result.manifest["counts"], conversion.counts)
    unresolved = list(conversion.unresolved_formulas)
    blockers = list(count_errors)
    if batch.failures:
        blockers.append(f"{len(batch.failures)} formula parse failures")
    if batch.pending_validation:
        blockers.append(
            f"{len(batch.pending_validation)} formulas await batch KaTeX validation"
        )
    if batch.validation_error:
        blockers.append(batch.validation_error)
    if unresolved and not (batch.failures or batch.pending_validation):
        blockers.append(f"{len(unresolved)} formulas require batch resolution")
    status = "blocked" if blockers else "converted"

    article_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = article_dir / f"{safe_file_name(title)}.md"
    markdown_path.write_text(conversion.markdown, encoding="utf-8")
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "requested_mode": mode,
        "preflight": result.manifest,
        "emitted_counts": conversion.counts.as_dict(),
        "count_errors": count_errors,
        "unresolved_formulas": unresolved,
        "warnings": list(conversion.warnings),
        "image_ledger": [asdict(entry) for entry in conversion.image_ledger],
        "markdown": str(markdown_path.relative_to(output)),
        "blockers": blockers,
        "formula_batch": batch.stats,
        "formula_failures": list(batch.failures),
        "formula_pending_validation": list(batch.pending_validation),
        "formula_validation_error": batch.validation_error,
    }
    write_json(output / "report.json", report)

    zip_path = None
    if status == "converted":
        zip_path = output / f"{package}.zip"
        deterministic_zip(article_dir, zip_path)
    return PipelineOutcome(status, report, markdown_path, zip_path)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Run the SingleFile fast-path pipeline")
    value.add_argument("input", type=Path)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--mode", choices=("auto", "fast", "strict"), default="auto")
    value.add_argument(
        "--formula-validation-report",
        type=Path,
        help="JSON emitted after running formula-validation.html with a pinned KaTeX runtime",
    )
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        outcome = run_pipeline(
            args.input,
            args.output,
            mode=args.mode,
            formula_validation_report=args.formula_validation_report,
        )
    except (OSError, UnicodeError, ValueError, preflight.BodySelectionError) as error:
        print(f"pipeline failed: {error}")
        return 2
    print(json.dumps(outcome.report, ensure_ascii=False, sort_keys=True))
    return 0 if outcome.status == "converted" else 3 if outcome.status == "strict_required" else 4


if __name__ == "__main__":
    raise SystemExit(main())
