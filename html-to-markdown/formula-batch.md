# 公式批处理、缓存与验证闸门

`formula_batch.py` 在 fast pipeline 中处理公式。它按规范化 DOM hash 去重，缓存唯一公式的**解析结果**，并把 KaTeX HTML 重建结果交给单批次浏览器验证。解析成功不等于验证成功；验证报告通过前不得替换占位符或生成最终 ZIP。

## 执行顺序

```text
formula records + compact DOM
→ 按 dom_hash 分组
→ parse cache lookup
→ 原始 LaTeX 直接采用
→ KaTeX HTML 递归解析
→ 未知结构 fail closed
→ 生成 formula-results.json
→ 生成单个 formula-validation.html
→ strict renderer 注入固定 KaTeX 并调用 runFormulaValidation()
→ 保存结构化 validation report
→ pipeline 校验 source_id/dom_hash/LaTeX/counts
→ 通过后替换占位符并允许打包
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

## 批量验证

每次转换只生成一个 `formula-validation.html`。页面不会在 KaTeX 缺失时静默跳过，而是提供：

```javascript
window.runFormulaValidation()
window.__FORMULA_VALIDATION__
```

调用 `runFormulaValidation()` 前必须注入固定版本 KaTeX。若 runtime 缺失，函数抛出错误。完成后报告必须包含：

- `runtime_loaded=true`；
- `completed=true`；
- 非空 `katex_version`；
- `total == passed`；
- 空 `failures`；
- 与 pending batch 完全一致的 `source_id`、`dom_hash` 和 `latex`。

验证报告通过 CLI 传入：

```bash
python html-to-markdown/pipeline.py input.html \
  --mode fast \
  --output dist \
  --formula-validation-report dist/formula-validation-report.json
```

报告缺失、未完成、KaTeX runtime 未加载、公式集合不匹配或存在失败时，pipeline 状态保持 `blocked`，不生成 ZIP。

## 输出

- `.formula-cache.json`：版本化 parse cache，不冒充验证缓存；
- `formula-results.json`：统计、parse failures、pending validation 和验证错误；
- `formula-validation.html`：单批次渲染输入与结构化验证函数；
- `report.json.formula_batch`：total、unique、cache hit、parsed unique、resolved、failure、pending validation 和 planned browser batch 数；
- `report.json.formula_pending_validation`：等待浏览器验证的 source ID、DOM hash 和 LaTeX。

任一 parse failure 或 pending validation 都保留 `{{FORMULA:source-id}}`，pipeline 状态为 `blocked`，不得生成最终 ZIP。
