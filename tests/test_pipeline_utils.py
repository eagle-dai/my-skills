from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline_utils.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline_utils", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline_utils = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline_utils
SPEC.loader.exec_module(pipeline_utils)


class PipelineUtilsTests(unittest.TestCase):
    def test_decode_data_uri_supports_standard_encodings_and_parameters(self) -> None:
        cases = (
            ("data:image/png;base64,iVBORw==", "image/png", b"\x89PNG"),
            (
                "data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
                "image/svg+xml",
                b"<svg></svg>",
            ),
            ("data:,plain%20text", "application/octet-stream", b"plain text"),
        )

        for source, expected_mime, expected_payload in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    pipeline_utils.decode_data_uri(source),
                    (expected_mime, expected_payload),
                )

    def test_decode_data_uri_rejects_malformed_metadata(self) -> None:
        malformed_sources = (
            "not-data:image/png;base64,iVBORw==",
            "data:image/png;charset,iVBORw==",
            "data:image/png;base64,not base64!",
        )

        for source in malformed_sources:
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "invalid data URI"):
                    pipeline_utils.decode_data_uri(source)

    def test_safe_package_name_preserves_chinese_text(self) -> None:
        self.assertEqual(
            pipeline_utils.safe_package_name("导读｜量化知识背景与研究能力地图"),
            "导读-量化知识背景与研究能力地图",
        )

    def test_distinct_chinese_names_do_not_collapse_to_article(self) -> None:
        first = pipeline_utils.safe_package_name("量化知识背景")
        second = pipeline_utils.safe_package_name("研究能力地图")

        self.assertNotEqual(first, "article")
        self.assertNotEqual(second, "article")
        self.assertNotEqual(first, second)

    def test_full_width_forms_are_normalized(self) -> None:
        self.assertEqual(pipeline_utils.safe_package_name("ＡＩ 技能"), "AI-技能")

    def test_punctuation_only_name_still_uses_fallback(self) -> None:
        self.assertEqual(pipeline_utils.safe_package_name("｜／："), "article")

    def test_write_json_uses_same_directory_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "nested" / "report.json"
            original_replace = pipeline_utils.os.replace
            replacements: list[tuple[Path, Path]] = []

            def checked_replace(source: str | Path, target: str | Path) -> None:
                source_path = Path(source)
                target_path = Path(target)
                self.assertEqual(source_path.parent, target_path.parent)
                replacements.append((source_path, target_path))
                original_replace(source, target)

            with mock.patch.object(
                pipeline_utils.os,
                "replace",
                side_effect=checked_replace,
            ):
                pipeline_utils.write_json(destination, {"message": "中文", "value": 2})

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                {"message": "中文", "value": 2},
            )
            self.assertEqual(len(replacements), 1)
            self.assertEqual(replacements[0][1], destination)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o644)
            self.assertEqual(list(destination.parent.glob(f".{destination.name}.*.tmp")), [])

    def test_write_json_preserves_existing_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "cache.json"
            destination.write_text('{"old": true}\n', encoding="utf-8")
            destination.chmod(0o640)

            pipeline_utils.write_json(destination, {"old": False})

            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o640)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"old": False})

    def test_write_json_failure_preserves_previous_file_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "cache.json"
            previous = '{"stable": true}\n'
            destination.write_text(previous, encoding="utf-8")
            destination.chmod(0o640)

            with mock.patch.object(
                pipeline_utils.os,
                "replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    pipeline_utils.write_json(destination, {"stable": False})

            self.assertEqual(destination.read_text(encoding="utf-8"), previous)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o640)
            self.assertEqual(list(root.glob(f".{destination.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
