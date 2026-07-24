from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillEntrypointTests(unittest.TestCase):
    def test_html_skill_runs_auto_pipeline_before_strict_dispatch(self) -> None:
        skill = (ROOT / "html-to-markdown" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("## Phase 0：确定性入口与状态分流", skill)
        self.assertIn("python html-to-markdown/pipeline.py input.html", skill)
        self.assertIn("--mode auto", skill)
        for status in ("converted", "blocked", "strict_required"):
            self.assertIn(f"`{status}`", skill)
        self.assertIn("Phase 1-5 只在 deterministic pipeline 返回 `strict_required` 时启动", skill)
        self.assertIn("`blocked` 与 `strict_required` 不是同一种状态", skill)

    def test_html_skill_preserves_image_and_caption_fail_closed_defaults(self) -> None:
        skill = (ROOT / "html-to-markdown" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("--allow-unprocessed-images", skill)
        self.assertIn("只有用户明确接受图片保持原样", skill)
        self.assertIn("已确认的 `<caption>` / `<figcaption>` 默认进入 strict", skill)
        self.assertIn("不会绕过外部资源、本地化失败、题注", skill)

    def test_html_skill_links_executable_contracts(self) -> None:
        skill = (ROOT / "html-to-markdown" / "SKILL.md").read_text(encoding="utf-8")

        for reference in (
            "@pipeline.py",
            "@preflight.py",
            "@contracts.py",
            "@formula_batch.py",
            "@image_disposition.py",
            "@markdown_fences.py",
        ):
            self.assertIn(reference, skill)


if __name__ == "__main__":
    unittest.main()
