from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "image_processing.py"
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
        # Content in the upper-left, a grey watermark blob in the bottom-right.
        draw.rectangle([20, 20, 180, 120], fill=(30, 90, 200))
        draw.rectangle([320, 250, 380, 285], fill=(128, 128, 128))

        result = ip.process_image(_encode(image), "image/png", "wm")

        self.assertTrue(result.meta.dewatermarked)
        self.assertTrue(result.meta.validation_passed)
        self.assertFalse(result.meta.fallback_to_original)
        bbox = result.meta.watermark_bbox
        self.assertIsNotNone(bbox)
        # bbox sits in the bottom-right region.
        self.assertGreater(bbox[0], 200)
        self.assertGreater(bbox[1], 150)

    def test_watermark_overlapping_content_falls_back(self) -> None:
        # A large grey block in the corner with dark content strokes running
        # through it: the detected bbox spans real content, so erasing it would
        # destroy the body. Validation must refuse and fall back to the original.
        image = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle([300, 230, 390, 290], fill=(128, 128, 128))  # grey block
        for y in range(238, 285, 8):
            draw.line([305, y, 385, y], fill=(20, 20, 20), width=2)  # dark strokes

        result = ip.process_image(_encode(image), "image/png", "overlap")

        self.assertTrue(result.meta.fallback_to_original)
        self.assertFalse(result.meta.dewatermarked)
        self.assertEqual(result.meta.validation_reason, "watermark_overlaps_content")
        self.assertIsNone(result.meta.watermark_bbox)
        # The original bytes are always preserved for offline audit.
        self.assertEqual(result.original_data, _encode(image))

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


if __name__ == "__main__":
    unittest.main()
