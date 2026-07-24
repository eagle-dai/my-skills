# 验证 Checklist 与输出报告

本 checklist 供主 agent 在 sub agent 返回后独立验收。selector、复杂度分级、DOM identity、候选去重和评论 ledger 以 @contracts.py 为准；Markdown fence 以 @markdown_fences.py 为准；图片判定以 @image_disposition.py 为准。

## 1. 基线建立

在提取前通过 Playwright 对整个正文容器执行 `querySelectorAll()`，不能只遍历直接子节点。候选发现后分配 `semantic_id` 并调用 `canonicalize_candidates()`；selector 原始命中数不能直接作为基线。

| 检查项 | HTML 侧 | 阻断条件 |
|---|---|---|
| 块级公式 | canonical 公式候选按 display 分类 | Markdown 输出数 `< N_formula_block` |
| 行内公式 | canonical 候选排除 display | 任何源公式无 ledger/输出对应项 |
| 表格 | `[data-slate-type="table"], table` 后 canonicalize | Markdown/HTML table 数 `< N_table` |
| 列表 | `[data-slate-type="list"], ul, ol` 后 canonicalize | 容器数量或 ordered/unordered 类型不一致且无解释 |
| 列表项 | `[data-slate-type="list-line"], li` 后 canonicalize | Markdown 列表项数 `< N_list_item` |
| 图片 | `img` + image ledger | 任一源图缺 ledger，或应保留图未输出一次 |
| 代码块 | `[data-slate-type="pre"], pre > code` 后 canonicalize | Markdown 代码块数 `< N_codeblock` |
| 标题 | Slate heading + `h1..h6` | 任一源标题无输出对应项且无原因 |
| 段落 | 站点段落 selector + `p` | 任一正文段落未映射到输出/过滤 ledger |
| 评论 | 顶层评论 `source_ids` | identity ledger 校验失败 |

Slate 代码块必须使用 `[data-slate-type="pre"]`。不得在验收阶段改成 `[data-slate-type="code-block"]`。

## 2. Markdown 侧结构扫描

先验证并剥离 fenced code block：

```python
from markdown_fences import scan_fenced_blocks, strip_fenced_blocks

scan_fenced_blocks(markdown)
no_code = strip_fenced_blocks(markdown)
```

标题、列表、blockquote 和段落计数都基于 `no_code`。不得使用 fence 行数奇偶、三反引号跨行正则或只支持 backtick 的脚本。

## 3. 表格

- canonical HTML 表格数与 Markdown/HTML table 输出数一致；
- Slate wrapper 与内部 `<table>` 使用同一 `semantic_id`；
- 原生 `<table>` 优先，wrapper 只作 fallback；
- 行列、表头、顺序一致；
- rowspan/colspan 无法表达时使用 fenced HTML 或人工复核；
- 表标题与表格之间保留空行；
- 至少局部截图抽检一张复杂表格。

## 4. 代码块与 Notebook

- 代码块数量与 canonical 基线一致；
- 语言标签有证据，不确定时使用 `text`；
- NBSP 已替换；
- code cell 与 markdown 内嵌代码块分开计数；
- `scan_fenced_blocks()` 无错误；
- `strip_fenced_blocks()` 后代码注释不再被误算为标题；
- output 未被 inner fence 截断；
- lazy-load IFrame/img 已回填或明确标注。

详见 @notebook-and-virtualized.md 和 @fence-validation.md。

## 5. 列表

- ordered/unordered/嵌套列表数量对比；
- 父列表与嵌套子列表具有不同 `semantic_id`；
- Slate list wrapper 与唯一顶层 `ul/ol` 共享身份；
- list-line wrapper 与原生 `li` 共享身份；
- 编号证据可能位于 item 子树；
- 禁止双 marker；
- 代码块行号不误作列表；
- 列表项总数一致。

## 6. 评论

转换前记录源顶层评论完整稳定 `source_ids`。每条源评论记录：

```text
source_id | status | emitted_count | reason
```

`status` 只能为：

```text
kept | removed_as_noise | failed | manual_review
```

交付前执行：

```python
assert_valid_comment_ledger(entries, source_ids=source_ids)
```

- ledger ID 集合与源 ID 集合完全相等；
- `kept` 输出一次；
- 其他状态输出 0 次并写明原因；
- 作者回复、代码、日志、公式、图片、链接和 blockquote 排版正确。

## 7. 图片与二维码

每张源图片建立 image ledger：

```text
source_id | decision | emitted_count | reason | decoded_url | decoded_link_emitted
```

交付前执行：

```python
assert_valid_image_ledger(entries, source_ids=source_ids)
```

- 正文或有内容关系的二维码必须保留；
- 分享/关注 UI 中且与正文无关的二维码才可 `remove_as_ui`；
- 无法判断的二维码为 `manual_review`，原图仍输出一次；
- `keep/manual_review` 的 `decoded_url` 非空时，Markdown 必须输出可点击链接，并记录 `decoded_link_emitted=True`；
- `decoded_link_emitted=True` 必须对应非空 `decoded_url`；
- `remove_as_ui` 不得输出 decoded link；
- 删除项必须有明确 UI/装饰证据；
- 重复 source ID 的错误必须指出具体 ID；
- 相对路径有效，文件真实存在，无 base64 直接嵌入；
- 图片顺序和题注对应；
- 压缩后文字仍可读。

### 去水印

- **默认执行**；只有用户**明确要求保留原始水印**时才跳过；
- 破坏性护栏不因默认执行而放松：
- 必须保留原图副本；
- 报告处理文件、方法和 bbox；
- 检测/验证用原图非缩略图；
- 特征色命中正文同色时只取最右下连通块；
- bbox 紧框水印不得一盖到角；
- 原尺寸/放大抽检，确认正文未被擦除；
- 任一护栏不满足或无法安全去除时降级使用原图并标注。

## 8. 题注与居中

短题注可与内容块同组；解释性长段落保持正文左对齐。

- **短题注示例：** `图 D-1　系统架构`，紧邻图片且仅用于命名，可与图片同组居中。
- **说明段落示例：** `图 D-1 给出了系统架构。它展示了……`，包含多句解释，保持正文左对齐。
- 历史样例中曾出现 **200–267 字** 的“图/公式开头说明段落”；长度只是辅助信号，最终判断其功能。

每个 confirmed caption 必须 `emitted_count == 1`，不得静默丢失或重复输出。

## 9. 公式

引用 `formula-extraction` skill：

- `.katex-error == 0`；
- `mstyle[mathcolor="#cc0000"] == 0`；
- 捕获 warning；
- 渲染后公式数不得少于源 canonical 公式数；
- 分式、上下标、矩阵和编号语义一致；
- 未知 KaTeX 结构 fail closed；
- 合法 `\simeq`、`\simneqq` 不得被拆分；
- 只有 parser parts 明确为 `["\sim", "p"]` 时才输出 `\sim p`。

## 10. GitHub / Markdown 边界

### 行内数学

首选在 CJK/全角标点与 `$` 之间插入 **ASCII 空格**。该方案在 **GitHub 与 VS Code** 都能渲染；**backtick 数学变体**虽然可在 GitHub 工作，但 VS Code 不识别，**因此不采用**。

### 强调

- 闭合 `**/*/_` 后紧贴字母、数字或 CJK 时检查；
- 紧贴标点的合法场景不得误修；
- 禁用 `\S` 宽类；
- 清理过度插入空格；
- 扫描相邻强调产生的 `****`；
- 命中时先移除该行已有强调定界符，再按语义重包；**不要把四个星号机械替换成两个**。

## 11. Playwright 渲染验证

1. 使用统一固定版本的 `render.html`；
2. 检查 KaTeX error/warning；
3. 对比渲染后公式数量与源 canonical 数；
4. 整页截图；
5. 公式、列表、表格、评论、二维码和处理过的图片做局部截图；
6. 发现问题后局部修复，并重新执行受影响的计数、scanner、ledger 和截图检查。

## 12. 最终报告模板

```text
复杂度级别：
正文容器：
编辑器类型：

DOM 基线 / Markdown 实际：
- 块级公式：
- 行内公式 ledger：
- 表格：
- 列表 / 列表项：
- 图片 ledger：
- 代码块：
- 标题：
- 段落 ledger：
- 评论 ledger：

Fence：scan_fenced_blocks 结果
图片：保留 / remove_as_ui / manual_review；decoded URL/link 对齐
去水印：默认是；用户是否明确要求保留原始水印；原图副本；方法/bbox/抽检
浏览器渲染：执行情况、差异、修复、人工复核项
```
