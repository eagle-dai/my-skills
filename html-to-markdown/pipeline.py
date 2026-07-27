"""CLI and orchestration for deterministic SingleFile fast/auto conversion."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Sequence


MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from fast_converter import EmittedCounts, FastPathUnsupported, MarkdownConverter
import formula_batch
from formula_batch import resolve_formulas
from pipeline_utils import (
    canonicalize_manifest_counts,
    contracts,
    deterministic_zip,
    preflight,
    root_from_html,
    safe_package_name,
    write_json,
)

SCHEMA_VERSION = "1.2"
RESUME_SCHEMA_VERSION = "1.0"
CONVERTER_VERSION = "markdown-converter-v2"
CONTRACT_VERSION = "html-contracts-v1"
TARGET_PLATFORM = "github"
RESUME_LEDGER_NAME = ".validation-resume.json"
TIMING_FIELDS = (
    "resume",
    "preflight",
    "snapshot",
    "formula",
    "validation",
    "conversion",
    "package",
    "total",
)

_RESUME_ARTIFACT_SCHEMAS: dict[str, str | None] = {
    "preflight/content.html": None,
    "preflight/manifest.json": preflight.SCHEMA_VERSION,
    "preflight/formulas.json": preflight.SCHEMA_VERSION,
    "preflight/assets.json": preflight.SCHEMA_VERSION,
    ".formula-cache.json": formula_batch.SCHEMA_VERSION,
    "formula-results.json": formula_batch.SCHEMA_VERSION,
    "formula-validation.html": None,
}


@dataclass(frozen=True)
class PipelineOutcome:
    status: str
    report: dict[str, Any]
    markdown_path: Path | None = None
    zip_path: Path | None = None


@dataclass(frozen=True)
class ResumeState:
    preflight_result: preflight.PreflightResult


def _elapsed_ms(started_at: float) -> float:
    """Return a stable, JSON-friendly wall-clock duration in milliseconds."""

    return round((time.perf_counter() - started_at) * 1000, 3)


def _new_timings() -> dict[str, float]:
    return {field: 0.0 for field in TIMING_FIELDS}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validation_job_digest(jobs: Sequence[dict[str, Any]]) -> str:
    normalized = [
        {
            "source_id": str(item["source_id"]),
            "source_ids": [str(value) for value in item.get("source_ids", ())],
            "dom_hash": str(item["dom_hash"]),
            "latex": str(item["latex"]),
        }
        for item in jobs
    ]
    return _sha256_bytes(_canonical_json_bytes(normalized))


def _resume_fingerprint(
    *,
    source_sha256: str,
    mode: str,
    allow_unprocessed_images: bool,
    validation_job_digest: str,
    package: str,
) -> dict[str, Any]:
    return {
        "source_sha256": source_sha256,
        "pipeline_schema_version": SCHEMA_VERSION,
        "preflight_schema_version": preflight.SCHEMA_VERSION,
        "formula_schema_version": formula_batch.SCHEMA_VERSION,
        "validation_schema_version": formula_batch.VALIDATION_SCHEMA_VERSION,
        "parser_version": formula_batch.PARSER_VERSION,
        "validator_version": formula_batch.VALIDATOR_VERSION,
        "converter_version": CONVERTER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "target_platform": TARGET_PLATFORM,
        "mode": mode,
        "allow_unprocessed_images": allow_unprocessed_images,
        "validation_job_digest": validation_job_digest,
        "package": package,
    }


def _artifact_entry(
    output: Path,
    relative: str,
    expected_schema: str | None,
) -> dict[str, Any]:
    path = output / relative
    data = path.read_bytes()
    if expected_schema is not None:
        payload = json.loads(data.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != expected_schema:
            raise ValueError(f"resume artifact schema mismatch: {relative}")
    return {
        "path": relative,
        "size": len(data),
        "sha256": _sha256_bytes(data),
        "schema_version": expected_schema,
    }


def _resume_ledger_path(output: Path) -> Path:
    return output / RESUME_LEDGER_NAME


def _remove_resume_ledger(output: Path) -> None:
    _resume_ledger_path(output).unlink(missing_ok=True)


def _write_resume_ledger(
    output: Path,
    *,
    source_sha256: str,
    mode: str,
    allow_unprocessed_images: bool,
    validation_jobs: Sequence[dict[str, Any]],
    package: str,
) -> None:
    job_digest = _validation_job_digest(validation_jobs)
    artifacts = [
        _artifact_entry(output, relative, expected_schema)
        for relative, expected_schema in _RESUME_ARTIFACT_SCHEMAS.items()
    ]
    write_json(
        _resume_ledger_path(output),
        {
            "schema_version": RESUME_SCHEMA_VERSION,
            "fingerprint": _resume_fingerprint(
                source_sha256=source_sha256,
                mode=mode,
                allow_unprocessed_images=allow_unprocessed_images,
                validation_job_digest=job_digest,
                package=package,
            ),
            "artifacts": artifacts,
            "reused_artifacts": sorted(_RESUME_ARTIFACT_SCHEMAS),
            "security_scope": (
                "Artifact digests detect accidental corruption and stale state; "
                "they do not authenticate against an actor who can rewrite both "
                "artifacts and this ledger."
            ),
        },
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise ValueError(f"invalid {label}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"invalid {label}: expected a JSON object")
    return payload


def _validate_artifact_ledger(output: Path, entries: Any) -> None:
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise ValueError("resume ledger artifacts must be a list of objects")
    by_path = {str(item.get("path", "")): item for item in entries}
    if len(by_path) != len(entries):
        raise ValueError("resume ledger contains duplicate artifact paths")
    if set(by_path) != set(_RESUME_ARTIFACT_SCHEMAS):
        raise ValueError("resume ledger artifact set mismatch")

    for relative, expected_schema in _RESUME_ARTIFACT_SCHEMAS.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"unsafe resume artifact path: {relative}")
        entry = by_path[relative]
        if entry.get("schema_version") != expected_schema:
            raise ValueError(f"resume ledger schema metadata mismatch: {relative}")
        path = output / relative
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ValueError(f"resume artifact missing or unreadable: {relative}: {error}") from error
        if int(entry.get("size", -1)) != len(data):
            raise ValueError(f"resume artifact size mismatch: {relative}")
        if str(entry.get("sha256", "")) != _sha256_bytes(data):
            raise ValueError(f"resume artifact digest mismatch: {relative}")
        if expected_schema is not None:
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeError, ValueError, TypeError) as error:
                raise ValueError(f"invalid resume artifact JSON: {relative}: {error}") from error
            if not isinstance(payload, dict) or payload.get("schema_version") != expected_schema:
                raise ValueError(f"resume artifact schema mismatch: {relative}")


def _load_resume_state(
    output: Path,
    *,
    source_sha256: str,
    mode: str,
    allow_unprocessed_images: bool,
    package: str,
) -> tuple[ResumeState | None, str]:
    ledger_path = _resume_ledger_path(output)
    if not ledger_path.exists():
        return None, "resume ledger does not exist"

    try:
        ledger = _read_json_object(ledger_path, "resume ledger")
        if ledger.get("schema_version") != RESUME_SCHEMA_VERSION:
            raise ValueError("resume ledger schema_version mismatch")
        fingerprint = ledger.get("fingerprint")
        if not isinstance(fingerprint, dict):
            raise ValueError("resume ledger fingerprint must be an object")

        static_expected = _resume_fingerprint(
            source_sha256=source_sha256,
            mode=mode,
            allow_unprocessed_images=allow_unprocessed_images,
            validation_job_digest=str(fingerprint.get("validation_job_digest", "")),
            package=package,
        )
        for field, expected in static_expected.items():
            if field == "validation_job_digest":
                continue
            if fingerprint.get(field) != expected:
                raise ValueError(f"resume fingerprint mismatch: {field}")

        _validate_artifact_ledger(output, ledger.get("artifacts"))

        formula_results = _read_json_object(
            output / "formula-results.json", "resume formula results"
        )
        if formula_results.get("parser_version") != formula_batch.PARSER_VERSION:
            raise ValueError("resume formula results parser_version mismatch")
        if formula_results.get("validator_version") != formula_batch.VALIDATOR_VERSION:
            raise ValueError("resume formula results validator_version mismatch")
        if formula_results.get("target_platform") != TARGET_PLATFORM:
            raise ValueError("resume formula results target_platform mismatch")
        jobs = formula_results.get("validation_jobs")
        if not isinstance(jobs, list) or not all(isinstance(item, dict) for item in jobs):
            raise ValueError("resume formula results validation_jobs are invalid")
        job_digest = _validation_job_digest(jobs)
        if fingerprint.get("validation_job_digest") != job_digest:
            raise ValueError("resume validation job digest mismatch")

        manifest = _read_json_object(
            output / "preflight" / "manifest.json", "resume preflight manifest"
        )
        formulas_payload = _read_json_object(
            output / "preflight" / "formulas.json", "resume formula manifest"
        )
        assets_payload = _read_json_object(
            output / "preflight" / "assets.json", "resume asset manifest"
        )
        if manifest.get("schema_version") != preflight.SCHEMA_VERSION:
            raise ValueError("resume preflight manifest schema mismatch")
        for label, payload in (
            ("formula", formulas_payload),
            ("asset", assets_payload),
        ):
            if payload.get("schema_version") != preflight.SCHEMA_VERSION:
                raise ValueError(f"resume {label} manifest schema mismatch")
            if not isinstance(payload.get("items"), list):
                raise ValueError(f"resume {label} manifest items must be a list")

        formulas = tuple(
            preflight.FormulaRecord(**item) for item in formulas_payload["items"]
        )
        assets = tuple(
            preflight.AssetRecord(**item) for item in assets_payload["items"]
        )
        compact_snapshot = (output / "preflight" / "content.html").read_text(
            encoding="utf-8"
        )
        compact_html = compact_snapshot[:-1] if compact_snapshot.endswith("\n") else compact_snapshot
        root = root_from_html(compact_html)
        result = preflight.PreflightResult(
            compact_html,
            manifest,
            formulas,
            assets,
            root,
        )
        return ResumeState(result), ""
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        return None, str(error)


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
    output_name: str,
    manifest: dict[str, Any],
    reasons: list[str],
    *,
    allow_unprocessed_images: bool = False,
    timings_ms: dict[str, float] | None = None,
    resume_used: bool = False,
    resume_fallback_reason: str = "",
) -> PipelineOutcome:
    _remove_resume_ledger(output)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "strict_required",
        "requested_mode": mode,
        "recommended_mode": "strict",
        "output_name": output_name,
        "allow_unprocessed_images": allow_unprocessed_images,
        "strict_reasons": reasons,
        "preflight": manifest,
        "resume_used": resume_used,
        "resume_fallback_reason": resume_fallback_reason,
        "resume_ledger_written": False,
        "resume_ledger_error": "",
        "timings_ms": timings_ms or _new_timings(),
    }
    write_json(output / "report.json", report)
    return PipelineOutcome("strict_required", report)


def _resume_eligible(
    *,
    validation_jobs: Sequence[dict[str, Any]],
    failures: Sequence[dict[str, Any]],
    count_errors: Sequence[str],
    unresolved: Sequence[dict[str, str]],
    pending_validation: Sequence[dict[str, str]],
) -> bool:
    if not validation_jobs or failures or count_errors:
        return False
    pending_ids = {item["source_id"] for item in pending_validation}
    unresolved_ids = {item["source_id"] for item in unresolved}
    return not unresolved_ids or unresolved_ids == pending_ids


def run_pipeline(
    input_path: Path,
    output: Path,
    *,
    mode: str = "auto",
    formula_validation_report: Path | None = None,
    allow_unprocessed_images: bool = False,
    output_name: str | None = None,
    _reuse_compact_root: bool = True,
) -> PipelineOutcome:
    if mode not in {"auto", "fast", "strict"}:
        raise ValueError(f"unsupported mode: {mode}")

    total_started = time.perf_counter()
    timings = _new_timings()
    package = safe_package_name(output_name if output_name is not None else input_path.stem)
    output.mkdir(parents=True, exist_ok=True)
    source_bytes = input_path.read_bytes()
    source_sha256 = _sha256_bytes(source_bytes)

    resume_used = False
    resume_fallback_reason = ""
    resume_state: ResumeState | None = None
    if formula_validation_report is None:
        _remove_resume_ledger(output)
    else:
        resume_started = time.perf_counter()
        resume_state, resume_fallback_reason = _load_resume_state(
            output,
            source_sha256=source_sha256,
            mode=mode,
            allow_unprocessed_images=allow_unprocessed_images,
            package=package,
        )
        resume_used = resume_state is not None

    clear_previous_delivery(output, package)

    preflight_started: float | None = None
    if resume_state is not None:
        result = resume_state.preflight_result
        root = result.compact_root
    else:
        if formula_validation_report is not None:
            _remove_resume_ledger(output)
        preflight_started = time.perf_counter()
        source_html = source_bytes.decode("utf-8")
        result = preflight.build_preflight(source_html)
        root = (
            result.compact_root
            if _reuse_compact_root
            else root_from_html(result.compact_html)
        )

    canonical_error = ""
    try:
        canonicalize_manifest_counts(root, result.manifest)
    except ValueError as error:
        canonical_error = str(error)

    if resume_state is not None:
        timings["resume"] = _elapsed_ms(resume_started)
    else:
        assert preflight_started is not None
        timings["preflight"] = _elapsed_ms(preflight_started)
        snapshot_started = time.perf_counter()
        preflight.write_preflight(result, output / "preflight")
        timings["snapshot"] = _elapsed_ms(snapshot_started)

    reasons = list(result.manifest["signals"]["strict_reasons"])
    if canonical_error:
        reasons.append(canonical_error)

    caption_count = len(root.select(contracts.CSS_SELECTORS["caption"]))
    if caption_count:
        reasons.append(
            f"{caption_count} captions require strict handling because the fast path "
            "does not yet provide caption ledger conservation"
        )

    # Data-URI images are handled deterministically on the fast path (backup,
    # dewatermarking, compression, original-size validation — see
    # image_processing.py). External/lazy/missing images still route to strict
    # via FastPathUnsupported / preflight signals, not here.

    if mode == "strict":
        reasons.append("strict mode explicitly requested")
    if reasons:
        timings["total"] = _elapsed_ms(total_started)
        return strict_outcome(
            output,
            mode,
            package,
            result.manifest,
            reasons,
            allow_unprocessed_images=allow_unprocessed_images,
            timings_ms=timings,
            resume_used=resume_used,
            resume_fallback_reason=resume_fallback_reason,
        )

    article_dir = output / package
    formula_started = time.perf_counter()
    batch = resolve_formulas(
        result.compact_html,
        result.formulas,
        cache_path=output / ".formula-cache.json",
        validation_path=output / "formula-validation.html",
        results_path=output / "formula-results.json",
        validation_report_path=formula_validation_report,
        target_platform=TARGET_PLATFORM,
        root=root if _reuse_compact_root or resume_used else None,
    )
    formula_elapsed = _elapsed_ms(formula_started)
    if formula_validation_report is None:
        timings["formula"] = formula_elapsed
    else:
        timings["validation"] = formula_elapsed

    converter = MarkdownConverter(
        root,
        batch.records,
        result.assets,
        article_dir / "files" / package,
        f"files/{package}",
        orig_dir=article_dir / "files" / package / "images_orig",
        enable_image_processing=not allow_unprocessed_images,
    )
    conversion_started = time.perf_counter()
    try:
        conversion = converter.convert()
    except FastPathUnsupported as error:
        timings["conversion"] = _elapsed_ms(conversion_started)
        clear_previous_delivery(output, package)
        timings["total"] = _elapsed_ms(total_started)
        return strict_outcome(
            output,
            mode,
            package,
            result.manifest,
            [str(error)],
            allow_unprocessed_images=allow_unprocessed_images,
            timings_ms=timings,
            resume_used=resume_used,
            resume_fallback_reason=resume_fallback_reason,
        )
    timings["conversion"] = _elapsed_ms(conversion_started)

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

    package_started = time.perf_counter()
    article_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = article_dir / f"{package}.md"
    markdown_path.write_text(conversion.markdown, encoding="utf-8")
    zip_path = None
    if status == "converted":
        zip_path = output / f"{package}.zip"
        deterministic_zip(article_dir, zip_path)
    timings["package"] = _elapsed_ms(package_started)

    resume_ledger_written = False
    resume_ledger_error = ""
    if _resume_eligible(
        validation_jobs=batch.validation_jobs,
        failures=batch.failures,
        count_errors=count_errors,
        unresolved=unresolved,
        pending_validation=batch.pending_validation,
    ):
        try:
            _write_resume_ledger(
                output,
                source_sha256=source_sha256,
                mode=mode,
                allow_unprocessed_images=allow_unprocessed_images,
                validation_jobs=batch.validation_jobs,
                package=package,
            )
            resume_ledger_written = True
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            _remove_resume_ledger(output)
            resume_ledger_error = str(error)
    else:
        _remove_resume_ledger(output)

    timings["total"] = _elapsed_ms(total_started)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "requested_mode": mode,
        "output_name": package,
        "allow_unprocessed_images": allow_unprocessed_images,
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
        "resume_used": resume_used,
        "resume_fallback_reason": resume_fallback_reason,
        "resume_ledger_written": resume_ledger_written,
        "resume_ledger_error": resume_ledger_error,
        "timings_ms": timings,
    }
    write_json(output / "report.json", report)
    return PipelineOutcome(status, report, markdown_path, zip_path)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Run the SingleFile fast-path pipeline")
    value.add_argument("input", type=Path)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--mode", choices=("auto", "fast", "strict"), default="auto")
    value.add_argument(
        "--output-name",
        help=(
            "Exact logical basename for the package, Markdown file, resource "
            "directory, and ZIP. It is normalized mechanically; when omitted, "
            "the input filename stem is used."
        ),
    )
    value.add_argument(
        "--formula-validation-report",
        type=Path,
        help="JSON emitted after running formula-validation.html with a pinned KaTeX runtime",
    )
    value.add_argument(
        "--allow-unprocessed-images",
        action="store_true",
        help=(
            "Skip deterministic image post-processing and package data-URI "
            "images as-is (no backup/dewatermark/compression/validation). Does "
            "not change fast/strict routing. Use only when the user explicitly "
            "opts out of image post-processing."
        ),
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
            allow_unprocessed_images=args.allow_unprocessed_images,
            output_name=args.output_name,
        )
    except (OSError, UnicodeError, ValueError, preflight.BodySelectionError) as error:
        print(f"pipeline failed: {error}")
        return 2
    print(json.dumps(outcome.report, ensure_ascii=False, sort_keys=True))
    return 0 if outcome.status == "converted" else 3 if outcome.status == "strict_required" else 4


if __name__ == "__main__":
    raise SystemExit(main())
