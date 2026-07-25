# 公式批处理、缓存与验证闸门

`formula_batch.py` 在 fast pipeline 中处理公式。它按规范化 `dom_hash` 去重解析、缓存唯一公式的**解析结果**，并让每个需要验证的唯一 `dom_hash` 只进入一次浏览器验证。解析成功不等于验证成功；验证报告通过前不得替换占位符或生成最终 ZIP。

## 执行顺序

```text
formula records + compact DOM
→ 按 dom_hash 分组
→ parse cache lookup
→ 原始 LaTeX 直接采用
→ KaTeX HTML 递归解析
→ 未知结构 fail closed
→ 为每个待验证的唯一 dom_hash 建立 validation job
→ 用首个 source_id 作为代表，并保存全部 source_ids 映射
→ 生成 formula-results.json
→ 生成单个 formula-validation.html
→ strict renderer 注入固定 KaTeX 并调用 runFormulaValidation()
→ 保存按唯一 validation job 生成的结构化 report
→ pipeline 校验 representative source_id/dom_hash/LaTeX/counts
→ 通过后按 dom_hash 解锁全部 source node 并允许打包
```

## Parse cache key

```text
<dom_hash>|<parser_version>|<target_platform>
```

缓存只表示“解析器对该 DOM 得到了什么结果”，不代表浏览器验证通过。每个 entry 明确记录：

```json
{
  "parse_result": {"latex": "...", "success": true},
  "validation_status": "not_validated"
}
```

解析器版本或目标平台变化会自然失效。成功和失败的 parse result 都可缓存，避免重复执行 DOM 重建；浏览器验证仍是独立交付闸门。

## 当前解析覆盖

- 普通 token、希腊字母、关系符和常用运算符；
- `.mord/.mbin/.mrel/.mopen/.mclose/.mpunct/.minner/.mop`；
- `.mathbb/.mathcal/.text`；
- `.msupsub` 的单上标、单下标和上下标；
- `.mfrac`；
- `.msqrt`；
- `.overline`；
- KaTeX wrapper、vlist 辅助节点和 spacing。

矩阵、cases、accent、op-limits、munder/mover 等尚未实现的语义结构返回失败。`diagnostic_text` 只用于定位，绝不能作为成功 LaTeX。

## Validation job 与 source 映射

浏览器验证按唯一 `dom_hash` 建立 job，而不是按每个 source node 建立 job。每个 job 包含：

```json
{
  "source_id": "formula-0001",
  "source_ids": ["formula-0001", "formula-0002"],
  "dom_hash": "...",
  "latex": "x+1"
}
```

- `source_id` 是首个来源的稳定代表，实际写入 validation HTML 和 validation report；
- `source_ids` 保留映射到该 hash 的全部来源，写入 `formula-results.json.validation_jobs`；
- `pending_validation` 仍按 source node 统计，因此每个尚未解锁的占位符都可审计；
- 一个 job 验证成功后，pipeline 按 `dom_hash` 解锁其全部 `source_ids`；
- 重复 source node 不得重复进入浏览器渲染。

## 批量验证

每次转换只生成一个 `formula-validation.html`。页面不会在 KaTeX 缺失时静默跳过，而是提供：

```javascript
window.runFormulaValidation()
window.__FORMULA_VALIDATION__
```

调用 `runFormulaValidation()` 前必须注入固定版本 KaTeX。若 runtime 缺失，函数抛出错误。完成后报告必须包含：

- 与代码一致的 `schema_version`、`parser_version` 和 `validator_version`；
- `runtime_loaded=true`；
- `completed=true`；
- 非空 `katex_version`；
- `total == passed == validation_jobs`；
- 空 `failures`；
- 与唯一 validation job 集合完全一致的代表 `source_id`、`dom_hash` 和 `latex`；
- 不得包含重复的 report `source_id`。

验证报告**不应**为同一 `dom_hash` 的每个重复 source node 各生成一条记录。完整的重复来源关系以 `formula-results.json.validation_jobs[].source_ids` 为准。

验证报告通过 CLI 传入：

```bash
python html-to-markdown/pipeline.py input.html \
  --mode fast \
  --output dist \
  --formula-validation-report dist/formula-validation-report.json
```

报告缺失、未完成、KaTeX runtime 未加载、唯一 job 集合不匹配、代表映射不一致、存在重复 ID 或存在失败时，pipeline 状态保持 `blocked`，不生成 ZIP。

## 输出

- `.formula-cache.json`：版本化 parse cache，不冒充验证缓存；
- `formula-results.json`：统计、`validation_jobs`、parse failures、source-level pending validation 和验证错误；
- `formula-validation.html`：每个唯一 `dom_hash` 一个节点的单批次渲染输入与结构化验证函数；
- `report.json.formula_batch`：total、unique、cache hit、parsed unique、resolved、failure、pending validation、validation jobs、saved validation nodes 和 planned browser batch 数；
- `report.json.formula_pending_validation`：等待浏览器验证的 source ID、DOM hash 和 LaTeX。

任一 parse failure 或 pending validation 都保留 `{{FORMULA:source-id}}`，pipeline 状态为 `blocked`，不得生成最终 ZIP。
