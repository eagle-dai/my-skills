# 验收案例清单（回归防线）

真实退化案例登记于此。每条用**用户看到的症状**描述（不是实现术语），指向钉住它的测试。改动转换规则前先读这里，别让修好的东西再退化。

规则本身写在 `html-to-markdown/conversion-rules.md` 和 `markdown_postprocess.py`；这里只记「哪些真实翻车过、谁在守」。

---

## 图/表下面的标题要居中

**症状**：图片、表格下面的题注（`图 6-1　数据证据门`、`表 6-1　行情数据的证据边界`）在 GitHub 上左对齐悬在内容块旁边，不居中，排版散。

**根因**：题注居中规则一度只活在 fast path，strict sub-agent 手工产出时漏掉；且规则曾被重写砍成几行泛泛之谈，丢了「命名性短标题才居中、讲解性长段落不居中」的判据。

**判据（机制信号，不靠猜文本）**：SingleFile 题注行是 `图/表 N-N` 后紧跟一个**全角空格 U+3000** 再接标题，整行独立成段。正文里的提及是 `图 6-1 把…`（半角空格 + 动词），没有全角空格锚点，因此不会被误命中。命中后包 `<div align="center">`，GitHub 认这个标签并居中。

**期望**：
- `表 6-1　标题` → `<div align="center">表 6-1　标题</div>`
- `图 6-1 把四类数据…画出来。`（半角空格正文提及）→ 原样不动
- 已经是 `<div align="center">` 包裹的 → 不重复包
- fenced code block 内长得像题注的行 → 不动

**守卫**：
- `tests/test_markdown_postprocess.py::CaptionCentering` — 规则本体（正例 + 4 反例）
- `tests/test_acceptance_caption_centering.py` — 图片 + figcaption 的 figure 必须路由 strict，不得 fast 吐纯文本
- `tests/test_pipeline_caption_routing.py` — caption 路由守恒

**未机械化（仍靠 conversion-rules.md + 人工）**：表格与短标题必须包**同一个** `<div align="center">`（只居中标题、表格不包 → 标题悬在左对齐表格上方）；长说明段落不居中（`公式 D-4 中，$\rho$ 为…` 267 字是段落不是题注）。

---

## 中文紧贴的行内公式，GitHub 里要能正常显示

**症状**：中文紧贴 `$` 的行内公式（`证据边界，$t_{obs}$ 为观测时间`、`定义 $P_{t}$：`）在 GitHub 上不渲染成数学，`$...$` 原样显示成美元符号加文本。

**根因**：GitHub 的行内数学要求 `$` 分隔符两侧是空白或特定标点；中文/全角标点直接贴 `$` 时 GitHub 不识别为数学。规则登记在 `self-improvement.md`，但一度没落到代码也没测试。

**判据**：CJK 或全角标点直接贴单个 `$`（非 `$$` 显示公式）时，在贴着的那一侧插一个半角空格。`$$` 显示公式分隔符不动，fenced code block 内不动。

**期望**：
- `收益率$r_t$表示` → `收益率 $r_t$ 表示`
- `（$w_t$）` → `（ $w_t$ ）`
- `see $r_t$ here`（已有半角空格）→ 原样不动
- `$$…$$` 显示公式贴中文 → 不拆
- code block 内 `价格$USD` → 不动

**守卫**：
- `tests/test_markdown_postprocess.py::CjkInlineMathSpacing` — 规则本体（正例 + 反例）
- `tests/test_acceptance_cjk_inline_math.py` — 端到端产物层

---

## 机械后处理门（两案例的公共执行入口）

上面两条能可靠机械化的部分都由 `markdown_postprocess.py` 执行，fast path 自动跑，strict Phase 3 用 CLI 跑：

```bash
python3 markdown_postprocess.py <交付>.md --check   # 不合规退出 1
python3 markdown_postprocess.py <交付>.md           # 就地修
```

守卫：`tests/test_markdown_postprocess.py::CommandLineInterface`（三态退出码契约）。

---

## 公式验证不用再手工搭 KaTeX

**症状**：`blocked` 于公式待验证时，主 agent 得手动往 `formula-validation.html` 注入 KaTeX（CDN 或本地），起 server 跑验证函数，再把结果 JSON 手抄回填——全流程最慢、最易错的一段。

**根因**：`formula-validation.html` 原来只有公式容器 + 验证函数，不带 runtime，也不自动跑。

**判据（机制信号）**：pipeline 把本地打包的 `assets/katex.min.js` 复制到 validation.html 同目录（相对引用，离线），validation.html `DOMContentLoaded` 后 auto-run `runFormulaValidation()`，结果写进 `window.__FORMULA_VALIDATION__`。只用 js 不带字体：`throwOnError` 只看 LaTeX 解析，与字体无关。runtime 没加载则保持 `completed:false`（fail closed），可回退手动注入。

**期望**：
- 主 agent 起 server 打开 validation.html → 直接读 `window.__FORMULA_VALIDATION__.completed===true` + `passed==total`，无需注入或手抄
- `validation_document()` 输出含 `src="katex.min.js"` + `DOMContentLoaded` auto-run，不引 CDN
- 验证语义（`githubMathUnescape` + `throwOnError`）不变 → `VALIDATOR_VERSION` 不 bump
- runtime 缺失 → `completed:false` + `load_error`，绝不伪装成功

**守卫**：
- `tests/test_validation_document.py` — 文档含本地 KaTeX 引用 + auto-run + fail-close + 版本未变；`copy_katex_runtime` 复制/幂等/缺源 fail-close

---

## 缺依赖直接崩，报错要能指路

**症状**：新环境首跑 `pipeline.py` 直接 `ModuleNotFoundError: numpy`，不知道要装什么、怎么装。

**判据**：CLI `main()` 在重 import 前试探关键依赖（numpy/cv2/PIL/bs4/lxml），缺失打印 requirements.txt 的 `uv` 安装命令并 exit 2。仅 CLI 生效，库调用方自管环境。

**守卫**：`tests/test_pipeline_deps.py`

---

## 多文档混进同一 `--output` 会互相覆盖

**症状**：两个 HTML 都 `--output dist`，第二个静默覆盖第一个的 `preflight/`、`formula-validation.html`、`.formula-cache.json`，第一个的失败公式记录丢失，无任何提示。

**判据**：`output.mkdir` 后扫已交付的**异名**包（`*.zip` stem / `<name>/files/` 子树），异于本次 `output_name` 即在 `report.json.output_collision` 列出。同名（resume）不算冲突。只警告不阻断不改路由。

**守卫**：`tests/test_pipeline_output_collision.py`

---

## 公式里带下划线的变量名，GitHub 里要能正常显示（别缩成下标）

**症状**：文章里 `field_coverage = valid_required_fields / required_fields` 这类块级公式（变量名里有下划线），在 GitHub 上下划线消失、下划线后面的部分缩成小小的下标（`field` 后面 `coverage` 变下标），看起来像乱码。更早的版本干脆卡在 `blocked` 交不出成品——公式一直等不到验证通过。

**根因**：GitHub 显示块级公式 `$$…$$` 时，会把公式里下划线前的单个反斜杠 `\_` 悄悄吃掉，交给数学渲染器时只剩裸下划线，渲染器就把它当"下标"符号。提取器原来只加**一个**反斜杠 → 被吃光 → 渲染错，且验证器（正确地）拦下这种会渲染错的形态 → 死锁在 blocked。

**判据**：提取器对公式里"变量名下划线"（不是真正的数学下标）产出**两个**反斜杠 `\\_`。GitHub 吃掉一个后还剩一个，数学渲染器就把它当**字面下划线**显示。真正的数学下标（`x` 底下带小 `i`）是另一套机制生成的，不受影响。

**期望**：
- `field_coverage`（公式里的变量名）→ 显示成 `field_coverage`，下划线在、不缩下标
- `valid_required_fields`（多个下划线）→ 每个下划线都在
- 真数学下标 `x_i`、`x_{ij}` → 原样正常显示成下标，不被误改
- 07/08 文章的分式公式 → pipeline 跑到 `converted` 出成品，GitHub 上分式 + 变量名都对（已真机验证）

**不该触发**：`\text{}` 里的下划线（另一套 text-mode 处理，gap #18/#20）；字面脱字符 `^`（保持既有 `\string^`）。

**守卫**：
- `tests/test_validation_document.py::test_map_text_escapes_literal_underscore_double_backslash` — 产出双反斜杠（规则本体）
- `tests/test_validation_document.py::test_map_text_double_backslash_multiple_underscores` — 多下划线
- `tests/test_validation_document.py::test_double_backslash_underscore_passes_github_guard` — 双反斜杠过验证门
- `tests/test_validation_document.py::test_single_backslash_underscore_still_fails_github_guard` — 单反斜杠（旧错形态）仍被拦
- `tests/test_validation_document.py::test_real_math_subscript_not_touched_by_map_text` — 真数学下标不被误伤

---

## 微信公众号文章能直接转，不再整篇卡死

**症状**：把微信公众号（mmbiz）保存的 SingleFile 页面丢进 pipeline，直接硬失败 `no unique semantic body found`，一个字都转不出来。这类页面里公式全是插图、图片下面挂着原始链接。

**根因**：skill 原本只认 `article`/`main`/`data-slate-editor` 这类语义正文容器，微信正文是固定的 `#js_content`，不在名单里 → 保守停下（行为对，但覆盖不到微信这一大来源）。另外微信的公式不是常见的 KaTeX，而是 MathJax 渲染的 SVG，原始 LaTeX 藏在外层 `data-formula` 属性里；图片则是真图已内联进 `src`（data-URI），只是残留了原始 CDN 地址在 `data-src`，被旧规则误当成"图还没加载"（lazy）而推去人工。

**判据（机制信号）**：
- 正文容器：`#js_content` / `.rich_media_content`（微信固定 id/class），排在语义 selector 之后，仍受"同一优先级只能唯一命中，否则歧义失败"的保守约束。
- 公式：`data-formula` 属性里的 LaTeX 原样可用（无需重建）；外层是 `<section ...display:block>` 就是块级 `$$…$$`，是 `<span>` 就是行内 `$…$`。
- 图片：`src` 是体量够大（解码 ≥512B）的 data-URI = 真图已内联，直接用，忽略残留的 `data-src`；只有 1px 占位符 / 空 `src` + 真 `data-src` 才是真 lazy，继续走人工。

**期望**：
- 微信文章（正文 + `data-formula` 公式 + data-URI 图）→ `converted`，块级公式出 `$$…$$`、行内出 `$…$`、图片进 `files/`
- 文章里没有 `data-formula` 的**真插图 SVG**（如统计图）→ 保守路由到 strict，由 Playwright 真浏览器截图成 PNG（cairosvg 会把中文渲成豆腐块，不可用）
- 已有 `<article>` 语义的旧页面 → 仍走 `article`，不被微信 selector 抢
- 两个 `.rich_media_content` 同时够长 → 仍歧义失败（不放松保守）
- 1px 占位 data-URI / 空 src + `data-src` → 仍判 lazy 走 strict

**不该触发**：真数学下标不受影响（公式走 `data-formula` verbatim，不经重建）；体量小的 data-URI（解码 <512B）+ 不同 `data-src` → 保守当 lazy 走 strict（宁可慢不猜错）。

**守卫**：
- `tests/test_preflight.py::WeChatMmbizTests` — 正文 selector（正例 + 语义优先 + 歧义失败 3 例）、`data-formula` 公式源（块/行内 + 插图 SVG 非公式 + KaTeX 旧源仍在）、data-URI 路由（真图优先 + 1px 占位仍 lazy + 空 src 仍 lazy）
- `tests/test_pipeline.py::WeChatMmbizPipelineTests::test_wechat_article_converts_with_formulas_and_data_uri_image` — 端到端 converted，块/行内公式与图片产物
- `tests/test_pipeline.py::WeChatMmbizPipelineTests::test_wechat_plain_svg_illustration_routes_to_strict` — 无 data-formula 插图 SVG 保守路由 strict
- `tests/test_pipeline.py::WeChatMmbizPipelineTests::test_wechat_span_wrapper_with_block_children_passes_through` — 微信 `<span data-tool>` 块级包裹透明穿透
- `tests/test_pipeline.py::WeChatMmbizPipelineTests::test_slate_typed_span_still_fails_closed` — slate 语义 span 仍保守 fail-close

**未机械化（仍靠人工）**：插图 SVG → PNG 的栅格化在 strict 里用 Playwright 做，本轮未做进确定性 pipeline；公式里 `\text{95\%}`、`\text{偏度 }` 这类 CJK/转义在真 GitHub 的渲染仍需肉眼验。
