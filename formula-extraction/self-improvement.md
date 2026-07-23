# formula-extraction 专属回归用例表

> **通用元规则**（泛化检查清单闸 1 + 病根 + 改进流程）见 `../_meta/skill-self-improvement.md`。改本 skill 前先过那份的两道闸。本文件只放 formula-extraction 的**专属回归用例表**（闸 2）。

后处理管道（SKILL.md 后处理段）是一串**文本替换规则**，最容易犯"改一条粘连修正、碰坏另一条"的回归。改任何替换/检测规则后，把全表喂给临时 Python 跑：替换类比对 `输出==期望`，检测类比对 `hit==expect`。全绿才落地。**禁删已有行。**

## 后处理替换规则（输入 → 期望输出）

| 规则 | 输入 | 期望输出 | 反例（不该动） |
|------|------|---------|----------------|
| Prime | `g^'` | `g'` | `g^{2}` → 不变 |
| `\sim` 后粘连 | `\simp` | `\sim p` | `\simeq` → 不变（是合法命令） |
| LaTeX 命令粘连 | `\gammaV` | `\gamma V` | `\gamma` → 不变（无粘连） |
| `\text{}` 后粘连 | `\text{prob}1` | `\text{prob} 1` | `\text{prob} 1` → 不变（已有空格） |
| Unicode 希腊 ϵ | `ϵ` | `\epsilon` | `\epsilon` → 不变 |
| Unicode ∗ | `∗` | `*`(数学)/`\ast`(GitHub) | 见平台差异 |
| Unicode 上标 | `x⁻¹` | `x^{-1}` | `x^{-1}` → 不变 |
| Unicode 下标 | `x₀` | `x_{0}` | `x_{0}` → 不变 |
| double caret | `x^^2` | `x^2` | `x^2` → 不变 |

> ⚠️ 命令粘连修正的假阳性风险：`\simeq`/`\simp` 都以 `\sim` 开头，但 `\simeq` 是合法命令、`\simp` 是粘连。规则必须**只在后接单个字母且非已知命令延续时**才拆——反例列里的合法命令是防线，别删。

## 平台差异规则（KaTeX vs GitHub MathJax，缺陷 2）

| 规则 | 输入 | 期望输出 | 机制 |
|------|------|---------|------|
| `\text{}` 内下标符 | `\text{signal_source}` | `\text{signal}\_\text{source}` | GitHub MathJax `\text{}` 内 `_` 即使 `\_` 也报 `'_' allowed only in math mode`；两端通吃唯一写法是拆到 `\text{}` 外 |
| 数学块内裸 `*` | `SR^{*}`（$...$内） | `SR^{\ast}` | 成对 `*` 被 GitHub markdown 当 emphasis 吃掉，MathJax 报 `Extra close brace` |

## 检测规则（命中 = 需修）

| 规则 | 输入 | 期望命中 | 理由 |
|------|------|:---:|------|
| 公式内裸 CJK | `$\text{收益}$` 外的裸中文入 math mode | ✅ | KaTeX warning |
| `\text{}` 内特殊符 | `\text{a_b}` | ✅ | 见平台差异 |
| double subscript | `d_\pi_\theta` | ✅ | 需补分组 `d_{\pi_\theta}`，只补分组不改方向 |

---

新增后处理规则请按同样格式加行（含正例 + **合法命令/已正确形态的反例**）。这些反例是防命令粘连修正误伤合法命令的关键防线。
