# KaTeX HTML 系统性重建参考

当页面无原始 LaTeX（无 annotation、无 data-tex、无 MathML）且公式密集（>10 个）时，编写 KaTeX `.katex-html` DOM 解析器是可行且推荐的方案。

## 前提条件（全部满足才可使用）

1. 编写**可复用的程序化解析器**（Python/JS），非手动逐公式提取
2. 解析器覆盖下方列出的关键结构
3. 通过 Playwright 渲染验证达到 **0 KaTeX error + 0 mstyle[mathcolor] error**
4. 批量处理后执行完整后处理管道（见 SKILL.md 后处理管道章节）

## KaTeX HTML 关键结构

KaTeX 的 HTML 渲染层 CSS 类是 KaTeX 库定义的，与宿主网站无关——任何使用 KaTeX 的网站都使用相同的 `.katex-html` 结构。

| 结构 | CSS 类 / 模式 | 解析要点 |
|------|--------------|---------|
| 普通字符 | `.mord` (text node) | Unicode → LaTeX 映射（θ→`\theta` 等） |
| 上下标 | `.msupsub > .vlist-t / .vlist-t2` | 见 vlist 方向规则 |
| 分式 | `.mfrac > .vlist` | top 最小 = 分子, top 最大 = 分母 |
| 运算符(无 limits) | `.mop` (无 `.msupsub` 子节点) | textContent → OP_MAP (`max`→`\max` 等) |
| 运算符(有 limits) | `.mop > .msupsub` | 先提取 op 文本, 再解析 supsub |
| 运算符(op-limits) | `.mop.op-limits > .vlist` | 3部分: sup/op/sub (按 CSS top 排列) |
| 根号 | `.msqrt` | `\sqrt{内容}` |
| 重音 | `.accent > .accent-body + .mord` | ˆ→`\hat`, ~→`\tilde`, ¯→`\bar`, ˙→`\dot`, →→`\vec` |
| 上划线 | `.overline` | `\overline{内容}` |
| 括号 + 上下标 | `.mclose/.mopen + .msupsub` 子节点 | 必须递归进子节点, 如 `(γλ)^l` |
| 数学字体(黑板体) | `.mord.mathbb` | `\mathbb{内容}` |
| 数学字体(花体) | `.mord.mathcal` | `\mathcal{内容}` |
| 文本模式 | `.mord.text` | `\text{内容}` |
| 矩阵/分段/cases | `.mtable > .col-align-* > .vlist` | 见 mtable 解析规则 |
| 分段函数包装 | `.minner > .mopen + .mtable + .mclose` | 外层 minner 含 `{` 和 nulldelimiter → `\begin{cases}` |
| 数组列间距 | `.arraycolsep` | 忽略（纯间距） |
| 空分隔符 | `.mclose.nulldelimiter` | 忽略（cases 右侧不可见分隔符） |
| 空格 | `.mspace` | 空格 |
| 忽略 | `.strut` / `.vlist-s` / `.frac-line` / `.rule` | 渲染辅助, 无语义 |

## vlist 方向规则（核心）

**方向错误导致上下标反转，这是最严重的语义错误。**

```text
.vlist-t2 + 1个 content span → 下标 (subscript)
.vlist-t (非 t2) + 1个 content span → 上标 (superscript)
任何 vlist + 2个 content spans → 按 CSS top 排序:
  top 值最小(最负) = 上标
  top 值最大(最正) = 下标
```

Content span 的识别：排除 `.vlist-s` 和 `.strut` 后的 `<span>` 子节点。

CSS `top` 值的解析：从 `style="top: -Xem"` 属性中提取数值。

## op-limits 结构

```text
.mop.op-limits 内的 .vlist 可能有 2 或 3 个 content span:
  3 个 span (按 top 排序): 上标, 运算符本体, 下标
  2 个 span (按 top 排序): 运算符本体, 下标
注意: 解析 content 返回的可能已经是 LaTeX 命令（如 \max），
  需先查 SYM_MAP/OP_MAP, 无匹配则直接使用
```

## mtable 解析规则

```text
.mtable 结构:
  .col-align-l / .col-align-r / .col-align-c  (每个对应一列)
    .vlist-t > .vlist-r > .vlist > span[style="top:..."]  (每个 span 对应一行)
      .mord  (行内容)

识别 cases 环境:
  .minner 的直接子节点中:
    - .mopen.delimcenter 文本为 "{"
    - .mclose.nulldelimiter（右侧无可见分隔符）
  满足条件 → \begin{cases} ... \end{cases}
  否则 → \begin{array}{} ... \end{array}

注意: 检测 .mopen / .mclose 时必须用 recursive=False，
  否则会命中 mtable 内部行中的 ( ) 等括号。

行内 \text{} 后紧跟数字/变量时需要空格:
  \text{with probability}1 → 渲染时 "probability" 和 "1" 会粘连
  建议: \text{内容 } 或 \text{内容}~
```

### mtable 行提取的关键陷阱：嵌套 vlist 污染

**问题：** mtable 的每个 cell 内容中可能包含 op-limits 结构（如 `\max_{w\in\mathcal{S}}`），而 op-limits 内部也有自己的 `.vlist`。如果用 `.//*[contains(@class, "vlist")]/*[@style]` 这种深搜 XPath 来提取行，会把 cell 内部 op-limits 的 vlist spans 也误识别为表格行，导致 3 行 cases 变成 7+ 行碎片。

**正确做法：** 只搜索**表格列结构直属的第一层 vlist**：

```text
col-align > vlist-t > vlist-r > vlist > span[style*="top:"]  ← 这些是行
                                           └── .mord 内可能有 .op-limits > .vlist  ← 这些是 cell 内容，不是行！
```

具体实现：
1. 从 `col-align` 找直接子元素 `.vlist-t`（不用 `.//*`）
2. 沿 `vlist-t > vlist-r > vlist` 路径导航到表格级 vlist
3. 只取该 vlist 的**直接子 span**（用 `./*[@style]`），不递归搜索后代

## Unicode → LaTeX 映射参考

解析器需要维护的核心映射表（非穷举，按需扩展）：

### 希腊字母

| Unicode | LaTeX |
|---------|-------|
| α (U+03B1) | `\alpha` |
| β (U+03B2) | `\beta` |
| γ (U+03B3) | `\gamma` |
| δ (U+03B4) | `\delta` |
| ε/ϵ (U+03B5/U+03F5) | `\varepsilon`/`\epsilon` |
| θ (U+03B8) | `\theta` |
| λ (U+03BB) | `\lambda` |
| μ (U+03BC) | `\mu` |
| π (U+03C0) | `\pi` |
| σ (U+03C3) | `\sigma` |
| φ/ϕ (U+03C6/U+03D5) | `\varphi`/`\phi` |
| ω (U+03C9) | `\omega` |

### 运算符

| Unicode/文本 | LaTeX |
|-------------|-------|
| max | `\max` |
| min | `\min` |
| arg | `\arg` |
| sup | `\sup` |
| inf | `\inf` |
| lim | `\lim` |
| log | `\log` |
| exp | `\exp` |
| sin/cos/tan | `\sin`/`\cos`/`\tan` |
| ∑ (U+2211) | `\sum` |
| ∏ (U+220F) | `\prod` |
| ∫ (U+222B) | `\int` |

### 关系/二元运算

| Unicode | LaTeX |
|---------|-------|
| ≤ (U+2264) | `\leq` |
| ≥ (U+2265) | `\geq` |
| ≠ (U+2260) | `\neq` |
| ≈ (U+2248) | `\approx` |
| ∈ (U+2208) | `\in` |
| ∉ (U+2209) | `\notin` |
| ⊂ (U+2282) | `\subset` |
| → (U+2192) | `\rightarrow` |
| ← (U+2190) | `\leftarrow` |
| ∞ (U+221E) | `\infty` |
| ∇ (U+2207) | `\nabla` |
| ∂ (U+2202) | `\partial` |
| × (U+00D7) | `\times` |
| · (U+00B7/U+22C5) | `\cdot` |

## 解析器架构建议

```python
def parse_katex_node(node) -> str:
    """递归解析单个 .katex-html 节点，返回 LaTeX 字符串。"""
    # 1. 判断节点类型（mord/mop/mfrac/msupsub/...）
    # 2. 分派到对应处理函数
    # 3. 递归处理子节点
    # 4. 拼接结果时检查命令粘连（join 阶段统一插空格）
    pass

def post_process(latex: str) -> str:
    """统一后处理管道，见 SKILL.md。"""
    pass
```

关键设计决策：
- 递归下降，每个 CSS 类对应一个处理函数
- join 阶段统一检查命令粘连（`\\[a-zA-Z]+$` + 后续字母开头 → 插空格）
- 后处理管道作为最后一步统一应用
- 遇到未识别结构时 fallback 到 textContent（有损但不崩溃）
