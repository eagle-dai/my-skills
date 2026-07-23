# Notebook 类页面与虚拟化容器

适用于 Jupyter、Databricks、Colab、Observable，以及 Monaco、CodeMirror、react-virtualized 等只渲染可见区域的页面。Markdown fence 的权威实现是 @markdown_fences.py；不得使用 fence 行数奇偶或跨行正则验收。

## 识别信号

任一信号成立即可进入本流程：

- 标题或元数据含 Jupyter、Databricks、Colab、notebook、`.ipynb`；
- DOM 含 `jp-Cell`、`command-input`、`cell-output`、`cm-editor`、`monaco-editor`；
- 页面重复出现“代码 + 输出”结构；
- 活跃编辑器行数明显少于 cell 总数，说明存在虚拟化。

## 1. Cell 模型与基线

抽象模型：

```text
Cell
├── Input
│   ├── Markdown cell
│   └── Code cell
└── Output (0..N)
    ├── Text / Stream / Traceback
    ├── HTML / Table
    ├── Image / SVG
    └── IFrame / Embedded content
```

Phase 1 必须确认：

- 顶层 cell selector；
- code/markdown 类型判定；
- 代码语言来源；
- output 容器 selector；
- `markdown_count + code_count == total_cells`。

### 类型判定

不要仅凭是否存在 `.command-input` 或编辑器容器判断 code cell。Databricks 等平台可能给 markdown cell 也包同类容器。

可靠顺序：

1. 尝试从该 cell 的备份源或渲染行提取代码；
2. 提取结果 `strip()` 非空 → code cell；
3. 否则 → markdown cell 或空 cell。

## 2. 虚拟化代码提取

每个 code cell 按优先级：

1. 完整备份容器，如 `.monaco-editor.unformatted pre`；
2. 渲染态行：
   - Monaco 按 `style.top` 数值排序；
   - CodeMirror 按 `.cm-line` DOM 顺序；
3. 均无结果时记录 cell index，保留警告，禁止静默跳过。

从渲染行提取时统一执行：

```python
code = code.replace("\xa0", " ")
```

最终报告备份源、渲染源和失败 cell 的数量与索引。

## 3. Output 处理

| 输出形式 | 处理方式 |
|---|---|
| stdout/stderr | `text` fenced block 或短引用 |
| Traceback | fenced block + 错误提示 |
| `<table>` | Markdown 表格；复杂跨度用 fenced HTML |
| DataFrame React widget | 保留 schema/有效数据，过滤 CSS 与可访问性 UI 噪声 |
| `<img>` | 解码保存并按 image ledger 处理 |
| `<svg>` | 保存 `.svg` 并引用 |
| 非空 `<iframe>` | 说明 + 链接 |
| 空 lazy-load 占位 | 按第 4 节回填或明确标注 |
| 空 output 容器 | 跳过，不生成空 Output 标签 |

复合输出格式：

````markdown
> **Output:**
>
> ```text
> stdout text
> ```
>
> ![plot](files/<zip>/plot.png)
````

### Outer fence

内容包含 inner fence 时，outer fence 长度必须大于同字符最长 run。例如 inner 最长为 4 个 backtick，outer 至少使用 5 个。生成后必须调用 `scan_fenced_blocks()` 验证，不能只依赖生成前估算。

## 4. Lazy-load 占位回填

| 类型 | 回填来源（按优先级） |
|---|---|
| IFrame | 相邻文字链接 → 同 cell 源代码常量 → hydration JSON/metadata → 未保留 URL 的显式说明 |
| img | `data-src` / `data-original` / `data-lazy` / `srcset` / 同 cell URL |
| video | `data-src` / `<source data-src>` |

代码反推只能在同 cell 或已验证关系内进行，禁止从全页任意 URL 猜测。

报告：

```text
回填了 N 个空占位（IFrame=K, img=M, video=L）；未回填并标注=R
```

## 5. Markdown cell 内嵌代码块

Markdown cell 中的 `<pre><code>` 是正文代码块，不是 code cell。两者分开计数：

- code cell：来自 cell input 编辑器；
- markdown 内嵌块：来自 markdown cell 渲染 HTML；
- output fence：来自 cell output。

不能用预期 fence 总数公式作为最终正确性证明，因为 outer fence、inner fence、blockquote 和列表容器会改变表面行数。

## 6. Fence 扫描与结构计数

交付前执行：

```python
from markdown_fences import scan_fenced_blocks, strip_fenced_blocks

blocks = scan_fenced_blocks(markdown)
no_code = strip_fenced_blocks(markdown)
```

`scan_fenced_blocks()` 会检查：

- backtick 与 tilde opener/closer 字符一致；
- closer 长度不短于 opener；
- 4+ outer fence 不会被较短 inner fence提前关闭；
- blockquote 深度匹配；
- 列表项 fence 的容器缩进可闭合；
- 文件末尾不存在未闭合 opener。

`strip_fenced_blocks()` 保留原行数和换行符。标题、列表、blockquote、段落等结构扫描必须基于 `no_code`。

以下做法无效并禁止：

- `n3 % 2 == 0` 或其他 fence 行数奇偶判断；
- `re.sub` 跨行匹配三反引号；
- 只处理 backtick、不处理 tilde；
- 把短 inner fence 当成 long outer fence 的 closer。

## 7. Cell 与 Markdown 对齐

不要依赖容易漂移的原始 cell index。可使用规范化后的代码前缀辅助对齐：

```python
import re

norm = lambda value: re.sub(r"\s+", "", value)
matched = (
    norm(block_code)[:80] == norm(cell_code)[:80]
    or norm(block_code) in norm(cell_code)
    or norm(cell_code) in norm(block_code)
)
```

仍须按源顺序匹配；不匹配时警告并保留内容，不能静默丢弃。

## 8. Phase 1 报告模板

```text
平台：
Cell 总数：N（markdown=M，code=C，校验 M+C=N）
代码语言：
Cell selector：
代码来源：备份=K1，渲染态=K2，失败=K3（idx: ...）
Output：文本/错误/表格/图片/SVG/IFrame/空容器
Lazy-load：总数、回填数、未回填标注数
NBSP：出现/已清理
Fence：scan_fenced_blocks 通过/失败位置
```

## 9. 阻断条件

| 检查项 | 阻断条件 |
|---|---|
| Cell 总数 | `markdown + code != total` |
| Code cell 完整性 | 任一预期 code cell 无代码且无明确失败记录 |
| NBSP | Markdown 代码中仍含 `\xa0` |
| Fence | `scan_fenced_blocks()` 抛错 |
| 结构计数 | 未先调用 `strip_fenced_blocks()` |
| Output 截断 | inner fence 导致后续内容漂出容器 |
| Lazy-load | 源占位既未回填也未标注 |

## 10. 常见失败模式

| 错误 | 修复 |
|---|---|
| 用 `.command-input` 判 code cell | 先提取代码，非空才判 code |
| 只读 Monaco 可见行 | 优先完整备份，渲染行作 fallback |
| `grep '^# '` 命中代码注释 | 先 `strip_fenced_blocks()` |
| fence 数量为偶数就通过 | 使用 `scan_fenced_blocks()` 状态机 |
| inner fence 提前关闭 output | outer 长度大于最长 inner run |
| 空 IFrame 直接删除 | 从同 cell 源代码或 metadata 回填，否则标注 |
| DataFrame widget 输出全是 UI CSS | 过滤噪声，仅保留有效 schema/数据 |
