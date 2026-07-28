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
# 可选的 ``**`` 前缀：SingleFile 的图题是独立 ``<div>``（无加粗）转出裸 ``图 N…``，
# 表题却是 ``data-slate-type=bold`` span 转出 ``**表 N…**``。此前正则只认行首
# ``图/表``，加粗表题被前缀 ``**`` 挡住不居中（bug）。这里容忍可选 ``**`` 前缀，
# 命中后连 ``**…**`` 整体包进 ``<div>``，保留加粗只补居中。
# 规则见 conversion-rules.md「块级居中与题注」；回归 tests/test_markdown_postprocess.py。
_CAPTION_LINE = re.compile(r"^(?:\*\*)?(图|表)\s*[A-Za-z0-9]+(?:[-–][A-Za-z0-9]+)?　\S")


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


# --- 独立成段公式 → $$ 块级居中 -------------------------------------------
# 源 HTML 把所有公式标为 inline-katex（无 katex-display/block-katex），展示公式
# 也转成行内 ``$…$``，GitHub 左对齐。判定「整段只有一个公式」：strip 后以单个
# ``$`` 开头且以单个 ``$`` 结尾，去掉首尾定界符后内部无裸 ``$``（无第二个公式、
# 无正文混排）。命中改写为 ``$$…$$``，GitHub 块级默认居中。
# 行内混排（``… $t_{obs}$ 为观测时间``、``$s_i$ 、 $e_i$ 分别代表…``）不以 ``$``
# 结尾或内部含 ``$``，自动排除。已是 ``$$…$$`` 的不重复包裹。
# 规则见 conversion-rules.md「块级居中与题注」；回归 tests/test_markdown_postprocess.py。
def _promote_standalone_formula_line(line: str) -> str:
    stripped = line.strip()
    if len(stripped) < 3 or not stripped.startswith("$") or not stripped.endswith("$"):
        return line
    if stripped.startswith("$$") or stripped.endswith("$$"):
        return line  # 已是块级
    inner = stripped[1:-1]
    if "$" in inner or not inner.strip():
        return line  # 内部还有公式定界符 / 空公式
    return f"$${inner}$$"


# --- 作者开头/结尾寒暄去除（课程/专栏类文章） -----------------------------
# 课程、专栏、公众号类文章常有作者的开场白和结束语，属社交套话非正文（规则见
# conversion-rules.md「作者寒暄去除」，最初由 commit 1e6ab40 引入，后在文档
# 精简中丢失且从未落代码——这就是它一直没生效的原因）。
#
# 判定是**文档级**（只看首个/末个内容段），不是逐行；且**保守 fail-safe**：只删
# 「整段就是纯寒暄」的首段与末段。原规则提到的「寒暄与实质内容混在同一句、只删引子」
# 属语义判断，机械化误删正文风险高，交给 conversion-rules.md + 人工，这里不做。
# 锚点锚定段首/整段（非子串），普通正文里偶然出现的「你好」不会被误删。
_GREETING_OPENERS = (
    re.compile(r"^你好[，,、]?\s*我是"),          # 你好，我是XXX。
    re.compile(r"^(?:大家好|同学们好|各位好)[，,。！!]?"),
    re.compile(r"^欢迎(?:来到|回到|收听|阅读|学习)"),  # 欢迎来到《…》
    re.compile(r"^你好[！!。]?$"),                # 单独一句「你好！」
)
# 结尾寒暄：预告 / 求转发点赞 / 道别。命中任一即判该段为纯结束语。
_GREETING_CLOSERS = (
    re.compile(r"下节?课(?:再)?见"),
    re.compile(r"我们(?:下次|下节课|下一讲)(?:再)?见"),
    re.compile(r"期待你的(?:分享|留言|反馈)"),
    re.compile(r"欢迎(?:你)?(?:转发|分享)给"),
    re.compile(r"(?:点赞|在看|收藏|转发)(?:[，,、]|在看|收藏|转发|一下)"),
    re.compile(r"敬请期待"),
)


def _is_pure_opener(segment: str) -> bool:
    """整段就是开场白（去掉可选 ** 加粗后按锚点匹配段首）。"""
    text = segment.strip().strip("*").strip()
    return any(p.match(text) for p in _GREETING_OPENERS)


def _is_pure_closer(segment: str) -> bool:
    """整段就是结束语：命中结尾锚点，且不含正文结构标记（#/列表/表格/代码/公式）。"""
    text = segment.strip()
    if not text or text.startswith(("#", "-", "*", ">", "|", "```", "$$")):
        return False
    return any(p.search(text) for p in _GREETING_CLOSERS)


def _strip_author_greetings(markdown: str) -> str:
    """删除课程/专栏文章的首段开场白与末段结束语（保守，只删纯寒暄整段）。"""
    blocks = markdown.split("\n\n")

    # 首段：跳过空块，命中开场白锚点则删整段
    i = 0
    while i < len(blocks) and not blocks[i].strip():
        i += 1
    if i < len(blocks) and _is_pure_opener(blocks[i]):
        blocks[i] = None  # type: ignore[assignment]

    # 末段：跳过空块，命中结束语锚点则删整段
    j = len(blocks) - 1
    while j >= 0 and not (blocks[j] or "").strip():
        j -= 1
    if j >= 0 and blocks[j] is not None and _is_pure_closer(blocks[j]):
        blocks[j] = None  # type: ignore[assignment]

    kept = [b for b in blocks if b is not None]
    return "\n\n".join(kept).strip("\n") + ("\n" if markdown.endswith("\n") else "")


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

    markdown = _strip_author_greetings(markdown)
    inside = _fenced_line_numbers(markdown)
    lines = markdown.split("\n")
    for index in range(len(lines)):
        if (index + 1) in inside:
            continue
        line = lines[index]
        line = _space_cjk_inline_math_line(line)
        line = _center_caption_line(line)
        line = _fix_quad_star_line(line)
        line = _promote_standalone_formula_line(line)
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
