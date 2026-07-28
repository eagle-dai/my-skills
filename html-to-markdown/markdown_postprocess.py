"""Path-independent Markdown post-processing shared by fast and strict outputs.

Both the deterministic fast converter and the strict sub-agent workflow produce
Markdown that must satisfy the same GitHub-rendering rules. Putting those rules
here — instead of only inside ``fast_converter`` — is what stops them from being
silently dropped on one path while the other keeps working (the caption-centering
and CJK-formula regressions were exactly this: rules that lived on one path only).

Everything here is deterministic and line-oriented, and every rule skips fenced
code blocks so code content is never rewritten. A caption line is recognised by
its structural anchor (``图/表 N`` + a fullwidth space U+3000), not by guessing
prose, so ordinary in-text mentions are never centered by mistake. Rules that
still need genuine DOM structure (a table and its caption sharing one wrapper)
remain in the prose rules (conversion-rules.md「块级居中与题注」) plus human
verification; this module does the parts that apply reliably and mechanically.
"""
from __future__ import annotations

import argparse
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


# --- 题注居中 -------------------------------------------------------------
# SingleFile 题注行的稳定形态：``图/表 N`` 后紧跟一个全角空格 U+3000，再接标题，
# 整行独立成段。正文里对图表的提及是 ``图 6-1 把…``（半角空格 + 动词），不含
# ``图N　``（全角空格）这个锚点，因此不会被误命中——这是把题注和正文引用区分开
# 的机制信号，不是靠猜文本内容。命中后包 ``<div align="center">`` 让 GitHub 居中。
# 编号 ``X-Y`` 的 X/Y 可为数字或字母（``图 D-1``、``表 A-2``、``图 6-1``），与
# conversion-rules.md「编号识别」一致——只用数字会漏掉附录常见的字母编号题注。
# 规则见 conversion-rules.md「块级居中与题注」；回归 tests/test_markdown_postprocess.py。
_CAPTION_LINE = re.compile(r"^(图|表)\s*[A-Za-z0-9]+(?:[-–][A-Za-z0-9]+)?　\S")


def _center_caption_line(line: str) -> str:
    if _CAPTION_LINE.match(line) and not line.lstrip().startswith("<div"):
        return f'<div align="center">{line}</div>'
    return line


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
        line = _center_caption_line(line)
        line = _fix_quad_star_line(line)
        lines[index] = line
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the path-independent Markdown rules (CJK↔inline-math spacing, "
            "caption centering, **** seam fix) to a Markdown file. Strict-path "
            "sub-agents run this so their output obeys the same GitHub-rendering "
            "rules the fast path already enforces."
        )
    )
    parser.add_argument("file", type=Path, help="Markdown file to process")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not modify the file. Exit 0 if it already satisfies the rules, "
            "exit 1 if postprocessing would change it (Phase 3 acceptance gate)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        original = args.file.read_text(encoding="utf-8")
    except OSError as error:
        print(f"cannot read {args.file}: {error}", file=sys.stderr)
        return 2

    processed = postprocess_markdown(original)

    if args.check:
        if processed == original:
            return 0
        print(
            f"{args.file}: not compliant — postprocessing would change it "
            "(uncentered captions or CJK-adjacent inline math). "
            "Run without --check to fix.",
            file=sys.stderr,
        )
        return 1

    if processed != original:
        args.file.write_text(processed, encoding="utf-8")
        print(f"{args.file}: postprocessed")
    else:
        print(f"{args.file}: already compliant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
