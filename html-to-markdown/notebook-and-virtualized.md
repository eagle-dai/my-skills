# Notebook 类页面 + 虚拟化容器的提取规则

适用于 Jupyter / Databricks / Colab / Observable 等 cell 模型页面，以及任何使用虚拟化滚动（Monaco editor / CodeMirror / react-virtualized）的富文本组件。

非本类页面也可参考"虚拟化容器"和"空 lazy-load 占位"两节——它们泛用。

---

## Notebook 类页面识别

**识别信号**（任一即可）：
- 标题含 `Databricks` / `Jupyter` / `Colab` / `notebook` / `.ipynb`
- DOM 中含 `command-input` / `command-box` / `cell-output` / `jp-Cell` / `cm-editor` / `monaco-editor` / `data-mode-id="python|sql|r|scala"` 等 cell 容器
- 有规整的"代码 + 输出"重复结构

---

## 1. Cell 模型梳理（提取前必做）

每个 notebook 平台的 DOM 结构不同，但抽象 cell 模型一致：

```text
Cell ──┬── Input
       │     ├── Markdown cell：渲染好的 HTML
       │     └── Code cell：源代码（语言已知）
       └── Output（可选，0..N 个）
             ├── Text/Stream（stdout/stderr 文本）
             ├── HTML/Table（DataFrame 等）
             ├── Image（PNG/SVG/Plot）
             ├── IFrame（视频、嵌入页）
             └── Error/Traceback
```

**Phase 1 必须确定的参数**：

| 参数 | 探查方法 |
|------|---------|
| Cell 顶层容器选择器 | 找一个 `count` 等于 `code+markdown cell 总数`的 class |
| Cell 类型判定 | **见下方"类型判定陷阱"** |
| 代码语言 | 编辑器属性如 `data-mode-id`、`data-language`、cm class |
| Output 容器选择器 | 通常与 input 兄弟，class 含 `result` / `output` |

**容易错的点**：直接用 `.command-input` / `.code-cell` 等"cell 容器"选择器，可能数量与真实 cell 数不符。**正确做法是按 type breakdown 校验**：

```text
markdown_count + code_count == total_cells
```

不等就说明选择器选错了层级。

### 类型判定陷阱（Databricks/Colab 实测）

不要用"是否含 `.command-input` / 编辑器容器"作为 code cell 标志——Databricks 的 markdown cell 内部**也包了一层 `.command-input`**（结构对称用），结果所有 cell 都被判成 code cell。

**可靠判定**（按优先级）：

```text
① 从该 cell 内的代码备份/渲染态选择器实际提取代码
② 提取结果 strip() 非空 → code cell
③ 否则 → markdown cell（或空 cell）
```

也就是说：先 try-extract，再分类。这同样能复用 §2 的双源协议，不引入新选择器。

---

## 2. 虚拟化容器的双源/多源代码提取

**问题**：Monaco editor / CodeMirror 等富文本编辑器使用虚拟滚动；SingleFile 保存时只有视口内的 cell 完成 DOM 渲染。其余 cell 看不到 `.view-line` 等渲染态元素。

**信号**：

```text
活跃 monaco editor 数量（.view-lines） < code cell 总数
```

**优先级提取协议**（按编辑器实际备份机制设计；不同平台可能不同）：

```text
对每个 code cell：
  ① 找渲染态备份容器（如 .monaco-editor.unformatted pre）
     → 直接读 pre.innerText 即完整源代码
  ② 没有 ① → 找渲染态片段容器（如 .view-line），按几何位置排序拼接
     - Monaco：按 element.style.top 数值升序
     - CodeMirror：按 DOM 顺序（每行一个 .cm-line）
  ③ 二者都没有 → 报错该 cell idx + 跳过/留空 + 加 ⚠️ 标注
  
最后必须报告：
  - 用 ① 的 cell 数 + 用 ② 的 cell 数 + 失败的 cell idx
```

**举例（Databricks）**：

| 来源 | 选择器 | 内容形式 |
|------|--------|---------|
| 备份 | `.monaco-editor.unformatted pre` | 完整源代码（视口外 cell 用） |
| 渲染态 | `.command-box .view-line` | 每行一个元素，按 `style.top` 排序 |

**举例（Jupyter Lab）**：

| 来源 | 选择器 | 内容形式 |
|------|--------|---------|
| 渲染态 | `.cm-editor .cm-line` | 每行一个，按 DOM 顺序 |
| 兜底 | `textarea.cm-content`（有时） | 完整源代码 |

**NBSP 陷阱**：从渲染态 `.view-line` 提取时，缩进可能被替换为 `\xa0`（不间断空格 U+00A0）。代码看起来正常但 Python/shell 不会执行。**统一在 join 阶段把 `\xa0` 替换为普通空格**。

---

## 3. Code cell 的 Output 处理策略

不同平台保存的输出完整度差异很大；SingleFile 经常**丢失**（输出未运行 / 已清空 / 懒加载未触发）。

### 3.1 决策矩阵

| 输出形式 | DOM 信号 | 处理方式 |
|---------|---------|---------|
| 文本（stdout/print） | output 容器内 `<pre>` 或纯文本 | fenced code block，语言可标 `text` |
| 错误/Traceback | class 含 `error` / `traceback`，颜色异常 | fenced code block + 高亮提示 |
| DataFrame/HTML 表格 | output 容器内 `<table>` | Markdown 表格（GFM 语法）；超长时改用 fenced HTML |
| **DataFrame React widget**（Databricks/Colab data inspector） | 容器内有 `<svg>` 但无 `<table>`，文本只剩 schema 行 + UI 噪声 | **只保留 schema 行**（如 `results_df:pandas.core.frame.DataFrame = [...]`）；其余按"widget 噪声"过滤；schema 也没有则跳过 |
| 图片（plot/PIL） | output 容器内 `<img src="data:image/...">` | 解码保存为图片，按图片规则引用 |
| SVG（plotly/matplotlib） | output 容器内 `<svg>` | 序列化保存为 `.svg` 引用 |
| IFrame（视频、嵌入页） | output 容器内 `<iframe src="...">`，src 非空 | 引用块说明 + 链接 |
| **空 IFrame（懒加载未触发）** | `<iframe src="">` 或 `height="0"` | 见 §4 回填 |
| 空 output 容器 | 无任何子元素或仅含装饰 UI | 跳过，不影响 markdown 结构 |

#### Widget 噪声过滤清单（DataFrame / 数据浏览器等 React 组件）

虚拟化数据 widget 的 `innerText` 经常掺入 CSS 字符串和 ARIA 可达性提示。提取后必须剥掉以下模式（按需扩充，不要硬编码站点名）：

```python
NOISE_PATTERNS = [
    re.compile(r'\[data-radix-scroll-area-viewport\][^\n]*'),  # Radix UI scrollbar CSS
    re.compile(r'^ ?To pick up a draggable item.*$', re.M),     # dnd-kit a11y hint
    re.compile(r'^ ?While dragging, use the arrow keys.*$', re.M),
    re.compile(r'^ ?Press space again to drop.*$', re.M),
    re.compile(r'\{scrollbar-width:none[^}]*\}'),                # 任何裸露的 CSS rule
]
```

剥离后 `strip()` 仍为空 → 跳过该 cell（不要写空 Output 标记）。

### 3.2 输出标记格式

代码块后空一行加引用块，统一格式：

```markdown
```python
print("hello")
```

> **Output:** hello
```

复合输出（多块）：

```markdown
> **Output:**
> 
> ```text
> stdout text...
> ```
> 
> ![plot](files/<zip>/output_plot_01.png)
```

#### Outer fence 升级规则（防 inner fence 提前关闭）

LLM 响应、教学型输出常含 ` ```bash ` ` ```python ` 等 inner fence。outer 用 3 反引号会被 inner 的 3 反引号提前关闭，导致后续内容溢出 blockquote。

**判定 + 升级**（注入前对每个 outputText 判断一次）：

```python
has_inner_fence = any(ln.lstrip().startswith('```')
                      for ln in out_text.split('\n'))
outer = '````' if has_inner_fence else '```'
```

注意 `lstrip()` —— inner fence 可能有缩进（列表内的代码块），不能只看行首。GitHub / CommonMark 都支持：外层 fence 的反引号数 > 内层即可。如内层出现 4 反引号，再升到 5。

### 3.3 默认行为

- **保留有内容的 output**（默认开启，不需要用户开关）
- **跳过空 output 容器**（不写 `> Output: (empty)`，避免噪声）
- **报告 output 处理统计**：保留 N、跳过 M、回填 K（§4）

---

## 4. 空 lazy-load 占位的回填

**问题**：SingleFile 保存时如果资源未加载（IFrame、`<img loading="lazy">`、`<video>`），`src` 可能为空字符串。直接丢弃会丢信息。

**回填规则**：

| 占位类型 | 回填来源（按优先级） |
|---------|---------------------|
| IFrame（视频嵌入） | ① 输出旁的 markdown 文字"click here to view"含真实链接<br>② **同一 cell 的源代码中提取常量**（如 `video_url = "..."`、`IFrame(src="...")`）<br>③ 全局 hydration JSON / 页面 metadata<br>④ 放弃，留 `> **Output:** Embedded content (URL not preserved)` |
| `<img>` | `data-src` / `data-original` / `data-lazy` 属性；srcset；同 cell 代码中的 URL |
| `<video>` | `data-src` / `<source data-src>` |

**通用代码反推算法**（适用于 IPython `display(IFrame(src=URL))` 模式）：

```python
# 对 cell 源代码做正则提取
url_re = re.compile(r'(?:video_url|src|url)\s*=\s*["\']([^"\']+)["\']')
m = url_re.search(cell_source)
if m and not iframe_src:
    iframe_src = m.group(1)
```

回填后必须在报告中说明：`回填了 N 个空占位（IFrame K, img M, video L）`。

---

## 5. Markdown cell 内嵌的 inline 代码块

Markdown cell 自身可能含 `<pre><code>` 块（不是 code cell！）。这些应转为 fenced code block 出现在 markdown 段落中。

**和 code cell 的区分**：
- 在 `.markdown` 内部 → markdown inline 代码块（无语言或语言来自 class）
- 在 cell input 编辑器容器内 → code cell

**fence 总数计算**：

```text
total_3bt_fences = code_cell_count * 2
                 + inline_code_block_count * 2
                 + output_blockquote_3bt_count * 2     # §3.2 注入的 > ```text ... > ```
                 + nested_inner_fence_in_4bt_outer     # 升级到 4-反引号 outer 时被包住的 inner ``` 行数
```

最后一项不可预先算出（取决于 LLM 输出实际形态），所以**严格的公式校验在 4-反引号升级出现时会失效**——这时改用更宽松但仍有效的"**配对校验**"代替总数校验：

```python
n3 = sum(1 for ln in md.splitlines() if re.match(r'^>?\s*```(?!`)', ln))
n4 = sum(1 for ln in md.splitlines() if re.match(r'^>?\s*````(?!`)', ln))
assert n3 % 2 == 0 and n4 % 2 == 0   # 偶数 = 配对完整即可
```

`>?\s*` 让正则同时覆盖 blockquote 内的 fence（行首是 `> `）；`(?!`)` 防止 4-反引号被误算成 3-反引号。

> 验证时 fence 数对不上不一定是错——可能是 markdown cell 自带 inline 代码块、注入了 Output blockquote、或 outer fence 升级包了 inner 3-反引号。审计基线里**分别计 markdown 内 `pre>code` 数量、Output blockquote 数量**，但**最终判定以"奇偶配对"为准**，不强求总数等式。

---

## 6. 验证脚本必备：剥离代码块再 grep

`grep ^# md_file` 会命中 Python 注释（`# 这是注释`），导致 H1 计数虚高。**所有针对结构的 grep 必须先剥离 fenced code block**：

```python
import re
# 剥离 ```...``` 代码块
no_code = re.sub(r'```.*?\n.*?```', '', text, flags=re.DOTALL)
# 然后才能正确数标题、列表
```

同理：
- 计列表项数量必须排除代码块
- 计标题必须排除代码块
- 计 blockquote 时必须排除代码块（代码里的 `>` 不算）

**也要排除评论区里的代码块嵌套**（出于同样理由）。

---

## 7. Phase 1 报告模板（notebook 类页面追加）

```text
平台: [Databricks / Jupyter / Colab / Observable / Other]
Cell 总数: N (markdown=M_md, code=M_code, 校验 M_md+M_code == N)
Code 语言: [Python / SQL / R / Scala / 多语言]
Cell 容器选择器: <selector>
代码提取分布:
  - 备份容器（如 .unformatted pre）: K1 cells
  - 渲染态片段（如 .view-line）: K2 cells
  - 失败: K3 cells (idx: ...)
Output 输出统计:
  - 文本/Traceback: ...
  - 表格: ...
  - 图片/SVG: ...
  - IFrame（含空占位）: ... (将回填 N 个)
  - 空容器（跳过）: ...
Lazy-load 空占位: K 个 (类型: IFrame=K1, img=K2)
  → 可回填: K' (来源: 源代码/data-src/...)
NBSP 出现: 是/否（提取时需替换）
```

---

## 8. Phase 2 sub agent prompt 追加段（notebook 时拼接）

```
## Notebook 处理规则

平台: [...]
Cell 容器: [...] (count=[N])
Cell breakdown: [M_md markdown + M_code code]

### 代码提取
- 优先 [备份选择器]
- fallback [渲染态选择器]，按 [排序方式] 排序
- NBSP 替换：提取后统一 .replace('\xa0', ' ')
- 失败 cell：留 ⚠️ 标记并报告 idx

### Output 处理
默认保留有内容输出，跳过空容器。每种输出类型按 §3.1 决策矩阵处理。
- 空 IFrame 必须从源代码反推 src（§4）
- DataFrame React widget：套用 §3.1 widget 噪声过滤清单，剥离后空则跳过
- 报告：保留 N、跳过 M、回填 K

### 输出标记格式
代码块后空一行：
> **Output:** <内容或链接>
复合输出用多行 blockquote。
**outer fence 升级**：若 outputText 任一行 `lstrip()` 后以 ` ``` ` 开头，外层 fence 用 4 反引号 ` ```` `（§3.2）。

### Cell-block 对齐
不要依赖原始 cell idx（多遍处理时容易漂移）。用 normalize 后的 code 前缀对齐：

```python
norm = lambda s: re.sub(r'\s+', '', s)
ok = norm(block_code)[:80] == norm(cell_code)[:80] \
     or norm(block_code) in norm(cell_code) \
     or norm(cell_code) in norm(block_code)
```

按顺序配对，不匹配则 warning 并保留原顺序，不要静默跳过。

### Markdown cell 内嵌代码块
保留为 fenced code block（无语言或从 class 取）。审计时单独计数。
```

---

## 9. 验证补丁（checklist 追加项）

| 检查项 | 方法 | 阻断? |
|-------|------|-------|
| Cell 总数 | `cells.length` vs markdown_count + code_count | **差异>0 阻断** |
| Code cell 代码完整 | 每个 cell 都能从 ① 或 ② 提取，不为空 | **任一空 cell 阻断** |
| NBSP 残留 | `'\xa0' in markdown` | **阻断** |
| 3-反引号 fence 配对 | `n3 % 2 == 0`（含 blockquote 内） | **奇数阻断** |
| 4-反引号 fence 配对 | `n4 % 2 == 0`（outer fence 升级用） | **奇数阻断** |
| Output blockquote 渲染 | Playwright 抽查含 inner fence 的 cell：单一 `<pre>` 块 + 末尾文本到位 | 截断 → 阻断（升 outer fence） |
| Output 回填 | 空 IFrame 数量 == 回填数量 + 标注未回填数量 | 缺一 → 警告 |
| 验证脚本剥离代码块 | grep 前必须 `re.sub(r'```.*?```', '', text, flags=re.DOTALL)`，4-反引号块同样剥 | 不剥离则计数无效 |
| Widget 噪声残留 | `re.search(r'\[data-radix-scroll-area-viewport\]', md)` | 命中 → 警告（漏过滤） |

---

## 10. 反例：Databricks 任务的真实教训

| 错误 | 修复 |
|------|------|
| 默认跳过所有 `.results` | 改为按内容分类决策（§3.1） |
| 7 个空 IFrame 输出当噪声扔掉 | 从 cell 源码提取 `video_url` 回填（§4） |
| `grep '^# '` 数 H1 得到 47（命中代码注释） | 验证脚本先剥离 fenced code block（§6） |
| Sub agent 报告 fence=62 与 30*2 不符 → 误判错误 | 认识到 markdown cell 内嵌 inline 代码块（§5） |
| 缩进 `\xa0` 让代码不可执行 | 提取阶段统一替换（§2） |
| 用 `.command-input` 当 code cell 标志 → 把 markdown cell 全算成 code（87 全选 vs 30 真实） | 改为"try-extract，非空才是 code"（§1 类型判定陷阱） |
| LLM 输出含 ` ```bash ` 把 outer 3 反引号 fence 提前关闭，"Happy coding!" 漂出 blockquote | inner fence 检测 → outer 升 4 反引号（§3.2） |
| DataFrame React widget innerText 提到 markdown 全是 Radix CSS + 拖拽 a11y 提示 | widget 噪声过滤清单（§3.1）；保留 schema 行或跳过 |
| 按 cell idx 注入，多遍处理时漂移 | normalize code 前缀对齐（§8） |
