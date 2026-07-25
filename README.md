# my-skills

一组面向 AI coding agent 的自定义 skills。当前仓库主要解决两类相互关联的任务：

1. 将 SingleFile 保存的完整网页转换为结构清晰、可离线阅读且可审计的 Markdown 包；
2. 从 KaTeX、MathJax 或 MathML 公式节点中提取语义正确的 LaTeX。

仓库强调内容完整性、可执行合同、fail-closed 路由，以及修改 skill 时的回归保护。

## Skills

| Skill | 入口 | 用途 |
|---|---|---|
| `html-to-markdown` | [`html-to-markdown/SKILL.md`](html-to-markdown/SKILL.md) | 默认先运行确定性 `pipeline.py --mode auto`，对可支持的静态 SingleFile 执行 compact snapshot、公式批处理、结构守恒和确定性打包；Notebook、虚拟化、lazy-load、题注、默认图片处理合同或其他歧义则进入 Playwright/sub-agent strict 工作流。 |
| `formula-extraction` | [`formula-extraction/SKILL.md`](formula-extraction/SKILL.md) | 从 KaTeX、MathJax 或 MathML 公式节点中提取 LaTeX。单节点模式优先读取原始语义来源；页面级批处理由 `html-to-markdown/formula_batch.py` 负责去重、缓存和浏览器验证门禁。 |

`html-to-markdown` 在处理公式密集页面时引用 `formula-extraction` 的规则；可执行的批量解析、缓存和验证合同位于 `html-to-markdown/formula_batch.py`。

## 关键目录与文件

```text
.
├── README.md
├── requirements.txt
├── .github/workflows/tests.yml
├── _meta/skill-self-improvement.md
├── formula-extraction/
│   ├── SKILL.md
│   ├── katex-html-parser.md
│   └── self-improvement.md
├── html-to-markdown/
│   ├── SKILL.md
│   ├── pipeline.py
│   ├── pipeline.md
│   ├── benchmark.py
│   ├── preflight.py
│   ├── preflight.md
│   ├── fast_converter.py
│   ├── formula_batch.py
│   ├── pipeline_utils.py
│   ├── contracts.py
│   ├── image_disposition.py
│   ├── markdown_fences.py
│   └── ...
└── tests/
    ├── fixtures/
    ├── test_pipeline.py
    ├── test_formula_batch.py
    ├── test_preflight.py
    ├── test_benchmark.py
    └── ...
```

### `_meta/`

跨 skill 共享的维护规则。

- `skill-self-improvement.md`：说明如何从真实缺陷提炼可泛化规则，并要求规则、实现、测试和文档同步更新。

### `formula-extraction/`

- `SKILL.md`：单节点与页面级 batch 的职责边界、提取优先级、语义退化检查和 fail-closed 行为。
- `katex-html-parser.md`：没有原始 LaTeX/MathML 时，从 KaTeX HTML 结构重建公式的参考规则。
- `self-improvement.md`：公式命令边界、Unicode 转换和平台差异等回归用例。

### `html-to-markdown/`

- `SKILL.md`：agent 的实际入口。Phase 0 必须先运行 deterministic pipeline；只有 `strict_required` 才进入 Playwright/sub-agent 流程。
- `pipeline.py`：`auto` / `fast` / `strict` 编排，输出 `converted`、`blocked` 或 `strict_required`，并记录阶段耗时。
- `pipeline.md`：CLI、状态/退出码、公式验证重跑、输出目录、timing 字段和 benchmark 说明。
- `benchmark.py`：生成不含私有内容的 CSS-heavy 合成 SingleFile，验证 compact snapshot 至少缩减 80%，并输出多次运行的中位耗时。
- `preflight.py`：选择唯一正文、生成 compact HTML、结构 manifest、公式索引和资源索引，并识别 strict 信号。
- `fast_converter.py`：将支持的静态结构转换为 Markdown，遇到无法无损表达的语义时 fail closed。
- `formula_batch.py`：按 normalized DOM hash 去重公式，使用版本化 cache，并生成单批浏览器验证文档。
- `pipeline_utils.py`：共享的文件名规范化、DOM 合同加载、JSON 写入和确定性 ZIP 工具。
- `contracts.py`：selector、复杂度、DOM semantic identity/canonicalization 和 comment ledger 合同。
- `image_disposition.py`：图片保留、删除或人工复核判定，以及 image ledger 守恒。
- `markdown_fences.py`：按行扫描 fenced code block，避免使用 fence 奇偶或跨行正则进行错误验证。
- 其余 Markdown 文件：strict 工作流的图片、题注、Notebook、阻断条件、验收清单和维护规则。

## 默认转换入口

```bash
python html-to-markdown/pipeline.py input.html \
  --mode auto \
  --output dist
```

以 `dist/report.json.status` 为权威：

- `converted`：已生成 ZIP；主 agent 仍需独立抽检后交付；
- `blocked`：已有 Markdown 工作产物，但公式验证或守恒检查未完成；修复 blocker 后重跑；
- `strict_required`：读取 `strict_reasons`，进入 `SKILL.md` 的 rendered-DOM strict 流程。

图片默认进入 strict，因为 fast path 尚未执行完整的原图备份、去水印、压缩和原尺寸验证合同。只有用户明确接受图片保持原样时，才使用 `--allow-unprocessed-images`。

## 性能基准

运行可重复的合成 benchmark：

```bash
python html-to-markdown/benchmark.py --iterations 5
```

输出包含：

- input/compact/visible-text bytes；
- compact snapshot 缩减百分比；
- formula total/unique 和后续运行的 cache-hit；
- `preflight`、`snapshot`、`formula`、`validation`、`conversion`、`package`、`total` 的中位耗时。

benchmark 只对至少 80% 的 snapshot 缩减设置稳定门槛。绝对耗时受机器、Python 和文件系统影响，仅作为本机前后对比，不作为跨环境 CI 阈值。

## 运行测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

GitHub Actions 在 pull request、推送到 `main` 和手动触发时，使用 Python 3.13 安装依赖并运行完整 `unittest` suite。

## 维护约定

- 每个 skill 目录以 `SKILL.md` 为 agent 入口；
- 可确定、可复用的规则优先落到 Python 合同和测试，而不是让 LLM 重复判断；
- 报告中的状态、strict reasons、blockers 和 ledgers 不得被手工伪造或绕过；
- 修改行为时同步更新实现、测试、`SKILL.md`、参考文档和 README，避免跨文件漂移；
- 不提交付费文章、私有网页或客户数据，性能回归使用 synthetic fixture/benchmark。
