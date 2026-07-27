"""Deterministic pixel-layer image processing for the fast conversion path.

This module owns the destructive image contract that the SKILL documents:
back up the original bytes, remove site watermarks from the corners, verify the
body content was not erased, then compress. Every step is *fail-closed*: any
decode error, any failed validation, any exception falls back to the original
image bytes. It never raises into the pipeline and never drops an image.

It depends on Pillow + numpy only. Connected-component labelling is hand-written
on numpy so we do not pull in scipy. Keep this module free of pipeline/ledger
imports so it stays independently unit-testable.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

# Load the sibling watermark module by path so this works whether we were
# imported normally (pipeline puts MODULE_DIR on sys.path) or via importlib with
# a custom name (the unit tests). The watermark module owns detection + inpaint;
# this module keeps the fail-closed contract, validation, and compression.
_WM_SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_watermark", Path(__file__).resolve().parent / "watermark.py"
)
assert _WM_SPEC is not None and _WM_SPEC.loader is not None
watermark = importlib.util.module_from_spec(_WM_SPEC)
# Register before exec so dataclass field-type resolution (which looks the
# module up in sys.modules via __module__) works under importlib loading.
sys.modules.setdefault(_WM_SPEC.name, watermark)
_WM_SPEC.loader.exec_module(watermark)

# Formats we never re-encode: vector / animated. They pass through untouched.
_PASSTHROUGH_MIMES = {"image/svg+xml", "image/gif"}

# Validation thresholds. Detection and inpaint now live in watermark.py; this
# module keeps the fail-closed contract, so it independently re-checks the
# result before shipping it.
#
# A pixel in the bbox that deviates from the local background by more than this
# is "strong content" (chart stroke, text), not a semi-transparent watermark.
_STRONG_CONTRAST_MIN = 130
# If more than this fraction of the bbox is strong content, the mark overlaps
# real content and the erase is refused.
_CONTENT_IN_BBOX_MAX_FRAC = 0.15
# After inpaint, the masked region's edge energy must drop to at most this
# fraction of the original watermark's, or the fill did not cover the mark.
_RESIDUAL_MAX_FRAC = 0.5

# Compression defaults.
_DEFAULT_MAX_WIDTH = 1600
_DEFAULT_WEBP_QUALITY = 82


@dataclass(frozen=True)
class ImageProcessMeta:
    width: int
    height: int
    dewatermarked: bool = False
    watermark_bbox: Optional[tuple[int, int, int, int]] = None
    dewatermark_method: str = "none"
    validation_passed: bool = True
    validation_reason: str = ""
    compressed: bool = False
    orig_bytes: int = 0
    final_bytes: int = 0
    format_kept_reason: str = ""
    fallback_to_original: bool = False


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    mime: str
    original_data: bytes
    original_mime: str
    meta: ImageProcessMeta


def process_image(
    data: bytes,
    mime: str,
    source_id: str,
    *,
    max_width: int = _DEFAULT_MAX_WIDTH,
    webp_quality: int = _DEFAULT_WEBP_QUALITY,
) -> ProcessedImage:
    """Back up → dewatermark → validate → compress, fail-closed throughout.

    Returns a ProcessedImage whose ``data`` is either the processed bytes or,
    on any failure, the untouched original bytes. Never raises.
    """

    mime_norm = (mime or "").lower()
    orig_bytes = len(data)

    def _fallback(
        reason: str,
        *,
        width: int = 0,
        height: int = 0,
        validation_reason: str = "",
    ) -> ProcessedImage:
        return ProcessedImage(
            data=data,
            mime=mime,
            original_data=data,
            original_mime=mime,
            meta=ImageProcessMeta(
                width=width,
                height=height,
                validation_passed=not validation_reason,
                validation_reason=validation_reason,
                orig_bytes=orig_bytes,
                final_bytes=orig_bytes,
                format_kept_reason=reason,
                fallback_to_original=True,
            ),
        )

    # Vector / animated formats: pass through untouched (not a fallback error).
    if mime_norm in _PASSTHROUGH_MIMES:
        return ProcessedImage(
            data=data,
            mime=mime,
            original_data=data,
            original_mime=mime,
            meta=ImageProcessMeta(
                width=0,
                height=0,
                orig_bytes=orig_bytes,
                final_bytes=orig_bytes,
                format_kept_reason="passthrough_format",
                fallback_to_original=False,
            ),
        )

    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception:
        return _fallback("decode_failed")

    try:
        # Detection and validation run on an RGB composite, but any alpha
        # channel must survive the whole path: dropping it turns transparent
        # pixels opaque (often black). Keep the original alpha aside and merge
        # it back before compression.
        alpha = _extract_alpha(image)
        rgb = image.convert("RGB")
        original_rgb = rgb.copy()
        width, height = rgb.size

        watermarked, wm = detect_and_remove_watermark(rgb)

        dewatermarked = False
        validation_passed = True
        validation_reason = ""
        working = original_rgb
        if wm.removed and wm.bbox is not None:
            ok, reason = validate_dewatermark(
                original_rgb, watermarked, wm.bbox, wm.mask
            )
            validation_passed = ok
            validation_reason = reason
            if ok:
                working = watermarked
                dewatermarked = True
            else:
                # A rejected destructive edit must not silently mutate the image
                # in any other way either. Return the untouched original bytes.
                return _fallback(
                    "dewatermark_validation_failed",
                    width=width,
                    height=height,
                    validation_reason=reason,
                )

        if alpha is not None:
            working = working.copy()
            working.putalpha(alpha)

        final_data, final_mime, compressed, format_note = compress_to_webp(
            working, mime, max_width=max_width, quality=webp_quality
        )

        meta = ImageProcessMeta(
            width=width,
            height=height,
            dewatermarked=dewatermarked,
            watermark_bbox=wm.bbox if dewatermarked else None,
            dewatermark_method=wm.method if dewatermarked else "none",
            validation_passed=validation_passed,
            validation_reason=validation_reason,
            compressed=compressed,
            orig_bytes=orig_bytes,
            final_bytes=len(final_data),
            format_kept_reason=format_note,
            fallback_to_original=(wm.removed and not validation_passed),
        )
        return ProcessedImage(
            data=final_data,
            mime=final_mime,
            original_data=data,
            original_mime=mime,
            meta=meta,
        )
    except Exception:
        return _fallback("processing_error")


def detect_and_remove_watermark(
    image: "Image.Image",
) -> tuple["Image.Image", "watermark.WatermarkResult"]:
    """Delegate to the generalized watermark module and adapt to PIL.

    The heavy lifting -- colour-agnostic detection, nearby-block merging, and
    cv2 inpaint fill -- lives in ``watermark.py`` so it stays independently
    testable. This wrapper converts to/from a PIL image and preserves the old
    return shape (image, result) for the fail-closed orchestration below.
    """

    arr = np.asarray(image, dtype=np.uint8)
    result = watermark.remove_corner_watermark(arr)
    if result.removed and result.image is not None:
        return Image.fromarray(result.image), result
    return image, result


def validate_dewatermark(
    original: "Image.Image",
    processed: "Image.Image",
    bbox: tuple[int, int, int, int],
    mask: Optional[np.ndarray] = None,
) -> tuple[bool, str]:
    """Confirm we only changed masked pixels and did not erase real content.

    Three checks (fail-closed: any failure means keep the original):
      1. Zero-tolerance: every pixel *outside* the inpaint mask must be
         byte-identical. The mask is tighter than the bbox -- inpaint only
         touched the watermark strokes, so the rest of the bbox must be intact
         too. (Falls back to the bbox rectangle if no mask is supplied.)
      2. Content-overlap: within the bbox but *outside the watermark mask*, the
         fraction of pixels that contrast strongly with the local background
         must stay below a threshold. The mask pixels are the mark itself (the
         icon may be highly saturated -- that is fine to erase); strong contrast
         *around* the mark means it overlaps real content (chart strokes, a
         framed box), so refuse. This replaces the old colour-locked test.
      3. Inpaint residual: after painting, the masked region must not retain
         strong high-frequency structure. Leftover edges mean the fill did not
         cover the mark; refuse rather than ship a half-erased watermark.
    """

    orig = np.asarray(original, dtype=np.uint8)
    proc = np.asarray(processed, dtype=np.uint8)
    if orig.shape != proc.shape:
        return False, "shape_mismatch"

    left, top, right, bottom = bbox

    # 1. Everything outside the touched mask must be identical.
    if mask is not None:
        outside = ~mask
    else:
        outside = np.ones(orig.shape[:2], dtype=bool)
        outside[top:bottom, left:right] = False
    if not np.array_equal(orig[outside], proc[outside]):
        return False, "pixels_changed_outside_bbox"

    # 2. Strong-contrast coverage inside the bbox but OUTSIDE the mark (measured
    #    on the ORIGINAL), relative to the local background -- no hard-coded
    #    colour. Mask pixels are the watermark itself; only content around it
    #    that stays strongly-contrasting counts as an overlap.
    region = orig[top:bottom, left:right, :].astype(np.int16)
    if region.size == 0:
        return False, "empty_bbox"
    bg = _local_bbox_background(orig, bbox)
    dev = np.abs(region - bg).max(axis=2)
    strong = dev > _STRONG_CONTRAST_MIN
    if mask is not None:
        strong = strong & ~mask[top:bottom, left:right]
    if float(strong.mean()) > _CONTENT_IN_BBOX_MAX_FRAC:
        return False, "watermark_overlaps_content"

    # 3. Inpaint residual: the painted region should be smoother than the
    #    original watermark it replaced. Compare masked-region gradient energy.
    if mask is not None and mask[top:bottom, left:right].any():
        region_mask = mask[top:bottom, left:right]
        orig_region = orig[top:bottom, left:right, :].astype(np.int16)
        proc_region = proc[top:bottom, left:right, :].astype(np.int16)
        before = _edge_energy(orig_region, region_mask)
        after = _edge_energy(proc_region, region_mask)
        if before > 0 and after > before * _RESIDUAL_MAX_FRAC:
            return False, "dewatermark_residual"

    return True, "ok"


def compress_to_webp(
    image: "Image.Image",
    mime: str,
    *,
    max_width: int = _DEFAULT_MAX_WIDTH,
    quality: int = _DEFAULT_WEBP_QUALITY,
) -> tuple[bytes, str, bool, str]:
    """Resize to max_width (never upscale) and encode webp; keep the original
    format if webp comes out larger. Returns (data, mime, compressed, note)."""

    mime_norm = (mime or "").lower()
    working = image
    resized = False
    if working.width > max_width:
        ratio = max_width / float(working.width)
        new_size = (max_width, max(1, int(round(working.height * ratio))))
        working = working.resize(new_size, Image.LANCZOS)
        resized = True

    webp_buf = BytesIO()
    working.save(webp_buf, format="WEBP", quality=quality, method=6)
    webp_data = webp_buf.getvalue()

    # Re-encode the (possibly resized) image in its original raster format to
    # compare sizes. If webp is not smaller, keep the original format. JPEG has
    # no alpha channel, so an image carrying alpha can only stay as webp.
    has_alpha = working.mode in ("RGBA", "LA") or (
        working.mode == "P" and "transparency" in working.info
    )
    orig_format = _pil_format_for_mime(mime_norm)
    if orig_format is not None and orig_format != "WEBP" and not (
        orig_format == "JPEG" and has_alpha
    ):
        try:
            orig_buf = BytesIO()
            save_kwargs = {}
            if orig_format == "JPEG":
                save_kwargs = {"quality": quality}
            working.save(orig_buf, format=orig_format, **save_kwargs)
            orig_data = orig_buf.getvalue()
        except Exception:
            orig_data = None
    else:
        orig_data = None

    if orig_data is not None and len(webp_data) >= len(orig_data):
        # webp not smaller: keep original format. compressed only if we resized.
        return orig_data, mime, resized, "webp_larger_kept_original"

    return webp_data, "image/webp", True, ""


# --- internal helpers -------------------------------------------------------


def _extract_alpha(image: "Image.Image") -> "Image.Image | None":
    """Return the image's alpha channel as an 'L' image, or None if opaque."""

    if image.mode in ("RGBA", "LA"):
        return image.getchannel("A")
    if image.mode == "P" and "transparency" in image.info:
        return image.convert("RGBA").getchannel("A")
    return None


def _local_bbox_background(arr: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Median colour of a ring strictly OUTSIDE the bbox (fallback: white).

    A padded rectangle around the bbox minus the bbox itself (four border
    strips), so watermark pixels never contaminate the estimate. Used by
    validation to measure how strongly bbox content contrasts with its
    surroundings -- the colour-agnostic replacement for the old grey test.
    """

    h, w = arr.shape[0], arr.shape[1]
    left, top, right, bottom = bbox
    pad = 3
    y0, y1 = max(0, top - pad), min(h, bottom + pad)
    x0, x1 = max(0, left - pad), min(w, right + pad)

    strips = []
    if y0 < top:
        strips.append(arr[y0:top, x0:x1, :].reshape(-1, 3))
    if bottom < y1:
        strips.append(arr[bottom:y1, x0:x1, :].reshape(-1, 3))
    if x0 < left:
        strips.append(arr[top:bottom, x0:left, :].reshape(-1, 3))
    if right < x1:
        strips.append(arr[top:bottom, right:x1, :].reshape(-1, 3))

    ring = np.concatenate(strips, axis=0) if strips else np.empty((0, 3), np.uint8)
    if ring.size == 0:
        return np.array([255, 255, 255], dtype=np.int16)
    return np.median(ring, axis=0).astype(np.int16)


def _edge_energy(region: np.ndarray, region_mask: np.ndarray) -> float:
    """Mean gradient magnitude over the masked pixels of a bbox region.

    A crisp watermark has high edge energy; a clean inpaint fill is smooth.
    Comparing before/after tells us whether the mark was actually covered.
    ``region`` is int16 HxWx3, ``region_mask`` is bool HxW.
    """

    grey = region.mean(axis=2)
    gy = np.zeros_like(grey)
    gx = np.zeros_like(grey)
    gy[1:, :] = np.abs(grey[1:, :] - grey[:-1, :])
    gx[:, 1:] = np.abs(grey[:, 1:] - grey[:, :-1])
    grad = gy + gx
    sel = grad[region_mask]
    return float(sel.mean()) if sel.size else 0.0


def _pil_format_for_mime(mime: str) -> Optional[str]:
    return {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(mime)
