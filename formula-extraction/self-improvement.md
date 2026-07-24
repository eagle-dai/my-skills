# formula-extraction 专属回归用例表

> **通用元规则**见 `../_meta/skill-self-improvement.md`。改本 skill 前先过泛化检查与回归两道闸。

后处理管道最容易出现“修一个粘连，破坏合法命令”的回归。改任何替换/检测规则后，必须跑完整表。**禁删已有行。**

## 后处理替换规则（输入 → 期望输出）

| 规则 | 输入 | 期望输出 | 反例（不该动） |
|------|------|---------|----------------|
| Prime | `g^'` | `g'` | `g^{2}` → 不变 |
| `\sim` token 边界 | parser parts `["\sim", "p"]` | `\sim p` | 单一 part `["\simeq"]` → 不变 |
| `\sim` + Greek token | parser parts `["\sim", "\nu"]` | `\sim \nu` | 单一 part `["\simneqq"]` → 不变 |
| 已有空格 | `\sim p` | 不变 | 不重复插空格 |
| LaTeX token 拼接 | parser parts `["\gamma", "V"]` | `\gamma V` | 单一 part `["\Gamma"]` → 不变 |
| 跨 base 命令边界 | parser parts（跨 base）`["\leq", "L"]` | `\leq L` | `["\leq", "1"]` → `\leq1`（数字不进命令名，不插空格） |
| 命令结尾 vs 分组结尾 | parser parts `["\leq", "L"]` | `\leq L` | `["\text{prob}", "x"]` → `\text{prob}x`（`}` 结尾非控制字，不插空格） |
| 跨 base 非命令 | parser parts `["E_{t}", "="]` | `E_{t}=` | `["=", "L"]` → `=L`（非命令收尾不插空格） |
| `.mspace` 空格 part | parser parts `["\leq", " ", "L"]`（中间 .mspace=空格） | `\leq L` | `["x", " ", "y"]` → `x y`（空格结尾使边界正则不匹配，不重复插） |
| `\text{}` 后粘连 | `\text{prob}1` | `\text{prob} 1` | `\text{prob} 1` → 不变 |
| Unicode ϵ | `ϵ` | `\epsilon` | `\epsilon` → 不变 |
| Unicode ∗ | `∗` | `*`（数学）/ `\ast`（GitHub） | 见平台差异 |
| Unicode 上标 | `x⁻¹` | `x^{-1}` | `x^{-1}` → 不变 |
| Unicode 下标 | `x₀` | `x_{0}` | `x_{0}` → 不变 |
| double caret | `x^^2` | `x^2` | `x^2` → 不变 |

> `\simeq`、`\simneqq` 等合法控制序列证明：不能在最终字符串上用 `\\sim([A-Za-z...])` 拆分。测试输入必须表达 parser part 边界，而不是只给最终字符串。

## 平台差异规则

| 规则 | 输入 | 期望输出 | 机制 |
|------|------|---------|------|
| `\text{}` 内下标符 | `\text{signal_source}` | `\text{signal}\_\text{source}` | GitHub MathJax 兼容 |
| 数学块内裸 `*` | `SR^{*}`（数学段内） | `SR^{\ast}` | 防止 GFM emphasis 破坏 |

## 检测规则（命中 = 需修）

| 规则 | 输入 | 期望命中 | 理由 |
|------|------|:---:|------|
| 公式内裸 CJK | math mode 中裸中文 | ✅ | KaTeX warning |
| `\text{}` 内特殊符 | `\text{a_b}` | ✅ | 平台差异 |
| double subscript | 原 DOM 证明嵌套下标，输出为 `d_\pi_\theta` | ✅ | 需补分组 |
| 相邻合法符号 | `\pi\theta`，且无原始下标证据 | ❌ | 可以是合法乘积 |
| 合法上下标 | `V^\pi_\theta`，原 DOM 同时含上下标 | ❌ | 不得按领域惯例改写 |

---

新增后处理规则必须包含：

- 至少 1 个正例；
- 至少 2 个合法反例；
- 输入来自哪个阶段（DOM token / parser part / 最终字符串）；
- 是否允许自动修复。
