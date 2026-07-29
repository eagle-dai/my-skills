"""Acceptance: 图/表下面的标题（题注）不能在 fast path 被静默吞成纯文本。

对应 html-to-markdown/acceptance/CASES.md「图/表下面的标题要居中」。

退化根因：带 <img> 的 <figure> 里如果有 <figcaption>，fast_converter 曾把它
当普通文本直接吐出——既不居中，也不做 caption ledger 守恒。这类页面必须路由到
strict，由 strict 流程负责居中 + 守恒。已有 test_pipeline_caption_routing 只覆盖
了「无 img 的 figure」和「table caption」，漏了「figure 同时含 img + figcaption」
这个实际退化场景，本测试补上。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "html-to-markdown" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_pipeline_acceptance_caption", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class CaptionCenteringAcceptance(unittest.TestCase):
    def test_figure_with_image_and_caption_routes_to_strict(self) -> None:
        """正例：图片 + figcaption 的 figure 必须路由 strict，不得 fast 吐纯文本。"""
        html = f"""
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          ends with a figure that carries both an image and a caption below it.</p>
          <figure>
            <img src="{PNG_DATA_URI}" alt="architecture" />
            <figcaption>图 4-1 系统架构</figcaption>
          </figure>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "figure-with-caption.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "strict_required")
            self.assertIsNone(outcome.markdown_path)
            self.assertIsNone(outcome.zip_path)

    def test_figure_image_without_caption_stays_on_fast_path(self) -> None:
        """反例：只有图片、没有 figcaption 的 figure 照常走 fast path，不受影响。"""
        html = f"""
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          ends with a plain figure that has an image but carries no caption at all.</p>
          <figure>
            <img src="{PNG_DATA_URI}" alt="plain" />
          </figure>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "figure-no-caption.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None

    def test_plain_long_paragraph_not_treated_as_caption(self) -> None:
        """反例：普通长段落不是题注，不该被误判路由 strict，照常 converted。"""
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          contains only ordinary explanatory paragraphs with no figure or caption.</p>
          <p>A second ordinary paragraph that merely continues the prose and should
          never be mistaken for a caption requiring strict centering treatment.</p>
        </article></body></html>
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "plain-paragraphs.html"
            source.write_text(html, encoding="utf-8")

            outcome = pipeline.run_pipeline(source, root / "out", mode="fast")

            self.assertEqual(outcome.status, "converted")
            assert outcome.markdown_path is not None


if __name__ == "__main__":
    unittest.main()
