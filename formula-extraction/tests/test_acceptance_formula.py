"""公式验收测试（端到端，对齐 acceptance/CASES.md）。

用户看得懂的效果 → 真实公式 DOM → 提取产出 → 断言。与
test_formula_postprocess_rules.py 的单元测试互补：那里逐条钉规则函数，这里钉
"用户报的那个症状不再复现"。

实现按路径加载 html-to-markdown/formula_batch.py（skill 名带连字符不可直接 import），
沿用 html-to-markdown 自己测试的惯例。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from bs4 import BeautifulSoup


SKILL = Path(__file__).resolve().parent.parent
HTML_TO_MARKDOWN = SKILL.parent / "html-to-markdown"


def _load_formula_batch():
    path = HTML_TO_MARKDOWN / "formula_batch.py"
    spec = importlib.util.spec_from_file_location("formula_extraction_accept_formula_batch", path)
    assert spec is not None and spec.loader is not None, f"无法定位实现模块: {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


formula_batch = _load_formula_batch()


class TextModeUnderscoreAcceptanceTests(unittest.TestCase):
    """CASES.md：`\\text{}` 里的下划线在 GitHub 上让整条公式渲染失败。

    KaTeX 对 `\\text{signal_source}` 渲染出的最小结构是 mord text 包裹文本。提取器
    必须在产出时就把 text-mode 的 `_` 转义成 `\\_`，否则推到 GitHub 会渲染失败。
    """

    def test_text_mode_underscore_is_escaped_end_to_end(self) -> None:
        soup = BeautifulSoup(
            '<span class="katex"><span class="katex-html"><span class="base">'
            '<span class="mord text"><span class="mord">signal_source</span></span>'
            '</span></span></span>',
            "lxml",
        )
        node = soup.select_one(".katex")
        assert node is not None

        result = formula_batch.parse_katex(node)

        self.assertTrue(result.success, "text-mode 文本应成功提取")
        # 症状不复现：产出里的下划线已转义成 \_，不是会让 GitHub 报错的裸 _
        self.assertIn(r"\text{signal\_source}", result.latex)


if __name__ == "__main__":
    unittest.main()
