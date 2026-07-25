"""Shared deterministic helpers for the HTML fast-path pipeline."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any
import unicodedata
from urllib.parse import unquote_to_bytes
import zipfile

from bs4 import BeautifulSoup, Tag

MODULE_DIR = Path(__file__).resolve().parent


def load_sibling(module_name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, MODULE_DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = load_sibling("html_to_markdown_preflight", "preflight.py")
contracts = load_sibling("html_to_markdown_contracts", "contracts.py")
markdown_fences = load_sibling("html_to_markdown_fences", "markdown_fences.py")
image_disposition = load_sibling(
    "html_to_markdown_image_disposition", "image_disposition.py"
)


def root_from_html(html: str) -> Tag:
    soup = BeautifulSoup(html, "lxml")
    root = soup.body.find() if soup.body else soup.find()
    if not isinstance(root, Tag):
        raise ValueError("compact HTML has no root element")
    return root


def canonical_heading_count(root: Tag) -> int:
    identities: set[int] = set()
    for node in root.select("[data-slate-type^=heading], h1, h2, h3, h4, h5, h6"):
        canonical = node
        if not re.fullmatch(r"h[1-6]", node.name or ""):
            native = node.find(re.compile(r"^h[1-6]$"))
            if isinstance(native, Tag):
                canonical = native
        identities.add(id(canonical))
    return len(identities)


def canonicalize_manifest_counts(root: Tag, manifest: dict[str, Any]) -> None:
    for kind, field in {
        "table": "tables",
        "list": "lists",
        "list_item": "list_items",
        "codeblock": "codeblocks",
    }.items():
        candidates = contracts.discover_semantic_candidates(root, kind=kind)
        manifest["counts"][field] = len(contracts.canonicalize_candidates(candidates))
    manifest["counts"]["headings"] = canonical_heading_count(root)


def title_from_root(root: Tag, fallback: str) -> str:
    heading = root.select_one("h1, [data-slate-type=heading-one]")
    title = heading.get_text(" ", strip=True) if heading else fallback
    return re.sub(r"\s+", " ", title).strip() or fallback


def safe_package_name(value: str) -> str:
    """Return a portable package name without discarding non-ASCII text.

    Python's ``\\w`` is Unicode-aware, so Chinese and other letter/digit scripts
    remain distinct while punctuation and path separators collapse to ``-``.
    NFKC normalization also makes visually equivalent full-width forms stable.
    """

    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-._")
    return value or "article"


def safe_file_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .")
    return value or "article"


def write_json(path: Path, payload: Any) -> None:
    """Atomically replace a UTF-8 JSON file in its destination directory.

    Writing to a same-directory temporary file and committing with ``os.replace``
    prevents an interrupted cache/report update from leaving a partially written
    JSON file. Existing permissions are preserved; a new file uses mode ``0644``.
    If any step fails, the previous destination remains unchanged and the temporary
    file is removed.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        destination_mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        destination_mode = 0o644

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor_open = False
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, destination_mode)
        os.replace(temporary_path, path)
    finally:
        if descriptor_open:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def decode_data_uri(source: str) -> tuple[str, bytes]:
    match = re.fullmatch(r"data:([^,]*),(.*)", source, flags=re.DOTALL | re.IGNORECASE)
    if match is None:
        raise ValueError("invalid data URI")

    metadata = match.group(1).split(";")
    mime = metadata.pop(0) or "application/octet-stream"
    is_base64 = bool(metadata and metadata[-1].lower() == "base64")
    if is_base64:
        metadata.pop()
    if (
        not re.fullmatch(r"[^/\s;,]+/[^\s;,]+", mime)
        or any("=" not in parameter for parameter in metadata)
    ):
        raise ValueError("invalid data URI media type")

    payload = match.group(2)
    try:
        data = (
            base64.b64decode(payload, validate=True)
            if is_base64
            else unquote_to_bytes(payload)
        )
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError(f"invalid data URI payload: {error}") from error
    return mime, data


def extension_for_mime(mime: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }.get(mime.lower(), ".bin")


def max_backticks(text: str) -> int:
    return max((len(m.group(0)) for m in re.finditer(r"`+", text)), default=0)


def deterministic_zip(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(
                path.relative_to(source_dir).as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
