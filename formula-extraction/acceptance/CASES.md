# 验收案例清单（公式回归防线）

真实公式退化案例登记于此。每条用**用户看到的症状**描述（不是实现术语），指向钉住它的测试。改动公式提取/后处理规则前先读这里，别让修好的东西再退化。

规则本身写在 `formula-extraction/self-improvement.md`、`katex-html-parser.md` 和 `SKILL.md`；实现在
`html-to-markdown/formula_batch.py`；这里只记「哪些真实翻车过、谁在守」。

---

## `\text{}` 里的下划线在 GitHub 上让整条公式渲染失败

**症状**：形如 `\text{signal_source}`、`\text{observed_at}` 的公式，本地 KaTeX 渲染正常，一推到 GitHub 就整条渲染报错或下标错位——读者看到公式变红或尾部缩成小下标。

**根因**：GitHub 的 MathJax 在 `\text{}`（text mode）里遇到裸 `_` 会当成非法数学下标；且 GitHub GFM 会先把 `$…$` 内可转义标点前的反斜杠剥掉再喂渲染器，所以简单的单反斜杠转义还会被还原。提取器必须在产出时就把 text-mode 的 `_` 转义成 `\_`。

**判据（机制信号，不靠猜文本）**：text mode 与 math mode 的转义强度不同——text mode 用单反斜杠 `\_`，math-mode 字面下划线用双反斜杠 `\\_`（gap #31）。两者不得混淆。

**期望**：
- text mode `signal_source` → `signal\_source`（单反斜杠）
- text mode `a_b`（表检测规则 `\text{a_b}` 命中）→ `a\_b`
- math mode 字面 `a_b` → `a\\_b`（双反斜杠，与 text mode 区分）
- 无特殊符的文本 `signal source 12` → 原样不动
- 真实数学下标 `x_i` / `x_2` / `x_{ij}` → 不被误判为标识符下标

**守卫**：
- `tests/test_formula_postprocess_rules.py::TextModeEscapeTests` — text-mode 转义（正例 + 反例）
- `tests/test_formula_postprocess_rules.py::MathModeUnderscoreTests` — 双闸对比：math vs text 转义强度
- `tests/test_formula_postprocess_rules.py::IdentifierSubscriptGuardTests` — 裸标识符误当下标的护栏
- `tests/test_acceptance_formula.py` — 端到端：`\text{signal_source}` 经提取产出转义后的 LaTeX

---

## 未落地的规则不算数

**症状**：`self-improvement.md` 表里有规则（如 Prime、double caret、Unicode 上下标），但代码里根本没实现，容易被误当成"已支持"。

**期望**：这些行在表里必须带 `[未实现-仅设计]` 标记；补了实现就去标记并加测试。

**守卫**：
- `tests/test_formula_postprocess_rules.py::UnimplementedRulesAreMarkedTests` — 强制"实现↔标记↔测试"三者同步
