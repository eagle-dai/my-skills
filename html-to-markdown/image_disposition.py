"""Executable image keep/remove decisions for html-to-markdown."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, Sequence


ImageDecision = Literal["keep", "remove_as_ui", "manual_review"]


@dataclass(frozen=True)
class ImageContext:
    source_id: str
    is_qr_code: bool = False
    in_body: bool = False
    has_content_relation: bool = False
    inside_share_or_follow_ui: bool = False
    decorative: bool = False
    decoded_url: str = ""


def decide_image(context: ImageContext) -> ImageDecision:
    """Classify one image without silently deleting uncertain content.

    QR codes are not inherently UI noise. A body-related QR code is content;
    an uncertain QR code is preserved for review. Only an image with positive UI
    evidence and no body/content relationship is removable by default.
    """

    content_related = context.in_body or context.has_content_relation

    if context.is_qr_code:
        if context.inside_share_or_follow_ui and not content_related:
            return "remove_as_ui"
        if content_related:
            return "keep"
        return "manual_review"

    if (context.decorative or context.inside_share_or_follow_ui) and not content_related:
        return "remove_as_ui"
    return "keep"


@dataclass(frozen=True)
class ImageLedgerEntry:
    source_id: str
    decision: ImageDecision
    emitted_count: int
    reason: str = ""
    decoded_url: str = ""
    decoded_link_emitted: bool = False


_ALLOWED_DECISIONS = {"keep", "remove_as_ui", "manual_review"}


def _duplicate_values(values: Sequence[str]) -> tuple[str, ...]:
    counts = Counter(values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def validate_image_ledger(
    entries: Sequence[ImageLedgerEntry],
    *,
    source_ids: Sequence[str],
) -> tuple[str, ...]:
    """Validate that every source image is preserved or explicitly explained.

    A decoded URL is part of the preserved content contract: when a kept or
    manual-review image has a decoded URL, the Markdown output must include a
    clickable link and record that emission in the ledger.
    """

    errors: list[str] = []
    expected = set(source_ids)
    for duplicate in _duplicate_values(source_ids):
        errors.append(f"duplicate source image id: {duplicate}")
    if "" in expected:
        errors.append("source image id must not be empty")

    seen: set[str] = set()
    for entry in entries:
        if not entry.source_id:
            errors.append("image source_id must not be empty")
        elif entry.source_id in seen:
            errors.append(f"duplicate image source_id: {entry.source_id}")
        else:
            seen.add(entry.source_id)

        if entry.decision not in _ALLOWED_DECISIONS:
            errors.append(f"unknown image decision for {entry.source_id}: {entry.decision}")
            continue
        if entry.emitted_count < 0:
            errors.append(f"negative emitted_count for {entry.source_id}")
            continue

        decoded_url = entry.decoded_url.strip()
        if entry.decoded_link_emitted and not decoded_url:
            errors.append(
                f"image {entry.source_id} marks a decoded link as emitted "
                "without decoded_url"
            )

        if entry.decision == "remove_as_ui":
            if entry.emitted_count != 0:
                errors.append(
                    f"removed image {entry.source_id} must have emitted_count == 0"
                )
            if not entry.reason.strip():
                errors.append(
                    f"removed image {entry.source_id} requires positive UI evidence"
                )
            if entry.decoded_link_emitted:
                errors.append(
                    f"removed image {entry.source_id} must not emit a decoded link"
                )
            continue

        # Both keep and manual_review preserve the original image. Uncertainty
        # must never turn into silent deletion.
        if entry.emitted_count != 1:
            errors.append(
                f"preserved image {entry.source_id} must have emitted_count == 1"
            )
        if entry.decision == "manual_review" and not entry.reason.strip():
            errors.append(f"manual_review image {entry.source_id} requires a reason")
        if decoded_url and not entry.decoded_link_emitted:
            errors.append(
                f"decoded URL for image {entry.source_id} must be emitted "
                "as a clickable link"
            )

    missing = expected - seen
    unexpected = seen - expected
    if missing:
        errors.append(f"missing source image ids: {sorted(missing)}")
    if unexpected:
        errors.append(f"unexpected source image ids: {sorted(unexpected)}")

    return tuple(errors)


def assert_valid_image_ledger(
    entries: Sequence[ImageLedgerEntry],
    *,
    source_ids: Sequence[str],
) -> None:
    errors = validate_image_ledger(entries, source_ids=source_ids)
    if errors:
        raise ValueError("; ".join(errors))
