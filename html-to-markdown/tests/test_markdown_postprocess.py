"""Regression + new-rule tests for markdown_postprocess.

Loads the sibling module by path (skill dir is not a package).
Run: python3 -m pytest tests/test_markdown_postprocess.py  (from skill dir)
  or: python3 tests/test_markdown_postprocess.py            (plain asserts)
"""
import atexit
import importlib.util
import shutil
import tempfile
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "markdown_postprocess", _SKILL / "markdown_postprocess.py"
)
mpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mpp)

pp = mpp.postprocess_markdown


# --- 规则1：题注居中 + 统一加粗 + 多行块级形态（间距修复）----------------
# 目标形态：多行居中块，内部用 Markdown ** / `code`（GitHub 会解析出 <p>，有 margin，
# 与后段自然分开）。gh api /markdown 实测：单行 div 无内部 <p>、后段贴太近。

_BLOCK = '<div align="center">\n\n{}\n\n</div>'


def test_bare_figure_caption_centered_and_bolded():
    # 图题源里无 **，命中后强制整题注加粗，包多行块
    out = pp("图 6-1　数据证据门")
    assert out == _BLOCK.format("**图 6-1　数据证据门**")


def test_bold_table_caption_centered():
    out = pp("**表 6-5　market_tickers 来源卡示例**")
    assert out == _BLOCK.format("**表 6-5　market_tickers 来源卡示例**")


def test_bold_figure_caption_centered():
    out = pp("**图 6-2　市场数据地图**")
    assert out == _BLOCK.format("**图 6-2　市场数据地图**")


def test_letter_numbered_bold_caption_centered():
    out = pp("**表 A-2　附录来源卡**")
    assert out == _BLOCK.format("**表 A-2　附录来源卡**")


def test_caption_block_has_blank_lines_for_spacing():
    # 间距修复核心：块内前后必须有空行（GitHub 才解析出带 margin 的 <p>）
    out = pp("**表 8-8　展示、指标与回测的放行矩阵**")
    assert out == '<div align="center">\n\n**表 8-8　展示、指标与回测的放行矩阵**\n\n</div>'


def test_prose_mention_not_centered():
    # 正文提及用半角空格，无 U+3000 锚点，不居中
    line = "图 6-1 把表 6-3 落到四张卡片上。"
    assert pp(line) == line


def test_already_centered_bare_figure_gets_bolded_and_blocked():
    # 上一轮单行 div 裸文本 → 归一成多行块 + 加粗
    line = '<div align="center">图 6-1　数据证据门</div>'
    assert pp(line) == _BLOCK.format("**图 6-1　数据证据门**")


def test_prev_singleline_strong_div_migrated_to_block():
    # 上一轮单行 <strong> div → 迁移成多行块（形态变了但内容等价）
    line = '<div align="center"><strong>图 6-1　数据证据门</strong></div>'
    assert pp(line) == _BLOCK.format("**图 6-1　数据证据门**")


def test_code_caption_centered_and_bolded():
    # 关键词集含 `代码`，代码题注也居中加粗
    out = pp("代码 8-1　normalize 入口")
    assert out == _BLOCK.format("**代码 8-1　normalize 入口**")


def test_code_caption_mixed_bold_and_inline_code():
    # 混排 **代码 N…：**`ident`**…**：多行块内用 Markdown，整题注一对 **，`code` 留在内
    line = "**代码 8-2　业务源码：**`normalize_candle`**外部 K 线行标准化入口**"
    out = pp(line)
    assert out == _BLOCK.format("**代码 8-2　业务源码：`normalize_candle`外部 K 线行标准化入口**")


def test_prev_singleline_div_with_code_tag_migrated():
    # 上一轮单行 div 含 <strong>/<code> → 迁移多行块，<code> 还原成 `code`
    line = (
        '<div align="center"><strong>代码 8-2　业务源码：</strong>'
        "<code>normalize_candle</code>"
        "<strong>外部 K 线行标准化入口</strong></div>"
    )
    out = pp(line)
    assert out == _BLOCK.format("**代码 8-2　业务源码：`normalize_candle`外部 K 线行标准化入口**")


def test_bare_figure_caption_with_inline_code():
    # 裸图题内含行内代码：多行块内 `main` 保留反引号（会被 Markdown 解析）
    out = pp("图 3-1　`main` 调用图")
    assert out == _BLOCK.format("**图 3-1　`main` 调用图**")


def test_prewrapped_singleline_div_bold_migrated():
    # 上一轮单行 div 内残留 ** → 迁移多行块
    line = '<div align="center">**表 8-8　展示、指标与回测的放行矩阵**</div>'
    out = pp(line)
    assert out == _BLOCK.format("**表 8-8　展示、指标与回测的放行矩阵**")


def test_multiline_block_idempotent():
    # 已是多行块 → 幂等，不重复包
    line = '<div align="center">\n\n**表 8-8　放行矩阵**\n\n</div>'
    assert pp(line) == line


def test_multiline_block_with_code_idempotent():
    line = '<div align="center">\n\n**代码 8-2　业务源码：`normalize_candle`入口**\n\n</div>'
    assert pp(line) == line


def test_centered_table_block_preserved_not_nested():
    # PR #55 review 抓到的回归：标题+表格同包一个居中 div，题注行不得被二次包成
    # 嵌套 div（否则标题从表格里拆出来）。整块必须原样保留。
    src = (
        '<div align="center">\n\n'
        "**表 8-8　放行矩阵**\n\n"
        "| 列 | 列 |\n| --- | --- |\n| a | b |\n\n"
        "</div>\n\n后段。"
    )
    out = pp(src)
    assert out == src  # 整块不动
    assert out.count('<div align="center">') == 1  # 无嵌套 div


def test_centered_image_block_preserved():
    # 居中图片块（多行内容，非单行题注）→ 整块原样保留
    src = '<div align="center">\n\n![](files/x/a.webp)\n\n</div>'
    assert pp(src) == src


def test_unterminated_center_div_not_mangled():
    # 无配对 </div>（不完整）：不吞后续内容，起始行原样、后面照常处理
    src = '<div align="center">\n\n普通段落没有闭合。'
    assert pp(src) == src


# --- 规则2：独立成段公式 → $$ 块级 ---------------------------------------

def test_standalone_formula_becomes_block():
    out = pp(r"$C = \frac{n_{valid}}{n_{expected}}$")
    assert out == r"$$C = \frac{n_{valid}}{n_{expected}}$$"


def test_standalone_formula_with_greek():
    out = pp(r"$Δt = t_{now} - t_{obs}$")
    assert out == r"$$Δt = t_{now} - t_{obs}$$"


def test_inline_formula_in_prose_untouched():
    # $ 开头但不以 $ 结尾（后有中文）→ 不改
    line = "- 时间类变量： $t_{obs}$ 为数据观测时间。"
    assert pp(line) == line


def test_multi_formula_line_untouched():
    # $s_{i}$ 开头但整行不是单个公式 → 不改
    line = "$s_{i}$ 、 $e_{i}$ 分别代表第 i 类数据源观测窗口起止时间："
    # 该行以中文结尾，非 $ 结尾；即便首尾都是 $ 也因中间夹文字排除
    assert pp(line) == line


def test_already_block_formula_untouched():
    line = r"$$C = \frac{a}{b}$$"
    assert pp(line) == line


def test_formula_inside_fence_untouched():
    md = "```\n$C = a$\n```"
    assert pp(md) == md


# --- 规则3：变量↔标识符映射公式拆分（缺陷 #16） -------------------------
import sys as _sys
if str(_SKILL) not in _sys.path:
    _sys.path.insert(0, str(_SKILL))
_fb_spec = importlib.util.spec_from_file_location(
    "formula_batch", _SKILL / "formula_batch.py"
)
_fb = importlib.util.module_from_spec(_fb_spec)
_sys.modules["formula_batch"] = _fb
_fb_spec.loader.exec_module(_fb)
split = _fb.split_text_mapping_formula


def test_split_basic_mapping():
    assert split(r"t_{obs} \leftarrow \text{observed\_at}") == ("t_{obs}", "observed_at")


def test_split_restores_underscore():
    assert split(r"n_{valid} \leftarrow \text{valid\_rows}") == ("n_{valid}", "valid_rows")


def test_split_single_letter_var():
    assert split(r"A \leftarrow \text{windows\_overlap}") == ("A", "windows_overlap")


def test_split_ident_without_underscore():
    assert split(r"x \leftarrow \text{count}") == ("x", "count")


def test_no_split_plain_formula():
    assert split(r"C = \frac{n_{valid}}{n_{expected}}") is None


def test_no_split_rightarrow():
    # 只拆 \leftarrow，不碰 \rightarrow
    assert split(r"a \rightarrow \text{b}") is None


def test_no_split_math_structure_in_text():
    # 右侧 \text{} 内含数学结构 → 不拆（保守）
    assert split(r"a \leftarrow \text{x_{i}}") is None


def test_no_split_missing_text():
    assert split(r"a \leftarrow b") is None


def test_no_split_chained_leftarrow():
    # 链式映射：行尾 $ 锚导致 ident 吃进中间 `} \leftarrow \text{`，必须拒绝
    assert split(r"y \leftarrow \text{count} \leftarrow \text{n}") is None


def test_no_split_backtick_in_ident():
    # 反引号会提前闭合 emit 的行内代码 span，拒绝
    assert split(r"x \leftarrow \text{a`b}") is None


def test_no_split_stray_brace_in_ident():
    # ident 含杂散 } → 非单个纯标识符，拒绝
    assert split(r"x \leftarrow \text{a}b}") is None


# --- 规则4：作者开头/结尾寒暄去除（保守，只删纯寒暄整段） -----------------

def test_opener_greeting_removed():
    md = "你好，我是袁从德。\n\n第 5 讲我们划清了安全边界。"
    assert pp(md) == "第 5 讲我们划清了安全边界。"


def test_closer_greeting_removed():
    md = "- 实践题：写一张来源卡。\n\n期待你的分享，我们下节课再见！"
    assert pp(md) == "- 实践题：写一张来源卡。"


def test_opener_and_closer_both_removed():
    md = (
        "你好，我是袁从德，欢迎来到《数据课》。\n\n"
        "正文第一段。\n\n"
        "正文最后一段。\n\n"
        "如果今天的课程让你有所收获，欢迎转发给有需要的朋友，我们下节课再见！"
    )
    assert pp(md) == "正文第一段。\n\n正文最后一段。"


def test_daijia_hao_opener():
    md = "大家好！\n\n今天讲第一课。"
    assert pp(md) == "今天讲第一课。"


# 反例：不该误删

def test_body_first_paragraph_not_removed():
    # 正文首段不是自我介绍，保留
    md = "第 5 讲我们划清了边界。\n\n第二段。"
    assert pp(md) == md


def test_thinking_questions_not_removed():
    # 结尾是思考题（列表），不是寒暄，必须保留
    md = "正文。\n\n- 概念题：为什么不能拼成同一时点事实？"
    assert pp(md) == md


def test_ni_hao_midbody_not_removed():
    # 正文里偶然出现「你好」不在段首自我介绍句式，保留
    md = "第一段。\n\n用户输入「你好」时系统应回显。"
    assert pp(md) == md


def test_closer_with_substance_kept_heading():
    # 末段是 heading 结构（有信息量），即使含「再见」字样也不删
    md = "正文。\n\n## 我们下次再见时要掌握的技能"
    assert pp(md) == md


def test_body_mention_of_share_not_removed():
    # 正文讨论「转发」机制，非求转发寒暄段首，保留（段首非道别）
    md = "正文。\n\n转发功能的实现见第 3 节。"
    assert pp(md) == md


# 误删反例（review 实证的坑：closer 子串命中 / opener 反问 / 单换行分段）

def test_body_jingqing_qidai_not_removed():
    # 正文以「敬请期待」收尾，但不是纯客套道别行 → 保留
    md = "新版本正在开发中，敬请期待。"
    assert pp(md) == md


def test_body_xiajieke_mention_not_removed():
    # 正文句中含「下节课见」但不以强道别收尾 → 保留
    md = "我们会在下节课见到更多例子来说明这一点。"
    assert pp(md) == md


def test_body_dianzan_zhuanfa_not_removed():
    # 末段讲「点赞/收藏/转发」是互动机制，非求转发寒暄 → 保留
    md = "正文。\n\n点赞、收藏、转发是三个核心互动。"
    assert pp(md) == md


def test_rhetorical_opener_not_removed():
    # 反问句「你好我是谁？」以问号收尾，不是自我介绍 → 保留
    md = "你好我是谁？这是本讲要回答的问题。\n\n正文。"
    assert pp(md) == md


def test_single_newline_opener_keeps_body():
    # opener 与正文用单 \n 同块：只删 opener 行，保留正文
    md = "你好，我是张三。\n正文内容在这里。"
    assert pp(md) == "正文内容在这里。"


def test_single_newline_closer_keeps_body():
    # closer 与正文用单 \n 同块：只删 closer 行，保留正文
    md = "正文内容在这里。\n我们下节课再见！"
    assert pp(md) == "正文内容在这里。"


def test_crlf_normalized_and_greeting_removed():
    # CRLF 文档：归一化后寒暄删除，正文不残留 \r
    md = "你好，我是李四。\r\n\r\n第一段正文。\r\n\r\n第二段正文。"
    out = pp(md)
    assert "\r" not in out
    assert "李四" not in out
    assert out == "第一段正文。\n\n第二段正文。"


def test_all_greeting_document_not_emptied_to_none():
    # 极端：整篇就一行 opener，删后不崩（返回空串可接受，但不能抛异常）
    out = pp("大家好！")
    assert out == "" or out == "大家好！"


# 静默丢正文回归（按句剥离，不整行删）：单行「实质正文 + 道别/开场白」混排

def test_closer_line_with_leading_substance_kept():
    # 行尾是道别句，但同一行前面有实质结论 → 只删道别句，保留结论（曾整行删丢正文）
    md = "重要结论：算法收敛。我们下节课再见！"
    assert pp(md) == "重要结论：算法收敛。"


def test_opener_line_with_trailing_substance_kept():
    # 行首是开场白句，但同一行后面有实质正文 → 只删开场白句，保留正文
    md = "你好，我是张三。这是本讲的核心正文，非常重要。"
    assert pp(md) == "这是本讲的核心正文，非常重要。"


def test_daijia_hao_opener_same_line_body_kept():
    md = "大家好！今天讲第一课，内容很关键。"
    assert pp(md) == "今天讲第一课，内容很关键。"


def test_whole_sentence_closer_still_removed():
    # 整句都是求转发+道别客套（无实质信息）→ 仍整句删掉
    md = "如果今天的课程让你有所收获，欢迎转发给有需要的朋友，我们下节课再见！"
    assert pp(md) == ""


def test_bold_wrapped_opener_removed():
    # 整行 ** 加粗包裹的开场白 → 脱壳后按句删（行首是 * 不能当列表跳过）
    md = "**你好，我是张三。**\n\n正文。"
    assert pp(md) == "正文。"


def test_bold_wrapped_closer_removed():
    md = "正文。\n\n**我们下节课再见！**"
    assert pp(md) == "正文。"


def test_bold_wrapped_partial_keeps_survivor_bold():
    # 加粗行里开场白句 + 正文句 → 删开场白句，幸存正文重新包 **
    md = "**你好，我是张三。这是本讲核心。**"
    assert pp(md) == "**这是本讲核心。**"


def test_bold_non_greeting_not_touched():
    # 加粗正文（非寒暄）保持不动
    md = "**加粗正文，不是寒暄，很重要。**"
    assert pp(md) == md


# --- 规则5：残留公式占位符护栏（fail-closed） ---------------------------

def test_find_residual_formula_placeholder():
    hits = mpp.find_residual_formula_placeholders("正文\n{{FORMULA:formula-0001}}\n更多")
    assert hits == [(2, "{{FORMULA:formula-0001}}")]


def test_placeholder_inside_fence_ignored():
    md = "```\n{{FORMULA:formula-0001}}\n```"
    assert mpp.find_residual_formula_placeholders(md) == []


def test_residual_formula_placeholder_blocks_check(tmp_path=None):
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        os.write(fd, "第一段\n\n{{FORMULA:formula-0001}}\n".encode("utf-8"))
        os.close(fd)
        assert mpp.main([path, "--check"]) == 1        # check 阻断
        assert mpp.main([path]) == 1                   # apply 也阻断，不静默写盘
    finally:
        os.unlink(path)


def test_clean_file_passes_check(tmp_path=None):
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        # 合规形态：字面下划线用**双**反斜杠 `\\_`（gap #31 提取器侧产出 / gap #38 后处理侧
        # 幂等保持）。GitHub GFM 剥一层 → `\_` → MathJax 字面下划线 = 对。`\frac` 是命令
        # （`\`+字母），两形态都保留。注意源串里 `\\\\_` 是 Python 字面两反斜杠 `\\_`。
        os.write(fd, "$$\nfield\\\\_coverage = \\frac{a}{b}\n$$\n".encode("utf-8"))
        os.close(fd)
        assert mpp.main([path, "--check"]) == 0
    finally:
        os.unlink(path)


# --- 规则6：CJK 行内公式两侧加空格（自根 tests/ 并入）--------------------
# GitHub 渲染 CJK 紧贴 $…$ 会吞掉分隔，两侧补半角空格；ASCII 已有空格不动，
# $$ 展示块与 fence 内的 $ 不碰。


def test_cjk_both_sides_get_space():
    assert pp("收益率$r_t$表示\n") == "收益率 $r_t$ 表示\n"


def test_fullwidth_paren_gets_space():
    assert pp("（$w_t$）\n") == "（ $w_t$ ）\n"


def test_ascii_spaced_is_left_alone():
    assert pp("see $r_t$ here\n") == "see $r_t$ here\n"


def test_display_dollar_pair_untouched():
    # $$ 展示分隔紧邻 CJK 不得被拆
    text = "结论\n\n$$\nx=1\n$$\n"
    assert pp(text) == text


def test_dollar_inside_fence_untouched():
    text = "前言\n\n```bash\necho 价格$USD 变量\n```\n"
    out = pp(text)
    assert "价格$USD" in out
    assert "价格 $USD" not in out


# --- 规则6b：NBSP 紧贴 $ 换成半角空格（gap#37，微信 mmbiz 真机验证）--------
# U+00A0 NBSP 紧贴 $ 时 GitHub 不认作行内公式边界 → 公式字面显示。换成 ASCII 空格。

_NB = " "  # NBSP


def test_nbsp_before_dollar_becomes_ascii_space():
    # 正例：NBSP 在 $ 前（微信正文分隔符），换成半角空格后 GitHub 能渲染
    assert pp(f"有{_NB}$n$ 个\n") == "有 $n$ 个\n"


def test_nbsp_after_dollar_becomes_ascii_space():
    # 正例：NBSP 在 $ 后
    assert pp(f"见 $n${_NB}个\n") == "见 $n$ 个\n"


def test_nbsp_both_sides_of_inline_formula():
    # 正例：两侧都是 NBSP（微信最常见形态）
    assert pp(f"有{_NB}$n${_NB}个\n") == "有 $n$ 个\n"


def test_nbsp_not_touching_dollar_untouched():
    # 反例：NBSP 不紧贴 $（正文里的 NBSP）保留不动
    assert pp(f"价格{_NB}上涨了\n") == f"价格{_NB}上涨了\n"


def test_nbsp_not_adjacent_to_dollar_preserved():
    # 反例：NBSP 不紧贴 $（跨了换行/在别处）不被规则触碰
    text = f"结论{_NB}\n\n$$\nx=1\n$$\n"
    out = pp(text)
    assert "$$\nx=1\n$$" in out          # 展示块完整
    assert f"结论{_NB}" in out            # 非相邻 NBSP 保留


def test_nbsp_dollar_inside_fence_untouched():
    # 反例：fence 内的 NBSP+$ 不碰
    text = f"前言\n\n```bash\necho 价格{_NB}$USD\n```\n"
    out = pp(text)
    assert f"价格{_NB}$USD" in out


# --- 规则7：相邻加粗拼成的 **** 接缝去除（自根 tests/ 并入）---------------


def test_quad_star_seam_removed():
    # 相邻 bold span 拼成四星，GitHub 渲染错误 → 去接缝
    assert pp("**表 1-4****置信度**\n") == "**表 1-4置信度**\n"


def test_normal_bold_untouched():
    assert pp("这是**重点**内容\n") == "这是**重点**内容\n"


def test_quad_star_inside_fence_untouched():
    text = "说明\n\n```\na****b\n```\n"
    assert pp(text) == text


# --- 规则1 补充：题注居中的裸表 / 裸字母编号 / fence 反例（自根 tests/ 并入）


def test_bare_table_caption_centered():
    # 裸表题注（区别于已覆盖的裸图题注）：走 bare 路径 + 表关键词
    assert pp("表 6-1　行情数据的证据边界\n") == (
        '<div align="center">\n\n**表 6-1　行情数据的证据边界**\n\n</div>\n'
    )


def test_bare_letter_numbered_caption_centered():
    # 裸字母编号题注（区别于已覆盖的加粗字母编号）：钉住 X-Y 的 X 可为字母
    assert pp("图 D-1　附录数据地图\n") == (
        '<div align="center">\n\n**图 D-1　附录数据地图**\n\n</div>\n'
    )
    assert pp("表 A-2　字母编号来源卡\n") == (
        '<div align="center">\n\n**表 A-2　字母编号来源卡**\n\n</div>\n'
    )


def test_caption_like_line_inside_fence_untouched():
    # 反例：代码块内长得像题注的行不动
    text = "说明\n\n```\n表 6-1　伪装成题注的代码行\n```\n"
    assert pp(text) == text


def test_letter_numbered_prose_mention_not_centered():
    # 反例：字母编号的正文提及是半角空格 + 讲解长句，无全角空格锚点，不居中
    line = "图 D-1 给出本讲核心知识地图。它不是要求每次都画图，而是提醒复核者。\n"
    assert pp(line) == line


# --- 规则8：CLI 三态退出码契约（自根 tests/ 并入）-------------------------
# strict Phase 3 用 CLI 跑机械后处理门；--check 只读不改，无 --check 原地修复。


def _write_delivery(text: str) -> Path:
    # plain-assert 风格无 unittest fixture，用 atexit 在进程结束时清理临时目录，
    # 避免每跑一次测试就漏一个 mkdtemp 目录。
    directory = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, directory, True)
    path = Path(directory) / "delivery.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_check_compliant_exits_zero_and_leaves_file():
    # 合规输入 = 已是多行居中块（当前目标形态）
    path = _write_delivery('<div align="center">\n\n**表 6-1　标题**\n\n</div>\n')
    original = path.read_text(encoding="utf-8")
    assert mpp.main([str(path), "--check"]) == 0
    assert path.read_text(encoding="utf-8") == original


def test_check_noncompliant_exits_one_and_leaves_file():
    # 退化产物：CJK 紧贴 $ + 未居中题注。--check 不改文件，只报退出 1。
    path = _write_delivery("表 6-1　标题\n收益率$r_t$表示\n")
    original = path.read_text(encoding="utf-8")
    assert mpp.main([str(path), "--check"]) == 1
    assert path.read_text(encoding="utf-8") == original


def test_fix_rewrites_file_in_place():
    path = _write_delivery("表 6-1　标题\n收益率$r_t$表示\n")
    assert mpp.main([str(path)]) == 0
    fixed = path.read_text(encoding="utf-8")
    assert '<div align="center">\n\n**表 6-1　标题**\n\n</div>' in fixed
    assert "收益率 $r_t$ 表示" in fixed


def test_missing_file_exits_two():
    assert mpp.main(["/no/such/file.md", "--check"]) == 2


# --- 规则9：数学段反斜杠加倍（gap #38，GitHub GFM strip 真机验证）----------
# GitHub GFM 在 $…$ / $$…$$ 内剥掉 `\`+ASCII标点 一层再喂 MathJax：矩阵/cases 换行
# `\\`、`\,` `\;` `\%` 等都掉一层。数学 span 内把该双写的双写；`\`+字母（命令
# \sigma \frac）不动。与 gap #31（提取器侧 _map_text 已产出 `\\_`）幂等兼容——`\\_`
# 不能被再翻成 `\\\\_`（follow 字符区分：换行 `\\` 后是空格→双写，`\\_` 后是 `_`→不动）。
# 规则见 conversion-rules.md / self-improvement.md gap #38。


def test_block_matrix_rowbreak_doubled():
    # 正例：块级矩阵换行 `\\`（k=2，后接空格）→ `\\\\`，GitHub 剥一层后 MathJax 收 `\\`
    text = "$$\n\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}\n$$\n"
    out = pp(text)
    assert "\\\\\\\\" in out                  # 换行翻成四反斜杠
    assert "\\begin{pmatrix}" in out          # \begin 命令不动
    assert out.count("$$") == 2               # 定界符完整


def test_cases_block_rowbreak_doubled():
    text = "$$\n\\begin{cases} x & a \\\\ y & b \\end{cases}\n$$\n"
    out = pp(text)
    assert "\\\\\\\\" in out
    assert "\\begin{cases}" in out


def test_inline_thin_space_doubled():
    # 行内 `\,` thin space（k=1，后接空格）→ `\\,`。CJK 空格规则也会在 $ 边界补空格。
    out = pp("见 $a \\, b$ 处\n")
    assert "\\\\," in out                     # thin space 双写
    assert "$a" in out and "b$" in out        # 公式内容在


def test_inline_backslash_percent_doubled():
    # 行内 `\%`（k=1，后接非反斜杠标点）→ `\\%`
    out = pp("涨了 $50\\%$ 呢\n")
    assert "\\\\%" in out


def test_backslash_before_letter_untouched():
    # 反例：`\`+字母 是命令，不动
    text = "见 $\\sigma + \\alpha$ 处\n"
    out = pp(text)
    assert "\\sigma" in out and "\\alpha" in out
    assert "\\\\sigma" not in out             # 没被误双写


def test_frac_command_untouched():
    text = "$$\n\\frac{a}{b}\n$$\n"
    assert pp(text) == text                   # 纯命令，无 `\`+标点 → 完全不变


def test_gap31_double_underscore_not_requadrupled():
    # 关键非干扰：gap #31 已产出 `\\_`（k=2，后接 `_` 标点）→ 保持 `\\_`，不翻成 `\\\\_`
    text = "$$\nfield\\\\_coverage = x\n$$\n"   # 源含 `\\_`（Python 里 \\\\ = 字面两反斜杠）
    out = pp(text)
    assert "field\\\\_coverage" in out         # 仍是两反斜杠
    assert "\\\\\\\\_coverage" not in out       # 没变四反斜杠


def test_backslash_doubling_idempotent():
    # 幂等：矩阵块跑两次不再增长
    text = "$$\n\\begin{pmatrix} a \\\\ b \\end{pmatrix}\n$$\n"
    once = pp(text)
    assert pp(once) == once
    # gap #31 `\\_` 双跑也不增长
    g31 = "$$\nfield\\\\_coverage\n$$\n"
    once31 = pp(g31)
    assert pp(once31) == once31


def test_math_backslash_inside_fence_untouched():
    # fence 内的 `$$ a \\ b $$` 既不翻块状态也不改写
    text = "前言\n\n```python\n$$ a \\\\ b $$\n```\n"
    out = pp(text)
    assert "$$ a \\\\ b $$" in out            # 原样，换行没被双写
    assert "\\\\\\\\" not in out


def test_prose_backslash_untouched():
    # 数学 span 外的反斜杠（Windows 路径、转义 markdown）绝不动
    text = "路径 C:\\Users\\dy 和 \\*not italic\\* 文本\n"
    assert pp(text) == text


def test_display_dollar_block_toggle_and_double():
    # 多行 $$ 块：`$$`-only 行正确 toggle，内部换行双写
    text = "结论\n\n$$\na \\\\ b\n$$\n\n后文\n"
    out = pp(text)
    assert "a \\\\\\\\ b" in out              # 块内换行双写
    assert "结论" in out and "后文" in out      # 块外文本不动


def test_rowbreak_then_command_no_space_doubled():
    # PR review finding 1：换行 `\\` 后紧跟命令（无空格）`\\alpha`（k=2+字母）——这是
    # 「换行 + alpha 命令」，换行 `\\` 仍须双写成 `\\\\`（GitHub 剥一层 → `\\` 换行 +
    # `\alpha` 命令）。不能因 follow 是字母就当命令保持 k=2（那样换行会丢）。
    bs = "\\"
    text = "$$\na " + bs * 2 + "alpha\n$$\n"   # 源含两反斜杠 + alpha
    out = pp(text)
    assert "a " + bs * 4 + "alpha" in out       # 换行双写成四反斜杠
    assert pp(out) == out                        # 幂等


def test_unbalanced_display_math_does_not_pollute_prose():
    # PR review finding 2：未闭合 `$$`（奇数个定界符）不得让块状态泄漏到文件尾，
    # 把后续正文的 `\*` `\%` 等 markdown 转义误双写。护栏=不平衡则放弃本 pass 返回原文。
    bs = "\\"
    text = "$$\nx=1\n\n正文 " + bs + "*斜体" + bs + "* 和 30" + bs + "% 折扣\n"
    out = pp(text)
    assert bs + "*斜体" + bs + "*" in out        # 正文转义星号不动
    assert "30" + bs + "% 折扣" in out            # 正文转义百分号不动
    assert bs * 2 + "*" not in out               # 没被误双写


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
