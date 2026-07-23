from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FirstBatchRuleConsistencyTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_sim_rule_is_token_based_and_preserves_legal_commands(self) -> None:
        skill = self.read("formula-extraction/SKILL.md")
        self.assertIn("禁止", skill)
        self.assertIn(r"\\sim([a-zA-Zα-ωΑ-Ω])", skill)  # retained only as a prohibited example
        self.assertIn(r"\simeq", skill)
        self.assertIn(r"\simneqq", skill)
        self.assertIn("parser parts", skill)
        self.assertNotIn("后紧跟任何字母", skill)

    def test_domain_specific_formula_shapes_are_not_auto_errors(self) -> None:
        skill = self.read("formula-extraction/SKILL.md")
        warning_section = skill.split("### 需要结构证据的警告", 1)[1]
        self.assertIn(r"\pi\theta", warning_section)
        self.assertIn(r"V^\pi_\theta", warning_section)
        self.assertIn("不得自动改写", warning_section)

    def test_unknown_katex_nodes_fail_closed(self) -> None:
        parser = self.read("formula-extraction/katex-html-parser.md")
        self.assertIn("未知结构 fail-closed", parser)
        self.assertIn("不得作为成功的 LaTeX 输出", parser)
        self.assertNotIn("fallback 到 textContent（有损但不崩溃）", parser)

    def test_slate_code_selector_is_consistent(self) -> None:
        for relative in (
            "html-to-markdown/SKILL.md",
            "html-to-markdown/conversion-rules.md",
            "html-to-markdown/checklist.md",
        ):
            text = self.read(relative)
            self.assertIn('[data-slate-type="pre"]', text, relative)
            if '[data-slate-type="code-block"]' in text:
                self.assertIn("不得", text, relative)

    def test_tables_are_mandatory_audit_items(self) -> None:
        for relative in (
            "html-to-markdown/SKILL.md",
            "html-to-markdown/conversion-rules.md",
            "html-to-markdown/checklist.md",
        ):
            text = self.read(relative)
            self.assertIn('[data-slate-type="table"]', text, relative)
            self.assertIn("表格", text, relative)

    def test_dewatermark_is_opt_in(self) -> None:
        for relative in (
            "html-to-markdown/SKILL.md",
            "html-to-markdown/conversion-rules.md",
            "html-to-markdown/checklist.md",
        ):
            text = self.read(relative)
            self.assertIn("默认", text, relative)
            self.assertIn("明确要求", text, relative)
            self.assertNotIn("默认去站点水印", text, relative)

    def test_mid_is_not_globally_rewritten_to_vert(self) -> None:
        skill = self.read("formula-extraction/SKILL.md")
        self.assertIn(r"不得全局执行 `\mid → \vert`", skill)
        self.assertIn("关系符号", skill)
        self.assertIn("不能解决 Markdown 表格分隔符冲突", skill)

    def test_gfm_inline_math_documents_cross_renderer_choice(self) -> None:
        checklist = self.read("html-to-markdown/checklist.md")
        self.assertIn("ASCII 空格", checklist)
        self.assertIn("GitHub 与 VS Code", checklist)
        self.assertIn("backtick 数学变体", checklist)
        self.assertIn("因此不采用", checklist)

    def test_emphasis_and_centering_repair_evidence_is_retained(self) -> None:
        checklist = self.read("html-to-markdown/checklist.md")
        self.assertIn("不要把四个星号机械替换成两个", checklist)
        self.assertIn("短题注示例", checklist)
        self.assertIn("说明段落示例", checklist)
        self.assertIn("200–267 字", checklist)


if __name__ == "__main__":
    unittest.main()