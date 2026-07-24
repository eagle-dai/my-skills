from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline_utils.py"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_pipeline_utils", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline_utils = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline_utils
SPEC.loader.exec_module(pipeline_utils)


class PipelineUtilsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
