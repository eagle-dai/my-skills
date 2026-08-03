"""Conservative deterministic HTML-to-Markdown converter for static articles."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from bs4 import NavigableString, Tag

from pipeline_utils import (
    decode_data_uri,
    extension_for_mime,
    image_disposition,
    image_processing,
    markdown_fences,
    markdown_postprocess,
    max_backticks,
    preflight,
)


BLOCK_TRANSPARENT_TAGS = {"div", "section", "article", "main"}
INLINE_TRANSPARENT_TAGS = {"span"}


class FastPathUnsupported(RuntimeError):
    pass


@dataclass
class EmittedCounts:
    headings: int = 0
    tables: int = 0
    lists: int = 0
    list_items: int = 0
    images: int = 0
    codeblocks: int = 0
    formula_block: int = 0
    formula_inline: int = 0

    def as_dict(self) -> dict[str, int]:
        total = self.formula_block + self.formula_inline
        return {
            "headings": self.headings,
            "tables": self.tables,
            "lists": self.lists,
            "list_items": self.list_items,
            "images": self.images,
            "codeblocks": self.codeblocks,
            "formula_block": self.formula_block,
            "formula_inline": self.formula_inline,
            "formula_total": total,
        }


@dataclass(frozen=True)
class ConversionResult:
    markdown: str
    counts: EmittedCounts
    image_ledger: tuple[Any, ...]
    unresolved_formulas: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


def _strip_blank_edges(text: str) -> str:
    """Drop leading and trailing blank lines from a code block.

    Slate lays out each source line as its own ``<div>``; an empty leading or
    trailing row (rendered as a blank or whitespace-only ``<div>``) is layout
    padding, not code, and would otherwise surface as blank lines just inside
    the fence (```` ```text ```` followed by empty lines). Interior blank lines
    are code and are preserved.
    """

    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _assert_indent_intact(code: str) -> None:
    """守恒门:检测代码块缩进是否被 BS4 空白折叠损坏。

    Slate 缩进靠 preflight._protect_code_indent 的 NBSP 保护穿过解析。若某行缩进
    漏保护,会塌成单空格。正常源代码不会用「1 空格」作缩进单位(惯例 2/4/tab)。
    因此「同一块内既有恰好 1 空格缩进的行,又有 ≥2 空格缩进的行」是折叠损坏的指纹
    ——fail-close 到 strict,不交付坏缩进。
    """

    has_single = False
    has_multi = False
    for line in code.split("\n"):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 1:
            has_single = True
        elif indent >= 2:
            has_multi = True
    if has_single and has_multi:
        raise FastPathUnsupported(
            "code block indentation looks collapsed (mixed 1-space and "
            "multi-space indent); requires strict handling"
        )


# gap #23: highlight.js pages carry no `language-xxx` class on <pre>/<code>
# (only inner hljs-* spans), so class-based detection falls back to `text` and
# loses the language. Infer from content, but only when confident — a wrong tag
# is worse than none. Signals are weighted: a strong structural signal (weight 2,
# e.g. `def name(`, a shebang) alone clears the bar; weak signals (weight 1) need
# a second signal. Threshold 2; ties between languages → None (→ ```text).
# STRONG signals must be unambiguous — `def\s+\w+\s*\(` needs `def name(`, so
# prose like "the def of done" (def + non-word) never matches.
_STRONG = 2
_WEAK = 1
_PY_SIGNALS = (
    (re.compile(r"^\s*def\s+\w+\s*\(", re.M), _STRONG),
    (re.compile(r"^\s*class\s+\w+\s*[:(]", re.M), _STRONG),
    (re.compile(r"^\s*(?:import\s+\w|from\s+[\w.]+\s+import\b)", re.M), _STRONG),
    (re.compile(r"->\s*(?:None|bool|int|str|float|list|dict|[A-Z]\w*)\s*:"), _STRONG),
    (re.compile(r"^\s*return\b", re.M), _WEAK),
    (re.compile(r"\bself\."), _WEAK),
    (re.compile(r":\s*(?:list|dict|tuple|set|str|int|float|bool)\["), _WEAK),
    (re.compile(r'\bf"[^"]*\{|\bf\'[^\']*\{'), _WEAK),
    (re.compile(r"\bprint\("), _WEAK),
    (re.compile(r"^\s*(?:if|for|while|with|try|elif|else|except)\b.*:\s*$", re.M), _WEAK),
)
_JS_SIGNALS = (
    (re.compile(r"\b(?:const|let|var)\s+\w+\s*="), _STRONG),
    (re.compile(r"\bfunction\s*\*?\s*\w*\s*\("), _STRONG),
    (re.compile(r"=>"), _WEAK),
    (re.compile(r"\brequire\(|\bexport\s+(?:default|const|function)\b"), _WEAK),
    (re.compile(r"\bconsole\.\w+\("), _WEAK),
)
_PS_SIGNALS = (
    # $env:VAR and $PSItem/heredoc @"..."@ are unambiguous PowerShell; without
    # these a `$env:PYTHONPATH=...; python -m pytest` block scores as bash.
    (re.compile(r"\$env:\w+", re.I), _STRONG),
    (re.compile(r'@"[\s\S]*?"@'), _STRONG),
    (re.compile(r"\bWrite-(?:Host|Output)\b|\bGet-\w+\b|\bSet-\w+\b"), _STRONG),
    (re.compile(r"\$PSItem\b|\$_\."), _WEAK),
)
_BASH_SIGNALS = (
    (re.compile(r"^\s*#!.*\b(?:bash|sh)\b", re.M), _STRONG),
    (re.compile(r"^\s*\$\s+\S", re.M), _STRONG),
    # Package/test invocations are only WEAK: a single `pip install ...` or
    # `python -m ...` line also appears in Dockerfiles (RUN pip install), CI YAML
    # (run: pip install), and prose, so one alone must NOT reach the bar. Two
    # command lines (or a pipe) clear it. Disjoint from the bare-utility list
    # below so the same text is never scored twice.
    (re.compile(r"\bpython\s+-m\b|\bpip\s+install\b|^\s*pytest\b", re.M), _WEAK),
    # Bare shell utilities at line start — weak; two lines (or a pipe) clear it.
    (re.compile(r"^\s*(?:npm|npx|git|cd|export|sudo|apt|curl|mkdir|rm|cp|mv|echo)\b", re.M), _WEAK),
    (re.compile(r"\|\s*(?:grep|jq|awk|sed|xargs)\b"), _WEAK),
)


def _looks_like_json(code: str) -> bool:
    """Strong structural signal: whole block is a JSON object/array with keys."""
    stripped = code.strip()
    if not (stripped.startswith(("{", "[")) and stripped.endswith(("}", "]"))):
        return False
    # A quoted-key colon pair, no statement keywords / comments that betray code.
    if not re.search(r'"[^"]+"\s*:', stripped):
        return False
    if re.search(r"\b(?:def|function|return|import|const|let|var)\b|#|//|=>", stripped):
        return False
    return True


def guess_code_language(code: str) -> str | None:
    """Infer a fenced-code language from content, or None if not confident.

    Used only when no ``language-xxx`` class is present (gap #23). Returns a
    language name only on strong evidence; ties or weak signals return None so
    the caller keeps ``text`` rather than mislabel prose/comments.
    """

    if not code.strip():
        return None
    if _looks_like_json(code):  # strong single structural signal
        return "json"

    def _score(signals: tuple[tuple[Any, int], ...]) -> int:
        return sum(weight for rx, weight in signals if rx.search(code))

    scores = {
        "python": _score(_PY_SIGNALS),
        "javascript": _score(_JS_SIGNALS),
        "powershell": _score(_PS_SIGNALS),
        "bash": _score(_BASH_SIGNALS),
    }
    # PowerShell command blocks (`$env:...`) also match bash command signals
    # (`python -m`, `git`); `$env:`/heredoc is unambiguous PowerShell, so once a
    # STRONG PS signal fires, suppress bash regardless of how many extra bash
    # command lines the block also has (else `$env:...; python -m ...; git ...`
    # scores bash 3 > ps 2 and mislabels as bash).
    if scores["powershell"] >= _STRONG:
        scores["bash"] = 0
    best = max(scores, key=lambda k: scores[k])
    top = scores[best]
    if top < 2:
        return None
    # Tie between languages → ambiguous, stay text.
    if sum(1 for v in scores.values() if v == top) > 1:
        return None
    return best


def _join_inline(parts: Iterable[str]) -> str:
    """Concatenate inline fragments, separating adjacent inline formulas.

    Two adjacent inline formulas render as ``$a$$b$``; the ``$$`` is parsed by
    GitHub/KaTeX as a display-math delimiter and breaks rendering. Inserting a
    single space (``$a$ $b$``) keeps both as inline math without changing the
    formula type or the ``formula_inline`` count. Only a ``$``-terminated
    fragment immediately followed by a ``$``-led fragment collides; every other
    boundary is left untouched.
    """

    result = ""
    for part in parts:
        if not part:
            continue
        if result.endswith("$") and part.startswith("$"):
            result += " "
        result += part
    return result


def clean_inline(value: str) -> str:
    value = re.sub(r"[\t\r\n ]+", " ", value)
    value = re.sub(r" +([,.;:!?，。；：！？、)])", r"\1", value)
    return re.sub(r"([(]) +", r"\1", value).strip()


class MarkdownConverter:
    def __init__(
        self,
        root: Tag,
        formulas: Sequence[Any],
        assets: Sequence[Any],
        asset_dir: Path,
        asset_prefix: str,
        orig_dir: Path | None = None,
        enable_image_processing: bool = True,
    ) -> None:
        self.root = root
        self.asset_dir = asset_dir
        self.asset_prefix = asset_prefix.rstrip("/")
        self.orig_dir = orig_dir
        self.enable_image_processing = enable_image_processing
        self.counts = EmittedCounts()
        self.ledger: list[Any] = []
        self.unresolved: list[dict[str, str]] = []
        self.warnings: list[str] = []

        formula_nodes = preflight._top_level_formula_nodes(root)
        asset_nodes = list(root.select("img, iframe, video"))
        if len(formula_nodes) != len(formulas):
            raise FastPathUnsupported("formula manifest does not match compact DOM")
        if len(asset_nodes) != len(assets):
            raise FastPathUnsupported("asset manifest does not match compact DOM")
        self.formulas = {id(n): r for n, r in zip(formula_nodes, formulas, strict=True)}
        self.assets = {id(n): r for n, r in zip(asset_nodes, assets, strict=True)}

    def convert(self) -> ConversionResult:
        markdown = "\n\n".join(x for x in self.blocks(self.root) if x.strip()).strip() + "\n"
        markdown = markdown_postprocess.postprocess_markdown(markdown)
        markdown_fences.scan_fenced_blocks(markdown)
        image_disposition.assert_valid_image_ledger(
            self.ledger,
            source_ids=[r.source_id for r in self.assets.values() if r.tag == "img"],
        )
        return ConversionResult(
            markdown,
            self.counts,
            tuple(self.ledger),
            tuple(self.unresolved),
            tuple(self.warnings),
        )

    def blocks(self, node: Tag) -> list[str]:
        result: list[str] = []
        for child in node.children:
            if isinstance(child, NavigableString):
                text = clean_inline(str(child))
                if text:
                    result.append(text)
            elif isinstance(child, Tag):
                rendered = self.block(child)
                if isinstance(rendered, list):
                    result.extend(rendered)
                elif rendered:
                    result.append(rendered)
        return result

    def block(self, node: Tag) -> str | list[str]:
        if id(node) in self.formulas:
            return self.formula(node)
        slate = str(node.attrs.get("data-slate-type", ""))
        if node.name in {f"h{i}" for i in range(1, 7)} or slate.startswith("heading"):
            self.counts.headings += 1
            level = int(node.name[1]) if re.fullmatch(r"h[1-6]", node.name or "") else 2
            return f"{'#' * level} {self.inline_children(node)}"
        if node.name == "p" or slate == "paragraph":
            # 原生 <p>（无 slate）可能被 mdnice 等编辑器塞入「前导行内 + 尾部块
            # wrapper（section/div 裹 table 等）」的混排。块全在尾部时拆成段落 + 块
            # 穿透；块夹中间 / 块后有行内 / Slate 段落 → 维持 inline_children，
            # 遇块子时仍 fail-close 到 strict（不猜混排布局）。
            if node.name == "p" and not slate:
                children = list(node.children)

                def _is_block_wrapper(c: Any) -> bool:
                    return (
                        isinstance(c, Tag)
                        and c.name in BLOCK_TRANSPARENT_TAGS
                        and not str(c.attrs.get("data-slate-type", ""))
                        and has_block_child(c)
                    )

                def _is_nonblank_inline(c: Any) -> bool:
                    if isinstance(c, NavigableString):
                        return bool(str(c).strip())
                    return isinstance(c, Tag) and not _is_block_wrapper(c)

                block_idx = [i for i, c in enumerate(children) if _is_block_wrapper(c)]
                if block_idx:
                    last_block = block_idx[-1]
                    tail_clean = not any(
                        _is_nonblank_inline(c) for c in children[last_block + 1 :]
                    )
                    if tail_clean:
                        first_block = block_idx[0]
                        result: list[str] = []
                        lead = clean_inline(
                            _join_inline(self.inline(c) for c in children[:first_block])
                        )
                        if lead.strip():
                            result.append(lead)
                        for c in children[first_block:]:
                            if _is_block_wrapper(c):
                                rendered = self.block(c)
                                if isinstance(rendered, list):
                                    result.extend(rendered)
                                elif rendered:
                                    result.append(rendered)
                            else:
                                # 块之间夹的行内内容作为独立段落发出（tail_clean 只
                                # 保证最后一个块之后无行内）。
                                between = clean_inline(_join_inline([self.inline(c)]))
                                if between.strip():
                                    result.append(between)
                        return result
            return self.inline_children(node)
        if node.name in {"ul", "ol"}:
            return self.list_block(node, 0)
        if slate == "list":
            native = top_level(node, {"ul", "ol"})
            if len(native) > 1:
                raise FastPathUnsupported("list wrapper contains multiple native lists")
            return self.list_block(native[0], 0) if native else self.slate_list(node)
        if node.name == "blockquote" or slate == "block-quote":
            text = "\n\n".join(self.blocks(node))
            return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
        if node.name == "pre" or slate == "pre":
            target = node if node.name == "pre" else node.find("pre") or node
            return self.code_block(target)
        if node.name == "table" or slate == "table":
            target = node if node.name == "table" else node.find("table")
            if not isinstance(target, Tag):
                raise FastPathUnsupported("table wrapper has no native table")
            return self.table_block(target)
        if node.name == "figure":
            values: list[str] = []
            images = node.find_all("img")
            if len(images) > 1:
                raise FastPathUnsupported("figure with multiple images requires strict handling")
            if images:
                values.append(self.image(images[0]))
            caption = node.find("figcaption", recursive=False)
            if isinstance(caption, Tag):
                # A confirmed <figcaption> needs strict handling: caption centering
                # and ledger conservation (emitted_count == 1) are not implemented on
                # the fast path. Emitting it as plain text silently dropped both, which
                # is exactly the caption-centering regression this routing prevents.
                # Mirrors the existing <table><caption> routing. Backed by
                # tests/test_acceptance_caption_centering.py.
                raise FastPathUnsupported("figcaption requires strict caption handling")
            return values
        if node.name == "img":
            return self.image(node)
        if node.name in {"iframe", "video"}:
            raise FastPathUnsupported(f"{node.name} requires strict resource handling")
        if node.name == "hr":
            return "---"
        if node.name in BLOCK_TRANSPARENT_TAGS:
            return self.blocks(node) if has_block_child(node) else self.inline_children(node)
        # WeChat (mmbiz) 用 <span data-tool ...> 包裹块级 <section>（编辑器产物）。
        # 当这样的 <span> 出现在块位置且**含块子**时，它是透明容器，穿透递归成
        # blocks（等价 BLOCK_TRANSPARENT_TAGS）。无块子的块位置 span 视为一段行内
        # 文本发出（内容保留）。有 data-slate 语义的 span 已在上面分支处理，不到这里。
        if node.name == "span" and not slate:
            return self.blocks(node) if has_block_child(node) else self.inline_children(node)
        raise FastPathUnsupported(f"unsupported semantic element <{node.name}>")

    def inline_children(self, node: Tag) -> str:
        return clean_inline(_join_inline(self.inline(child) for child in node.children))

    def inline(self, node: Any) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        if id(node) in self.formulas:
            return self.formula(node)
        slate = str(node.attrs.get("data-slate-type", ""))
        if node.name in {"strong", "b"} or slate == "bold":
            text = self.inline_children(node)
            return f"**{text}**" if text else ""
        if node.name in {"em", "i"} or slate == "italic":
            text = self.inline_children(node)
            return f"*{text}*" if text else ""
        if node.name == "code":
            text = node.get_text()
            fence = "`" * max(1, max_backticks(text) + 1)
            pad = " " if text.startswith("`") or text.endswith("`") else ""
            return f"{fence}{pad}{text}{pad}{fence}"
        if node.name == "a":
            text = self.inline_children(node) or str(node.attrs.get("href", ""))
            href = str(node.attrs.get("href", ""))
            return f"[{text}]({href})" if href else text
        if node.name == "br":
            return "\n"
        if node.name == "img":
            return self.image(node)
        if node.name in {"del", "s"}:
            text = self.inline_children(node)
            return f"~~{text}~~" if text else ""
        if node.name in {"sup", "sub"}:
            text = self.inline_children(node)
            return f"<{node.name}>{text}</{node.name}>" if text else ""
        if node.name in INLINE_TRANSPARENT_TAGS:
            return _join_inline(self.inline(child) for child in node.children)
        if node.name in BLOCK_TRANSPARENT_TAGS and not slate:
            # A semantic-free wrapper (bare div/section/article/main) carrying
            # only inline content is transparent here, mirroring the block
            # context (see block-transparent handling above). A wrapper hiding a
            # real block child still fails closed and routes the page to strict.
            if has_block_child(node):
                raise FastPathUnsupported(
                    f"inline wrapper <{node.name}> contains block content"
                )
            return _join_inline(self.inline(child) for child in node.children)
        raise FastPathUnsupported(f"unsupported inline semantic element <{node.name}>")

    def formula(self, node: Tag) -> str:
        record = self.formulas[id(node)]
        if record.display == "block":
            self.counts.formula_block += 1
        else:
            self.counts.formula_inline += 1
        latex = record.original_latex.strip()
        if latex:
            # 缺陷 #16：映射公式拆分后，标识符移出公式变行内代码。
            # ``$var$ ← `ident``` 两部分都 GitHub-safe（原整式 \text{a\_b} 在 GitHub 挂）。
            if record.trailing_code:
                return f"${latex}$ ← `{record.trailing_code}`"
            return f"$$\n{latex}\n$$" if record.display == "block" else f"${latex}$"
        self.unresolved.append(
            {"source_id": record.source_id, "source_kind": record.source_kind, "dom_hash": record.dom_hash}
        )
        return f"{{{{FORMULA:{record.source_id}}}}}"

    @staticmethod
    def _li_inline_passthrough_target(child: Any) -> Tag | None:
        """li 内 mdnice 块 wrapper（section/div 无 slate）裹单个可行内段落时，
        返回那个段落节点供取行内内容；否则 None（走原 inline，含 fail-close）。

        WeChat/mdnice 把有序列表项包成 ``<li><section><p>文字</p></section></li>``。
        section 是透明排版 wrapper，穿透后取内层 <p> 的行内内容即可。裹 table/
        list/pre/多段落/更深块 → 返回 None，交给 self.inline() fail-close（列表内嵌
        真块 GFM 表达受限，保守交 strict）。
        """
        if not isinstance(child, Tag):
            return None
        if child.name not in BLOCK_TRANSPARENT_TAGS:
            return None
        if str(child.attrs.get("data-slate-type", "")):
            return None
        block_children = [
            c for c in child.children
            if isinstance(c, Tag) and c.name in _HAS_BLOCK_NAMES
        ]
        if len(block_children) != 1:
            return None
        # wrapper 内块之外的裸文本（如 <section>散文<p>foo</p></section>）穿透后会被
        # inline_children(inner) 静默丢弃 → fail-close 交 self.inline，不吞内容。
        if any(
            isinstance(c, NavigableString) and str(c).strip()
            for c in child.children
        ):
            return None
        inner = block_children[0]
        if inner.name not in {"p", "div"}:
            return None  # 裹 table/list/pre 等真块 → 不穿透
        if str(inner.attrs.get("data-slate-type", "")):
            return None  # 带 slate 语义的段落交原路径处理
        # 段落自身不能再藏块子
        if any(isinstance(g, Tag) and g.name in _HAS_BLOCK_NAMES for g in inner.children):
            return None
        return inner

    def list_block(self, node: Tag, level: int) -> str:
        self.counts.lists += 1
        lines: list[str] = []
        index = 0
        # 遍历所有直接子，而非只 li：WeChat/mdnice 会把嵌套 ul/ol 直接挂在
        # 父 ol/ul 下（不在 li 内），只遍历 li 会整块吞掉这些游离嵌套列表。
        # li → 输出列表项并递增序号；游离 ul/ol → 当嵌套列表递归（缩进 level+1）。
        for node_child in node.children:
            if not isinstance(node_child, Tag):
                continue
            if node_child.name in {"ul", "ol"}:
                lines.extend(self.list_block(node_child, level + 1).splitlines())
                continue
            if node_child.name != "li":
                continue
            item = node_child
            index += 1
            self.counts.list_items += 1
            nested: list[Tag] = []
            content: list[str] = []
            for child in item.children:
                if isinstance(child, Tag) and child.name in {"ul", "ol"}:
                    nested.append(child)
                else:
                    target = self._li_inline_passthrough_target(child)
                    if target is not None:
                        content.append(self.inline_children(target))
                    else:
                        content.append(self.inline(child))
            marker = f"{index}." if node.name == "ol" else "-"
            lines.append(f"{'  ' * level}{marker} {clean_inline(_join_inline(content))}".rstrip())
            for child in nested:
                lines.extend(self.list_block(child, level + 1).splitlines())
        return "\n".join(lines)

    def slate_list(self, node: Tag) -> str:
        self.counts.lists += 1
        items = [
            item for item in node.select('[data-slate-type="list-line"]')
            if item.find_parent(attrs={"data-slate-type": "list"}) is node
        ]
        if not items:
            raise FastPathUnsupported("Slate list has no list-line items")
        self.counts.list_items += len(items)
        return "\n".join(f"- {self.inline_children(item)}" for item in items)

    def code_block(self, node: Tag) -> str:
        self.counts.codeblocks += 1
        code_node = node.find("code") if node.name == "pre" else None
        target = code_node if isinstance(code_node, Tag) else node
        code = _strip_blank_edges(self._code_text(target).replace("\xa0", " "))
        _assert_indent_intact(code)
        language = ""
        for name in list(target.get("class", ())) + list(node.get("class", ())):
            match = re.search(r"(?:language|lang)-([A-Za-z0-9_+-]+)", name)
            if match:
                language = match.group(1)
                break
        # gap #23: highlight.js pages have no language-* class; infer from content
        # when confident, else fall back to text.
        if not language:
            language = guess_code_language(code) or "text"
        fence = "`" * max(3, max_backticks(code) + 1)
        return f"{fence}{language}\n{code}\n{fence}"

    @staticmethod
    def _code_text(target: Tag) -> str:
        """Return code text, honoring Slate's block-per-line layout.

        The Slate/hljs code widget renders each source line as its own
        block-level ``<div>`` and lets the block boundary carry the newline;
        there is no ``\\n`` text node between lines. ``get_text()`` would then
        glue the lines together (``a.jsonb.py``). When the code is laid out as
        such per-line ``<div>`` rows, join their text with ``\\n``; otherwise
        fall back to the raw text extraction.
        """

        lines = [
            child
            for child in target.descendants
            if isinstance(child, Tag)
            and child.name == "div"
            and any(isinstance(c, Tag) and c.name == "span" for c in child.children)
            and not any(
                isinstance(c, Tag) and c.name == "div" for c in child.children
            )
        ]
        if len(lines) > 1:
            return "\n".join(line.get_text() for line in lines)
        return target.get_text()

    def table_block(self, node: Tag) -> str:
        if node.select("[rowspan], [colspan]"):
            raise FastPathUnsupported("rowspan/colspan table requires strict handling")
        rows: list[list[str]] = []
        first_has_header = False
        for row in node.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if cells:
                if not rows:
                    first_has_header = any(cell.name == "th" for cell in cells)
                rows.append([self.inline_children(cell).replace("|", "\\|") for cell in cells])
        if not rows or any(len(row) != len(rows[0]) for row in rows):
            raise FastPathUnsupported("empty or ragged table requires strict handling")
        self.counts.tables += 1
        if not first_has_header:
            self.warnings.append("table first row promoted to Markdown header")
        lines = [
            "| " + " | ".join(rows[0]) + " |",
            "| " + " | ".join("---" for _ in rows[0]) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)

    def image(self, node: Tag) -> str:
        record = self.assets[id(node)]
        source = str(node.attrs.get("src", ""))
        ledger_extra: dict[str, Any] = {}
        if source.startswith("data:"):
            try:
                mime, data = decode_data_uri(source)
            except ValueError as error:
                raise FastPathUnsupported(str(error)) from error
            if self.enable_image_processing:
                processed = image_processing.process_image(data, mime, record.source_id)
                # Back up the untouched original so the erase is auditable offline.
                if self.orig_dir is not None:
                    self.orig_dir.mkdir(parents=True, exist_ok=True)
                    orig_name = (
                        f"{record.source_id}"
                        f"{extension_for_mime(processed.original_mime)}"
                    )
                    (self.orig_dir / orig_name).write_bytes(processed.original_data)
                out_data, out_mime = processed.data, processed.mime
                meta = processed.meta
                ledger_extra = {
                    "bbox": meta.watermark_bbox,
                    "dewatermarked": meta.dewatermarked,
                    "validation_passed": meta.validation_passed,
                    "orig_bytes": meta.orig_bytes,
                    "final_bytes": meta.final_bytes,
                    "format_note": meta.format_kept_reason,
                    "fallback_to_original": meta.fallback_to_original,
                }
            else:
                out_data, out_mime = data, mime
            filename = f"{record.source_id}{extension_for_mime(out_mime)}"
            self.asset_dir.mkdir(parents=True, exist_ok=True)
            (self.asset_dir / filename).write_bytes(out_data)
            target = f"{self.asset_prefix}/{filename}"
        elif source:
            raise FastPathUnsupported(
                f"external image {record.source_id} must be localized by strict handling"
            )
        else:
            raise FastPathUnsupported(f"image {record.source_id} has no source")
        decision = image_disposition.decide_image(
            image_disposition.ImageContext(
                source_id=record.source_id, in_body=True, has_content_relation=True
            )
        )
        if decision != "keep":
            raise FastPathUnsupported(f"body image classified as {decision}")
        self.counts.images += 1
        self.ledger.append(
            image_disposition.ImageLedgerEntry(
                record.source_id, "keep", 1, **ledger_extra
            )
        )
        alt = str(node.attrs.get("alt", "")).replace("]", "\\]")
        return f"![{alt}]({target})"


def top_level(node: Tag, names: set[str]) -> list[Tag]:
    result: list[Tag] = []
    for candidate in node.find_all(list(names)):
        parent = candidate.parent
        while isinstance(parent, Tag) and parent is not node:
            if parent.name in names:
                break
            parent = parent.parent
        else:
            result.append(candidate)
    return result


_HAS_BLOCK_NAMES = {
    "p", "div", "section", "article", "main", "h1", "h2", "h3", "h4",
    "h5", "h6", "ul", "ol", "pre", "table", "blockquote", "figure",
}


def has_block_child(node: Tag) -> bool:
    return any(
        isinstance(child, Tag) and child.name in _HAS_BLOCK_NAMES
        for child in node.children
    )
