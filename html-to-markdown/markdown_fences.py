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
    """One closed Markdown fenced code block using 1-based line numbers."""

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

    return (
        blockquote_depth,
        len(match.group("indent")),
        fence[0],
        len(fence),
    )


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

    # Accept a repeated list marker, although normal list continuations usually
    # close with indentation only.
    list_match = _LIST_OPEN_RE.match(remainder)
    if list_match is not None:
        fence = list_match.group("fence")
        return (
            fence[0] == marker
            and len(fence) >= marker_length
            and not list_match.group("info").strip()
        )

    # Top-level fences may be indented by at most three spaces. A list opener
    # can place its fence farther right, so retain that exact container width.
    max_indent = max(3, container_indent)
    close_re = re.compile(
        rf"^ {{0,{max_indent}}}(?P<fence>{re.escape(marker)}"
        rf"{{{marker_length},}})[ \t]*$"
    )
    return close_re.match(remainder) is not None


def scan_fenced_blocks(markdown: str) -> tuple[FencedBlock, ...]:
    """Return all closed fenced blocks or raise on an unclosed opener.

    The scanner recognizes backtick and tilde fences, longer outer fences,
    blockquote prefixes, and list-item openers. While a block is open, shorter
    fences and fences using the other marker are content rather than closers.
    """

    blocks: list[FencedBlock] = []
    open_state: tuple[int, int, int, FenceMarker, int] | None = None

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

    if open_state is not None:
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
