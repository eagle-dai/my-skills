from __future__ import annotations

from pathlib import Path
import sys
import unittest

from bs4 import BeautifulSoup

SKILL = Path(__file__).resolve().parent.parent
MODULE_DIR = SKILL
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import fast_converter  # noqa: E402


class GuessCodeLanguageTests(unittest.TestCase):
    # gap #23: highlight.js 页无 language-* class,从内容推断,高置信才标否则 text。
    # 回归用例表(禁删已有行)。

    def test_python_signals(self) -> None:
        for code in (
            "def _to_float(value):\n    return None",
            "import pandas as pd\ndf = pd.to_numeric(s)",
            "class Foo:\n    def bar(self) -> None:\n        self.x = 1",
        ):
            self.assertEqual(fast_converter.guess_code_language(code), "python", code)

    def test_json_signal(self) -> None:
        for code in ('{"a": 1, "b": [2, 3]}', '[\n  {"k": "v"}\n]'):
            self.assertEqual(fast_converter.guess_code_language(code), "json", code)

    def test_javascript_signals(self) -> None:
        code = "const add = (a, b) => a + b;\nconsole.log(add(1, 2));"
        self.assertEqual(fast_converter.guess_code_language(code), "javascript")

    def test_bash_signals(self) -> None:
        # 跨信号组:命令调用组(pip install) + 裸 shell 工具组(export/cd) = 2 条 → bash。
        code = "export PYTHONPATH=src\npip install -r requirements.txt\ncd tests"
        self.assertEqual(fast_converter.guess_code_language(code), "bash")
        # shebang 单独即达标(STRONG)。
        self.assertEqual(
            fast_converter.guess_code_language("#!/bin/bash\necho hi"), "bash"
        )

    def test_single_command_invocation_is_not_bash(self) -> None:
        # 单条 pip install / python -m / pytest 是 WEAK,单独不达标 → None（回退
        # text）。这些命令也出现在 Dockerfile(RUN pip install)、CI YAML(run: pip
        # install)、散文里，单条判 bash 会误标。宁 text 不误判。
        for code in ("pip install numpy", "python -m build", "pytest -q"):
            self.assertIsNone(fast_converter.guess_code_language(code), code)
        # 同一信号组内多条命令只算一次（pip install 与 pytest 同属命令组），仍不
        # 达标 → None。宁 text 不误判。
        self.assertIsNone(
            fast_converter.guess_code_language("pip install -r req.txt\npytest -q")
        )
        # 跨信号组（命令调用 + 裸 shell 工具）才达标 = bash。
        self.assertEqual(
            fast_converter.guess_code_language("pip install -r req.txt\ncd /app && ls"),
            "bash",
        )

    def test_dockerfile_and_yaml_pip_install_not_bash(self) -> None:
        # 回归：含 pip install 的 Dockerfile / CI YAML 单行不该判 bash（否则破坏
        # 各自高亮）。无强 bash 信号 → None。
        self.assertIsNone(
            fast_converter.guess_code_language("FROM python:3.11\nRUN pip install flask")
        )
        self.assertIsNone(
            fast_converter.guess_code_language("steps:\n  - run: pip install -r req.txt")
        )
        self.assertIsNone(
            fast_converter.guess_code_language("Run pip install flask to install it.")
        )

    def test_powershell_signals(self) -> None:
        # $env: 是 PowerShell 强特征;哪怕含 `python -m`(也命中 bash)也应判 powershell。
        code = '$env:PYTHONPATH="src"\npython -m pytest tests/test_x.py -q'
        self.assertEqual(fast_converter.guess_code_language(code), "powershell")
        # heredoc @"..."@ 同为强特征。
        self.assertEqual(
            fast_converter.guess_code_language('$env:X="1"\npython -c @"\nprint(1)\n"@'),
            "powershell",
        )
        # PS + 多条 bash 命令行:$env: 强特征应压过 bash 的累加分,仍判 powershell。
        self.assertEqual(
            fast_converter.guess_code_language(
                '$env:PYTHONPATH="src"\npython -m pytest tests/\ngit status'
            ),
            "powershell",
        )

    def test_prose_and_weak_evidence_return_none(self) -> None:
        # 反例:含 def/{} 的英文散文、纯注释、普通句子,都不该误判。
        for code in (
            "The def of done is when {done} is true.",  # 含 def + {}
            "# just a comment\nhello world",  # 纯注释 + 散文
            "This is a plain english sentence.",
            "value 42",  # 无任何结构
        ):
            self.assertIsNone(fast_converter.guess_code_language(code), code)

    def test_single_weak_signal_returns_none(self) -> None:
        # 只 1 个弱特征(单个 print 或单个 =>)不足以判定。
        self.assertIsNone(fast_converter.guess_code_language("print"))
        self.assertIsNone(fast_converter.guess_code_language("a => b in a set"))

    def test_json_with_code_keywords_is_not_json(self) -> None:
        # 花括号包裹但含语句关键字/注释 → 不当 json。
        self.assertNotEqual(
            fast_converter.guess_code_language('{ return x; } // note'), "json"
        )

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(fast_converter.guess_code_language(""))
        self.assertIsNone(fast_converter.guess_code_language("   \n  "))


class CodeBlockLanguageTests(unittest.TestCase):
    def _fence(self, html: str) -> str:
        root = BeautifulSoup(html, "html.parser")
        node = root.find(["pre", "code"])
        conv = fast_converter.MarkdownConverter(root, [], [], Path("/tmp"), "files")
        return conv.code_block(node)

    def test_explicit_language_class_wins(self) -> None:
        out = self._fence('<pre><code class="language-go">x := 1</code></pre>')
        self.assertTrue(out.startswith("```go\n"), out)

    def test_hljs_python_inferred_when_no_class(self) -> None:
        # highlight.js 结构:无 language-* class,内部 hljs span。应推断 python。
        html = (
            "<pre><code>"
            '<span class="hljs-keyword">def</span> '
            '<span class="hljs-title function_">_to_float</span>(value):\n'
            "    <span class=\"hljs-keyword\">return</span> None"
            "</code></pre>"
        )
        out = self._fence(html)
        self.assertTrue(out.startswith("```python\n"), out)

    def test_unknown_content_falls_back_to_text(self) -> None:
        out = self._fence("<pre><code>plain english here.</code></pre>")
        self.assertTrue(out.startswith("```text\n"), out)


if __name__ == "__main__":
    unittest.main()
