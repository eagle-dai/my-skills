# 人话验收清单 + 防退化机制 设计

日期：2026-07-28
分支：`fix/prevent-regression-acceptance-suite`
skill：`html-to-markdown`

## 一句话目标

用户只用**中文效果描述**维护一份验收清单；机器负责把每条效果变成 CI 自动测试；此后任何改动自动验，退化即红灯。用户永不接触内部实现（selector、正则、fast/strict 路由）。

## 触发本设计的两个退化

当前一次 html→md 转换里，两个曾修复过的功能重新暴露：

1. **题注居中丢失** —— 图/表下的 `<figcaption>`/`<caption>` 不再居中。
2. **inline 公式在 GitHub 渲染错误** —— 例 sec 4.1.1 `$t_{obs}$`，中文紧贴 `$` 时 GitHub 不渲染。

## 根因

**规则只停在文档层，从未进入 CI 测试。**

- 题注居中：`conversion-rules.md:118` / `checklist.md:144` 明确要求，但 `fast_converter.py:187-189` 把 `<figcaption>` 当纯文本吐出——既不居中，也不路由 strict。`table > caption` 有路由测试（`test_pipeline_caption_routing.py`），`<figcaption>` 是漏网的。
- CJK 公式空格：`self-improvement.md:23-31` 登记了正则和用例，但从没落成 `fast_converter` 实现，也没落成 pipeline 测试。

基础设施（unittest + GitHub Actions + `test_documentation_alignment.py`）**齐全**，但这两条规则从没被测试钉死。代码重写（commit `88db1ce` 引入 deterministic fast pipeline）时静默丢失，CI 因无对应测试而沉默。

**通用病根：文档写了「必须做」，但没有对应的自动化考题去查它做没做。**

## 机制设计

### 分层

```
用户层：中文效果清单（用户读写）      acceptance/CASES.md
  ↓  人负责翻译（Claude）
测试层：pipeline 级 CI 测试（机器执行） tests/test_acceptance_*.py
  ↓  CI 执行
守卫：GitHub Actions 每次 PR/push 跑，挂一条即红灯
```

### 用户层：`html-to-markdown/acceptance/CASES.md`

一份纯中文清单，每条一个「效果 → 样例 → 期望」。用户只维护这里。示例格式：

```markdown
## 图/表下面的标题要居中
- 样例：acceptance/fixtures/figcaption-basic.html
- 期望：图片下方的 figcaption 文字，在 GitHub Markdown 里居中显示
- 反例：正文长段落不许被误判成题注跟着居中

## 中文紧贴的行内公式，GitHub 里要能正常显示
- 样例：`收益率$r_t$表示`
- 期望：转出后变成 `收益率 $r_t$ 表示`（中文与 $ 之间有空格）
- 反例：代码块里的 $ 不许被动
```

每条清单条目对应一个 `tests/test_acceptance_*.py` 测试。CASES.md 里每条末尾标注它对应的测试名，用户能对上号。

### 测试层：把「效果」翻译成机器判断

关键：测试断言的是**用户能理解的效果**，不是内部机制。

- 「题注居中」→ 断言转出的 Markdown 里 figcaption 文字被居中包裹（或页面被正确路由到会做居中的流程），且反例长段落不受影响。
- 「CJK 公式加空格」→ 断言 `收益率$r_t$表示` 转出为 `收益率 $r_t$ 表示`；反例断言 fenced code block 内的 `$` 原样不动。

### 守卫

沿用现有 `.github/workflows/tests.yml`：`python -m unittest discover -s tests`。新测试自动被发现，无需改 CI 配置。

## 本次落地的两个修复

### 修复 1：figcaption 路由 strict

- 改 `fast_converter.py:187-189`：figcaption 不再当纯文本，检测到即 `raise FastPathUnsupported("figcaption requires strict caption handling")`，与 `table > caption` 对齐。
- 效果：带 figcaption 的页面路由 strict，由 strict 流程做居中 + caption ledger 守恒（文档本就如此规定）。
- 与文档一致：`SKILL.md` 0.3 节已声明「已确认的 figcaption 默认进入 strict」，代码此前未落实。

### 修复 2：CJK 紧贴 `$` 插空格

- 在 `fast_converter.py` 最终 Markdown 生成后加后处理 pass。
- 正则用 `self-improvement.md:25` 已登记的：`([一-鿿　-〿＀-￯])\$(?!\$)` 与 `(?<!\$)\$([一-鿿　-〿＀-￯])`。
- **陷阱处理**：先用 `markdown_fences.py` 剥离 fenced code block 再扫，避免误伤代码块内 `$`。这是 CJK 反例测试要覆盖的点。

## 测试计划

新增（用户视角命名，效果导向）：

1. `tests/test_acceptance_caption_centering.py`
   - 正例：带 figcaption 的页面不以 `converted`+纯文本题注收尾（被路由 strict / 居中）。
   - 反例：无题注的普通长段落页面照常 `converted`，不受影响。
2. `tests/test_acceptance_cjk_inline_math.py`
   - 正例：`收益率$r_t$表示` → `收益率 $r_t$ 表示`；`（$w_t$）` 同理。
   - 反例：`见 $r_t$ 公式`（已有空格）不重复插；fenced code block 内 `$...$` 原样不动。

两个测试都走 `pipeline.run_pipeline(..., mode="fast")` 端到端，与现有 `test_pipeline.py` 风格一致。

## 同步更新

- `self-improvement.md`：CJK 公式小节补注「已落 `tests/test_acceptance_cjk_inline_math.py`」；题注小节补注 figcaption 路由测试。
- `SKILL.md` / `conversion-rules.md`：确认 figcaption→strict 描述与代码一致（本就一致，无需改）。

## 未覆盖 / 已知边界

- 「居中」的最终视觉呈现仍需人工渲染验收（strict 流程输出）；本机制只保证 figcaption 不被 fast path 静默吞成纯文本。
- CASES.md 的清单条目需用户持续补充；机制只保证「已登记的效果不退化」，不保证发现未登记的新问题。
