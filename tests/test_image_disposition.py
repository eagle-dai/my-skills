from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "image_disposition.py"
SPEC = importlib.util.spec_from_file_location("image_disposition", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
image_disposition = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = image_disposition
SPEC.loader.exec_module(image_disposition)


class ImageDecisionTests(unittest.TestCase):
    def test_body_qr_code_is_kept(self) -> None:
        context = image_disposition.ImageContext(
            source_id="qr-body",
            is_qr_code=True,
            in_body=True,
        )
        self.assertEqual(image_disposition.decide_image(context), "keep")

    def test_content_related_qr_code_is_kept(self) -> None:
        context = image_disposition.ImageContext(
            source_id="qr-download",
            is_qr_code=True,
            has_content_relation=True,
            decoded_url="https://example.com/download",
        )
        self.assertEqual(image_disposition.decide_image(context), "keep")

    def test_share_ui_qr_code_is_removed_only_with_positive_ui_evidence(self) -> None:
        context = image_disposition.ImageContext(
            source_id="qr-follow",
            is_qr_code=True,
            inside_share_or_follow_ui=True,
        )
        self.assertEqual(image_disposition.decide_image(context), "remove_as_ui")

    def test_uncertain_qr_code_is_preserved_for_review(self) -> None:
        context = image_disposition.ImageContext(
            source_id="qr-unknown",
            is_qr_code=True,
        )
        self.assertEqual(image_disposition.decide_image(context), "manual_review")

    def test_body_relationship_overrides_ui_container_hint(self) -> None:
        context = image_disposition.ImageContext(
            source_id="qr-embedded",
            is_qr_code=True,
            in_body=True,
            inside_share_or_follow_ui=True,
        )
        self.assertEqual(image_disposition.decide_image(context), "keep")

    def test_decorative_non_body_image_is_removable(self) -> None:
        context = image_disposition.ImageContext(
            source_id="divider",
            decorative=True,
        )
        self.assertEqual(image_disposition.decide_image(context), "remove_as_ui")


class ImageLedgerTests(unittest.TestCase):
    def test_valid_ledger_preserves_manual_review_image(self) -> None:
        entries = [
            image_disposition.ImageLedgerEntry("body", "keep", 1),
            image_disposition.ImageLedgerEntry(
                "unknown-qr",
                "manual_review",
                1,
                "QR context is ambiguous",
            ),
            image_disposition.ImageLedgerEntry(
                "follow-ui",
                "remove_as_ui",
                0,
                "inside follow widget outside article",
            ),
        ]

        self.assertEqual(
            image_disposition.validate_image_ledger(
                entries,
                source_ids=["body", "unknown-qr", "follow-ui"],
            ),
            (),
        )

    def test_manual_review_cannot_silently_drop_image(self) -> None:
        entries = [
            image_disposition.ImageLedgerEntry(
                "unknown-qr",
                "manual_review",
                0,
                "ambiguous",
            )
        ]

        errors = image_disposition.validate_image_ledger(
            entries,
            source_ids=["unknown-qr"],
        )

        self.assertTrue(any("emitted_count == 1" in error for error in errors))

    def test_removed_image_requires_ui_evidence(self) -> None:
        entries = [
            image_disposition.ImageLedgerEntry("qr", "remove_as_ui", 0),
        ]

        errors = image_disposition.validate_image_ledger(entries, source_ids=["qr"])

        self.assertTrue(any("positive UI evidence" in error for error in errors))

    def test_missing_source_image_is_rejected(self) -> None:
        entries = [image_disposition.ImageLedgerEntry("one", "keep", 1)]

        with self.assertRaisesRegex(ValueError, "missing source image ids"):
            image_disposition.assert_valid_image_ledger(
                entries,
                source_ids=["one", "two"],
            )


if __name__ == "__main__":
    unittest.main()
