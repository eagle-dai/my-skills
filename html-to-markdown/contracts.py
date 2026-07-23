"""Executable contracts for the html-to-markdown skill.

The Markdown files explain the workflow. This module owns the small pieces that
must be deterministic and regression-testable: selector syntax, complexity
classification, semantic candidate de-duplication, and comment ledger checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence


CSS_SELECTORS: Mapping[str, str] = {
    "codeblock": '[data-slate-type="pre"], pre > code',
    "table": '[data-slate-type="table"], table',
    "list": '[data-slate-type="list"], ul, ol',
    "list_item": '[data-slate-type="list-line"], li',
    "formula": '[data-slate-type*="katex"], .katex, math',
    "caption": 'figure > figcaption, table > caption',
    "heading": '[data-slate-type^="heading"], h1, h2, h3, h4, h5, h6',
}


@dataclass(frozen=True)
class DomCounts:
    formula_block: int = 0
    formula_inline: int = 0
    table: int = 0
    list: int = 0
    list_item: int = 0
    image: int = 0
    caption: int = 0
    codeblock: int = 0
    heading: int = 0
    comment: int = 0

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"{name} must be >= 0")

    @property
    def formula_total(self) -> int:
        return self.formula_block + self.formula_inline


def classify_complexity(counts: DomCounts, *, has_original_latex: bool) -> int:
    """Return the workflow level defined by the skill contract.

    Level 0 is intentionally explicit: there are no formulas, body images,
    code blocks, tables, or comments. Lists may still exist and are covered by
    the baseline checks shared by every level.
    """

    if counts.formula_total == 0:
        has_rich_blocks = any(
            (
                counts.image,
                counts.codeblock,
                counts.table,
                counts.comment,
            )
        )
        return 1 if has_rich_blocks else 0

    return 2 if has_original_latex else 3


@dataclass(frozen=True)
class SemanticCandidate:
    """One DOM representation of a semantic content block.

    ``semantic_id`` groups multiple DOM nodes that represent the same block,
    for example a Slate table wrapper and its nested native ``<table>``.
    Lower ``priority`` wins; input order breaks ties deterministically.
    """

    semantic_id: str
    source_dom_id: str
    representation: str
    priority: int


def canonicalize_candidates(
    candidates: Iterable[SemanticCandidate],
) -> tuple[SemanticCandidate, ...]:
    """Return exactly one candidate for each semantic block."""

    chosen: dict[str, tuple[int, SemanticCandidate]] = {}
    for index, candidate in enumerate(candidates):
        if not candidate.semantic_id:
            raise ValueError("semantic_id must not be empty")
        if not candidate.source_dom_id:
            raise ValueError("source_dom_id must not be empty")

        current = chosen.get(candidate.semantic_id)
        rank = (candidate.priority, index)
        if current is None or rank < (current[1].priority, current[0]):
            chosen[candidate.semantic_id] = (index, candidate)

    return tuple(item[1] for item in sorted(chosen.values(), key=lambda pair: pair[0]))


CommentStatus = Literal["kept", "removed_as_noise", "failed", "manual_review"]


@dataclass(frozen=True)
class CommentLedgerEntry:
    source_id: str
    status: CommentStatus
    emitted_count: int
    reason: str = ""


_ALLOWED_COMMENT_STATUSES = {
    "kept",
    "removed_as_noise",
    "failed",
    "manual_review",
}


def validate_comment_ledger(
    entries: Sequence[CommentLedgerEntry],
    *,
    source_total: int,
) -> tuple[str, ...]:
    """Validate comment conservation without requiring output-count equality."""

    errors: list[str] = []
    if source_total < 0:
        return ("source_total must be >= 0",)

    if len(entries) != source_total:
        errors.append(
            f"ledger entry count {len(entries)} does not equal source_total {source_total}"
        )

    seen: set[str] = set()
    for entry in entries:
        if not entry.source_id:
            errors.append("comment source_id must not be empty")
        elif entry.source_id in seen:
            errors.append(f"duplicate comment source_id: {entry.source_id}")
        else:
            seen.add(entry.source_id)

        if entry.status not in _ALLOWED_COMMENT_STATUSES:
            errors.append(f"unknown comment status for {entry.source_id}: {entry.status}")
            continue

        if entry.emitted_count < 0:
            errors.append(f"negative emitted_count for {entry.source_id}")
            continue

        if entry.status == "kept":
            if entry.emitted_count != 1:
                errors.append(
                    f"kept comment {entry.source_id} must have emitted_count == 1"
                )
            continue

        if entry.emitted_count != 0:
            errors.append(
                f"non-kept comment {entry.source_id} must have emitted_count == 0"
            )
        if not entry.reason.strip():
            errors.append(f"{entry.status} comment {entry.source_id} requires a reason")

    return tuple(errors)


def assert_valid_comment_ledger(
    entries: Sequence[CommentLedgerEntry],
    *,
    source_total: int,
) -> None:
    errors = validate_comment_ledger(entries, source_total=source_total)
    if errors:
        raise ValueError("; ".join(errors))
