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
    markdown_fences,
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
    ) -> None:
        self.root = root
        self.asset_dir = asset_dir
        self.asset_prefix = asset_prefix.rstrip("/")
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
                values.append(clean_inline(caption.get_text(" ", strip=True)))
            return values
        if node.name == "img":
            return self.image(node)
        if node.name in {"iframe", "video"}:
            raise FastPathUnsupported(f"{node.name} requires strict resource handling")
        if node.name == "hr":
            return "---"
        if node.name in BLOCK_TRANSPARENT_TAGS:
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
            return "".join(self.inline(child) for child in node.children)
        raise FastPathUnsupported(f"unsupported inline semantic element <{node.name}>")

    def formula(self, node: Tag) -> str:
        record = self.formulas[id(node)]
        if record.display == "block":
            self.counts.formula_block += 1
        else:
            self.counts.formula_inline += 1
        latex = record.original_latex.strip()
        if latex:
            return f"$$\n{latex}\n$$" if record.display == "block" else f"${latex}$"
        self.unresolved.append(
            {"source_id": record.source_id, "source_kind": record.source_kind, "dom_hash": record.dom_hash}
        )
        return f"{{{{FORMULA:{record.source_id}}}}}"

    def list_block(self, node: Tag, level: int) -> str:
        self.counts.lists += 1
        lines: list[str] = []
        for index, item in enumerate(node.find_all("li", recursive=False), start=1):
            self.counts.list_items += 1
            nested: list[Tag] = []
            content: list[str] = []
            for child in item.children:
                if isinstance(child, Tag) and child.name in {"ul", "ol"}:
                    nested.append(child)
                else:
                    content.append(self.inline(child))
            marker = f"{index}." if node.name == "ol" else "-"
            lines.append(f"{'  ' * level}{marker} {clean_inline(''.join(content))}".rstrip())
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
        code = target.get_text().replace("\xa0", " ").rstrip("\n")
        language = "text"
        for name in list(target.get("class", ())) + list(node.get("class", ())):
            match = re.search(r"(?:language|lang)-([A-Za-z0-9_+-]+)", name)
            if match:
                language = match.group(1)
                break
        fence = "`" * max(3, max_backticks(code) + 1)
        return f"{fence}{language}\n{code}\n{fence}"

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
        if source.startswith("data:"):
            try:
                mime, data = decode_data_uri(source)
            except ValueError as error:
                raise FastPathUnsupported(str(error)) from error
            filename = f"{record.source_id}{extension_for_mime(mime)}"
            self.asset_dir.mkdir(parents=True, exist_ok=True)
            (self.asset_dir / filename).write_bytes(data)
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
            image_disposition.ImageLedgerEntry(record.source_id, "keep", 1)
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


def has_block_child(node: Tag) -> bool:
    names = {
        "p", "div", "section", "article", "main", "h1", "h2", "h3", "h4",
        "h5", "h6", "ul", "ol", "pre", "table", "blockquote", "figure",
    }
    return any(isinstance(child, Tag) and child.name in names for child in node.children)
