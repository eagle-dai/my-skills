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
