"""Tests for the generalized corner-watermark module.

The module is pure image in/out: it takes an RGB numpy array and returns a
WatermarkResult. Detection anchors on a compact, filled, *saturated* brand icon
(any hue) and grows over adjacent grey lettering, so the synthetic fixtures
build an icon + text mark in the bottom-right corner. The tests prove the anchor
is colour-agnostic (orange and blue icons both hit), that a gradient background
inpaints without a colour smear, that a clean image and a tall chart bar are not
mistaken for a watermark, that only masked pixels change, and that a missing cv2
degrades to a skip rather than a flat-fill regression.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw


SKILL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODULE_PATH = SKILL / "watermark.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_watermark_tests", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
wm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wm
SPEC.loader.exec_module(wm)


def _draw_mark(draw: ImageDraw.ImageDraw, x: int, y: int, icon_rgb, *, size: int = 24):
    """Draw a compact filled icon at (x, y) followed by three grey glyph blocks.

    Mimics a brand watermark: a roundish saturated icon plus adjacent lettering.
    Returns the approximate right edge of the mark.
    """

    draw.ellipse([x, y, x + size, y + size], fill=icon_rgb)          # icon anchor
    gx = x + size + max(4, size // 4)
    for _ in range(3):                                              # 3 grey glyphs
        draw.rectangle([gx, y + 4, gx + size - 6, y + size - 4], fill=(140, 140, 140))
        gx += size
    return gx


def _make(bg, mark_xy, icon_rgb, size=24, mode="RGB"):
    w, h = 480, 320
    image = Image.new(mode, (w, h), bg)
    draw = ImageDraw.Draw(image)
    _draw_mark(draw, mark_xy[0], mark_xy[1], icon_rgb, size=size)
    return image


def _arr(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


class WatermarkDetectionTests(unittest.TestCase):
    def test_orange_icon_watermark_detected_and_inpainted(self) -> None:
        image = _make((255, 255, 255), (300, 270), (240, 130, 30))
        result = wm.remove_corner_watermark(_arr(image))

        self.assertTrue(result.removed)
        self.assertEqual(result.method, "inpaint_telea")
        self.assertIsNotNone(result.bbox)
        self.assertGreater(result.bbox[0], 200)   # bottom-right region
        self.assertGreater(result.bbox[1], 150)
        # Inpaint on a white page must land near white where the icon was.
        cx = (result.bbox[0] + result.bbox[2]) // 2
        cy = (result.bbox[1] + result.bbox[3]) // 2
        self.assertTrue((result.image[cy, cx] > 200).all(), result.image[cy, cx].tolist())

    def test_anchor_is_colour_agnostic(self) -> None:
        # A blue icon must be detected just as an orange one is -- the anchor is
        # "saturated + compact + filled", never a hard-coded hue.
        image = _make((255, 255, 255), (300, 270), (40, 90, 220))
        result = wm.remove_corner_watermark(_arr(image))
        self.assertTrue(result.removed)
        self.assertGreater(result.bbox[0], 200)

    def test_icon_and_text_merged_into_one_bbox(self) -> None:
        # The bbox must span the icon plus its trailing grey lettering, not just
        # the icon.
        image = _make((255, 255, 255), (300, 270), (240, 130, 30), size=24)
        result = wm.remove_corner_watermark(_arr(image))
        self.assertTrue(result.removed)
        left, top, right, bottom = result.bbox
        self.assertLessEqual(left, 305)              # includes the icon
        self.assertGreaterEqual(right, 300 + 24 + 3 * 24)  # includes the glyphs

    def test_gradient_background_inpaints_without_colour_smear(self) -> None:
        h, w = 320, 480
        grad = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            t = y / (h - 1)
            grad[y, :, :] = (int(250 - 40 * t), int(240 - 45 * t), int(210 - 40 * t))
        img = Image.fromarray(grad)
        draw = ImageDraw.Draw(img)
        _draw_mark(draw, 320, 275, (240, 130, 30), size=22)
        arr = _arr(img)

        result = wm.remove_corner_watermark(arr)
        self.assertTrue(result.removed)
        # Sample a painted icon pixel: it should match the local gradient, not a
        # constant fill and not the orange icon.
        iy, ix = 286, 331
        painted = result.image[iy, ix].astype(int)
        expected = grad[iy, ix].astype(int)
        self.assertLess(abs(painted[0] - expected[0]), 45, painted.tolist())

    def test_clean_image_not_flagged(self) -> None:
        image = Image.new("RGB", (480, 320), (255, 255, 255))
        ImageDraw.Draw(image).rectangle([40, 40, 220, 160], fill=(30, 90, 200))
        result = wm.remove_corner_watermark(_arr(image))
        self.assertFalse(result.removed)

    def test_tall_chart_bar_not_mistaken_for_icon(self) -> None:
        # A saturated but tall, thin bar (aspect < 0.5) in the corner is chart
        # content, not a brand icon. Shape filtering must reject it.
        image = Image.new("RGB", (480, 320), (255, 255, 255))
        ImageDraw.Draw(image).rectangle([360, 210, 380, 300], fill=(240, 150, 60))
        result = wm.remove_corner_watermark(_arr(image))
        self.assertFalse(result.removed)

    def test_only_touches_inside_mask(self) -> None:
        image = _make((255, 255, 255), (300, 270), (240, 130, 30))
        arr = _arr(image)
        result = wm.remove_corner_watermark(arr)
        self.assertTrue(result.removed)
        outside = ~result.mask
        self.assertTrue(
            np.array_equal(arr[outside], result.image[outside]),
            "pixels changed outside the inpaint mask",
        )

    def _bottom_right_orange_count(self, image, arr) -> int:
        # Count strongly-orange (site brand hue) pixels in the bottom-right
        # quadrant after inpaint. Uses HSV hue to separate the orange teardrop
        # (OpenCV hue ~8-15) from nearby pure-red frame/text (hue ~0), which a
        # naive R/G/B box would misclassify as orange.
        import cv2 as _cv2
        h, w = arr.shape[:2]
        roi = image[int(h * 0.5):, int(w * 0.6):, :].astype("uint8")
        hsv = _cv2.cvtColor(roi, _cv2.COLOR_RGB2HSV)
        hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        orange = (hue >= 6) & (hue <= 22) & (sat > 120) & (val > 120)
        return int(orange.sum())

    def test_real_solid_logo_on_white_leaves_no_orange_residue(self) -> None:
        # Real site logo (orange teardrop icon + grey glyphs) on a white page
        # (full-size image; a crop changes ROI proportions and hides the bug).
        # The teardrop's anti-aliased tip is lower-saturation than its body, so
        # the anchor bbox stops short and an orange arc survives below the erased
        # region unless the bbox extends downward (缺陷: 框不全).
        arr = _arr(Image.open(FIXTURES / "watermark_solid_white_bg.webp"))
        pre = self._bottom_right_orange_count(arr, arr)
        self.assertGreater(pre, 0, "fixture should contain the orange logo")
        result = wm.remove_corner_watermark(arr)
        self.assertTrue(result.removed, "solid logo on white must be detected")
        post = self._bottom_right_orange_count(result.image, arr)
        self.assertEqual(
            post, 0,
            f"{post} orange watermark pixels survived inpaint (was {pre})",
        )

    def test_real_logo_on_colored_frame_is_detected_at_bottom_right(self) -> None:
        # Same logo on a pink fill crossed by a red border. The icon touches the
        # frame, so a naive saturated-blob anchor merges icon+frame into one long
        # thin component and rejects it, falling back to the original with the
        # logo intact (缺陷: 漏检). Detection must land on the real logo in the
        # bottom-right, not a stray chart blob elsewhere.
        arr = _arr(Image.open(FIXTURES / "watermark_on_colored_frame.webp"))
        result = wm.remove_corner_watermark(arr)
        self.assertTrue(result.removed, "logo on a colored frame must be detected")
        h, w = arr.shape[:2]
        left, top, right, bottom = result.bbox
        self.assertGreater(right, w * 0.55, f"bbox not in bottom-right: {result.bbox}")
        self.assertGreater(bottom, h * 0.55, f"bbox not in bottom-right: {result.bbox}")
        self.assertEqual(
            self._bottom_right_orange_count(result.image, arr), 0,
            "orange logo pixels survived in the bottom-right",
        )

    def test_missing_cv2_degrades_to_skip(self) -> None:
        image = _make((255, 255, 255), (300, 270), (240, 130, 30))
        arr = _arr(image)
        original_cv2 = wm.cv2
        wm.cv2 = None
        try:
            result = wm.remove_corner_watermark(arr)
        finally:
            wm.cv2 = original_cv2
        self.assertFalse(result.removed)
        self.assertEqual(result.method, "skipped_no_cv2")
        self.assertIsNone(result.image)


class BboxCornerGuardrailTests(unittest.TestCase):
    """The corner-hug guardrail keeps a mark flush against the image corner.

    A real brand watermark sits slightly inset with clear background around it;
    a bbox that touches the ROI's outer image corner within the margin is more
    likely a cropped element or a page edge than a removable logo, so it is kept.
    """

    def test_bbox_hugging_outer_corner_is_rejected(self) -> None:
        # Bottom-right ROI (its outer corner is the image's bottom-right). A bbox
        # flush against that corner within the margin must be flagged.
        roi_w, roi_h = 200, 100
        width, height = 480, 320
        x0, y0 = width - roi_w, height - roi_h    # on_right and on_bottom
        margin_x, margin_y = 4, 2
        flush = (roi_w - 20, roi_h - 12, roi_w, roi_h)   # right/bottom at the edge
        self.assertTrue(
            wm._bbox_hugs_outer_corner(
                flush, roi_w, roi_h, x0, y0, width, height, margin_x, margin_y
            )
        )

    def test_inset_bbox_is_not_rejected(self) -> None:
        # The same ROI, but the bbox sits inset from the outer corner: a normal
        # removable watermark with background around it. Must not be flagged.
        roi_w, roi_h = 200, 100
        width, height = 480, 320
        x0, y0 = width - roi_w, height - roi_h
        margin_x, margin_y = 4, 2
        inset = (60, 30, 140, 70)                 # well clear of the edges
        self.assertFalse(
            wm._bbox_hugs_outer_corner(
                inset, roi_w, roi_h, x0, y0, width, height, margin_x, margin_y
            )
        )


if __name__ == "__main__":
    unittest.main()
