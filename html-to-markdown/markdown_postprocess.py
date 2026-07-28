"""Path-independent Markdown post-processing shared by fast and strict outputs.

Both the deterministic fast converter and the strict sub-agent workflow produce
Markdown that must satisfy the same GitHub-rendering rules. Putting those rules
here — instead of only inside ``fast_converter`` — is what stops them from being
silently dropped on one path while the other keeps working (the caption-centering
and CJK-formula regressions were exactly this: rules that lived on one path only).

Everything here is deterministic and line-oriented, and every rule skips fenced
code blocks so code content is never rewritten. Rules that need real structural
understanding (table + caption sharing one ``<div align="center">``) stay in the
prose rules (conversion-rules.md「块级居中与题注」) and human verification; this
module only does the parts that can be applied reliably and mechanically.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


def _load_sibling(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).resolve().parent / filename
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


markdown_fences = _load_sibling("html_to_markdown_fences_pp", "markdown_fences.py")


# --- CJK ↔ inline-math spacing --------------------------------------------
# CJK / fullwidth punctuation directly touching a ``$`` inline-math delimiter
# stops GitHub from rendering the math (收益率$r_t$). Insert one ASCII space on
# the touching side. The negative lookarounds leave ``$$`` display delimiters
# alone. Registered in self-improvement.md「行内公式 $ 边界」.
_CJK_CLASS = "一-鿿　-〿＀-￯"
_CJK_BEFORE_DOLLAR = re.compile(rf"([{_CJK_CLASS}])\$(?!\$)")
_DOLLAR_BEFORE_CJK = re.compile(rf"(?<!\$)\$([{_CJK_CLASS}])")


def _space_cjk_inline_math_line(line: str) -> str:
    line = _CJK_BEFORE_DOLLAR.sub(r"\1 $", line)
    return _DOLLAR_BEFORE_CJK.sub(r"$ \1", line)


# --- **** concatenation fix -----------------------------------------------
# Adjacent bold spans concatenate into four stars (**表 1-4****置信度**), which
# GitHub renders wrong. Collapse runs of 3+ stars that sit between word chars
# back to a single ``**`` boundary is unsafe in general, so target only the
# specific ``****`` seam produced by adjacent bold spans.
_QUAD_STAR = re.compile(r"\*\*\*\*")


def _fix_quad_star_line(line: str) -> str:
    return _QUAD_STAR.sub("", line)


def _fenced_line_numbers(markdown: str) -> set[int]:
    inside: set[int] = set()
    for block in markdown_fences.scan_fenced_blocks(markdown):
        inside.update(range(block.start_line, block.end_line + 1))
    return inside


def postprocess_markdown(markdown: str) -> str:
    """Apply all path-independent line rules outside fenced code blocks.

    Order is irrelevant between the current rules (they touch disjoint syntax),
    but they are applied per non-fenced line in one pass.
    """

    inside = _fenced_line_numbers(markdown)
    lines = markdown.split("\n")
    for index in range(len(lines)):
        if (index + 1) in inside:
            continue
        line = lines[index]
        line = _space_cjk_inline_math_line(line)
        line = _fix_quad_star_line(line)
        lines[index] = line
    return "\n".join(lines)
