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

## 进化原则加强（先于修复落地）

用户要求：先加强 skill 的进化元规则本身，把根因从制度上堵死，而不只补两个洞。分三处，全上。

### A. 硬化测试铁律（`_meta/skill-self-improvement.md` 闸 2）

现状：「每条可机器判定的规则**应该**落到测试」——「应该」是软约束，无人查，规则得以停在文档层。

改为硬门：任何写进文档的「必须 / 默认 / 守恒 / 居中 / 边界」类**效果规则**，同一 PR 内必须同时提交对应 CI 测试。只有文档、没有测试的规则视为**未完成，不许合并**。附自查一句：

> 问自己——这条规则如果被删，哪个测试会变红？答不上来，就是没落测试。

### B. 新增第三个病根（`_meta/skill-self-improvement.md` 病根表）

原两个病根：泛化不够、改坏旧样例。新增：

| 病根 | 症状 |
|------|------|
| **规则只停在文档层** | 文档郑重写了规则，但无对应测试；代码重写/进化时静默丢失，CI 沉默无警 |

本次两个退化正是此病根的实例。

### C. 用户话验收清单写进元规则

把「用户写中文效果 → Claude 翻译成 CI 测试」这套机制固化为长期约定，写进 `_meta/skill-self-improvement.md`：

- 用户维护 `<skill>/acceptance/CASES.md`（纯中文效果清单，用户唯一读写的文件）。
- 每条清单条目必须有对应 `tests/test_acceptance_*.py`，条目末尾标注测试名，用户可对号。
- 用户只描述「效果」，不描述实现（正则、selector、路由）；翻译成机器判断是 Claude 的职责。

### D. 元规则重构为「六步闭环」

用户提出七问框架（Why / Done / Proof / Anti / Bounds / Trade / Unknown）作为 skill 改进的验收骨架，并要求**深度融合、针对 skill 开发、用人话写**，不照抄。

判定：七问是通用项目管理框架，直接搬进来会与现有闸 1/闸 2/流程大量重叠。改为把 `_meta/skill-self-improvement.md` 整体重构成 skill 改进的**六步闭环**，七问溶进各环、不留独立形态：

```
① 想清为什么改 → ② 把规则写扎实 → ③ 每条规则配测试 → ④ 别走捷径糊弄
   ↑                                                      ↓
⑥ 验收+把教训存回来 ← ⑤ 守住边界、想好取舍、留好后路 ←──┘
```

- Why→①（含病根表照妖镜前置）；Done/Proof→②③⑥（复用闸 1/闸 2，不重写）。
- Anti→④「别走捷径糊弄」：捷径清单换成 skill 实际手法（改宽正则、只跑新增测试、删旧用例、文档假装配测试、伪造 converted 报告、textContent 假成功、随机数消重）。
- Bounds/Trade/Unknown→⑤：只改相关项不越界；取舍序改用 **skill 自己的价值序** `fail-closed > 结果可重复 > 结构守恒 > 覆盖 > 简洁`（速度剔出，靠 fast/strict 分流解决，不牺牲正确性换）；未知一律 fail-closed + 上报。
- 新增 ⑥ 的「教训回灌」——七问没有的一环：本轮新退化/新捷径反补进病根表或捷径清单，闭环才真正闭上。
- 全文用人话改写：黑话（双层落地/回灌/泛化不够）换口语；术语（fail-closed/strict/CI/CASES.md）保留但首次补大白话；开篇加导语说清「这规则解决什么、为什么 skill 特别容易坏」，并举本次题注/公式退化当实例。

### 后续（本次不做）

自动守卫：一个 `test_documentation_alignment` 风格的测试，自动扫描 `CASES.md` 每条是否都有对应 `test_acceptance_*`，缺失即红灯。本次先靠元规则铁律止血；守卫单列为后续任务。

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
