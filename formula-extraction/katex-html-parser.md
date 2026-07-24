# KaTeX HTML 系统性重建参考

当页面无原始 LaTeX（无 annotation、无 data-tex、无 MathML）且公式密集（>10 个）时，编写 KaTeX `.katex-html` DOM 解析器是可行方案。

## 前提条件（全部满足才可使用）

1. 编写**可复用的程序化解析器**（Python/JS），非手动逐公式提取
2. 解析器覆盖下方列出的关键结构
3. 通过 Playwright 渲染验证达到 **0 KaTeX error + 0 mstyle[mathcolor] error**
4. 批量处理后执行完整后处理管道（见 SKILL.md）
5. 对未识别结构采用 fail-closed：返回失败并交给调用方截图，不静默摊平成文本

## KaTeX HTML 关键结构

KaTeX 的 HTML 渲染层 CSS 类由 KaTeX 定义，与宿主网站无关，但不同 KaTeX 版本仍可能改变细节。解析器必须记录测试过的 KaTeX 版本。

| 结构 | CSS 类 / 模式 | 解析要点 |
|------|--------------|---------|
| 普通字符 | `.mord` (text node) | Unicode → LaTeX 映射 |
| 上下标 | `.msupsub > .vlist-t / .vlist-t2` | 见 vlist 方向规则 |
| 分式 | `.mfrac > .vlist` | top 最小 = 分子，top 最大 = 分母 |
| 运算符（无 limits） | `.mop`（无 `.msupsub`） | textContent → OP_MAP |
| 运算符（有 limits） | `.mop > .msupsub` | 先提取 op，再解析 supsub |
| 运算符（op-limits） | `.mop.op-limits > .vlist` | 见 op-limits 结构 |
| 根号 | `.msqrt` | `\sqrt{内容}` |
| 重音 | `.accent > .accent-body + .mord` | `\hat` / `\tilde` / `\bar` / `\dot` / `\vec` |
| 上划线 | `.overline` | `\overline{内容}` |
| 括号 + 上下标 | `.mclose/.mopen + .msupsub` | 递归进入子节点 |
| 黑板体 | `.mord.mathbb` | `\mathbb{内容}` |
| 花体 | `.mord.mathcal` | `\mathcal{内容}` |
| 文本模式 | `.mord.text` | `\text{内容}` |
| 矩阵/分段/cases | `.mtable > .col-align-* > .vlist` | 见 mtable |
| 分段函数包装 | `.minner > .mopen + .mtable + .mclose` | 识别 `cases` |
| 数组列间距 | `.arraycolsep` | 忽略 |
| 空分隔符 | `.mclose.nulldelimiter` | 忽略 |
| 空格 | `.mspace` | 空格 |
| 渲染辅助 | `.strut` / `.vlist-s` / `.frac-line` / `.rule` | 忽略 |

## vlist 方向规则（核心）

**方向错误导致上下标反转，是最严重的语义错误。**

```text
.vlist-t2 + 1 个 content span → 下标
.vlist-t（非 t2）+ 1 个 content span → 上标
任何 vlist + 2 个 content spans → 按 CSS top 排序：
  top 最小（最负）= 上标
  top 最大（最正）= 下标
```

Content span：排除 `.vlist-s` 和 `.strut` 后的直接 `<span>` 子节点。

CSS `top`：从 `style="top: -Xem"` 中提取数值。

## 多 `.base` 拼接与命令边界

一个 `.katex-html` 常被 KaTeX 切成**多个 `.base` span**：每个关系符/二元运算符（`=`、`≤`、`+` 等）后会开一个新 `.base`。例如 `A_t=E_t≤L` 渲染为 3 个 `.base`。

合并多个 base（以及 base 内多个 token）时，**必须走同一条 TeX control-word 边界规则**，不能裸 `''.join`：只有当**前一 part 以 `\[A-Za-z]+` 形式的控制字命令结尾，且后一 part 以字母开头**时，才插一个空格。

- `\leq` + `L` → `\leq L`：不插空格会粘成 `\leqL`，被当成一个未定义控制序列（`Undefined control sequence`）。
- `\leq` + `1` → `\leq1`：**数字不会成为命令名的一部分**，不需分隔。
- `\text{prob}` + `x` → `\text{prob}x`：命令以闭合分组 `}` 结尾，不是控制字，`}x` 不会粘成命令；`\text{}` 后是否补视觉间距属于另一条后处理规则，不在此列。
- 普通符号（`=`、数字、已闭合分组）结尾 + 任意后续 → 不插空格。

`.mspace` 解析为一个空格 part（不是空串）；join 时把 falsy/空 part 跳过即可，真正的命令边界空格由上面的规则补回。

**仓库已有实现**：`html-to-markdown/formula_batch.py` 的 `_join()` 就是这条规则（`re.search(r"\\[A-Za-z]+$", result)` 且下一 part 以字母开头才插空格），`_merge()` 把它同时用于分式、上下标和 `.katex-html` 下多个 `.base` 的合并。自己写临时 parser 时照抄这一条，不要用 `''.join`。

## op-limits 结构

```text
.mop.op-limits 内的 .vlist：
  3 个 span（按 top 排序）：上标、运算符本体、下标
  2 个 span（按 top 排序）：运算符本体、下标
```

解析结果可能已是 `\max` 等命令；先查 SYM_MAP/OP_MAP，无匹配则保留解析结果。

## mtable 解析规则

```text
.mtable：
  .col-align-l / .col-align-r / .col-align-c
    .vlist-t > .vlist-r > .vlist > span[style*="top:"]
```

识别 cases：

- `.minner` 的**直接子节点**中有文本为 `{` 的 `.mopen.delimcenter`
- 同层有 `.mclose.nulldelimiter`
- 满足 → `\begin{cases} ... \end{cases}`
- 否则 → `\begin{array}{} ... \end{array}`

检测 `.mopen` / `.mclose` 必须使用 `recursive=False`，否则会误命中 cell 内的括号。

### mtable 行提取陷阱：嵌套 vlist 污染

cell 内部可能包含 op-limits，它也有自己的 `.vlist`。深搜所有 `.vlist` 会把运算符 limits 当成表格行。

正确路径：

```text
col-align > vlist-t > vlist-r > vlist > span[style*="top:"]  ← 表格行
                                            └── cell 内的 op-limits > vlist
```

实现要求：

1. 从 `col-align` 找直接子元素 `.vlist-t`
2. 沿固定路径到表格级 vlist
3. 只取该 vlist 的直接 `span[style]`

## Unicode → LaTeX 映射参考

### 希腊字母

| Unicode | LaTeX |
|---------|-------|
| α | `\alpha` |
| β | `\beta` |
| γ | `\gamma` |
| δ | `\delta` |
| ε / ϵ | `\varepsilon` / `\epsilon` |
| θ | `\theta` |
| λ | `\lambda` |
| μ | `\mu` |
| π | `\pi` |
| σ | `\sigma` |
| φ / ϕ | `\varphi` / `\phi` |
| ω | `\omega` |

### 运算符

| Unicode/文本 | LaTeX |
|-------------|-------|
| max / min | `\max` / `\min` |
| arg / sup / inf / lim | 对应 LaTeX 命令 |
| log / exp / sin / cos / tan | 对应 LaTeX 命令 |
| ∑ / ∏ / ∫ | `\sum` / `\prod` / `\int` |

### 关系/二元运算

| Unicode | LaTeX |
|---------|-------|
| ≤ / ≥ / ≠ / ≈ | `\leq` / `\geq` / `\neq` / `\approx` |
| ∈ / ∉ / ⊂ | `\in` / `\notin` / `\subset` |
| → / ← | `\rightarrow` / `\leftarrow` |
| ∞ / ∇ / ∂ | `\infty` / `\nabla` / `\partial` |
| × / · | `\times` / `\cdot` |

## 解析器返回契约

不要只返回字符串。返回结构化结果：

```python
from dataclasses import dataclass, field

@dataclass
class ParseResult:
    latex: str | None
    success: bool
    unknown_nodes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostic_text: str | None = None
```

- `success=True`：所有有语义的节点均已识别
- `success=False`：出现未知语义结构、结构数量不一致或无法保持方向
- `diagnostic_text`：可保存 `textContent` 供排查，但**不得作为成功的 LaTeX 输出**

## 解析器架构建议

```python
def parse_katex_node(node) -> ParseResult:
    """递归解析单个 .katex-html 节点。"""
    # 1. 判断节点类型
    # 2. 分派处理函数
    # 3. 递归处理子节点
    # 4. join 时跳过 falsy part，在 control-word 边界补空格
    #    ——base 内和跨 base 合并都走同一规则（见「多 .base 拼接与命令边界」）
    # 5. 任一未知语义节点 → success=False
    ...

def post_process(latex: str) -> str:
    """统一后处理管道，见 SKILL.md。"""
    ...
```

关键设计决策：

- 递归下降，每个 CSS 类对应一个处理函数
- 命令边界只在 parser parts 的 join 阶段处理；**base 内与跨 base 合并共用同一 join，先过滤空 part**
- 后处理管道作为最后一步统一应用
- **未知结构 fail-closed**：返回失败标记和节点信息，由调用方截图或人工复核
- **禁止**把 `textContent` 当作可交付公式；它会静默丢失分式、上下标、矩阵等结构
