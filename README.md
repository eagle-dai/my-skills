# my-skills

一组面向 AI coding agent 的自定义 skills。当前仓库主要解决两类相互关联的任务：

1. 将 SingleFile 保存的完整网页转换为结构清晰、可离线阅读的 Markdown 包；
2. 从 KaTeX、MathJax 或 MathML 公式节点中提取语义正确的 LaTeX。

仓库强调内容完整性、可验证的转换规则，以及修改 skill 时的回归保护。

## Skills

| Skill | 入口 | 用途 |
|---|---|---|
| `html-to-markdown` | [`html-to-markdown/SKILL.md`](html-to-markdown/SKILL.md) | 将 SingleFile HTML 转换为离线 Markdown 包。覆盖正文定位、DOM 基线、表格、列表、图片、题注、评论、Notebook、虚拟化容器、公式处理和浏览器验收。采用主 agent 分析与验收、sub agent 执行转换的调度模式。 |
| `formula-extraction` | [`formula-extraction/SKILL.md`](formula-extraction/SKILL.md) | 从单个 KaTeX、MathJax 或 MathML 公式 DOM 节点中提取 LaTeX。优先读取原始语义数据，必要时进行 MathML 或 KaTeX HTML 结构重建；无法可靠恢复时 fail closed，由调用方改用截图或人工复核。 |

`html-to-markdown` 在处理公式密集页面时会引用 `formula-extraction`，后者是公式提取与验证规则的权威来源。

## 目录结构

```text
.
├── .github/
│   └── workflows/
│       └── tests.yml
├── _meta/
│   └── skill-self-improvement.md
├── formula-extraction/
│   ├── SKILL.md
│   ├── katex-html-parser.md
│   └── self-improvement.md
├── html-to-markdown/
│   ├── SKILL.md
│   ├── blocking-rules.md
│   ├── checklist.md
│   ├── contracts.py
│   ├── conversion-rules.md
│   ├── notebook-and-virtualized.md
│   └── self-improvement.md
└── tests/
    ├── test_first_batch_rules.py
    └── test_html_to_markdown_contracts.py
```

## 各目录说明

### `.github/workflows/`

GitHub Actions 配置。`tests.yml` 在 pull request、推送到 `main` 和手动触发时，使用 Python 3.13 运行仓库的 `unittest` 测试。

### `_meta/`

跨 skill 共享的维护规则。

- `skill-self-improvement.md`：说明如何从真实缺陷中提炼可泛化规则，并要求新增或修改规则时补充正例、反例和回归检查。

### `formula-extraction/`

公式提取 skill 及其专属参考资料。

- `SKILL.md`：职责边界、提取优先级、语义退化检查、后处理和渲染验证流程。
- `katex-html-parser.md`：在没有原始 LaTeX 或 MathML 时，从 KaTeX HTML 渲染结构重建公式的参考规则。
- `self-improvement.md`：公式命令边界、Unicode 转换和平台差异等专属回归用例。

### `html-to-markdown/`

SingleFile HTML 转 Markdown 的主 skill。

- `SKILL.md`：主流程、复杂度分级、主 agent / sub agent 分工和最终交付要求。
- `contracts.py`：可执行的 selector、复杂度分级、语义候选去重和评论 ledger 合同。
- `conversion-rules.md`：表格、列表、评论、图片、题注、代码块、文本清理等非公式转换规则。
- `notebook-and-virtualized.md`：Jupyter、Databricks、Colab、Monaco、CodeMirror、lazy-load 等特殊页面处理规则。
- `blocking-rules.md`：交付前必须通过的内容完整性和渲染阻断条件。
- `checklist.md`：主 agent 独立验收清单和最终报告模板。
- `self-improvement.md`：Markdown 边界和题注提取等专属回归用例。

### `tests/`

基于 Python 标准库 `unittest` 的回归测试。

- `test_html_to_markdown_contracts.py`：测试 `contracts.py` 的行为，并检查关键文档是否引用统一合同。
- `test_first_batch_rules.py`：检查公式、选择器、图片处理和 Markdown 边界等关键规则是否在文档中保持一致。

## 运行测试

仓库测试只依赖 Python 标准库：

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

## 维护约定

- 每个 skill 目录以 `SKILL.md` 作为入口。
- 详细规则放在同目录参考文件中，由 `SKILL.md` 明确引用。
- 可确定、可复用的规则优先落到可执行代码和测试，而不是只复制自然语言。
- 修改规则时同步更新受影响的 skill、参考文档和回归测试，避免跨文件漂移。
