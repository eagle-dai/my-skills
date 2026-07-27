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

from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import numpy as np
from PIL import Image

# Formats we never re-encode: vector / animated. They pass through untouched.
_PASSTHROUGH_MIMES = {"image/svg+xml", "image/gif"}

# Default watermark feature colour: semi-transparent grey overlays flatten to a
# mid grey with low saturation once composited on a light page. Not a site name.
_WATERMARK_GREY = 128
_WATERMARK_GREY_TOL = 34          # |channel - 128| <= tol on all of R,G,B
_WATERMARK_SAT_MAX = 28           # max(R,G,B) - min(R,G,B) <= this (low saturation)

# Corner ROI where a watermark may live. Bottom-right is checked first because
# that is where site logos sit; the fractions bound how far in we ever erase.
_ROI_W_FRAC = 0.35
_ROI_H_FRAC = 0.22

# Connected-component size filters, as a fraction of the ROI pixel area.
_CC_MIN_FRAC = 0.0008             # smaller than this = noise, ignore
_CC_MAX_FRAC = 0.60               # larger than this = likely body content, ignore

# Guardrail: the erased bbox must not hug the ROI's outer corner too tightly, or
# we risk painting over content that runs to the edge.
_BBOX_EDGE_MARGIN_FRAC = 0.02

# Validation: fraction of the erased bbox (in the ORIGINAL image) that is
# "content colour" (not near-white, not the watermark grey). Above this we judge
# the watermark to overlap real content and refuse the erase.
_CONTENT_IN_BBOX_MAX_FRAC = 0.15
_NEAR_WHITE_MIN = 244             # pixels this bright count as background

# Compression defaults.
_DEFAULT_MAX_WIDTH = 1600
_DEFAULT_WEBP_QUALITY = 82


@dataclass(frozen=True)
class WatermarkResult:
    """Outcome of the detect+erase step, before validation."""

    removed: bool
    bbox: Optional[tuple[int, int, int, int]] = None  # (left, top, right, bottom)
    method: str = "none"                               # fill_background | none | ...
    reason: str = ""


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

    def _fallback(reason: str, *, width: int = 0, height: int = 0) -> ProcessedImage:
        return ProcessedImage(
            data=data,
            mime=mime,
            original_data=data,
            original_mime=mime,
            meta=ImageProcessMeta(
                width=width,
                height=height,
                validation_passed=True,
                validation_reason="",
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
        rgb = image.convert("RGB")
        original_rgb = rgb.copy()
        width, height = rgb.size

        watermarked, wm = detect_and_remove_watermark(rgb)

        dewatermarked = False
        validation_passed = True
        validation_reason = ""
        working = original_rgb
        if wm.removed and wm.bbox is not None:
            ok, reason = validate_dewatermark(original_rgb, watermarked, wm.bbox)
            validation_passed = ok
            validation_reason = reason
            if ok:
                working = watermarked
                dewatermarked = True
            # else: keep original_rgb, fall through with fallback flag set below.

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


def detect_and_remove_watermark(image: "Image.Image") -> tuple["Image.Image", WatermarkResult]:
    """Detect a corner watermark by feature colour and paint it out.

    Only the corner ROIs are searched (bottom-right first). The feature mask is
    connected-component labelled; only the bottom-right-most qualifying block is
    erased, and only if its bbox does not hug the outer corner. The erased region
    is filled with the dominant background colour just outside the bbox.
    """

    arr = np.asarray(image, dtype=np.uint8)
    height, width = arr.shape[0], arr.shape[1]
    if height < 8 or width < 8:
        return image, WatermarkResult(removed=False, reason="too_small")

    roi_w = max(1, int(round(width * _ROI_W_FRAC)))
    roi_h = max(1, int(round(height * _ROI_H_FRAC)))

    # Bottom-right corner first, then the other three. Each entry is the ROI's
    # absolute (x0, y0) offset in the full image plus a slice.
    corners = [
        (width - roi_w, height - roi_h),   # bottom-right (priority)
        (0, height - roi_h),               # bottom-left
        (width - roi_w, 0),                # top-right
        (0, 0),                            # top-left
    ]

    for x0, y0 in corners:
        roi = arr[y0:y0 + roi_h, x0:x0 + roi_w, :]
        mask = _feature_color_mask(roi)
        if not mask.any():
            continue

        bbox = _bottom_right_component_bbox(mask, roi_h, roi_w)
        if bbox is None:
            continue

        # Guardrail: reject a bbox that hugs the ROI's outer corner (content that
        # runs to the image edge). The "outer" corner depends on which corner ROI.
        margin_x = max(1, int(round(roi_w * _BBOX_EDGE_MARGIN_FRAC)))
        margin_y = max(1, int(round(roi_h * _BBOX_EDGE_MARGIN_FRAC)))
        rl, rt, rr, rb = bbox  # roi-relative
        if _bbox_hugs_outer_corner(
            (rl, rt, rr, rb), roi_w, roi_h, x0, y0, width, height, margin_x, margin_y
        ):
            continue

        # Absolute bbox in the full image.
        abs_bbox = (x0 + rl, y0 + rt, x0 + rr, y0 + rb)
        out = arr.copy()
        fill = _background_color(arr, abs_bbox)
        out[abs_bbox[1]:abs_bbox[3], abs_bbox[0]:abs_bbox[2], :] = fill
        return Image.fromarray(out), WatermarkResult(
            removed=True, bbox=abs_bbox, method="fill_background"
        )

    return image, WatermarkResult(removed=False, reason="no_feature_color")


def validate_dewatermark(
    original: "Image.Image", processed: "Image.Image", bbox: tuple[int, int, int, int]
) -> tuple[bool, str]:
    """Confirm we only changed pixels inside ``bbox`` and did not erase content.

    Two checks:
      1. Zero-tolerance: every pixel *outside* bbox must be byte-identical.
      2. In the original, the fraction of ``bbox`` that is content colour
         (neither near-white nor watermark grey) must be below a threshold; a
         watermark overlapping real content is refused.
    """

    orig = np.asarray(original, dtype=np.uint8)
    proc = np.asarray(processed, dtype=np.uint8)
    if orig.shape != proc.shape:
        return False, "shape_mismatch"

    left, top, right, bottom = bbox

    # 1. Outside-bbox pixels must be identical. Build a boolean mask of the bbox.
    outside = np.ones(orig.shape[:2], dtype=bool)
    outside[top:bottom, left:right] = False
    if not np.array_equal(orig[outside], proc[outside]):
        return False, "pixels_changed_outside_bbox"

    # 2. Content coverage inside the bbox (measured on the ORIGINAL).
    region = orig[top:bottom, left:right, :]
    if region.size == 0:
        return False, "empty_bbox"
    near_white = np.all(region >= _NEAR_WHITE_MIN, axis=2)
    wm_grey = _feature_color_mask(region)
    content = ~(near_white | wm_grey)
    content_frac = float(content.mean())
    if content_frac > _CONTENT_IN_BBOX_MAX_FRAC:
        return False, "watermark_overlaps_content"

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
    # compare sizes. If webp is not smaller, keep the original format.
    orig_format = _pil_format_for_mime(mime_norm)
    if orig_format is not None and orig_format != "WEBP":
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


def _feature_color_mask(arr: np.ndarray) -> np.ndarray:
    """Boolean mask of pixels near the watermark grey with low saturation."""

    a = arr.astype(np.int16)
    near_grey = np.all(np.abs(a - _WATERMARK_GREY) <= _WATERMARK_GREY_TOL, axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    low_sat = sat <= _WATERMARK_SAT_MAX
    return near_grey & low_sat


def _label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connectivity connected-component labelling on a boolean mask.

    Iterative flood fill (BFS) on numpy — no scipy. Returns (labels, count)
    where labels are 1..count and 0 is background.
    """

    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    # Use a plain Python stack; ROIs are small (corner crops).
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or labels[sy, sx] != 0:
                continue
            current += 1
            stack = [(sy, sx)]
            labels[sy, sx] = current
            while stack:
                y, x = stack.pop()
                if y > 0 and mask[y - 1, x] and labels[y - 1, x] == 0:
                    labels[y - 1, x] = current
                    stack.append((y - 1, x))
                if y + 1 < h and mask[y + 1, x] and labels[y + 1, x] == 0:
                    labels[y + 1, x] = current
                    stack.append((y + 1, x))
                if x > 0 and mask[y, x - 1] and labels[y, x - 1] == 0:
                    labels[y, x - 1] = current
                    stack.append((y, x - 1))
                if x + 1 < w and mask[y, x + 1] and labels[y, x + 1] == 0:
                    labels[y, x + 1] = current
                    stack.append((y, x + 1))
    return labels, current


def _bottom_right_component_bbox(
    mask: np.ndarray, roi_h: int, roi_w: int
) -> Optional[tuple[int, int, int, int]]:
    """Return the roi-relative bbox of the bottom-right-most qualifying
    connected component, or None. Filters tiny (noise) and huge (content) blocks.
    """

    labels, count = _label_components(mask)
    if count == 0:
        return None

    roi_area = roi_h * roi_w
    min_area = max(1.0, roi_area * _CC_MIN_FRAC)
    max_area = roi_area * _CC_MAX_FRAC

    best = None
    best_key = None  # (bottom, right) — larger is more bottom-right
    for label in range(1, count + 1):
        ys, xs = np.where(labels == label)
        area = xs.size
        if area < min_area or area > max_area:
            continue
        left, right = int(xs.min()), int(xs.max()) + 1
        top, bottom = int(ys.min()), int(ys.max()) + 1
        key = (bottom, right)
        if best_key is None or key > best_key:
            best_key = key
            best = (left, top, right, bottom)
    return best


def _bbox_hugs_outer_corner(
    bbox: tuple[int, int, int, int],
    roi_w: int,
    roi_h: int,
    x0: int,
    y0: int,
    width: int,
    height: int,
    margin_x: int,
    margin_y: int,
) -> bool:
    """True if the (roi-relative) bbox touches the ROI's outer image corner
    within the margin. The outer corner is the one nearest the image corner."""

    left, top, right, bottom = bbox
    # Which image corner is this ROI anchored to?
    on_right = (x0 + roi_w) >= width
    on_bottom = (y0 + roi_h) >= height

    touches_x = (right >= roi_w - margin_x) if on_right else (left <= margin_x)
    touches_y = (bottom >= roi_h - margin_y) if on_bottom else (top <= margin_y)
    return touches_x and touches_y


def _background_color(arr: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Dominant colour of a thin ring just outside the bbox (fallback: white)."""

    h, w = arr.shape[0], arr.shape[1]
    left, top, right, bottom = bbox
    pad = 3
    y0, y1 = max(0, top - pad), min(h, bottom + pad)
    x0, x1 = max(0, left - pad), min(w, right + pad)
    ring = arr[y0:y1, x0:x1, :].reshape(-1, 3)
    if ring.size == 0:
        return np.array([255, 255, 255], dtype=np.uint8)
    # Median is robust to the watermark pixels bleeding into the padded window.
    return np.median(ring, axis=0).astype(np.uint8)


def _pil_format_for_mime(mime: str) -> Optional[str]:
    return {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(mime)
