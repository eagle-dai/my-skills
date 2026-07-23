"""Executable contracts for the html-to-markdown skill.

The Markdown files explain the workflow. This module owns the small pieces that
must be deterministic and regression-testable: selector syntax, complexity
classification, semantic candidate discovery/de-duplication, and comment ledger
checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Sequence


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
    # These fields belong to the shared DOM baseline/report contract. They do
    # not currently change the Level 0/1 split, but callers must still record
    # and validate them in every level.
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

    chosen: dict[str, tuple[int, int, SemanticCandidate]] = {}
    for index, candidate in enumerate(candidates):
        if not candidate.semantic_id:
            raise ValueError("semantic_id must not be empty")
        if not candidate.source_dom_id:
            raise ValueError("source_dom_id must not be empty")

        current = chosen.get(candidate.semantic_id)
        if current is None:
            chosen[candidate.semantic_id] = (index, index, candidate)
            continue

        first_index, chosen_index, chosen_candidate = current
        if (candidate.priority, index) < (chosen_candidate.priority, chosen_index):
            chosen[candidate.semantic_id] = (first_index, index, candidate)

    return tuple(
        item[2] for item in sorted(chosen.values(), key=lambda item: item[0])
    )


def _element_children(node: Any) -> list[Any]:
    """Return element children using identity-preserving DOM order.

    BeautifulSoup ``Tag`` objects satisfy this tiny protocol. Keeping the
    helper duck-typed lets callers use a rendered DOM snapshot serialized by
    Playwright without coupling the contract module to a browser runtime.
    """

    return [
        child
        for child in getattr(node, "children", ())
        if getattr(child, "name", None)
    ]


def stable_dom_path(node: Any) -> str:
    """Return a stable element-only path for one parsed DOM snapshot.

    The path is not intended to survive arbitrary page edits. It is an identity
    key within one Phase 1 extraction/verification run, which is exactly the
    lifetime required by semantic and comment ledgers. ``select()`` results and
    parent ``children`` traversal must expose the same element instances; do not
    mix nodes from separate parses or reconstructed wrapper objects.
    """

    parts: list[str] = []
    current = node
    while getattr(current, "name", None):
        parent = getattr(current, "parent", None)
        if parent is None or not getattr(parent, "name", None):
            parts.append(str(current.name))
            break

        siblings = _element_children(parent)
        index = next(
            (
                position
                for position, sibling in enumerate(siblings)
                if sibling is current
            ),
            None,
        )
        if index is None:
            raise ValueError("node is not present in its parent's element children")
        parts.append(f"{current.name}[{index}]")
        current = parent

    if not parts:
        raise ValueError("node must be an element")
    return "/".join(reversed(parts))


_DOM_DISCOVERY_SPECS: Mapping[str, tuple[str, str, str]] = {
    # kind: (native selector, native representation, wrapper representation)
    "table": ("table", "native-table", "slate-table-wrapper"),
    "codeblock": ("pre > code", "native-code", "slate-pre-wrapper"),
}


def discover_semantic_candidates(
    root: Any,
    *,
    kind: str,
) -> tuple[SemanticCandidate, ...]:
    """Discover wrapper/native candidates and assign semantic IDs from DOM identity.

    ``root`` must provide BeautifulSoup-compatible ``select()`` semantics. In
    the real workflow, callers should first render the page with Playwright,
    serialize the confirmed content container, and parse that rendered snapshot.

    A wrapper containing exactly one native node shares the native node's
    ``semantic_id``. Native nodes have higher priority. A wrapper containing
    multiple native nodes is ambiguous and fails closed instead of silently
    collapsing several blocks into one.
    """

    if kind not in _DOM_DISCOVERY_SPECS:
        raise ValueError(f"unsupported semantic candidate kind: {kind}")
    if not hasattr(root, "select"):
        raise TypeError("root must provide select(selector)")

    native_selector, native_representation, wrapper_representation = (
        _DOM_DISCOVERY_SPECS[kind]
    )
    candidates: list[SemanticCandidate] = []

    for node in root.select(CSS_SELECTORS[kind]):
        # Use element shape for the two supported native representations.
        if kind == "table":
            is_native = getattr(node, "name", None) == "table"
        else:
            parent = getattr(node, "parent", None)
            is_native = (
                getattr(node, "name", None) == "code"
                and getattr(parent, "name", None) == "pre"
            )

        if is_native:
            canonical_node = node
            representation = native_representation
            priority = 0
        else:
            native_nodes = list(node.select(native_selector))
            if len(native_nodes) > 1:
                raise ValueError(
                    f"ambiguous {kind} wrapper {stable_dom_path(node)} contains "
                    f"{len(native_nodes)} native nodes"
                )
            canonical_node = native_nodes[0] if native_nodes else node
            representation = wrapper_representation
            priority = 10

        candidates.append(
            SemanticCandidate(
                semantic_id=stable_dom_path(canonical_node),
                source_dom_id=stable_dom_path(node),
                representation=representation,
                priority=priority,
            )
        )

    return tuple(candidates)


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
    source_ids: Sequence[str],
) -> tuple[str, ...]:
    """Validate exact source-comment conservation without output-count equality."""

    errors: list[str] = []
    expected_ids = list(source_ids)
    expected_seen: set[str] = set()
    for source_id in expected_ids:
        if not source_id:
            errors.append("source comment id must not be empty")
        elif source_id in expected_seen:
            errors.append(f"duplicate source comment id: {source_id}")
        else:
            expected_seen.add(source_id)

    ledger_seen: set[str] = set()
    for entry in entries:
        if not entry.source_id:
            errors.append("comment source_id must not be empty")
        elif entry.source_id in ledger_seen:
            errors.append(f"duplicate comment source_id: {entry.source_id}")
        else:
            ledger_seen.add(entry.source_id)

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

    missing = expected_seen - ledger_seen
    unexpected = ledger_seen - expected_seen
    if missing:
        errors.append(f"missing source comment ids: {sorted(missing)}")
    if unexpected:
        errors.append(f"unexpected source comment ids: {sorted(unexpected)}")

    return tuple(errors)


def assert_valid_comment_ledger(
    entries: Sequence[CommentLedgerEntry],
    *,
    source_ids: Sequence[str],
) -> None:
    errors = validate_comment_ledger(entries, source_ids=source_ids)
    if errors:
        raise ValueError("; ".join(errors))
