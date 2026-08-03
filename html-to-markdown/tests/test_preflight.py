from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parent.parent
MODULE_PATH = SKILL / "preflight.py"
FIXTURE_PATH = SKILL / "tests" / "fixtures" / "preflight_article.html"
SPEC = importlib.util.spec_from_file_location("html_to_markdown_preflight", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_compacts_article_and_deduplicates_equivalent_formula_hashes(self) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8")

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["body"]["selector"], "article")
        self.assertEqual(result.manifest["recommended_mode"], "fast")
        self.assertLess(
            result.manifest["sizes"]["compact_bytes"],
            result.manifest["sizes"]["input_bytes"],
        )
        self.assertNotIn("<style", result.compact_html)
        self.assertNotIn("<script", result.compact_html)
        self.assertNotIn("Navigation", result.compact_html)
        self.assertIn('class="katex"', result.compact_html)
        self.assertIn("display", result.compact_html)
        self.assertEqual(result.manifest["counts"]["tables"], 1)
        self.assertEqual(result.manifest["counts"]["images"], 1)
        self.assertEqual(result.manifest["counts"]["formula_total"], 2)
        self.assertEqual(result.manifest["counts"]["formula_unique"], 1)
        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].source_kind, "data-uri")
        self.assertEqual(
            result.compact_root.decode(formatter="minimal"),
            result.compact_html,
        )

    def test_standalone_math_tex_signal_is_collected_during_preflight(self) -> None:
        html = """
        <html><body><article>
          <p>This substantial article body includes a standalone MathJax v2 source
          script that compaction cannot bind to a recognized formula container.</p>
          <script type="math/tex; mode=display">x^2</script>
        </article></body></html>
        """

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["recommended_mode"], "strict")
        self.assertEqual(
            result.manifest["signals"]["standalone_math_tex_scripts"],
            1,
        )
        self.assertTrue(
            any(
                "standalone math/tex script formulas" in reason
                for reason in result.manifest["signals"]["strict_reasons"]
            )
        )

    def test_virtualized_editor_recommends_strict(self) -> None:
        html = """
        <html><body><main>
          <p>This substantial article body has enough text to pass selection and
          contains a virtualized editor marker that requires strict inspection.</p>
          <div class="monaco-editor"><div class="view-lines">code</div></div>
        </main></body></html>
        """

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["recommended_mode"], "strict")
        self.assertTrue(result.manifest["signals"]["virtualized_editor"])
        self.assertIn(
            "virtualized editor markers detected",
            result.manifest["signals"]["strict_reasons"],
        )

    def test_distinct_lazy_source_recommends_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This substantial article body contains an image whose src is only a
          placeholder while data-src points to the real chart resource.</p>
          <img src="placeholder.gif" data-src="real-chart.png" alt="chart">
        </article></body></html>
        """

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["recommended_mode"], "strict")
        self.assertEqual(result.assets[0].source_kind, "lazy:data-src")
        self.assertTrue(result.assets[0].lazy)
        self.assertIn(
            "1 lazy or missing resource placeholders",
            result.manifest["signals"]["strict_reasons"],
        )

    def test_matching_lazy_source_does_not_force_strict(self) -> None:
        html = """
        <html><body><article>
          <p>This substantial article body contains duplicate source metadata, but
          both attributes identify exactly the same image resource.</p>
          <img src="chart.png" data-src="chart.png" alt="chart">
        </article></body></html>
        """

        result = preflight.build_preflight(html)

        self.assertEqual(result.manifest["recommended_mode"], "fast")
        self.assertEqual(result.assets[0].source_kind, "url")
        self.assertFalse(result.assets[0].lazy)

    def test_ambiguous_body_fails_closed(self) -> None:
        body = (
            "This is substantial article text that deliberately exceeds the "
            "minimum body threshold so ambiguity cannot be ignored by preflight."
        )
        html = f"<html><body><article>{body}</article><article>{body}</article></body></html>"

        with self.assertRaisesRegex(preflight.BodySelectionError, "ambiguous"):
            preflight.build_preflight(html)

    def test_writes_deterministic_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            first_result = preflight.run_preflight(FIXTURE_PATH, first_dir)
            second_result = preflight.run_preflight(FIXTURE_PATH, second_dir)

            self.assertEqual(first_result.manifest, second_result.manifest)
            for name in ("content.html", "manifest.json", "formulas.json", "assets.json"):
                self.assertEqual(
                    (first_dir / name).read_bytes(),
                    (second_dir / name).read_bytes(),
                )

            manifest = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.0")


# 一段 ≥512B 解码的 data-URI（SingleFile 内联真图的形态），和一个 1px 占位 data-URI。
_BIG_DATA_URI = "data:image/png;base64," + ("A" * 1076)  # 解码 ~807B，过 512 门槛
_TINY_DATA_URI = (
    "data:image/gif;base64,"
    "R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="  # 1px gif，解码 43B
)


class WeChatMmbizTests(unittest.TestCase):
    """微信公众号 (mmbiz) 页面支持：正文 selector、MathJax-SVG 公式源、data-URI 图路由。"""

    def _wechat(self, inner: str) -> str:
        return (
            "<html><body id='activity-detail'>"
            "<div id='js_article' class='rich_media'>"
            "<div id='js_content' class='rich_media_content'>"
            f"{inner}"
            "</div></div></body></html>"
        )

    # --- 正文 selector ---
    def test_wechat_js_content_selected_as_body(self) -> None:
        html = self._wechat(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "确保 #js_content 被唯一选中而不是回退到 strict inspection。</p>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.manifest["body"]["selector"], "#js_content")

    def test_semantic_article_still_wins_over_wechat_selector(self) -> None:
        # 反例：同时有 <article> 语义容器时，优先级更高的语义 selector 命中，
        # 微信 selector 不该抢先（保证不影响旧的语义页面）。
        html = (
            "<html><body><article>"
            "<p>This substantial semantic article body must be selected by the "
            "higher-priority article selector, not by any WeChat fallback rule.</p>"
            "</article></body></html>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.manifest["body"]["selector"], "article")

    def test_wechat_ambiguous_body_still_fails_closed(self) -> None:
        # 反例：两个 substantial 的 .rich_media_content 仍然 ambiguous 失败，
        # 不因新增 selector 而放松 fail-closed。
        block = (
            "<div class='rich_media_content'><p>这是足够长的微信正文文本块，"
            "长度越过 body 选择的最小文本阈值，用来制造两个同优先级的 substantial "
            "命中从而形成歧义，验证 fail-closed 不因新增 selector 而放松。</p></div>"
        )
        html = f"<html><body>{block}{block}</body></html>"
        with self.assertRaisesRegex(preflight.BodySelectionError, "ambiguous"):
            preflight.build_preflight(html)

    # --- MathJax-SVG 公式源 data-formula ---
    def test_data_formula_block_and_inline_sources(self) -> None:
        html = self._wechat(
            "<p>正文引入公式：块级公式随后给出，行内公式 "
            "<span data-formula='n'><svg role='img'></svg></span> 嵌在句中。"
            "这段文本足够长以越过 body 选择的最小文本阈值并让 preflight 正常运行，"
            "因此后面的公式收集逻辑能够按预期在渲染后的紧凑 DOM 上执行。</p>"
            "<section data-formula='R_t = \\frac{P_t}{P_{t-1}} - 1' "
            "style='text-align:center;display:block'><svg role='img'></svg></section>"
        )
        result = preflight.build_preflight(html)
        kinds = {f.source_kind for f in result.formulas}
        self.assertEqual(kinds, {"data-formula"})
        by_disp = {f.display: f for f in result.formulas}
        self.assertIn("block", by_disp)
        self.assertIn("inline", by_disp)
        # verbatim LaTeX 直接来自 data-formula 属性，无需 KaTeX 重建
        self.assertEqual(by_disp["block"].original_latex, "R_t = \\frac{P_t}{P_{t-1}} - 1")
        self.assertEqual(by_disp["inline"].original_latex, "n")

    def test_inline_formula_under_block_formula_ancestor_stays_inline(self) -> None:
        # 反例（PR review 发现）：块级 data-formula wrapper 若恰是某行内 data-formula
        # 的祖先，display:block 判定必须只看行内节点自身，不能被块级祖先污染成 block。
        html = self._wechat(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "随后构造一个块级公式 wrapper 内部嵌套一个行内公式的病态结构，"
            "用来验证 display 判定只看节点自身、不被块级祖先污染。</p>"
            "<section data-formula='A' style='text-align:center;display:block'>"
            "<svg role='img'></svg>"
            "<span data-formula='n'><svg role='img'></svg></span>"
            "</section>"
        )
        result = preflight.build_preflight(html)
        by_latex = {f.original_latex: f.display for f in result.formulas}
        # 外层 section 自身 display:block → block；内层 span 自身无 display:block → inline
        self.assertEqual(by_latex.get("A"), "block")
        self.assertEqual(by_latex.get("n"), "inline")

    def test_double_wrapped_same_latex_data_formula_counted_once(self) -> None:
        # mdnice/微信把公式包成两层相同 data-formula span（外层加 cursor:pointer
        # 点击效果）。两层 LaTeX 相同 → 是同一个公式，只应计一次，否则 formula_total
        # 虚高、下游守恒必然 blocked。区别于上面「父子不同 LaTeX」的合法嵌套。
        html = self._wechat(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "随后构造一个被双层相同 data-formula span 包装的行内公式，"
            "验证 preflight 只把它计为一个公式而非两个。</p>"
            "<span data-formula='\\hat{\\sigma}^2' style='cursor:pointer'>"
            "<span data-formula='\\hat{\\sigma}^2'><svg role='img'></svg></span>"
            "</span>"
        )
        result = preflight.build_preflight(html)
        latexes = [f.original_latex for f in result.formulas]
        self.assertEqual(latexes, ["\\hat{\\sigma}^2"])
        self.assertEqual(result.manifest["counts"]["formula_total"], 1)

    def test_substantial_data_uri_ignores_base64_whitespace_and_padding(self) -> None:
        # 反例（PR review 发现）：base64 payload 含换行/=padding 时，体量估算须先剥掉，
        # 否则空白撑大估值让 <512B 的占位图误过门槛。构造一个解码 <512B 但含大量换行的
        # data-URI + 真 data-src，期望仍判 lazy。
        import base64

        raw = base64.b64encode(b"\x89PNG" + b"x" * 200).decode()  # 解码 ~204B < 512
        wrapped = "\n".join(raw[i : i + 4] for i in range(0, len(raw), 4))  # 每4字符插换行
        tiny_but_whitespaced = "data:image/png;base64," + wrapped
        html = self._wechat(
            "<p>这是一篇足够长的微信公众号正文，用来越过 body 选择的最小文本阈值，"
            "图片 src 是含大量换行的小 data-URI（解码不足 512B），真图在 data-src。</p>"
            f"<img src='{tiny_but_whitespaced}' "
            "data-src='https://mmbiz.qpic.cn/real.png' alt='图片'>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.assets[0].source_kind, "lazy:data-src")
        self.assertTrue(result.assets[0].lazy)

    def test_plain_svg_without_data_formula_is_not_a_formula(self) -> None:
        # 反例：真插图 <svg>（无 data-formula wrapper）不该被当公式收集，
        # 交给 fast_converter 落到 unsupported <svg> → strict。
        html = self._wechat(
            "<p>下面是一张统计图插图，它是普通 SVG，没有 data-formula 属性，"
            "因此不应进入公式清单。这段正文足够长以越过 body 选择的最小文本阈值，"
            "保证 preflight 能正常选择正文容器并收集公式与资源清单。</p>"
            "<p><svg role='img' viewBox='0 0 720 480'><path d='M0 0'/></svg></p>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(len(result.formulas), 0)

    def test_katex_source_still_recognized(self) -> None:
        # 反例：旧的 KaTeX 源不受 data-formula 新增影响，仍正常识别。
        html = (
            "<html><body><article>"
            "<p>This substantial article body carries a KaTeX formula with an "
            "embedded TeX annotation that preflight must keep recognizing.</p>"
            "<span class='katex'><annotation encoding='application/x-tex'>a+b"
            "</annotation></span>"
            "</article></body></html>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(len(result.formulas), 1)
        self.assertEqual(result.formulas[0].source_kind, "annotation")
        self.assertEqual(result.formulas[0].original_latex, "a+b")

    # --- data-URI 图优先于残留 data-src ---
    def test_substantial_data_uri_src_wins_over_leftover_data_src(self) -> None:
        html = self._wechat(
            "<p>微信正文里的图片：src 已内联为完整 data-URI，data-src 只是残留的"
            " CDN 地址。这段文本足够长以越过 body 选择的最小文本阈值，"
            "确保图片资源路由逻辑能够在正常选中的正文容器上被执行到。</p>"
            f"<img src='{_BIG_DATA_URI}' data-src='https://mmbiz.qpic.cn/x.png' alt='图片'>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.assets[0].source_kind, "data-uri")
        self.assertFalse(result.assets[0].lazy)
        self.assertEqual(result.manifest["recommended_mode"], "fast")

    def test_tiny_data_uri_placeholder_with_data_src_still_lazy(self) -> None:
        # 反例：1px 占位 data-URI + 真 data-src = 真 lazy，仍走 strict。
        html = self._wechat(
            "<p>这里的图片 src 只是 1px 占位符，真图在 data-src，属于真正的 lazy。"
            "这段文本足够长以越过 body 选择的最小文本阈值，"
            "确保图片资源路由逻辑能够在正常选中的正文容器上被执行到。</p>"
            f"<img src='{_TINY_DATA_URI}' data-src='https://mmbiz.qpic.cn/real.png' alt='图片'>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.assets[0].source_kind, "lazy:data-src")
        self.assertTrue(result.assets[0].lazy)

    def test_empty_src_with_data_src_still_lazy(self) -> None:
        # 反例：空 src + data-src = 经典 lazy，不因 data-URI 规则被误放。
        html = self._wechat(
            "<p>图片 src 为空，真图在 data-src，是经典 lazy 占位。"
            "这段文本足够长以越过 body 选择的最小文本阈值，"
            "确保图片资源路由逻辑能够在正常选中的正文容器上被执行到。</p>"
            "<img src='' data-src='https://mmbiz.qpic.cn/real.png' alt='图片'>"
        )
        result = preflight.build_preflight(html)
        self.assertEqual(result.assets[0].source_kind, "lazy:data-src")
        self.assertTrue(result.assets[0].lazy)


class ProtectCodeIndentTests(unittest.TestCase):
    """缺陷 39:Slate 代码缩进(独立纯空白 slate-string 节点)被 BS4 折叠。
    解析前转 NBSP 保护。"""

    def test_multi_space_pure_node_becomes_nbsp(self) -> None:
        # ≥2 空格纯空白缩进节点 → NBSP(不折叠)
        html = 'x<span data-slate-string=true>            </span>y'
        out = preflight._protect_code_indent(html)
        self.assertIn("\xa0" * 12, out)
        self.assertNotIn("            ", out)

    def test_quoted_attr_variant(self) -> None:
        # 带引号属性形态也命中
        html = 'x<span data-slate-string="true">    </span>y'
        out = preflight._protect_code_indent(html)
        self.assertIn("\xa0\xa0\xa0\xa0", out)

    def test_single_space_untouched(self) -> None:
        # 单空格是正文正常空格,不是缩进 → 不动,免误伤正文
        html = 'a<span data-slate-string=true> </span>b'
        out = preflight._protect_code_indent(html)
        self.assertEqual(out, html)

    def test_node_with_code_untouched(self) -> None:
        # 含代码字符的节点(缩进+首词同节点)末尾非纯空格 → 不匹配,靠 BS4 内部
        # 前导空格保留机制,本函数不动它
        html = '<span data-slate-string=true>    merged = </span>'
        out = preflight._protect_code_indent(html)
        self.assertEqual(out, html)

    def test_roundtrip_survives_bs4_parse(self) -> None:
        # 端到端:NBSP 保护后经 BS4 解析,缩进完整存活,还原得回空格
        from bs4 import BeautifulSoup
        html = (
            '<div data-slate-type=code-line>'
            '<span data-slate-string=true>            </span>'
            '<span data-slate-string=true>"ok": True,</span></div>'
        )
        protected = preflight._protect_code_indent(html)
        text = BeautifulSoup(protected, "lxml").get_text()
        self.assertEqual(text.replace("\xa0", " "), '            "ok": True,')


if __name__ == "__main__":
    unittest.main()
