from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw


SKILL = Path(__file__).resolve().parent.parent
MODULE_PATH = SKILL / "image_processing.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_image_processing_tests", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
ip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ip
SPEC.loader.exec_module(ip)


def _encode(image: Image.Image, fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


class ImageProcessingTests(unittest.TestCase):
    def test_corner_watermark_removed_and_validated(self) -> None:
        image = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        # Content in the upper-left; a brand watermark (saturated icon + grey
        # lettering) in the bottom-right corner.
        draw.rectangle([20, 20, 180, 120], fill=(30, 90, 200))
        draw.ellipse([322, 258, 344, 280], fill=(240, 130, 30))       # icon anchor
        draw.rectangle([350, 262, 388, 278], fill=(140, 140, 140))    # lettering

        result = ip.process_image(_encode(image), "image/png", "wm")

        self.assertTrue(result.meta.dewatermarked)
        self.assertTrue(result.meta.validation_passed)
        self.assertFalse(result.meta.fallback_to_original)
        bbox = result.meta.watermark_bbox
        self.assertIsNotNone(bbox)
        # bbox sits in the bottom-right region.
        self.assertGreater(bbox[0], 200)
        self.assertGreater(bbox[1], 150)
        # The erased region must actually become the background colour (white),
        # not stay the watermark grey. Decode the emitted (lossy) webp and
        # sample the bbox centre; it must be near white, far from grey 128.
        import numpy as np

        emitted = np.asarray(Image.open(BytesIO(result.data)).convert("RGB"))
        cy = (bbox[1] + bbox[3]) // 2
        cx = (bbox[0] + bbox[2]) // 2
        centre = emitted[cy, cx]
        self.assertTrue(
            (centre > 220).all(),
            f"erased region not background-coloured: {centre.tolist()}",
        )

    def test_watermark_overlapping_content_falls_back(self) -> None:
        # A brand icon in the corner whose bbox also spans strong dark content
        # strokes (a chart drawn behind the mark): erasing it would destroy the
        # body. Detection fires on the icon, but validation must refuse the
        # erase (strong-contrast content inside the bbox) and fall back.
        image = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse([305, 255, 327, 277], fill=(240, 130, 30))      # icon anchor
        # Strong dark content strokes filling the lettering side of the mark's
        # row (kept clear of the icon so detection still anchors on it).
        for y in range(250, 292, 5):
            draw.line([333, y, 392, y], fill=(15, 15, 15), width=3)

        result = ip.process_image(_encode(image), "image/png", "overlap")

        self.assertTrue(result.meta.fallback_to_original)
        self.assertFalse(result.meta.dewatermarked)
        self.assertEqual(result.meta.validation_reason, "watermark_overlaps_content")
        self.assertIsNone(result.meta.watermark_bbox)
        # A rejected destructive edit must not mutate the image in any way,
        # including compression: the emitted bytes are exactly the original.
        original = _encode(image)
        self.assertEqual(result.original_data, original)
        self.assertEqual(result.data, original)

    def test_no_watermark_is_not_dewatermarked(self) -> None:
        image = Image.new("RGB", (400, 300), (255, 255, 255))
        ImageDraw.Draw(image).rectangle([50, 50, 200, 150], fill=(30, 90, 200))

        result = ip.process_image(_encode(image), "image/png", "clean")

        self.assertFalse(result.meta.dewatermarked)
        self.assertFalse(result.meta.fallback_to_original)
        self.assertIsNone(result.meta.watermark_bbox)

    def test_wide_image_is_downscaled(self) -> None:
        image = Image.new("RGB", (3000, 1000), (255, 255, 255))
        ImageDraw.Draw(image).rectangle([100, 100, 900, 400], fill=(200, 40, 40))

        result = ip.process_image(_encode(image), "image/png", "wide")

        self.assertTrue(result.meta.compressed)
        reopened = Image.open(BytesIO(result.data))
        self.assertEqual(reopened.width, 1600)

    def test_webp_larger_keeps_original_format(self) -> None:
        # When webp does not come out smaller than the original raster format,
        # compress_to_webp keeps the original format. Real webp is almost always
        # smaller, so force the comparison by patching the webp encoder to emit
        # a deliberately large payload for this call only.
        image = Image.new("RGB", (100, 100), (123, 200, 45))
        real_save = Image.Image.save

        def bloated_save(self, fp, format=None, **kwargs):  # noqa: ANN001
            if format == "WEBP":
                fp.write(b"\0" * 100_000)
                return
            return real_save(self, fp, format=format, **kwargs)

        Image.Image.save = bloated_save
        try:
            data, mime, compressed, note = ip.compress_to_webp(
                image, "image/png", max_width=1600, quality=82
            )
        finally:
            Image.Image.save = real_save

        self.assertEqual(mime, "image/png")
        self.assertFalse(compressed)
        self.assertEqual(note, "webp_larger_kept_original")
        # The kept bytes are a real PNG, not the bloated webp stand-in.
        self.assertEqual(Image.open(BytesIO(data)).format, "PNG")

    def test_decode_failure_falls_back(self) -> None:
        # The pipeline fixture's fake PNG: an 8-byte signature that will not
        # decode. Must fail closed and package the original bytes.
        fake = b"iVBORw0KGgo="

        result = ip.process_image(fake, "image/png", "bad")

        self.assertTrue(result.meta.fallback_to_original)
        self.assertEqual(result.data, fake)
        self.assertEqual(result.mime, "image/png")

    def test_gif_passes_through_untouched(self) -> None:
        payload = b"GIF89a-not-a-real-gif"

        result = ip.process_image(payload, "image/gif", "anim")

        self.assertEqual(result.data, payload)
        self.assertEqual(result.mime, "image/gif")
        self.assertFalse(result.meta.dewatermarked)

    def test_transparent_image_keeps_alpha(self) -> None:
        # A transparent RGBA PNG must not acquire an opaque (black) background
        # when no watermark is present. Alpha must survive processing.
        import numpy as np

        image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))  # fully transparent
        draw = ImageDraw.Draw(image)
        draw.rectangle([50, 50, 200, 200], fill=(200, 40, 40, 255))  # opaque box

        result = ip.process_image(_encode(image), "image/png", "alpha")

        self.assertFalse(result.meta.fallback_to_original)
        emitted = Image.open(BytesIO(result.data))
        self.assertIn("A", emitted.getbands())
        arr = np.asarray(emitted.convert("RGBA"))
        # A corner that was fully transparent must stay transparent.
        self.assertLess(int(arr[10, 250, 3]), 16)
        # The opaque content box must stay opaque.
        self.assertGreater(int(arr[120, 120, 3]), 240)

    def test_validate_sees_content_outside_the_tight_bbox(self) -> None:
        # validate_dewatermark measures content overlap in a ring padded OUTSIDE
        # the bbox, not just the bbox interior. A watermark's bbox hugs the mark,
        # so colliding content (a chart stroke) sits just beyond it. Prove the
        # padded ring catches it: identical inputs, the only difference being a
        # dark stroke just outside the bbox, must flip pass -> refuse.
        import numpy as np

        h, w = 300, 400
        bbox = (300, 250, 324, 274)          # a small corner mark, 24x24
        l, t, r, b = bbox
        mask = np.zeros((h, w), dtype=bool)
        mask[t:b, l:r] = True                # the whole tiny bbox is "the mark"

        # Original: white page + coloured mark in the bbox. Processed: mark
        # painted out to white. No content anywhere else -> validation passes.
        base = np.full((h, w, 3), 255, dtype=np.uint8)
        orig_clean = base.copy()
        orig_clean[t:b, l:r] = (240, 130, 30)
        proc = base.copy()                   # mark erased to white
        ok, reason = ip.validate_dewatermark(
            Image.fromarray(orig_clean), Image.fromarray(proc), bbox, mask
        )
        self.assertTrue(ok, reason)

        # Same, but a dark content stroke sits just OUTSIDE the bbox (within the
        # ring). It is outside the mask, strongly contrasts the white bg, and
        # must trip the overlap guard -> refuse.
        orig_overlap = orig_clean.copy()
        orig_overlap[t:b, r + 4 : r + 28] = (15, 15, 15)   # stroke past the bbox
        # The stroke is outside the mask, so a correct erase leaves it intact:
        # it must be present in the processed image too (else check 1 fires).
        proc_overlap = proc.copy()
        proc_overlap[t:b, r + 4 : r + 28] = (15, 15, 15)
        ok2, reason2 = ip.validate_dewatermark(
            Image.fromarray(orig_overlap), Image.fromarray(proc_overlap), bbox, mask
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "watermark_overlaps_content")

    def test_validate_residual_refuses_half_erased_mark(self) -> None:
        # Check 3 (dewatermark_residual): if the "painted" image still carries
        # the mark's high-frequency structure inside the mask, the fill did not
        # cover it. A clean flat fill passes; leaving the strokes in place must
        # refuse rather than ship a half-erased watermark.
        import numpy as np

        h, w = 300, 400
        bbox = (180, 130, 240, 170)          # away from every image edge
        l, t, r, b = bbox
        mask = np.zeros((h, w), dtype=bool)

        # Original: white page with sharp black strokes inside the bbox.
        orig = np.full((h, w, 3), 255, dtype=np.uint8)
        for x in range(l + 4, r - 4, 8):     # vertical strokes -> strong edges
            orig[t + 4 : b - 4, x : x + 3] = 15
            mask[t + 4 : b - 4, x : x + 3] = True

        # A clean fill (mask region painted to flat white) must pass check 3.
        proc_clean = orig.copy()
        proc_clean[mask] = 255
        ok, reason = ip.validate_dewatermark(
            Image.fromarray(orig), Image.fromarray(proc_clean), bbox, mask
        )
        self.assertTrue(ok, reason)

        # A no-op "fill" leaves the strokes intact: after-energy == before-energy,
        # so the residual guard must fire. Only the mask pixels differ between the
        # two processed images, so check 1 (identity outside the mask) still holds.
        proc_residual = orig.copy()
        ok2, reason2 = ip.validate_dewatermark(
            Image.fromarray(orig), Image.fromarray(proc_residual), bbox, mask
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "dewatermark_residual")

    def test_transparent_watermark_dewatermarked_preserves_alpha(self) -> None:
        # Alpha must also survive a successful dewatermark: erase the corner
        # watermark but keep the transparency map intact.
        import numpy as np

        image = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle([20, 20, 180, 120], fill=(30, 90, 200, 255))
        draw.ellipse([322, 258, 344, 280], fill=(240, 130, 30, 255))     # icon anchor
        draw.rectangle([350, 262, 388, 278], fill=(140, 140, 140, 255))  # lettering
        # Punch a transparent hole far from the watermark.
        draw.rectangle([10, 250, 60, 290], fill=(0, 0, 0, 0))

        result = ip.process_image(_encode(image), "image/png", "alpha-wm")

        self.assertTrue(result.meta.dewatermarked)
        emitted = Image.open(BytesIO(result.data)).convert("RGBA")
        arr = np.asarray(emitted)
        self.assertLess(int(arr[270, 35, 3]), 16)   # hole still transparent
        self.assertGreater(int(arr[60, 100, 3]), 240)  # content still opaque


if __name__ == "__main__":
    unittest.main()
