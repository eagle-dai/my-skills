# Fast/Auto 转换 Pipeline

`pipeline.py` 将常见静态文章的转换规则落到确定性代码中。它不替代 strict 流程；遇到动态、虚拟化、无法无损表达的结构，或 fast path 尚未实现的完整性合同，输出 `strict_required`，由主 agent 进入 Playwright 与人工验收流程。

## 使用

默认运行：

```bash
python html-to-markdown/pipeline.py input.html --mode auto --output dist
```

图片默认进入 strict，因为 fast path 尚未执行“原图备份 → 去水印 → 压缩 → 原尺寸验证”的完整合同。只有用户明确接受图片保持原样、跳过全部图片后处理时，才可使用：

```bash
python html-to-markdown/pipeline.py input.html \
  --mode auto \
  --output dist \
  --allow-unprocessed-images
```

该参数只放宽图片后处理要求，不会绕过外部资源、本地化失败、题注、结构守恒或其他 strict 条件。参数值会写入 `report.json.allow_unprocessed_images`，包括最终仍路由到 strict 的情况。

模式：

- `auto`：运行 preflight；无 strict 信号且满足 fast path 合同时进入 fast path，否则只生成预检和 strict 路由报告。
- `fast`：要求输入满足 fast path 条件；阻断项仍会返回 `strict_required`，不能强制绕过。
- `strict`：显式生成 strict 路由报告，不执行确定性 Markdown 转换。

退出码：

- `0`：转换、验证、打包成功；
- `2`：输入、正文选择或参数错误；
- `3`：必须进入 strict；
- `4`：已生成 Markdown 工作产物，但公式或结构守恒仍阻断最终 ZIP。

当最终状态为 `strict_required` 时，顶层 `report.json.recommended_mode` 固定为 `strict`。preflight 自身的原始建议仍保留在 `report.json.preflight.recommended_mode`，便于区分“预检建议”和后续合同检查作出的最终路由决定。

## Fast path 支持

- 标题、段落、强调、链接和行内代码；
- 原生及常见 Slate 列表；
- blockquote；
- fenced code block；
- 无 rowspan/colspan 的规则表格；
- 在显式指定 `--allow-unprocessed-images` 时，对 data URI 图片进行离线解码并保持原样；
- 带 annotation/data 属性等原始 LaTeX 的公式；
- 位于已识别公式容器内部的 `math/tex` script 原始 LaTeX；
- KaTeX HTML-only 公式的批量解析、去重、缓存与验证中间态；
- wrapper/native DOM canonicalization；
- image ledger、fence scanner 和结构数量守恒；
- 确定性 ZIP 时间戳与文件顺序。

## DOM 复用

进程内 fast pipeline 只解析完整 SingleFile 一次。preflight 为隔离正文而保留一次 selected-body detach/reparse，并将该 `compact_root` 直接交给 canonical count、公式解析和 Markdown 转换；不会再从 `compact_html` 重建两棵相同 DOM。序列化的 `preflight/content.html` 仍保留为外部工具与 strict handoff 的稳定边界。测试会比较 root-reuse 与 serialize/reparse 路径的 Markdown、manifest、formula result 和 ZIP，要求字节一致。

## Strict 路由

以下情况不猜测：

- Notebook、Monaco、CodeMirror、虚拟化或 lazy-load；
- iframe/video；
- 多个 native list、缺失 native table；
- rowspan/colspan 或 ragged table；
- 资源缺失或外部图片尚未本地化；
- `<table><caption>`、`<figure><figcaption>` 等已确认题注，因为 fast path 尚未提供 caption ledger 守恒；
- 页面包含图片且用户没有显式指定 `--allow-unprocessed-images`；
- 独立于已识别公式容器的 MathJax v2 `<script type="math/tex">`；这类 source script 会在 compaction 中被删除，且无法与渲染节点可靠绑定，必须用原始页面进入 strict；
- fast path 不支持的结构。

## 公式批处理与验证

存在原始 LaTeX 的公式可直接输出。对于只有 KaTeX HTML 的公式，`formula_batch.py` 会：

1. 按 `dom_hash` 去重并尝试确定性解析；
2. 使用 `.formula-cache.json` 缓存解析结果；只有 cache entry 变化时才原子重写；
3. 每个需要验证的唯一 `dom_hash` 只生成一个 browser validation job；
4. 使用首个 `source_id` 作为 job 的稳定代表，并在 `formula-results.json.validation_jobs[].source_ids` 中保留全部重复来源；
5. 在验证完成前为每个 source node 保留 `{{FORMULA:formula-0001}}` 占位符，将状态设为 `blocked`，且不生成最终 ZIP；
6. 一次 hash-level 验证成功后，将结果映射回该 `dom_hash` 对应的全部 source node。

因此，`pending_validation` 统计等待解锁的 source node 数量，而 `validation_jobs` 统计实际需要浏览器渲染的唯一公式数。`validation_nodes_saved` 表示通过 `dom_hash` 去重省掉的重复渲染节点数。

独立的 MathJax v2 source script 不属于上述 batch 输入。preflight 会在首次解析完整页面时同步检测它们并返回 `strict_required`；不会为了这项检测再次解析 CSS-heavy SingleFile。只有嵌入 `.katex`、Slate KaTeX 等已识别公式容器的 `math/tex` script 才能作为对应 FormulaRecord 的原始 LaTeX。

运行 `formula-validation.html` 中的批量验证逻辑并保存 JSON 报告后，使用：

```bash
python html-to-markdown/pipeline.py input.html \
  --mode auto \
  --output dist \
  --formula-validation-report validation-report.json
```

验证报告只包含每个唯一 job 的代表 `source_id`、`dom_hash` 和 LaTeX。schema、parser/validator 版本、唯一 job 集合、数量或映射不匹配时继续 fail-closed；重复 report source ID 也会被拒绝。解析失败、待验证 source node 或未解决占位符都会记录在 `report.json`，最终 ZIP 只在 `status=converted` 时生成。

## Timing 字段

所有成功、阻断和 strict 路由报告都包含 `report.json.timings_ms`：

| 字段 | 包含内容 |
|---|---|
| `preflight` | 读取并解析输入一次，在同一 DOM 上完成 MathJax source 检测与正文选择，再构建 detached compact snapshot、manifest 和 canonical count |
| `snapshot` | 将 `content.html`、`manifest.json`、`formulas.json`、`assets.json` 写入磁盘 |
| `formula` | 首次运行时的公式去重、cache 查找/必要写入、解析和 validation batch 生成 |
| `validation` | 带 `--formula-validation-report` 重跑时的 cache 复用、无变化写入跳过和验证报告摄取/核对 |
| `conversion` | Markdown 转换、结构计数、ledger 和 blocker 计算 |
| `package` | 写 Markdown，并在 `converted` 时生成确定性 ZIP |
| `total` | 从进入 `run_pipeline()` 到最终报告内容定格前的总 wall-clock 时间；不包含最后一次 `report.json` 写盘，也不包含外部浏览器实际运行 validation HTML 的等待时间 |

这些字段用于同一机器、相近环境下的前后对比。绝对值会受 Python 版本、CPU 和文件系统影响，不应设置跨环境的固定性能阈值。`report.json` 自身写盘被明确排除，是因为报告必须先包含已经定格的 timing 值，避免为计入自身写盘而进行递归式重复写入。

## 可重复 Benchmark

仓库提供 synthetic benchmark，不使用付费文章、私有页面或客户数据：

```bash
python html-to-markdown/benchmark.py --iterations 5
```

默认输入模拟：

- 大量 page-level `<style>` 和脚本噪声；
- 168 个公式节点，其中只有 12 个 normalized DOM 唯一公式；
- 常见标题、列表、表格和代码块；
- 无图片、Notebook、virtualized/lazy-load 等 strict 信号。

输出为 JSON，同时包含 `original_latex` 与 `katex_html_only` 两个场景。后者执行 blocked cold pass、合成 validation report、converted validation pass 和 warm pass，并分别报告 timings、DOM parse count、cache write count、validation job 去重和 source mapping。cold pass 必须写入新 cache；validation/warm pass 在 entry 未变化时必须报告零次 cache write。benchmark 只把以下稳定合同作为失败条件：

- 原始 LaTeX 场景必须转换并生成 ZIP；
- KaTeX HTML-only cold pass 必须在验证前阻断，validation/warm pass 必须转换并生成 ZIP；
- compact snapshot 必须至少缩减 80%；
- 公式总数、唯一数、validation job 和 source mapping 必须守恒。

可以保留生成文件并调整规模：

```bash
python html-to-markdown/benchmark.py \
  --iterations 5 \
  --workdir work/benchmark \
  --style-blocks 800 \
  --formula-count 168 \
  --unique-formulas 12 \
  --json-output work/benchmark/result.json
```

## 输出

```text
dist/
├── preflight/
│   ├── content.html
│   ├── manifest.json
│   ├── formulas.json
│   └── assets.json
├── .formula-cache.json
├── formula-validation.html   # 有待验证公式时
├── formula-results.json
├── report.json
├── <input-stem>/
│   ├── <title>.md
│   └── files/<input-stem>/...
└── <input-stem>.zip          # 仅 status=converted
```
