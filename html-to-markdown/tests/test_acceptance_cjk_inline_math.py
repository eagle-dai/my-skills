"""Acceptance: 中文紧贴 $ 的行内公式，在 GitHub 里要能正常渲染。

对应 html-to-markdown/acceptance/CASES.md「中文紧贴的行内公式，GitHub 里要能正常显示」。

机制：CJK / 全角标点直接贴着 $ 时（如 收益率$r_t$），GitHub 不渲染这段数学。
在紧贴的一侧插一个 ASCII 空格（收益率 $r_t$）即可修好，且不改变公式本身。
规则登记于 self-improvement.md「行内公式 $ 边界」。代码块内的 $ 不受影响。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
MODULE_PATH = SKILL / "pipeline.py"
SPEC = importlib.util.spec_from_file_location(
    "html_to_markdown_pipeline_acceptance_cjk_math", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


def _katex(latex: str) -> str:
    return (
        '<span class="katex"><span class="katex-mathml"><math>'
        f'<annotation encoding="application/x-tex">{latex}</annotation>'
        "</math></span></span>"
    )


def _convert(html: str) -> str:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "doc.html"
        source.write_text(html, encoding="utf-8")
        outcome = pipeline.run_pipeline(source, root / "out", mode="fast")
        assert outcome.status == "converted", outcome.status
        assert outcome.markdown_path is not None
        return outcome.markdown_path.read_text(encoding="utf-8")


class CjkInlineMathAcceptance(unittest.TestCase):
    def test_cjk_touching_dollar_gets_a_space(self) -> None:
        """正例：中文汉字紧贴 $ 两侧，转出后各插一个空格。"""
        html = f"""
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          then presents an inline formula pressed against Chinese characters.</p>
          <p>收益率{_katex("r_t")}表示当期结果。</p>
        </article></body></html>
        """
        markdown = _convert(html)
        self.assertIn("收益率 $r_t$ 表示", markdown)
        self.assertNotIn("收益率$r_t$", markdown)

    def test_fullwidth_punctuation_touching_dollar_gets_a_space(self) -> None:
        """正例：全角括号紧贴 $，同样插空格。"""
        html = f"""
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          wraps an inline formula inside fullwidth parentheses without any spaces.</p>
          <p>（{_katex("w_t")}）是权重。</p>
        </article></body></html>
        """
        markdown = _convert(html)
        self.assertIn("（ $w_t$ ）", markdown)

    def test_ascii_spaced_formula_is_left_alone(self) -> None:
        """反例：已经用 ASCII 空格隔开的公式，不重复插空格。"""
        html = f"""
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          keeps a formula already separated by regular ASCII spaces on both sides.</p>
          <p>see {_katex("r_t")} formula here.</p>
        </article></body></html>
        """
        markdown = _convert(html)
        self.assertIn("see $r_t$ formula", markdown)
        self.assertNotIn("  $r_t$", markdown)

    def test_dollar_inside_code_fence_is_untouched(self) -> None:
        """反例：代码块里的 $ 紧贴中文，不许被动（fence 内零改动）。"""
        html = """
        <html><body><article>
          <p>This article body is sufficiently long for deterministic selection and
          then shows a shell snippet where a dollar sign hugs Chinese text.</p>
          <pre><code>echo 价格$USD 变量</code></pre>
        </article></body></html>
        """
        markdown = _convert(html)
        # fence 内原样：$ 前后不得被插入空格
        self.assertIn("价格$USD", markdown)
        self.assertNotIn("价格 $USD", markdown)


if __name__ == "__main__":
    unittest.main()
