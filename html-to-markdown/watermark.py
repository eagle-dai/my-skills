"""Generalized corner-watermark detection and removal (pure image in/out).

This module has one job: given an RGB image, find a site watermark sitting in
one of the four corners and paint it out. It is deliberately free of any
pipeline, ledger, mime, or backup concern so it can be imported and unit-tested
on its own. ``image_processing.py`` is the only caller today; keeping the
boundary clean means a second consumer can reuse it without dragging the
conversion contract along.

Design (see docs/superpowers/specs/2026-07-27-generalized-dewatermark-design.md
and the empirical tuning on the six real course images):

* **Colour-anchor + shape, not a hard-coded RGB.** A site watermark is a compact
  brand *icon* (a saturated, filled, roughly-square blob) followed by lettering.
  We do not hard-code the icon's colour: the anchor is any *saturated, compact,
  filled, roundish* connected component in the corner ROI. Shape does the
  discriminating -- tall chart bars (aspect < 0.5) and thin/hollow frame borders
  (low fill) are rejected, so we do not need to name the hue. This generalizes
  across colours of brand icon; it does NOT promise to catch a text-only
  watermark with no coloured anchor -- those simply fall back (keep original),
  which is the safe direction (宁漏勿误伤).
* **Grow to adjacent lettering across small gaps only.** From the icon we extend
  rightward over the logo text, stopping at the first wide gap so a neighbouring
  axis label or caption is not swept in.
* **Fill is cv2.inpaint (TELEA), not a flat colour.** Flat fill streaks on
  gradients and destroys structure under a logo; inpaint propagates surrounding
  texture. cv2 also powers connected-components (fast on large images) and HSV.
  If cv2 is unavailable we skip dewatermarking entirely (``skipped_no_cv2``)
  rather than regress to the old flat-fill behaviour.

Everything downstream (validation, backup, ledger, compression) lives in the
caller. This module returns the painted image plus the exact pixel mask it
touched so the caller can enforce a zero-tolerance "nothing else changed" check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:  # cv2 is optional; its absence degrades dewatermarking to a no-op.
    import cv2  # type: ignore
except Exception:  # pragma: no cover - exercised via the no-cv2 test path
    cv2 = None  # type: ignore


# Corner ROI where a watermark may live. Bottom-right is checked first because
# that is where site logos sit; the fractions bound how far in we ever erase.
_ROI_W_FRAC = 0.42
_ROI_H_FRAC = 0.32

# Anchor (brand icon) detection in HSV. A watermark icon is saturated and not
# dark; these thresholds are colour-agnostic (any hue qualifies).
_ANCHOR_SAT_MIN = 90              # HSV S: "coloured", not grey
_ANCHOR_VAL_MIN = 90             # HSV V: not a dark stroke
# Anchor shape filters, as fractions of the ROI area and as ratios.
_ANCHOR_AREA_MIN_FRAC = 0.0004    # smaller = noise
_ANCHOR_AREA_MAX_FRAC = 0.06      # larger = a fill/frame, not an icon
_ANCHOR_FILL_MIN = 0.5            # area / bbox-area; rejects hollow frames & lines
_ANCHOR_ASPECT_LO = 0.55          # rejects tall chart bars
_ANCHOR_ASPECT_HI = 1.7

# Logo lettering: dark, low-saturation glyphs sitting on the icon's row.
_TEXT_VAL_MAX = 175
_TEXT_SAT_MAX = 130

# Guardrail: the erased bbox must not hug the ROI's outer corner too tightly, or
# we risk painting over content that runs to the edge.
_BBOX_EDGE_MARGIN_FRAC = 0.02

# Mask dilation (iterations) so the paint covers anti-aliased fringe.
_MASK_DILATE = 2


@dataclass(frozen=True)
class WatermarkResult:
    """Outcome of the detect+erase step, before the caller's validation.

    ``mask`` is the full-image boolean array of pixels the inpaint touched
    (already dilated). The caller uses it for zero-tolerance "nothing changed
    outside the mask" validation, which is tighter than checking the bbox.
    """

    removed: bool
    image: Optional["np.ndarray"] = None            # full RGB array, dewatermarked
    bbox: Optional[tuple[int, int, int, int]] = None  # (left, top, right, bottom)
    mask: Optional["np.ndarray"] = None             # bool HxW, pixels inpainted
    method: str = "none"                            # inpaint_telea | none | skipped_no_cv2
    reason: str = ""


def remove_corner_watermark(rgb: "np.ndarray") -> WatermarkResult:
    """Find a corner watermark and inpaint it out. Pure image in/out.

    ``rgb`` is an HxWx3 uint8 array. Returns a WatermarkResult; on any
    no-detection or missing-cv2 path ``removed`` is False and ``image`` is None
    (the caller keeps the original). Never raises for image-content reasons.
    """

    arr = np.asarray(rgb, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 3:
        return WatermarkResult(removed=False, reason="not_rgb")
    height, width = arr.shape[0], arr.shape[1]
    if height < 8 or width < 8:
        return WatermarkResult(removed=False, reason="too_small")

    # Detection and inpaint both need cv2. Without it, skip -- never flat-fill.
    if cv2 is None:
        return WatermarkResult(
            removed=False, method="skipped_no_cv2", reason="cv2_unavailable"
        )

    roi_w = max(1, int(round(width * _ROI_W_FRAC)))
    roi_h = max(1, int(round(height * _ROI_H_FRAC)))

    # Bottom-right first, then the other three corners. (x0, y0) = ROI offset.
    corners = [
        (width - roi_w, height - roi_h),   # bottom-right (priority)
        (0, height - roi_h),               # bottom-left
        (width - roi_w, 0),                # top-right
        (0, 0),                            # top-left
    ]

    for x0, y0 in corners:
        roi = arr[y0:y0 + roi_h, x0:x0 + roi_w, :]
        found = _detect_in_roi(roi, roi_w, roi_h)
        if found is None:
            continue
        rl, rt, rr, rb, roi_wm_mask = found

        # Guardrail: reject a bbox that hugs the ROI's outer image corner.
        margin_x = max(1, int(round(roi_w * _BBOX_EDGE_MARGIN_FRAC)))
        margin_y = max(1, int(round(roi_h * _BBOX_EDGE_MARGIN_FRAC)))
        if _bbox_hugs_outer_corner(
            (rl, rt, rr, rb), roi_w, roi_h, x0, y0, width, height, margin_x, margin_y
        ):
            continue

        abs_bbox = (x0 + rl, y0 + rt, x0 + rr, y0 + rb)

        # Full-image inpaint mask: watermark pixels inside the bbox, dilated to
        # swallow the anti-aliased fringe. Restricting to the actual mark (not
        # the whole rectangle) keeps inpaint from smearing clean background and
        # lets validation demand identity everywhere else.
        full_mask = np.zeros((height, width), dtype=bool)
        full_mask[abs_bbox[1]:abs_bbox[3], abs_bbox[0]:abs_bbox[2]] = roi_wm_mask
        full_mask = _dilate(full_mask, _MASK_DILATE)

        bbox_h = abs_bbox[3] - abs_bbox[1]
        radius = max(2, int(round(bbox_h / 12)))
        painted = cv2.inpaint(
            np.ascontiguousarray(arr),
            full_mask.astype(np.uint8),
            radius,
            cv2.INPAINT_TELEA,
        )
        return WatermarkResult(
            removed=True,
            image=painted,
            bbox=abs_bbox,
            mask=full_mask,
            method="inpaint_telea",
        )

    return WatermarkResult(removed=False, reason="no_watermark")


# --- detection internals ----------------------------------------------------


def _detect_in_roi(
    roi: "np.ndarray", roi_w: int, roi_h: int
) -> Optional[tuple[int, int, int, int, "np.ndarray"]]:
    """Detect a watermark in one corner ROI.

    Returns (left, top, right, bottom, wm_mask) in ROI-relative coordinates,
    where ``wm_mask`` is the boolean watermark-pixel mask cropped to the bbox,
    or None if no anchor+mark is found.
    """

    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    roi_area = roi_w * roi_h

    anchor = _find_anchor(sat, val, roi_area)
    if anchor is None:
        return None
    ax0, ay0, ax1, ay1 = anchor
    icon_h = ay1 - ay0

    # Grow rightward over adjacent logo lettering, stopping at the first wide gap
    # so a neighbouring axis label / caption is not swept in.
    text = ((val < _TEXT_VAL_MAX) & (sat < _TEXT_SAT_MAX)).astype(np.uint8)
    ker = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, icon_h // 3), max(3, icon_h // 6))
    )
    text = cv2.morphologyEx(text, cv2.MORPH_CLOSE, ker, iterations=1)
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(text, 8)

    row_lo, row_hi = ay0 - icon_h * 0.4, ay1 + icon_h * 0.4
    cands: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, ww, hh, _area = stats[i]
        cy = y + hh / 2.0
        if cy < row_lo or cy > row_hi:
            continue
        if hh > icon_h * 1.8 or hh < icon_h * 0.25:
            continue
        if x < ax1 - icon_h * 0.3:          # must be at/right of the icon
            continue
        if ww > icon_h * 8 and hh < icon_h * 0.4:   # thin line remnant
            continue
        cands.append((int(x), int(y), int(x + ww), int(y + hh)))
    cands.sort()

    left, top, right, bottom = ax0, ay0, ax1, ay1
    max_gap = icon_h * 1.2
    for (l, t, r, b) in cands:
        if l - right > max_gap:             # wide gap -> not part of the logo
            break
        left = min(left, l); top = min(top, t)
        right = max(right, r); bottom = max(bottom, b)

    # The watermark-pixel mask inside the bbox = coloured icon OR dark lettering.
    region_hsv = hsv[top:bottom, left:right, :]
    rs, rv = region_hsv[:, :, 1], region_hsv[:, :, 2]
    wm_mask = ((rs > _ANCHOR_SAT_MIN) & (rv > _ANCHOR_VAL_MIN)) | (
        (rv < _TEXT_VAL_MAX) & (rs < _TEXT_SAT_MAX)
    )
    return left, top, right, bottom, wm_mask


def _find_anchor(
    sat: "np.ndarray", val: "np.ndarray", roi_area: int
) -> Optional[tuple[int, int, int, int]]:
    """Find the bottom-right-most compact, filled, roundish saturated blob.

    This is the brand icon. Shape filters (fill, aspect) reject tall chart bars
    and thin/hollow frame borders without naming a colour. Returns the anchor
    bbox (roi-relative) or None.
    """

    mask = ((sat > _ANCHOR_SAT_MIN) & (val > _ANCHOR_VAL_MIN)).astype(np.uint8)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), 1
    )
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)

    area_min = roi_area * _ANCHOR_AREA_MIN_FRAC
    area_max = roi_area * _ANCHOR_AREA_MAX_FRAC
    best = None
    best_key = None
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        if area < area_min or area > area_max:
            continue
        if ww == 0 or hh == 0:
            continue
        fill = area / float(ww * hh)
        aspect = ww / float(hh)
        if fill < _ANCHOR_FILL_MIN:
            continue
        if not (_ANCHOR_ASPECT_LO <= aspect <= _ANCHOR_ASPECT_HI):
            continue
        key = (int(y + hh), int(x + ww))   # most bottom-right
        if best_key is None or key > best_key:
            best_key = key
            best = (int(x), int(y), int(x + ww), int(y + hh))
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
    on_right = (x0 + roi_w) >= width
    on_bottom = (y0 + roi_h) >= height
    touches_x = (right >= roi_w - margin_x) if on_right else (left <= margin_x)
    touches_y = (bottom >= roi_h - margin_y) if on_bottom else (top <= margin_y)
    return touches_x and touches_y


def _dilate(mask: "np.ndarray", k: int) -> "np.ndarray":
    """Square-kernel binary dilation by ``k`` pixels, numpy-only (no scipy)."""

    if k <= 0:
        return mask
    out = mask.copy()
    for _ in range(k):
        grown = out.copy()
        grown[:-1, :] |= out[1:, :]
        grown[1:, :] |= out[:-1, :]
        grown[:, :-1] |= out[:, 1:]
        grown[:, 1:] |= out[:, :-1]
        out = grown
    return out
