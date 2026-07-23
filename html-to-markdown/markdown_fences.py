"""Deterministic fenced-code scanning for Markdown validation.

The skill must exclude fenced code before counting headings, lists, blockquotes,
and other Markdown structures. Counting fence lines or using a cross-line regex
cannot prove that fences are correctly nested or closed. This module provides a
small line-oriented state machine for that contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


FenceMarker = Literal["`", "~"]


@dataclass(frozen=True)
class FencedBlock:
    """One closed Markdown fenced code block using 1-based line numbers.

    ``blockquote_depth`` and ``container_indent`` preserve the structural
    container needed to validate the closer. ``container_indent`` is zero for a
    normal fence and the minimum content indentation for a list-item fence.
    """

    start_line: int
    end_line: int
    marker: FenceMarker
    marker_length: int
    blockquote_depth: int
    container_indent: int


_OPEN_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$"
)
_LIST_OPEN_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>(?:[-+*]|\d{1,9}[.)]))"
    r"(?P<spacing>[ \t]+)(?P<fence>`{3,}|~{3,})(?P<info>.*)$"
)
_FENCE_LINE_RE = re.compile(
    r"^(?P<indent> *)(?P<fence>`{3,}|~{3,})(?P<rest>.*)$"
)


def _strip_blockquote_prefix(line: str) -> tuple[int, str]:
    """Return blockquote depth and content after Markdown ``>`` prefixes."""

    position = 0
    depth = 0
    while True:
        start = position
        spaces = 0
        while position < len(line) and line[position] == " " and spaces < 3:
            position += 1
            spaces += 1

        if position < len(line) and line[position] == ">":
            position += 1
            depth += 1
            if position < len(line) and line[position] in " \t":
                position += 1
            continue

        position = start
        break

    return depth, line[position:]


def _parse_opener(line: str) -> tuple[int, int, FenceMarker, int] | None:
    blockquote_depth, remainder = _strip_blockquote_prefix(line)

    match = _LIST_OPEN_RE.match(remainder)
    if match is not None:
        fence = match.group("fence")
        info = match.group("info")
        if fence[0] == "`" and "`" in info:
            return None
        return (
            blockquote_depth,
            match.start("fence"),
            fence[0],
            len(fence),
        )

    match = _OPEN_RE.match(remainder)
    if match is None:
        return None

    fence = match.group("fence")
    info = match.group("info")
    if fence[0] == "`" and "`" in info:
        return None

    # A normally indented fence remains in the root container: CommonMark
    # permits its closer at any indentation from column 0 through column 3.
    return (
        blockquote_depth,
        0,
        fence[0],
        len(fence),
    )


def _closing_indent_bounds(container_indent: int) -> tuple[int, int]:
    if container_indent:
        return container_indent, container_indent + 3
    return 0, 3


def _is_closer(
    line: str,
    *,
    blockquote_depth: int,
    container_indent: int,
    marker: FenceMarker,
    marker_length: int,
) -> bool:
    current_depth, remainder = _strip_blockquote_prefix(line)
    if current_depth != blockquote_depth:
        return False

    match = _FENCE_LINE_RE.match(remainder)
    if match is None:
        return False

    fence = match.group("fence")
    if fence[0] != marker or len(fence) < marker_length:
        return False
    if match.group("rest").strip():
        return False

    minimum_indent, maximum_indent = _closing_indent_bounds(container_indent)
    indent = len(match.group("indent"))
    return minimum_indent <= indent <= maximum_indent


def _invalid_closer_reason(
    line: str,
    *,
    blockquote_depth: int,
    container_indent: int,
    marker: FenceMarker,
    marker_length: int,
) -> str | None:
    """Describe a fence-looking line that cannot legally close the block."""

    current_depth, remainder = _strip_blockquote_prefix(line)
    match = _FENCE_LINE_RE.match(remainder)
    if match is None:
        return None

    fence = match.group("fence")
    if current_depth != blockquote_depth:
        return "blockquote depth does not match the opener"
    if fence[0] != marker:
        return "closing fence uses a different marker"
    if len(fence) < marker_length:
        return "closing fence is shorter than the opener"

    minimum_indent, maximum_indent = _closing_indent_bounds(container_indent)
    indent = len(match.group("indent"))
    if not minimum_indent <= indent <= maximum_indent:
        if container_indent:
            return (
                "closing fence is outside the list-item content indentation "
                f"{minimum_indent}-{maximum_indent}"
            )
        return "closing fence indentation exceeds three spaces"
    if match.group("rest").strip():
        return "closing fence has trailing text"
    return None


def scan_fenced_blocks(markdown: str) -> tuple[FencedBlock, ...]:
    """Return all closed fenced blocks or raise on malformed/unclosed input.

    The scanner recognizes backtick and tilde fences, longer outer fences,
    blockquote prefixes, and list-item openers. While a block is open, shorter
    fences and fences using the other marker are content rather than closers.
    If no valid closer is found, a previously seen fence-looking line is used to
    report the most specific available diagnostic.
    """

    blocks: list[FencedBlock] = []
    open_state: tuple[int, int, int, FenceMarker, int] | None = None
    invalid_closer: tuple[int, str] | None = None

    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if open_state is None:
            opener = _parse_opener(line)
            if opener is not None:
                blockquote_depth, container_indent, marker, marker_length = opener
                open_state = (
                    line_number,
                    blockquote_depth,
                    container_indent,
                    marker,
                    marker_length,
                )
                invalid_closer = None
            continue

        (
            start_line,
            blockquote_depth,
            container_indent,
            marker,
            marker_length,
        ) = open_state
        if _is_closer(
            line,
            blockquote_depth=blockquote_depth,
            container_indent=container_indent,
            marker=marker,
            marker_length=marker_length,
        ):
            blocks.append(
                FencedBlock(
                    start_line=start_line,
                    end_line=line_number,
                    marker=marker,
                    marker_length=marker_length,
                    blockquote_depth=blockquote_depth,
                    container_indent=container_indent,
                )
            )
            open_state = None
            invalid_closer = None
            continue

        reason = _invalid_closer_reason(
            line,
            blockquote_depth=blockquote_depth,
            container_indent=container_indent,
            marker=marker,
            marker_length=marker_length,
        )
        if reason is not None:
            invalid_closer = (line_number, reason)

    if open_state is not None:
        if invalid_closer is not None:
            line_number, reason = invalid_closer
            raise ValueError(
                f"invalid closing fence at line {line_number}: {reason}; "
                f"block opened at line {open_state[0]}"
            )
        raise ValueError(
            f"unclosed fenced code block opened at line {open_state[0]}"
        )

    return tuple(blocks)


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def strip_fenced_blocks(markdown: str) -> str:
    """Remove fenced block contents while preserving line count and endings."""

    blocks = scan_fenced_blocks(markdown)
    lines = markdown.splitlines(keepends=True)
    for block in blocks:
        for index in range(block.start_line - 1, block.end_line):
            lines[index] = _line_ending(lines[index])
    return "".join(lines)
