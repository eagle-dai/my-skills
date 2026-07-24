# Fast/Auto 转换 Pipeline

`pipeline.py` 将常见静态文章的转换规则落到确定性代码中。它不替代现有 strict 流程；遇到动态、虚拟化或无法无损表达的结构时，输出 `strict_required`，由主 agent 进入 Playwright 与人工验收流程。

## 使用

```bash
python html-to-markdown/pipeline.py input.html --mode auto --output dist
```

模式：

- `auto`：运行 preflight；无 strict 信号时进入 fast path，否则只生成预检和 strict 路由报告。
- `fast`：要求输入满足 fast path 条件；阻断项仍会返回 `strict_required`，不能强制绕过。
- `strict`：显式生成 strict 路由报告，不执行确定性 Markdown 转换。

退出码：

- `0`：转换、验证、打包成功；
- `2`：输入、正文选择或参数错误；
- `3`：必须进入 strict；
- `4`：已生成 Markdown 工作产物，但公式或结构守恒仍阻断最终 ZIP。

## Fast path 支持

- 标题、段落、强调、链接和行内代码；
- 原生及常见 Slate 列表；
- blockquote；
- fenced code block；
- 无 rowspan/colspan 的规则表格；
- data URI 图片离线解码；
- 带 annotation/data 属性等原始 LaTeX 的公式；
- wrapper/native DOM canonicalization；
- image ledger、fence scanner 和结构数量守恒；
- 确定性 ZIP 时间戳与文件顺序。

## Strict 路由

以下情况不猜测：

- Notebook、Monaco、CodeMirror、虚拟化或 lazy-load；
- iframe/video；
- 多个 native list、缺失 native table；
- rowspan/colspan 或 ragged table；
- 资源缺失；
- fast path 不支持的结构。

## 公式中间态

本阶段只直接输出存在原始 LaTeX 的公式。KaTeX HTML-only 节点写成：

```text
{{FORMULA:formula-0001}}
```

同时加入 `report.json.unresolved_formulas`，状态为 `blocked`，不生成最终 ZIP。后续公式批处理 PR 会按 hash 去重、缓存并替换这些占位符。

## 输出

```text
dist/
├── preflight/
│   ├── content.html
│   ├── manifest.json
│   ├── formulas.json
│   └── assets.json
├── report.json
├── <input-stem>/
│   ├── <title>.md
│   └── files/<input-stem>/...
└── <input-stem>.zip        # 仅 status=converted
```
