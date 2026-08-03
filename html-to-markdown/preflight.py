"""Deterministic preflight analysis for SingleFile HTML.

The preflight stage keeps the full SingleFile document out of the agent context.
It selects one semantic body container, writes a compact HTML snapshot, and
emits machine-readable manifests for downstream conversion and validation.

This module deliberately fails closed when it cannot identify one body
container. The strict workflow can then inspect the original page instead of a
fast-path converter silently guessing the wrong content range.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from bs4 import BeautifulSoup, Tag


SCHEMA_VERSION = "1.0"
MIN_BODY_TEXT_CHARS = 80
BODY_SELECTORS: tuple[str, ...] = (
    "[data-slate-editor]",
    "article",
    "main",
    '[role="main"]',
    # WeChat 公众号 (mmbiz) SingleFile 页面：正文容器无 article/main 语义，
    # 用固定 id/class。排在语义 selector 之后，仍受「首个有 substantial
    # 命中的优先级必须唯一」的 fail-closed 约束（多个命中→ambiguous 失败）。
    "#js_content",
    ".rich_media_content",
)
FORMULA_SELECTOR = '[data-slate-type*="katex"], .katex, math, [data-formula]'
REMOVABLE_TAGS: tuple[str, ...] = ("script", "style", "noscript", "template")
LAZY_SOURCE_ATTRIBUTES: tuple[str, ...] = (
    "data-src",
    "data-original",
    "data-lazy",
    "srcset",
)
STRICT_MARKERS: dict[str, tuple[str, ...]] = {
    "notebook": (
        "jp-cell",
        "command-input",
        "cell-output",
        "data-mode-id",
        "jupyter",
        "databricks",
        "colab",
    ),
    "virtualized_editor": (
        "monaco-editor",
        "codemirror",
        "cm-editor",
        "react-virtualized",
        "view-lines",
    ),
}


class BodySelectionError(ValueError):
    """Raised when a unique, sufficiently substantial body cannot be selected."""


@dataclass(frozen=True)
class FormulaRecord:
    source_id: str
    display: str
    source_kind: str
    dom_hash: str
    original_latex: str
    # 缺陷 #16：``var \leftarrow \text{ident}`` 映射公式拆分后，标识符从公式里移出、
    # 变行内代码。非空时 emit 为 ``$original_latex$ ← `trailing_code```。默认空=不拆。
    trailing_code: str = ""


@dataclass(frozen=True)
class AssetRecord:
    source_id: str
    tag: str
    source_kind: str
    source_chars: int
    alt: str
    lazy: bool


@dataclass(frozen=True)
class PreflightResult:
    compact_html: str
    manifest: dict[str, Any]
    formulas: tuple[FormulaRecord, ...]
    assets: tuple[AssetRecord, ...]
    compact_root: Tag = field(compare=False, repr=False)


def _normalized_text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _substantial(nodes: Iterable[Tag]) -> list[Tag]:
    return [node for node in nodes if len(_normalized_text(node)) >= MIN_BODY_TEXT_CHARS]


def select_body(soup: BeautifulSoup) -> tuple[Tag, str]:
    """Return one semantic body and the selector that identified it.

    Selectors are evaluated by priority. At the first priority with substantial
    matches, exactly one candidate must exist. Multiple candidates fail closed;
    choosing the largest one would risk silently dropping another article.
    """

    for selector in BODY_SELECTORS:
        candidates = _substantial(soup.select(selector))
        if len(candidates) == 1:
            return candidates[0], selector
        if len(candidates) > 1:
            raise BodySelectionError(
                f"ambiguous body selector {selector!r}: {len(candidates)} substantial matches"
            )

    raise BodySelectionError(
        "no unique semantic body found; strict inspection is required"
    )


def _matches_formula(node: Tag) -> bool:
    slate_type = str(node.attrs.get("data-slate-type", ""))
    classes = set(node.get("class", ()))
    return (
        "katex" in slate_type
        or "katex" in classes
        or node.name == "math"
    )


def _inside_formula(node: Tag) -> bool:
    current: Tag | None = node
    while current is not None:
        if _matches_formula(current):
            return True
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def standalone_math_tex_script_count(soup: BeautifulSoup) -> int:
    """Count MathJax v2 source scripts outside recognized formula containers.

    The full document has already been parsed for body selection. Reusing that
    tree avoids a second expensive parse of CSS-heavy SingleFile input while
    preserving fail-closed routing for scripts compaction cannot bind to a
    formula node.
    """

    return sum(
        1
        for node in soup.find_all("script")
        if str(node.attrs.get("type", "")).strip().lower().startswith("math/tex")
        and not _inside_formula(node)
    )


def compact_body(body: Tag) -> Tag:
    """Clone and compact a body while preserving formula structure."""

    clone_soup = BeautifulSoup(str(body), "lxml")
    clone = clone_soup.body.find() if clone_soup.body else clone_soup.find()
    if not isinstance(clone, Tag):
        raise ValueError("selected body could not be serialized")

    for tag_name in REMOVABLE_TAGS:
        for node in list(clone.find_all(tag_name)):
            if not _inside_formula(node):
                node.decompose()

    # Event handlers are executable page chrome, not article semantics. Retain
    # class/style/data attributes because rich text and KaTeX reconstruction use
    # them as structural evidence.
    for node in clone.find_all(True):
        for attribute in list(node.attrs):
            if attribute.lower().startswith("on"):
                del node.attrs[attribute]

    return clone


def _normalize_style(value: str) -> str:
    declarations: list[tuple[str, str]] = []
    for raw in value.split(";"):
        if not raw.strip() or ":" not in raw:
            continue
        name, content = raw.split(":", 1)
        declarations.append((name.strip().lower(), " ".join(content.split())))
    return ";".join(f"{name}:{content}" for name, content in sorted(declarations))


def _canonical_attribute(name: str, value: Any) -> str:
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
        if name == "class":
            parts.sort()
        rendered = " ".join(parts)
    else:
        rendered = str(value)
    if name == "style":
        rendered = _normalize_style(rendered)
    return f"{name.lower()}={rendered}"


def canonical_dom(node: Tag) -> str:
    """Return a deterministic formula serialization for hashing.

    Attribute order, class order, insignificant text whitespace, and CSS
    declaration order are normalized. Formula classes and inline styles remain
    part of the hash because they can encode KaTeX structure.
    """

    pieces: list[str] = []

    def visit(current: Any) -> None:
        if isinstance(current, Tag):
            attributes = ",".join(
                _canonical_attribute(name, current.attrs[name])
                for name in sorted(current.attrs)
                if not name.lower().startswith("on")
            )
            pieces.append(f"<{current.name.lower()}|{attributes}>")
            for child in current.children:
                visit(child)
            pieces.append(f"</{current.name.lower()}>")
            return

        text = " ".join(str(current).split())
        if text:
            pieces.append(text)

    visit(node)
    return "".join(pieces)


def formula_hash(node: Tag) -> str:
    return hashlib.sha256(canonical_dom(node).encode("utf-8")).hexdigest()


_FORMULA_LATEX_ATTRS = ("data-tex", "data-latex", "data-math", "data-formula", "alttext")


def _own_attr_latex(node: Tag) -> str:
    """节点**自身** data 属性携带的 verbatim LaTeX（不搜后代）。

    专供双层包装去重使用：``_formula_source`` 会用 ``select_one`` 后代搜索
    annotation，对祖先节点会误命中其后代公式的 LaTeX，不能用于祖先比较。
    """
    for attribute in _FORMULA_LATEX_ATTRS:
        value = str(node.attrs.get(attribute, "")).strip()
        if value:
            return value
    return ""


def _top_level_formula_nodes(root: Tag) -> list[Tag]:
    result: list[Tag] = []
    for node in root.select(FORMULA_SELECTOR):
        if not isinstance(node, Tag):
            continue
        node_latex = _own_attr_latex(node)
        ancestor = node.parent
        nested = False
        while isinstance(ancestor, Tag) and ancestor is not root:
            if _matches_formula(ancestor):
                nested = True
                break
            # mdnice/微信把公式包成两层相同 data-formula span（外层加 cursor:pointer
            # 点击效果）。祖先自身 data 属性带**相同** LaTeX → 是同一公式的外包装，
            # 本节点判 nested 去重。LaTeX 不同的祖先公式是合法嵌套（块级公式内嵌不同
            # 的行内公式），不判 nested。只比祖先自身属性，不搜后代。
            if node_latex and _own_attr_latex(ancestor) == node_latex:
                nested = True
                break
            ancestor = ancestor.parent
        if not nested:
            result.append(node)
    return result


def _formula_source(node: Tag) -> tuple[str, str]:
    annotation = node.select_one('annotation[encoding="application/x-tex"]')
    if annotation is not None and annotation.get_text(strip=True):
        return "annotation", annotation.get_text(strip=True)

    # ``data-formula`` 是微信公众号 (mmbiz) 里 MathJax-SVG 公式 wrapper 携带的原始
    # LaTeX（如 ``R_t = \frac{P_t}{P_{t-1}} - 1``）。verbatim 可用，无需 KaTeX HTML 重建。
    for attribute in _FORMULA_LATEX_ATTRS:
        value = str(node.attrs.get(attribute, "")).strip()
        if value:
            return attribute, value

    script = node.select_one('script[type^="math/tex"]')
    if script is not None and script.get_text(strip=True):
        return "math-tex-script", script.get_text(strip=True)

    if node.name == "math" or node.find("math") is not None:
        return "mathml", ""

    if "katex" in set(node.get("class", ())) or "katex" in str(
        node.attrs.get("data-slate-type", "")
    ):
        return "katex-html-only", ""

    return "unknown", ""


def _formula_display(node: Tag) -> str:
    current: Tag | None = node
    while current is not None:
        classes = set(current.get("class", ()))
        slate_type = str(current.attrs.get("data-slate-type", ""))
        if "katex-display" in classes or "block-katex" in slate_type:
            return "block"
        # WeChat (mmbiz) MathJax-SVG 公式：块级公式 wrapper 是 <section>，其 style
        # 含 display:block；行内公式 wrapper 是 <span>，style 无 display:block。
        # 只认**传入的 formula 节点自身** (current is node) 的 display:block——不看
        # 任何祖先，否则一个块级公式 wrapper 若恰是某行内公式的祖先，会把行内误判为
        # 块级。祖先仍参与上面的 katex-display/block-katex 判定（那是 KaTeX 语义）。
        if (
            current is node
            and current.has_attr("data-formula")
            and "display:block"
            in str(current.attrs.get("style", "")).replace(" ", "")
        ):
            return "block"
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return "inline"


def collect_formulas(root: Tag) -> tuple[FormulaRecord, ...]:
    records: list[FormulaRecord] = []
    for index, node in enumerate(_top_level_formula_nodes(root), start=1):
        source_kind, original_latex = _formula_source(node)
        records.append(
            FormulaRecord(
                source_id=f"formula-{index:04d}",
                display=_formula_display(node),
                source_kind=source_kind,
                dom_hash=formula_hash(node),
                original_latex=original_latex,
            )
        )
    return tuple(records)


def _substantial_data_uri(source: str) -> bool:
    """True when ``src`` is a data-URI carrying a real (non-placeholder) payload.

    SingleFile inlines the actual image into ``src`` as a base64 data-URI. A
    genuine image decodes to well over a KiB; 1x1 tracking/placeholder pixels
    decode to under ~100 bytes. The 512-byte floor sits safely between the two
    (smallest real inlined image observed ~9 KiB) so a real inlined image is
    trusted while a tiny placeholder still falls through to the lazy check.
    """

    if not source.startswith("data:") or "," not in source:
        return False
    header, payload = source.split(",", 1)
    if ";base64" in header:
        # 4 base64 chars encode 3 bytes; approximate decoded size without decoding.
        # Strip whitespace (some encoders wrap every 76 chars) and trailing "="
        # padding first, so newlines/padding are not miscounted as real data —
        # otherwise a whitespace-heavy sub-512B payload could overcount past the
        # floor and be wrongly trusted over a real data-src.
        payload = "".join(payload.split()).rstrip("=")
        approx_bytes = len(payload) * 3 // 4
    else:
        approx_bytes = len(payload)
    return approx_bytes >= 512


def _asset_source(node: Tag) -> tuple[str, str]:
    """Return the effective source class without trusting placeholder ``src``.

    SingleFile pages commonly retain both a placeholder ``src`` and the real
    resource in ``data-src``/``srcset``. Any distinct lazy candidate is routed
    to strict mode rather than allowing the fast path to emit the placeholder.
    """

    source = str(node.attrs.get("src", "")).strip()

    # WeChat (mmbiz) SingleFile pages inline the real image into ``src`` as a
    # data-URI yet keep the original CDN URL in ``data-src``. That leftover is
    # NOT a lazy placeholder — the image is fully present — so a substantial
    # data-URI ``src`` is authoritative and must win over the ``data-src``
    # lazy heuristic below. Tiny placeholder data-URIs (tracking pixels) fail
    # the size floor and still fall through to the lazy routing.
    if _substantial_data_uri(source):
        return "data-uri", source

    lazy_candidates = [
        (attribute, str(node.attrs.get(attribute, "")).strip())
        for attribute in LAZY_SOURCE_ATTRIBUTES
        if str(node.attrs.get(attribute, "")).strip()
    ]
    for attribute, fallback in lazy_candidates:
        if fallback != source:
            return f"lazy:{attribute}", fallback

    if source.startswith("data:"):
        return "data-uri", source
    if source:
        return "url", source
    if lazy_candidates:
        attribute, fallback = lazy_candidates[0]
        return f"lazy:{attribute}", fallback
    return "missing", ""


def collect_assets(root: Tag) -> tuple[AssetRecord, ...]:
    records: list[AssetRecord] = []
    nodes: Sequence[Tag] = tuple(root.select("img, iframe, video"))
    for index, node in enumerate(nodes, start=1):
        source_kind, source = _asset_source(node)
        records.append(
            AssetRecord(
                source_id=f"asset-{index:04d}",
                tag=node.name,
                source_kind=source_kind,
                source_chars=len(source),
                alt=str(node.attrs.get("alt", "")),
                lazy=source_kind.startswith("lazy:") or source_kind == "missing",
            )
        )
    return tuple(records)


def _canonical_count(root: Tag, wrapper_selector: str, native_name: str) -> int:
    """Count wrapper/native blocks once without importing the full contract module."""

    identities: set[int] = set()
    for node in root.select(f"{wrapper_selector}, {native_name}"):
        canonical = node
        if node.name != native_name:
            native_nodes = [
                child
                for child in node.select(native_name)
                if child.find_parent(native_name) is None
                or child.find_parent(native_name) is node
            ]
            if len(native_nodes) == 1:
                canonical = native_nodes[0]
        identities.add(id(canonical))
    return len(identities)


def structural_counts(root: Tag, formulas: Sequence[FormulaRecord]) -> dict[str, int]:
    return {
        "headings": len(root.select("h1, h2, h3, h4, h5, h6, [data-slate-type^=heading]")),
        "tables": _canonical_count(root, '[data-slate-type="table"]', "table"),
        "lists": len(root.select("ul, ol, [data-slate-type=list]")),
        "list_items": len(root.select("li, [data-slate-type=list-line]")),
        "images": len(root.select("img")),
        "codeblocks": _canonical_count(root, '[data-slate-type="pre"]', "pre"),
        "formula_block": sum(item.display == "block" for item in formulas),
        "formula_inline": sum(item.display == "inline" for item in formulas),
        "formula_total": len(formulas),
        "formula_unique": len({item.dom_hash for item in formulas}),
    }


def detect_signals(
    original_html: str,
    root: Tag,
    assets: Sequence[AssetRecord],
    *,
    standalone_math_tex_scripts: int = 0,
) -> dict[str, Any]:
    lowered = original_html.lower()
    signals: dict[str, Any] = {
        name: any(marker in lowered for marker in markers)
        for name, markers in STRICT_MARKERS.items()
    }
    signals["lazy_placeholders"] = sum(item.lazy for item in assets)
    signals["iframes"] = len(root.select("iframe"))
    signals["standalone_math_tex_scripts"] = standalone_math_tex_scripts
    signals["strict_reasons"] = []

    if signals["notebook"]:
        signals["strict_reasons"].append("notebook markers detected")
    if signals["virtualized_editor"]:
        signals["strict_reasons"].append("virtualized editor markers detected")
    if signals["lazy_placeholders"]:
        signals["strict_reasons"].append(
            f"{signals['lazy_placeholders']} lazy or missing resource placeholders"
        )
    if standalone_math_tex_scripts:
        signals["strict_reasons"].append(
            f"{standalone_math_tex_scripts} standalone math/tex script formulas require "
            "strict MathJax handling because preflight cannot bind them to a formula node"
        )
    return signals


# Slate 代码块把缩进存成独立的纯空白 ``data-slate-string`` 文本节点。BS4/浏览器
# 按 HTML 标准折叠连续空白,该缩进在解析瞬间塌成 1 空格 → 代码缩进丢失、Python
# 不可运行。解析前把 ≥2 空格的纯空白 slate-string 节点转 NBSP:BS4 不折叠 NBSP,
# 缩进原样穿过解析/序列化/二次解析,``fast_converter._code_text`` 的
# ``.replace("\xa0", " ")`` 再还原成普通空格。
#
# ≥2 空格是关键约束:单空格是正文正常空格(非缩进),不匹配以免误伤正文;含代码
# 字符的节点末尾不是紧邻 ``</span>`` 的纯空格,同样不匹配。为免误伤正文里恰好
# ≥2 空格的纯空白节点(预排版对齐等),只在 ``data-slate-type=code-line`` 块内替换
# ——不再依赖"所有 ≥2 空格节点都在 code-line 内"的实证假设。
_CODE_LINE_RE = re.compile(
    r'<[a-zA-Z]+\b[^>]*\bdata-slate-type=(?:"code-line"|\'code-line\'|code-line)[^>]*>'
    r'.*?</[a-zA-Z]+>',
    re.DOTALL,
)
# 属性值三形态(裸/双引号/单引号)都认,漏一种缩进即漏保护退回折叠。
_CODE_INDENT_RE = re.compile(
    r'(data-slate-string=(?:"true"|\'true\'|true)>)(  +)(</span>)'
)


def _protect_indent_in_segment(segment: str) -> str:
    return _CODE_INDENT_RE.sub(
        lambda m: m.group(1) + "\xa0" * len(m.group(2)) + m.group(3),
        segment,
    )


def _protect_code_indent(html: str) -> str:
    """把 code-line 块内 ≥2 空格纯空白 slate-string 节点的空格换成 NBSP,防 BS4
    折叠代码缩进。只在 code-line 段内替换,正文不受影响。"""
    return _CODE_LINE_RE.sub(
        lambda m: _protect_indent_in_segment(m.group(0)),
        html,
    )


def build_preflight(html: str) -> PreflightResult:
    original_html = html
    html = _protect_code_indent(html)
    soup = BeautifulSoup(html, "lxml")
    standalone_math_tex_scripts = standalone_math_tex_script_count(soup)
    body, body_selector = select_body(soup)
    compact_root = compact_body(body)
    compact_html = compact_root.decode(formatter="minimal")
    formulas = collect_formulas(compact_root)
    assets = collect_assets(compact_root)
    # signals 用原始 html:NBSP 保护是内部机制,strict marker 检测应看原文。
    signals = detect_signals(
        original_html,
        compact_root,
        assets,
        standalone_math_tex_scripts=standalone_math_tex_scripts,
    )
    source_counts: dict[str, int] = {}
    for item in formulas:
        source_counts[item.source_kind] = source_counts.get(item.source_kind, 0) + 1

    input_bytes = len(original_html.encode("utf-8"))
    compact_bytes = len(compact_html.encode("utf-8"))
    visible_text_bytes = len(_normalized_text(compact_root).encode("utf-8"))
    recommended_mode = "strict" if signals["strict_reasons"] else "fast"

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "body": {
            "selector": body_selector,
            "text_chars": len(_normalized_text(compact_root)),
        },
        "sizes": {
            "input_bytes": input_bytes,
            "compact_bytes": compact_bytes,
            "visible_text_bytes": visible_text_bytes,
            "reduction_ratio": round(compact_bytes / input_bytes, 6) if input_bytes else 0,
        },
        "counts": structural_counts(compact_root, formulas),
        "formula_sources": source_counts,
        "signals": signals,
        "recommended_mode": recommended_mode,
    }
    return PreflightResult(compact_html, manifest, formulas, assets, compact_root)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_preflight(result: PreflightResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "content.html").write_text(result.compact_html + "\n", encoding="utf-8")
    _write_json(output_dir / "manifest.json", result.manifest)
    _write_json(
        output_dir / "formulas.json",
        {
            "schema_version": SCHEMA_VERSION,
            "items": [asdict(item) for item in result.formulas],
        },
    )
    _write_json(
        output_dir / "assets.json",
        {
            "schema_version": SCHEMA_VERSION,
            "items": [asdict(item) for item in result.assets],
        },
    )


def run_preflight(input_path: Path, output_dir: Path) -> PreflightResult:
    html = input_path.read_text(encoding="utf-8")
    result = build_preflight(html)
    write_preflight(result, output_dir)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a compact body snapshot and structured SingleFile manifest."
    )
    parser.add_argument("input", type=Path, help="SingleFile HTML path")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for content.html and JSON manifests",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_preflight(args.input, args.output)
    except (OSError, UnicodeError, BodySelectionError, ValueError) as error:
        print(f"preflight failed: {error}")
        return 2

    print(
        json.dumps(
            {
                "recommended_mode": result.manifest["recommended_mode"],
                "counts": result.manifest["counts"],
                "sizes": result.manifest["sizes"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
