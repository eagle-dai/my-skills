"""Batched, cached and fail-closed formula resolution for compact HTML."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence

from bs4 import NavigableString, Tag

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from pipeline_utils import preflight, root_from_html, write_json

SCHEMA_VERSION = "1.1"
VALIDATION_SCHEMA_VERSION = "1.0"
PARSER_VERSION = "katex-html-v2"
VALIDATOR_VERSION = "formula-batch-v1"

SYMBOLS = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ϵ": r"\epsilon", "θ": r"\theta",
    "λ": r"\lambda", "μ": r"\mu", "π": r"\pi", "σ": r"\sigma",
    "φ": r"\varphi", "ϕ": r"\phi", "ω": r"\omega",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∞": r"\infty",
    "∇": r"\nabla", "∂": r"\partial", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "∈": r"\in", "∉": r"\notin",
    "⊂": r"\subset", "→": r"\rightarrow", "←": r"\leftarrow",
    "×": r"\times", "·": r"\cdot", "−": "-", "∥": r"\|",
}
OPERATORS = {
    name: f"\\{name}"
    for name in ("max", "min", "arg", "sup", "inf", "lim", "log", "exp", "sin", "cos", "tan")
}
TOKEN_CLASSES = {"mord", "mbin", "mrel", "mopen", "mclose", "mpunct", "minner", "mop"}
IGNORE_CLASSES = {"strut", "pstrut", "vlist-s", "frac-line", "rule", "arraycolsep", "nulldelimiter"}
WRAPPER_CLASSES = {
    "katex", "katex-html", "base", "vlist-r", "vlist", "vlist-t", "vlist-t2",
    "sizing", "mtight", "textstyle", "displaystyle", "scriptstyle", "scriptscriptstyle",
}
UNSUPPORTED_SEMANTIC = {"mtable", "accent", "op-limits", "munder", "mover"}


@dataclass(frozen=True)
class ParseResult:
    latex: str | None
    success: bool
    unknown_nodes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostic_text: str = ""


@dataclass(frozen=True)
class BatchResult:
    records: tuple[Any, ...]
    failures: tuple[dict[str, Any], ...]
    pending_validation: tuple[dict[str, str], ...]
    stats: dict[str, int]
    validation_html: str
    validation_error: str = ""


class FormulaCache:
    """Cache parse work only; browser validation is deliberately not implied."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("schema_version") == SCHEMA_VERSION:
                    self.entries = dict(payload.get("entries", {}))
            except (OSError, ValueError, TypeError):
                self.entries = {}

    @staticmethod
    def key(dom_hash: str, target: str) -> str:
        return f"{dom_hash}|{PARSER_VERSION}|{target}"

    def get(self, dom_hash: str, target: str) -> ParseResult | None:
        item = self.entries.get(self.key(dom_hash, target))
        if not item:
            return None
        parsed = item.get("parse_result", {})
        return ParseResult(
            parsed.get("latex"), bool(parsed.get("success")),
            tuple(parsed.get("unknown_nodes", ())), tuple(parsed.get("warnings", ())),
            str(parsed.get("diagnostic_text", "")),
        )

    def put(self, dom_hash: str, target: str, result: ParseResult) -> None:
        self.entries[self.key(dom_hash, target)] = {
            "parse_result": asdict(result),
            "validation_status": "not_validated",
        }

    def save(self) -> None:
        write_json(
            self.path,
            {
                "schema_version": SCHEMA_VERSION,
                "parser_version": PARSER_VERSION,
                "entries": self.entries,
            },
        )


def _classes(node: Tag) -> set[str]:
    return set(node.get("class", ()))


def _top_value(node: Tag) -> float:
    match = re.search(r"top:\s*(-?[0-9.]+)em", str(node.attrs.get("style", "")))
    return float(match.group(1)) if match else 0.0


def _content_spans(node: Tag) -> list[Tag]:
    return [
        child for child in node.find_all("span", recursive=False)
        if not (_classes(child) & IGNORE_CLASSES) and "top:" in str(child.attrs.get("style", ""))
    ]


def _map_text(text: str) -> str:
    text = " ".join(text.split())
    if text in OPERATORS:
        return OPERATORS[text]
    return "".join(SYMBOLS.get(char, char) for char in text)


def _join(parts: Iterable[str]) -> str:
    result = ""
    for part in (item for item in parts if item):
        if result and re.search(r"\\[A-Za-z]+$", result) and re.match(r"[A-Za-z\\]", part):
            result += " "
        result += part
    return result


def _unknown(node: Tag, reason: str) -> ParseResult:
    return ParseResult(
        None,
        False,
        (f"{node.name}.{reason}",),
        diagnostic_text=node.get_text(" ", strip=True),
    )


def _merge(results: Sequence[ParseResult]) -> ParseResult:
    unknown = tuple(item for result in results for item in result.unknown_nodes)
    warnings = tuple(item for result in results for item in result.warnings)
    if any(not result.success for result in results):
        diagnostic = " ".join(
            result.diagnostic_text for result in results if result.diagnostic_text
        )
        return ParseResult(None, False, unknown, warnings, diagnostic)
    return ParseResult(_join(result.latex or "" for result in results), True, unknown, warnings)


def _parse_children(node: Tag, *, skip: set[int] | None = None) -> ParseResult:
    skip = skip or set()
    return _merge([_parse(child) for child in node.children if id(child) not in skip])


def _parse_vlist(node: Tag, kind: str) -> ParseResult:
    vlist = node.select_one(".vlist")
    if not isinstance(vlist, Tag):
        return _unknown(node, f"{kind}-missing-vlist")
    spans = sorted(_content_spans(vlist), key=_top_value)
    if kind == "fraction":
        if len(spans) < 2:
            return _unknown(node, "fraction-arity")
        numerator = _parse_children(spans[0])
        denominator = _parse_children(spans[-1])
        merged = _merge((numerator, denominator))
        if not merged.success:
            return merged
        return ParseResult(f"\\frac{{{numerator.latex}}}{{{denominator.latex}}}", True)
    if len(spans) not in {1, 2}:
        return _unknown(node, "supsub-arity")
    parsed = [_parse_children(span) for span in spans]
    merged = _merge(parsed)
    if not merged.success:
        return merged
    if len(parsed) == 1:
        is_sub = bool(node.select_one(".vlist-t2"))
        return ParseResult(
            f"_{{{parsed[0].latex}}}" if is_sub else f"^{{{parsed[0].latex}}}",
            True,
        )
    return ParseResult(f"^{{{parsed[0].latex}}}_{{{parsed[1].latex}}}", True)


def _parse(node: Any) -> ParseResult:
    if isinstance(node, NavigableString):
        return ParseResult(_map_text(str(node)), True)
    if not isinstance(node, Tag):
        return ParseResult("", True)
    classes = _classes(node)
    if classes & IGNORE_CLASSES or node.name in {"svg", "path"}:
        return ParseResult("", True)
    if "katex-mathml" in classes:
        return ParseResult("", True)
    if classes & UNSUPPORTED_SEMANTIC:
        return _unknown(node, "unsupported-semantic")
    if "mfrac" in classes:
        return _parse_vlist(node, "fraction")
    if "msupsub" in classes:
        return _parse_vlist(node, "supsub")
    if "msqrt" in classes:
        content = [
            child for child in node.children
            if not (
                isinstance(child, Tag)
                and ("sqrt" in _classes(child) or child.name == "svg")
            )
        ]
        parsed = _merge([_parse(child) for child in content])
        return ParseResult(f"\\sqrt{{{parsed.latex}}}", True) if parsed.success else parsed
    if "overline" in classes:
        parsed = _parse_children(node)
        return ParseResult(f"\\overline{{{parsed.latex}}}", True) if parsed.success else parsed
    if "mathbb" in classes or "mathcal" in classes or "text" in classes:
        command = "mathbb" if "mathbb" in classes else "mathcal" if "mathcal" in classes else "text"
        parsed = _parse_children(node)
        return ParseResult(f"\\{command}{{{parsed.latex}}}", True) if parsed.success else parsed
    if "mspace" in classes:
        return ParseResult(" ", True)
    if classes & TOKEN_CLASSES:
        return _parse_children(node)
    if classes & WRAPPER_CLASSES or not classes or all(
        name.startswith(("size", "reset-size")) for name in classes
    ):
        return _parse_children(node)
    semantic = [name for name in classes if name.startswith("m") or name.startswith("vlist")]
    if semantic:
        return _unknown(node, "+".join(sorted(semantic)))
    return _parse_children(node)


def parse_katex(node: Tag) -> ParseResult:
    target = node.select_one(".katex-html")
    target = target if isinstance(target, Tag) else node
    result = _parse_children(target)
    if not result.success or not (result.latex or "").strip():
        return ParseResult(
            None,
            False,
            result.unknown_nodes or ("empty-result",),
            result.warnings,
            node.get_text(" ", strip=True),
        )
    return ParseResult((result.latex or "").strip(), True, result.unknown_nodes, result.warnings)


def validation_document(items: Sequence[dict[str, str]]) -> str:
    rows = "\n".join(
        '<div class="formula" '
        f'data-source-id="{escape(item["source_id"])}" '
        f'data-dom-hash="{escape(item["dom_hash"])}" '
        f'data-latex="{escape(item["latex"], quote=True)}"></div>'
        for item in items
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Formula batch validation</title>
{rows}
<script>
window.__FORMULA_VALIDATION__ = {{
  schema_version: {json.dumps(VALIDATION_SCHEMA_VERSION)},
  parser_version: {json.dumps(PARSER_VERSION)},
  validator_version: {json.dumps(VALIDATOR_VERSION)},
  completed: false,
  runtime_loaded: false,
  katex_version: "",
  total: 0,
  passed: 0,
  failures: [],
  items: []
}};
window.runFormulaValidation = function () {{
  if (!window.katex || typeof window.katex.render !== 'function') {{
    throw new Error('KaTeX runtime is missing');
  }}
  const nodes = [...document.querySelectorAll('.formula')];
  const result = window.__FORMULA_VALIDATION__;
  result.runtime_loaded = true;
  result.katex_version = String(window.katex.version || 'unknown');
  result.total = nodes.length;
  result.failures = [];
  result.items = [];
  for (const node of nodes) {{
    const item = {{
      source_id: node.dataset.sourceId,
      dom_hash: node.dataset.domHash,
      latex: node.dataset.latex
    }};
    try {{
      window.katex.render(item.latex, node, {{throwOnError: true}});
      result.items.push(item);
    }} catch (error) {{
      result.failures.push({{...item, error: String(error)}});
    }}
  }}
  result.passed = result.total - result.failures.length;
  result.completed = true;
  return result;
}};
</script>
"""


def _load_validation_report(
    path: Path | None,
    expected: Sequence[dict[str, str]],
) -> tuple[set[str], str]:
    if not expected:
        return set(), ""
    if path is None:
        return set(), "batch KaTeX validation report is required"
    if not path.exists():
        return set(), f"validation report does not exist: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as error:
        return set(), f"invalid validation report: {error}"

    if payload.get("schema_version") != VALIDATION_SCHEMA_VERSION:
        return set(), "validation report schema_version mismatch"
    if payload.get("parser_version") != PARSER_VERSION:
        return set(), "validation report parser_version mismatch"
    if payload.get("validator_version") != VALIDATOR_VERSION:
        return set(), "validation report validator_version mismatch"
    if not payload.get("runtime_loaded") or not payload.get("completed"):
        return set(), "validation report did not complete with a loaded KaTeX runtime"
    if not str(payload.get("katex_version", "")).strip():
        return set(), "validation report is missing katex_version"
    if payload.get("failures"):
        return set(), f"validation report contains {len(payload['failures'])} failures"

    expected_by_id = {item["source_id"]: item for item in expected}
    actual_items = payload.get("items", [])
    actual_by_id = {
        str(item.get("source_id", "")): item
        for item in actual_items
        if isinstance(item, dict)
    }
    if set(actual_by_id) != set(expected_by_id):
        return set(), "validation report source IDs do not match the pending batch"
    if int(payload.get("total", -1)) != len(expected) or int(payload.get("passed", -1)) != len(expected):
        return set(), "validation report counts do not match the pending batch"

    for source_id, expected_item in expected_by_id.items():
        actual = actual_by_id[source_id]
        if actual.get("dom_hash") != expected_item["dom_hash"]:
            return set(), f"validation report dom_hash mismatch for {source_id}"
        if actual.get("latex") != expected_item["latex"]:
            return set(), f"validation report LaTeX mismatch for {source_id}"

    return {item["dom_hash"] for item in expected}, ""


def resolve_formulas(
    compact_html: str,
    records: Sequence[Any],
    *,
    cache_path: Path,
    validation_path: Path,
    results_path: Path,
    validation_report_path: Path | None = None,
    target_platform: str = "github",
) -> BatchResult:
    root = root_from_html(compact_html)
    nodes = preflight._top_level_formula_nodes(root)
    if len(nodes) != len(records):
        raise ValueError("formula records do not match compact DOM")

    cache = FormulaCache(cache_path)
    first_by_hash: dict[str, Tag] = {}
    for node, record in zip(nodes, records, strict=True):
        first_by_hash.setdefault(record.dom_hash, node)

    resolved_by_hash: dict[str, ParseResult] = {}
    cache_hits = 0
    parsed_unique = 0
    for record in records:
        if record.dom_hash in resolved_by_hash:
            continue
        cached = cache.get(record.dom_hash, target_platform)
        if cached is not None:
            resolved_by_hash[record.dom_hash] = cached
            cache_hits += 1
            continue
        if record.original_latex.strip():
            parsed = ParseResult(record.original_latex.strip(), True)
        elif record.source_kind == "katex-html-only":
            parsed = parse_katex(first_by_hash[record.dom_hash])
            parsed_unique += 1
        else:
            parsed = ParseResult(None, False, (f"unsupported-source:{record.source_kind}",))
        cache.put(record.dom_hash, target_platform, parsed)
        resolved_by_hash[record.dom_hash] = parsed
    cache.save()

    validation: list[dict[str, str]] = []
    for record in records:
        parsed = resolved_by_hash[record.dom_hash]
        if (
            record.source_kind == "katex-html-only"
            and parsed.success
            and parsed.latex
        ):
            validation.append(
                {
                    "source_id": record.source_id,
                    "dom_hash": record.dom_hash,
                    "latex": parsed.latex,
                }
            )

    html = validation_document(validation)
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(html, encoding="utf-8")
    validated_hashes, validation_error = _load_validation_report(
        validation_report_path,
        validation,
    )

    updated: list[Any] = []
    failures: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    for record in records:
        parsed = resolved_by_hash[record.dom_hash]
        if not parsed.success or not parsed.latex:
            updated.append(record)
            failures.append(
                {
                    "source_id": record.source_id,
                    "dom_hash": record.dom_hash,
                    "source_kind": record.source_kind,
                    "unknown_nodes": list(parsed.unknown_nodes),
                    "warnings": list(parsed.warnings),
                    "diagnostic_text": parsed.diagnostic_text,
                }
            )
            continue

        if record.source_kind == "katex-html-only" and record.dom_hash not in validated_hashes:
            updated.append(record)
            pending.append(
                {
                    "source_id": record.source_id,
                    "dom_hash": record.dom_hash,
                    "latex": parsed.latex,
                }
            )
            continue

        updated.append(replace(record, original_latex=parsed.latex))

    stats = {
        "formula_total": len(records),
        "formula_unique": len(first_by_hash),
        "cache_hits": cache_hits,
        "parsed_unique": parsed_unique,
        "resolved": len(records) - len(failures) - len(pending),
        "failures": len(failures),
        "pending_validation": len(pending),
        "browser_batches_planned": 1 if validation else 0,
    }
    write_json(
        results_path,
        {
            "schema_version": SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "target_platform": target_platform,
            "stats": stats,
            "validation_error": validation_error,
            "failures": failures,
            "pending_validation": pending,
            "items": [
                {
                    "source_id": record.source_id,
                    "dom_hash": record.dom_hash,
                    "latex": record.original_latex,
                }
                for record in updated
            ],
        },
    )
    return BatchResult(
        tuple(updated),
        tuple(failures),
        tuple(pending),
        stats,
        html,
        validation_error,
    )
