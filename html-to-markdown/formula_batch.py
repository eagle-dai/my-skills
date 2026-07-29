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
VALIDATION_SCHEMA_VERSION = "1.1"
PARSER_VERSION = "katex-html-v3"
VALIDATOR_VERSION = "formula-batch-v3"

# Pinned local KaTeX runtime bundled under assets/ and copied next to each
# validation.html. Bumping the version does NOT change validation semantics
# (githubMathUnescape + throwOnError), so VALIDATOR_VERSION is left untouched.
KATEX_VERSION = "0.16.9"
KATEX_ASSET_NAME = "katex.min.js"

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
    stats: dict[str, int | bool]
    validation_html: str
    validation_error: str = ""
    validation_jobs: tuple[dict[str, Any], ...] = ()


class FormulaCache:
    """Cache parse work only; browser validation is deliberately not implied."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        self.dirty = False
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

    def put(self, dom_hash: str, target: str, result: ParseResult) -> bool:
        key = self.key(dom_hash, target)
        entry = {
            "parse_result": {
                "latex": result.latex,
                "success": result.success,
                "unknown_nodes": list(result.unknown_nodes),
                "warnings": list(result.warnings),
                "diagnostic_text": result.diagnostic_text,
            },
            "validation_status": "not_validated",
        }
        if self.entries.get(key) == entry:
            return False
        self.entries[key] = entry
        self.dirty = True
        return True

    def save(self) -> bool:
        if not self.dirty:
            return False
        write_json(
            self.path,
            {
                "schema_version": SCHEMA_VERSION,
                "parser_version": PARSER_VERSION,
                "entries": self.entries,
            },
        )
        self.dirty = False
        return True


# --- 变量↔标识符映射公式拆分（缺陷 #16） ---------------------------------
# 原网页把「数学变量 ↔ 工程标识符」写成一个公式 ``var \leftarrow \text{ident}``。
# GitHub GFM 会剥掉 ``$…$`` 内 ``\_`` 的反斜杠，``\text{observed_at}`` 里裸 ``_``
# 在 text mode 非法 → KaTeX 报 ``Expected 'EOF', got '_'``（真 KaTeX 验证证实）。
# 这类「映射」本就不是纯数学式：数学变量该留公式、标识符该是行内代码。拆成
# ``$var$ ← `ident``` 后两部分都 GitHub-safe。判定必须在验证前做（见 formula-batch.md），
# 拆出的 ``$var$`` 仍进验证。右侧 ``\text{}`` 内若含数学结构（``_{`` / ``\frac`` 等）
# 则不拆，保守避免破坏真公式（纯标识符经叶子转义只会有 ``\_``，不含 ``_{``）。
# 回归 tests/test_markdown_postprocess.py::formula split。
_TEXT_MAPPING_RE = re.compile(r"^(.+?)\s*\\leftarrow\s*\\text\{(.+?)\}$")


def split_text_mapping_formula(latex: str) -> tuple[str, str] | None:
    """``var \\leftarrow \\text{ident}`` → (var, ident) 或 None（不拆）。

    ident 里的 text-mode 转义 ``\\_`` 还原成 ``_``（行内代码不需转义）。
    右侧含数学结构记号（``_{`` / ``^{`` / ``\\frac`` 等）时返回 None。
    """
    match = _TEXT_MAPPING_RE.match(latex.strip())
    if not match:
        return None
    var, ident_raw = match.group(1).strip(), match.group(2).strip()
    if not var or not ident_raw:
        return None
    if _MATH_ONLY_IN_TEXT_RE.search(ident_raw):
        return None  # 右侧不是纯标识符，别拆
    # 链式映射 `y \leftarrow \text{a} \leftarrow \text{b}`：因行尾 $ 锚，非贪婪的
    # ident 仍会吃进中间的 `} \leftarrow \text{`。含这些定界/连接记号说明右侧不是
    # 单个纯标识符，别拆（否则 emit 出 `` `a} \leftarrow \text{b` `` 这种坏行内代码）。
    if any(tok in ident_raw for tok in ("{", "}", "\\text", "\\leftarrow", "\\left")):
        return None
    # 反引号会提前闭合 emit 出的行内代码 span（`` `a`b` ``），别拆。
    if "`" in ident_raw:
        return None
    ident = ident_raw.replace(r"\_", "_")
    if _MATH_ONLY_IN_TEXT_RE.search(var) is None and "\\text" in var:
        return None  # 左侧还有 \text，结构复杂，别拆
    return var, ident


def _write_text_if_changed(path: Path, content: str) -> bool:
    """Write UTF-8 text only when the destination bytes would change."""

    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


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


_TEXT_MODE_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "_": r"\_",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "&": r"\&",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
}
_TEXT_MODE_RE = re.compile("|".join(re.escape(c) for c in _TEXT_MODE_ESCAPES))


def _escape_text_mode(text: str) -> str:
    return _TEXT_MODE_RE.sub(lambda m: _TEXT_MODE_ESCAPES[m.group(0)], text)


# text mode 下非法的 math-only 结构记号:下标/上标结构 _{ ^{ 与 \frac \sqrt 等命令。
# 命中 = \text{} 内含未包裹的数学子式(源 \text{$...$}),重建器不自动包 $ → fail-close。
# 叶子转义后的 \_ / \textasciicircum{} 不含 _{ / ^{,不会误命中。
_MATH_ONLY_IN_TEXT_RE = re.compile(r"[_^]\{|\\(?:frac|sqrt|overline|mathbb|mathcal)\b")


def _map_text(text: str, text_mode: bool = False) -> str:
    text = " ".join(text.split())
    if text_mode:
        return _escape_text_mode(text)
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


def _parse_children(node: Tag, *, skip: set[int] | None = None, text_mode: bool = False) -> ParseResult:
    skip = skip or set()
    return _merge([_parse(child, text_mode=text_mode) for child in node.children if id(child) not in skip])


def _parse_vlist(node: Tag, kind: str) -> ParseResult:
    # vlist(分式/上下标)内部恒为 math mode:下标 _ / 上标 ^ 是结构字符。
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


def _parse(node: Any, *, text_mode: bool = False) -> ParseResult:
    if isinstance(node, NavigableString):
        return ParseResult(_map_text(str(node), text_mode), True)
    if not isinstance(node, Tag):
        return ParseResult("", True)
    classes = _classes(node)
    if classes & IGNORE_CLASSES or node.name in {"svg", "path"}:
        return ParseResult("", True)
    if "katex-mathml" in classes:
        return ParseResult("", True)
    if classes & UNSUPPORTED_SEMANTIC:
        return _unknown(node, "unsupported-semantic")
    # 结构容器(分式/上下标/根号/上划线)内部一律是 math mode,即便嵌在 \text{} 内
    # (对应 \text{$...$});其下标 _ / 上标 ^ 是结构字符,不得当字面字符转义。
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
    if "mathbb" in classes or "mathcal" in classes:
        # \mathbb / \mathcal 是 math-mode 命令,内部下标/上标合法,不进 text mode
        command = "mathbb" if "mathbb" in classes else "mathcal"
        parsed = _parse_children(node, text_mode=text_mode)
        return ParseResult(f"\\{command}{{{parsed.latex}}}", True) if parsed.success else parsed
    if "text" in classes:
        # \text{} 内为 text mode:叶子文本须转义特殊字符(_map_text 的 text_mode 分支)。
        # 内嵌数学结构(msupsub/mfrac 等,源自 \text{$...$})的 _{ / ^{ / \frac 是
        # math-only 记号,须 $...$ 包裹才在 text mode 合法;当前重建器不自动包裹,
        # 故 fail-close 交 strict,绝不静默产出非法 \text{t_{n}}(缺陷 18 反向)。
        parsed = _parse_children(node, text_mode=True)
        if not parsed.success:
            return parsed
        if _MATH_ONLY_IN_TEXT_RE.search(parsed.latex or ""):
            return _unknown(node, "math-structure-in-text-mode")
        return ParseResult(f"\\text{{{parsed.latex}}}", True)
    if "mspace" in classes:
        return ParseResult(" ", True)
    if classes & TOKEN_CLASSES:
        return _parse_children(node, text_mode=text_mode)
    if classes & WRAPPER_CLASSES or not classes or all(
        name.startswith(("size", "reset-size")) for name in classes
    ):
        return _parse_children(node, text_mode=text_mode)
    semantic = [name for name in classes if name.startswith("m") or name.startswith("vlist")]
    if semantic:
        return _unknown(node, "+".join(sorted(semantic)))
    return _parse_children(node, text_mode=text_mode)


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


def validation_document(items: Sequence[dict[str, Any]]) -> str:
    rows = "\n".join(
        '<div class="formula" '
        f'data-source-id="{escape(item["source_id"])}" '
        f'data-dom-hash="{escape(item["dom_hash"])}" '
        f'data-source-count="{len(item.get("source_ids", ())) or 1}" '
        f'data-latex="{escape(item["latex"], quote=True)}"></div>'
        for item in items
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Formula batch validation</title>
<!-- Local pinned KaTeX runtime ({KATEX_VERSION}); copied next to this file by
     the pipeline so validation is fully offline. Only katex.min.js is needed
     (parse-time throwOnError is font-independent), so no CSS/fonts. -->
<script src="{KATEX_ASSET_NAME}"></script>
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
// GitHub GFM strips a backslash before any CommonMark-escapable ASCII
// punctuation inside $...$, then hands the result to KaTeX. Validation must
// mimic this, else \\text{{a\\_b}} passes local KaTeX but errors on GitHub
// ('_' allowed only in math mode). The class covers all ASCII punctuation
// (33-47/58-64/91-96/123-126); a command backslash (backslash + letter, e.g.
// leftarrow, frac) does not match and is preserved.
window.githubMathUnescape = function (s) {{
  return s.replace(/\\\\([!-\\/:-@\\[-`{{-~}}])/g, '$1');
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
    // 用 GitHub 实际会喂给 KaTeX 的形式(反转义后)验证,而非源 md 里的转义形式。
    const target = window.githubMathUnescape(item.latex);
    try {{
      window.katex.render(target, node, {{throwOnError: true}});
      result.items.push(item);
    }} catch (error) {{
      result.failures.push({{...item, error: String(error)}});
    }}
  }}
  result.passed = result.total - result.failures.length;
  result.completed = true;
  return result;
}};
// Auto-run once the DOM + local KaTeX <script> have parsed, so the main agent
// only has to open this page and read window.__FORMULA_VALIDATION__ — no manual
// runtime injection or copy-paste. If KaTeX failed to load, stay completed:false
// (fail closed) so a stale/partial report is never mistaken for success; the
// agent can then inject a runtime and call runFormulaValidation() by hand.
window.__runFormulaValidationSafe__ = function () {{
  try {{
    window.runFormulaValidation();
  }} catch (error) {{
    window.__FORMULA_VALIDATION__.completed = false;
    window.__FORMULA_VALIDATION__.load_error = String(error);
  }}
}};
// If the page is opened after DOMContentLoaded already fired (common when a
// driver navigates and waits for 'load'), the event never comes again — run
// immediately in that case, else wait for the event.
if (document.readyState === 'loading') {{
  window.addEventListener('DOMContentLoaded', window.__runFormulaValidationSafe__);
}} else {{
  window.__runFormulaValidationSafe__();
}}
</script>
"""


def copy_katex_runtime(dest_dir: Path) -> bool:
    """Copy the bundled KaTeX runtime next to a validation.html.

    Returns True if the asset now exists in ``dest_dir``. Copies only when the
    destination is missing or differs, so repeated runs are cheap and
    deterministic. Missing source asset fails closed (returns False) rather
    than raising; validation.html then falls back to manual runtime injection.
    """
    src = MODULE_DIR / "assets" / KATEX_ASSET_NAME
    if not src.is_file():
        return False
    dest = dest_dir / KATEX_ASSET_NAME
    # A non-file at dest (e.g. a stray directory) can't be a valid runtime and
    # read_bytes() would raise; fail closed rather than crash.
    if dest.exists() and not dest.is_file():
        return False
    src_bytes = src.read_bytes()
    if not dest.exists() or dest.read_bytes() != src_bytes:
        # Atomic replace: write to a temp sibling then rename, so an interrupted
        # copy never leaves a truncated katex.min.js that a later validation
        # would load and fail on with an opaque JS parse error.
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(src_bytes)
        tmp.replace(dest)
    return True


def _load_validation_report(
    path: Path | None,
    expected: Sequence[dict[str, Any]],
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
    if not isinstance(actual_items, list) or not all(
        isinstance(item, dict) for item in actual_items
    ):
        return set(), "validation report items must be a list of objects"
    actual_by_id = {
        str(item.get("source_id", "")): item
        for item in actual_items
    }
    if len(actual_by_id) != len(actual_items):
        return set(), "validation report contains duplicate source IDs"
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


def _validation_jobs(
    records: Sequence[Any],
    resolved_by_hash: dict[str, ParseResult],
) -> list[dict[str, Any]]:
    """Create one browser-validation job per unique reconstructed DOM hash.

    The first source ID is the stable representative used by the validation HTML
    and report. ``source_ids`` preserves the complete source-to-result mapping so
    a successful hash-level validation can unlock every duplicate source node.
    """

    jobs_by_hash: dict[str, dict[str, Any]] = {}
    for record in records:
        parsed = resolved_by_hash[record.dom_hash]
        if not (
            record.source_kind == "katex-html-only"
            and parsed.success
            and parsed.latex
        ):
            continue
        job = jobs_by_hash.setdefault(
            record.dom_hash,
            {
                "source_id": record.source_id,
                "source_ids": [],
                "dom_hash": record.dom_hash,
                "latex": parsed.latex,
            },
        )
        job["source_ids"].append(record.source_id)
    return list(jobs_by_hash.values())


def resolve_formulas(
    compact_html: str,
    records: Sequence[Any],
    *,
    cache_path: Path,
    validation_path: Path,
    results_path: Path,
    validation_report_path: Path | None = None,
    target_platform: str = "github",
    root: Tag | None = None,
) -> BatchResult:
    root = root if root is not None else root_from_html(compact_html)
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
    cache_written = cache.save()

    # 变量↔标识符映射公式拆分（缺陷 #16）：在验证 job 生成前把 ``var \leftarrow
    # \text{ident}`` 的 latex 改成 ``var``（进验证会过），拆出的标识符记进
    # split_by_hash 供 emit 补行内代码。缓存已在上面按原始 parsed 落盘，拆分不污染
    # 解析缓存。拆分后 latex 为空的极端情况不会发生（var 非空经 split 保证）。
    split_by_hash: dict[str, str] = {}
    for dom_hash, parsed in list(resolved_by_hash.items()):
        if not (parsed.success and parsed.latex):
            continue
        split = split_text_mapping_formula(parsed.latex)
        if split is None:
            continue
        var, ident = split
        split_by_hash[dom_hash] = ident
        resolved_by_hash[dom_hash] = replace(parsed, latex=var)

    validation_jobs = _validation_jobs(records, resolved_by_hash)
    html = validation_document(validation_jobs)
    validation_html_written = _write_text_if_changed(validation_path, html)
    if validation_jobs:
        copy_katex_runtime(validation_path.parent)
    validated_hashes, validation_error = _load_validation_report(
        validation_report_path,
        validation_jobs,
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

        trailing = split_by_hash.get(record.dom_hash, "")
        if trailing:
            updated.append(
                replace(record, original_latex=parsed.latex, trailing_code=trailing)
            )
        else:
            updated.append(replace(record, original_latex=parsed.latex))

    stats = {
        "formula_total": len(records),
        "formula_unique": len(first_by_hash),
        "cache_hits": cache_hits,
        "cache_written": cache_written,
        "parsed_unique": parsed_unique,
        "resolved": len(records) - len(failures) - len(pending),
        "failures": len(failures),
        "pending_validation": len(pending),
        "validation_jobs": len(validation_jobs),
        "validation_html_written": validation_html_written,
        "validation_nodes_saved": sum(
            len(job["source_ids"]) for job in validation_jobs
        ) - len(validation_jobs),
        "browser_batches_planned": 1 if validation_jobs else 0,
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
            "validation_jobs": validation_jobs,
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
        records=tuple(updated),
        failures=tuple(failures),
        pending_validation=tuple(pending),
        stats=stats,
        validation_html=html,
        validation_error=validation_error,
        validation_jobs=tuple(validation_jobs),
    )
