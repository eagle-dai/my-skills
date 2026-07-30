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

# A U+00A0 NBSP directly touching a ``$`` inline-math delimiter stops GitHub
# from rendering the math: GitHub requires an ASCII-whitespace (or start/end)
# boundary around ``$…$`` and does NOT accept NBSP as that boundary, so the
# formula shows up literally (``有\u00a0$n$\u00a0个`` → literal ``$n$``). WeChat
# (mmbiz) SingleFile pages use NBSP to separate formulas from surrounding CJK.
# Normalize an NBSP that is adjacent to a ``$`` into a plain ASCII space so the
# boundary is valid. Leaves NBSP elsewhere in prose untouched. Verified against
# real GitHub rendering (not local KaTeX/MathJax — see gap #25 铁律).
_NBSP_BEFORE_DOLLAR = re.compile("\u00a0(?=\\$)")
_DOLLAR_BEFORE_NBSP = re.compile("(?<=\\$)\u00a0")


def _space_cjk_inline_math_line(line: str) -> str:
    line = _NBSP_BEFORE_DOLLAR.sub(" ", line)
    line = _DOLLAR_BEFORE_NBSP.sub(" ", line)
    line = _CJK_BEFORE_DOLLAR.sub(r"\1 $", line)
    return _DOLLAR_BEFORE_CJK.sub(r"$ \1", line)


# --- 题注居中 + 统一加粗（多行块级形态）-----------------------------------
# SingleFile 题注行的稳定形态：``图/表/代码/清单/公式 N`` 后紧跟一个全角空格 U+3000，
# 再接标题，整行独立成段。正文里对图表的提及是 ``图 6-1 把…``（半角空格 + 动词），
# 不含 ``图N　``（全角空格）这个锚点，因此不会被误命中——这是把题注和正文引用区分开
# 的机制信号，不是靠猜文本内容。命中后包 ``<div align="center">`` 让 GitHub 居中。
# 编号 ``X-Y`` 的 X/Y 可为数字或字母（``图 D-1``、``表 A-2``、``图 6-1``），与
# conversion-rules.md「编号识别」一致——只用数字会漏掉附录常见的字母编号题注。
#
# **关键词集**：``图 表 代码 清单 公式``。keyword 与 conversion-rules.md
# 「块级居中与题注」的命名性短标题列表保持一致。
#
# **统一加粗（用户决策）**：所有题注一律加粗，不管源 HTML 有无加粗 mark。SingleFile 里
# 表题/代码题是 ``data-slate-type=bold`` span（转出带 ``**``），图题却是纯 ``<div>``
# （转出裸文本无 ``**``）。为视觉一致，命中后强制整题注加粗。
#
# **多行块级形态（间距修复）**：题注输出为**上下空行分隔的多行 ``<div>`` 块**：
#
#     <div align="center">
#
#     **图 8-1　标题**
#
#     </div>
#
# 而不是单行 ``<div align="center"><strong>…</strong></div>``。原因是 GitHub 渲染
# 差异（``gh api /markdown`` 实测）：单行裸 div 内直接是 inline 内容，GitHub 输出的
# ``<div>`` **不含内部 ``<p>``**、CSS 无段落 margin，紧跟的正文 ``<p>`` 贴上来——题注和
# 后段视觉粘连（用户反馈的问题）。多行块内空行让 GitHub 当 Markdown 段落解析成
# ``<div><p>…</p></div>``，``<p>`` 自带上下 margin，与前后正文自然分开。
#
# **内部用 Markdown 标记不用 HTML tag**：多行块内 GitHub **会**解析 Markdown，所以内部用
# ``**…**``（加粗）和 `` `code` ``（行内代码），不再需要单行块被迫用的 ``<strong>``/
# ``<code>``。整题注用**一对** ``**`` 包住（行内代码 `` ` `` 留在内），混排代码题注
# （``代码 8-2　业务源码：`normalize_candle` …``）不再有 ``**`` 被 `` ` `` 断开的坏接缝。
#
# 规则见 conversion-rules.md「块级居中与题注」；回归 tests/test_markdown_postprocess.py。
#
# 归一化吃三种输入形态，全部收敛到上面的多行块：
#   1. 裸题注行 ``图 N　…`` / ``**表 N　…**`` / 混排 ``**代码 N　`c` …**``；
#   2. 上一轮单行 div ``<div align="center"><strong>…</strong></div>``（含 ``<code>``）；
#   3. 已是多行块（幂等，不动）。
_CAPTION_KEYWORDS = r"图|表|代码|清单|公式"
_CAPTION_NUM = r"[A-Za-z0-9]+(?:[-–][A-Za-z0-9]+)?"
# 裸题注单行：可选 ``**`` 前缀 + 关键词 + 编号 + U+3000 + 标题。
_CAPTION_LINE = re.compile(rf"^(?:\*\*)?(?:{_CAPTION_KEYWORDS})\s*{_CAPTION_NUM}　\S")
# 单行 div（上一轮产物）：``<div align="center">…</div>``。
_ONE_LINE_DIV = re.compile(r'^<div align="center">(.*)</div>$')
# div 内文里提取纯题注文本用：<strong>/<code>/**/` 都要还原。
_STRONG_TAG = re.compile(r"</?strong>")
_CODE_OPEN = re.compile(r"<code(?:\s[^>]*)?>")
_CODE_CLOSE = re.compile(r"</code>")
# 行内代码占位保护：先把 `` `x` `` 和 ``<code>x</code>`` 抽出，避免包 ``**`` 时误伤。
_INLINE_CODE = re.compile(r"`([^`]+)`")


def _caption_to_bold_markdown(raw: str) -> str:
    """把任意形态的题注内容归一成单行 ``**…**``（行内代码用 `` `…` `` 留在内）。

    去掉外层/内部的 ``**`` 与 ``<strong>``，把 ``<code>x</code>`` 还原成 `` `x` ``，
    再整题注包**一对** ``**``。幂等——已是干净 ``**…**`` 时结果不变。
    """
    text = raw.strip()
    # <strong> → 去标签（整题注会重新统一加粗）；<code>x</code> → `x`
    text = _STRONG_TAG.sub("", text)
    text = _CODE_OPEN.sub("`", text)
    text = _CODE_CLOSE.sub("`", text)
    # 去掉所有裸 ``**``（旧混排会有多对），最后统一包一层。
    text = text.replace("**", "")
    return f"**{text}**"


def _centered_block(caption_bold_md: str) -> str:
    """把 ``**…**`` 题注包成多行居中块（含前后空行，GitHub 解析出 <p> 有 margin）。"""
    return f'<div align="center">\n\n{caption_bold_md}\n\n</div>'


def _normalize_captions(markdown: str, fenced: set[int]) -> str:
    """块级扫描：把三种题注形态统一成多行居中块。fenced 行内的按行号跳过。

    逐行游标：命中单行 div / 已有多行块 / 裸题注行时，消费对应行数并 emit 多行块。
    """
    lines = markdown.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        lineno = i + 1  # 1-based，与 fenced 对齐
        line = lines[i]
        if lineno in fenced:
            out.append(line)
            i += 1
            continue
        stripped = line.strip()

        # 形态 3：多行 ``<div align="center">`` 块。向后找配对 ``</div>``，抓非空内容行。
        if stripped == '<div align="center">':
            j = i + 1
            content_lines = []
            while j < n and lines[j].strip() != "</div>":
                if lines[j].strip():
                    content_lines.append(lines[j].strip())
                j += 1
            if j < n:
                # 找到配对 </div>：这是一个完整居中块。
                if len(content_lines) == 1 and _is_caption_text(content_lines[0]):
                    # 纯题注块 → 归一（幂等）。
                    out.append(_centered_block(_caption_to_bold_markdown(content_lines[0])))
                else:
                    # 含表格/图片/多行内容的居中块（如 conversion-rules 的「标题+表格
                    # 同包」）→ **整块原样保留**，绝不逐行走进去，否则内部的 ``**表 X**``
                    # 会被下面「形态 1 裸题注行」二次包成嵌套 div，把标题从表格里拆出来
                    # （回归 bug，PR #55 review 抓到）。
                    out.extend(lines[i : j + 1])
                i = j + 1
                continue
            # 没找到配对 </div>（不完整/误报）：只吐起始行，逐行继续。
            out.append(line)
            i += 1
            continue

        # 形态 2：单行 div
        m = _ONE_LINE_DIV.match(stripped)
        if m and _is_caption_text(m.group(1)):
            out.append(_centered_block(_caption_to_bold_markdown(m.group(1))))
            i += 1
            continue

        # 形态 1：裸题注行
        if _CAPTION_LINE.match(line):
            out.append(_centered_block(_caption_to_bold_markdown(line)))
            i += 1
            continue

        out.append(line)
        i += 1
    return "\n".join(out)


def _is_caption_text(inner: str) -> bool:
    """div 内文/内容行是否是命名性题注（去掉 **、<strong>、`code` 后看开头锚点）。"""
    t = inner.strip()
    t = _STRONG_TAG.sub("", t)
    t = t.replace("**", "").lstrip()
    return bool(_CAPTION_LINE.match(t))


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
# 判定按**行**（单个 \n 也拆开），只看首个/末个**非空内容行**，删的是整行——因此
# 单换行分段（SingleFile/Slate 常见）时不会把同块的正文一起删掉。且**保守 fail-safe**：
# 宁漏勿误删。原规则提到的「寒暄与实质内容混在同一句、只删引子」属语义判断，机械化
# 误删风险高，交给 conversion-rules.md + 人工，这里不做。
#
# 误删防线（review 实证过的坑）：
# - opener 的逗号**必需**（`你好，我是`），排除反问句「你好我是谁？…」——反问以 ？/? 收尾。
# - closer 用**整行结尾锚定**（短语在行尾 `$`），不是子串命中：正文里出现「敬请期待」「转发」
#   这些词但句子没以道别收尾，不会误删。且 closer 只保留正文几乎不可能以之收尾的**强道别
#   信号**（明确的课程道别 / 求转发分享 / 求互动）；裸「点赞/收藏/转发/敬请期待」正文太常见，
#   不作为独立信号（会误删「新版本开发中，敬请期待。」这类正文）。
_OPENER_PREFIXES = (
    re.compile(r"^你好[，,]\s*我是"),                # 你好，我是XXX（逗号必需，排除反问）
    re.compile(r"^(?:大家好|同学们好|各位好|亲爱的.{0,6}们好)[，,。！!]"),
    re.compile(r"^欢迎(?:来到|回到|收听|阅读|学习)"),   # 欢迎来到《…》
    re.compile(r"^你好[！!。]$"),                     # 单独一句「你好！」
)
_QUESTION_END = re.compile(r"[？?]\s*$")             # 反问/疑问收尾 → 不是开场白
# 强道别短语，要求出现在**行尾**（句末标点可选）：正文极少以这些收尾。
_CLOSER_SUFFIXES = (
    re.compile(r"我们下[节一]?[节课讲次]?(?:再)?见[！!。～~\s]*$"),  # 我们下节课再见！
    re.compile(r"下节?课(?:再)?见[！!。～~\s]*$"),
    re.compile(r"欢迎(?:你)?(?:转发|分享)给.{0,20}朋友[，,。！!\s]*$"),
    re.compile(r"期待你的(?:分享|留言|反馈)[。！!\s]*$"),
    re.compile(r"我们下(?:次|回)(?:再)?(?:见|聊)[！!。～~\s]*$"),
)


# 句子切分：以 。！？ 收尾切句，保留终止符。行首/末的开场白与结束语按**句**判定，
# 只删纯寒暄句，保留同一行里带实质信息的句子——避免「正文。我们下节课再见！」这类
# 单行混排被整行删掉丢正文（review 实证的静默丢失坑）。
_SENTENCE_SPLIT = re.compile(r"[^。！？!?]*[。！？!?]+|[^。！？!?]+")


def _split_sentences(text: str) -> list[str]:
    """把一行切成句子（保留句末标点）；无终止符时整体作一句。"""
    return _SENTENCE_SPLIT.findall(text)


def _sentence_is_opener(sentence: str) -> bool:
    """该句是开场白（去掉可选 ** 加粗后匹配开头前缀，且不是反问句）。"""
    text = sentence.strip().strip("*").strip()
    if not text or _QUESTION_END.search(text):
        return False
    return any(p.match(text) for p in _OPENER_PREFIXES)


def _sentence_is_closer(sentence: str) -> bool:
    """该句是结束语：去掉可选 ** 加粗后以强道别短语收尾。"""
    text = sentence.strip().strip("*").strip()
    if not text:
        return False
    return any(p.search(text) for p in _CLOSER_SUFFIXES)


# 行首正文结构标记 → 不做寒暄处理。列表项要求 marker + 空格（`- `/`* `/`+ `），
# 否则 `**大家好！**`（加粗寒暄，行首是 `*`）会被误判成列表而跳过——它是寒暄，
# 该按句剥离（_sentence_is_* 会 strip 掉 `**` 再匹配）。
_STRUCTURE_MARKER = re.compile(r"(?:[#>|!]|```|\$\$|[-*+]\s)")


def _has_structure_marker(line: str) -> bool:
    """行首是正文结构标记（标题/列表/表格/代码/公式/图片）→ 不做寒暄处理。"""
    return bool(_STRUCTURE_MARKER.match(line.strip()))


# 整行被 ** 加粗包裹（`**寒暄整句**`）：先脱壳再切句，否则句切会把闭合 ``**`` 割成
# 单独一段污染判定；剥离后若有幸存正文，重新包壳保持加粗。
_BOLD_WRAP = re.compile(r"^\*\*(?P<inner>.+)\*\*$", re.DOTALL)


def _unwrap_bold(line: str) -> tuple[str, bool]:
    """整行 ``**…**`` → (内层, True)；否则 (原行, False)。内层不含裸 ``**`` 才脱壳。"""
    stripped = line.strip()
    m = _BOLD_WRAP.match(stripped)
    if m and "**" not in m.group("inner"):
        return m.group("inner"), True
    return line, False


def _strip_opener_from_line(line: str) -> str | None:
    """删掉行首连续的开场白句，保留其后实质内容；整行皆开场白则返回 None（删整行）。"""
    if _has_structure_marker(line):
        return line
    body, wrapped = _unwrap_bold(line)
    sentences = _split_sentences(body)
    idx = 0
    while idx < len(sentences) and _sentence_is_opener(sentences[idx]):
        idx += 1
    if idx == 0:
        return line  # 行首不是开场白，不动
    remainder = "".join(sentences[idx:]).strip()
    if not remainder:
        return None
    return f"**{remainder}**" if wrapped else remainder


def _strip_closer_from_line(line: str) -> str | None:
    """删掉行尾连续的结束语句，保留其前实质内容；整行皆结束语则返回 None（删整行）。"""
    if _has_structure_marker(line):
        return line
    body, wrapped = _unwrap_bold(line)
    sentences = _split_sentences(body)
    idx = len(sentences)
    while idx > 0 and _sentence_is_closer(sentences[idx - 1]):
        idx -= 1
    if idx == len(sentences):
        return line  # 行尾不是结束语，不动
    remainder = "".join(sentences[:idx]).strip()
    if not remainder:
        return None
    return f"**{remainder}**" if wrapped else remainder


def _strip_author_greetings(markdown: str) -> str:
    """删除课程/专栏文章的首行开场白与末行结束语。

    保守，按**句**判定：只删行首/行尾的纯寒暄句，保留同一行里带实质内容的句子
    （单换行/单行混排常见），绝不因为一行以道别收尾就删掉整行的正文。
    """
    had_trailing_nl = markdown.endswith("\n")
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # 首个非空行：剥离行首开场白句
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines):
        lines[i] = _strip_opener_from_line(lines[i])  # type: ignore[assignment]

    # 末个非空行：剥离行尾结束语句
    j = len(lines) - 1
    while j >= 0 and not (lines[j] or "").strip():
        j -= 1
    if j >= 0 and lines[j] is not None:
        lines[j] = _strip_closer_from_line(lines[j])  # type: ignore[assignment]

    kept = [ln for ln in lines if ln is not None]
    result = "\n".join(kept).strip("\n")
    return result + ("\n" if had_trailing_nl and result else "")


def _fenced_line_numbers(markdown: str) -> set[int]:
    inside: set[int] = set()
    for block in markdown_fences.scan_fenced_blocks(markdown):
        inside.update(range(block.start_line, block.end_line + 1))
    return inside


# --- 残留公式占位符护栏（fail-closed） ------------------------------------
# ``fast_converter.py`` 在 ``original_latex`` 为空（公式未解析/未通过 KaTeX 验证）时
# emit 唯一形态 ``{{FORMULA:<source_id>}}`` 占位符。pipeline 本身会因此判 blocked、
# 不出 ZIP；但 strict/blocked 手工收尾时，agent 可能把占位符删掉手编成 inline-code
# 之类的降级形态、或直接把带占位符的 md 当成品交付。这道机械门在共享后处理阶段扫描
# 残留占位符：命中即阻断（check 返回 1、apply 拒绝写盘），逼公式走正确验证流程解析成
# ``$$…$$`` 而不是靠人手瞎编。占位符本身改写不了（缺 LaTeX），所以只检测不改写。
# fenced code block 内的字面量不算（可能是讲占位符机制的正文）。
# 规则见 blocking-rules.md「残留公式占位符」。
_RESIDUAL_FORMULA = re.compile(r"\{\{FORMULA:[^}]+\}\}")


def find_residual_formula_placeholders(markdown: str) -> list[tuple[int, str]]:
    """返回 (行号从1起, 命中文本) 列表，排除 fenced code block 内的字面量。"""
    inside = _fenced_line_numbers(markdown)
    hits: list[tuple[int, str]] = []
    for index, line in enumerate(markdown.split("\n"), start=1):
        if index in inside:
            continue
        for match in _RESIDUAL_FORMULA.finditer(line):
            hits.append((index, match.group(0)))
    return hits


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
        line = _fix_quad_star_line(line)
        line = _promote_standalone_formula_line(line)
        lines[index] = line
    markdown = "\n".join(lines)
    # 题注归一是**块级**（多行居中块，改变行数），放最后单独跑；重算 fenced 行号，
    # 因为上面的逐行规则不加减行、行号不变，但题注块级前必须用当前文本的 fenced。
    inside = _fenced_line_numbers(markdown)
    return _normalize_captions(markdown, inside)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the path-independent Markdown rules (CJK↔inline-math spacing, "
            "caption centering, **** seam fix) to a Markdown file, and fail-closed "
            "on residual {{FORMULA:...}} placeholders. Strict-path sub-agents run "
            "this so their output obeys the same GitHub-rendering rules the fast "
            "path already enforces."
        )
    )
    parser.add_argument("file", type=Path, help="Markdown file to process")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not modify the file. Exit 0 if it already satisfies the rules, "
            "exit 1 if postprocessing would change it or a residual formula "
            "placeholder survives (Phase 3 acceptance gate)."
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

    # 残留公式占位符：无论 check/apply 都是硬阻断，先于合规比较。
    residual = find_residual_formula_placeholders(processed)
    if residual:
        for line_no, text in residual:
            print(
                f"{args.file}:{line_no}: residual formula placeholder {text} — "
                "formula was never resolved; run the KaTeX validation loop "
                "(formula-validation.html → --formula-validation-report) instead "
                "of hand-editing. Delivery blocked.",
                file=sys.stderr,
            )
        return 1

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
