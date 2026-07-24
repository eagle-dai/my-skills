# Fast/Auto 转换 Pipeline

`pipeline.py` 将常见静态文章的转换规则落到确定性代码中。它不替代现有 strict 流程；遇到动态、虚拟化、无法无损表达的结构，或 fast path 尚未实现的完整性合同，输出 `strict_required`，由主 agent 进入 Playwright 与人工验收流程。

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
- KaTeX HTML-only 公式的批量解析、去重、缓存与验证中间态；
- wrapper/native DOM canonicalization；
- image ledger、fence scanner 和结构数量守恒；
- 确定性 ZIP 时间戳与文件顺序。

## Strict 路由

以下情况不猜测：

- Notebook、Monaco、CodeMirror、虚拟化或 lazy-load；
- iframe/video；
- 多个 native list、缺失 native table；
- rowspan/colspan 或 ragged table；
- 资源缺失或外部图片尚未本地化；
- `<table><caption>`、`<figure><figcaption>` 等已确认题注，因为 fast path 尚未提供 caption ledger 守恒；
- 页面包含图片且用户没有显式指定 `--allow-unprocessed-images`；
- fast path 不支持的结构。

## 公式批处理与验证

存在原始 LaTeX 的公式可直接输出。对于只有 KaTeX HTML 的公式，`formula_batch.py` 会：

1. 按 DOM hash 去重并尝试确定性解析；
2. 使用 `.formula-cache.json` 缓存解析结果；
3. 为待验证公式生成 `formula-validation.html` 和 `formula-results.json`；
4. 在验证完成前保留 `{{FORMULA:formula-0001}}` 占位符，将状态设为 `blocked`，且不生成最终 ZIP。

运行 `formula-validation.html` 中的批量验证逻辑并保存 JSON 报告后，使用：

```bash
python html-to-markdown/pipeline.py input.html \
  --mode auto \
  --output dist \
  --formula-validation-report validation-report.json
```

验证报告的 schema、parser/validator 版本、条目集合或 DOM hash 不匹配时继续 fail-closed。解析失败、待验证项目或未解决占位符都会记录在 `report.json`，最终 ZIP 只在 `status=converted` 时生成。

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
