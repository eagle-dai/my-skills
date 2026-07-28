# html-to-markdown 专属回归用例表

> **通用元规则**（泛化检查清单闸 1 + 病根 + 改进流程）见 `../_meta/skill-self-improvement.md`。改本 skill 前先过那份的两道闸。本文件只放 html-to-md 的**专属回归用例表**（闸 2）。

改任何下列检测/清理正则后，把全表喂给临时 Python 跑，`hit != expect` 即 FAIL，全绿才落地。**禁删已有行。**

## 强调定界符边界（缺陷 6/7，已被烧两次，重点保护）

当前正则：`(\*\*[^*\n]+?\*\*)([^\s。，、；：！？）】」』.,;:!?)])`

| 输入 | 期望命中 | 类别 | 理由 |
|------|:---:|------|------|
| `**标签：**https://` | ✅ | 英文字母紧贴 | right-flanking 失败，真违规 |
| `**概念辨析：**为什么` | ✅ | CJK 汉字紧贴 | 真违规 |
| `**结论**。` | ❌ | CJK 句号紧贴 | 标点是有效 right-flanking，GitHub 渲染正常 |
| `**结论**，后面` | ❌ | CJK 逗号紧贴 | 同上 |
| `**记录**：写清` | ❌ | 全角冒号紧贴 | 同上 |
| `**读法**。只看` | ❌ | 句号+汉字 | 句号先紧贴→合法 |
| `**结论** 。` | ❌ | 已插空格 | 不该再命中（此形态另用反向正则清） |

反向清理正则（清缺陷 7 过度修复留下的错误空格）：`\*\*[^*\n]+?\*\* [。，、；：！？）]` —— 命中即删空格。

## 行内公式 `$` 边界（缺陷 3，GitHub 平台）

当前正则：`([一-鿿　-〿＀-￯])\$(?!\$)` / `(?<!\$)\$([一-鿿　-〿＀-￯])`

| 输入 | 期望命中 | 类别 | 理由 |
|------|:---:|------|------|
| `收益率$r_t$表示` | ✅ | CJK 紧贴 $ 两侧 | GitHub 不渲染 |
| `见 $r_t$ 公式` | ❌ | ASCII 空格隔开 | 正常 |
| `（$w_t$）` | ✅ | 全角括号紧贴 | GitHub 不渲染 |

## 数学块内裸 `*`（缺陷 5，GitHub 平台）

检测：数学段内 `(?<!\\)\*` 命中 → 阻断，修 `*`→`\ast`

| 输入 | 期望命中 | 理由 |
|------|:---:|------|
| `$SR^{*}$` | ✅ | 裸 `*` 被当 emphasis，MathJax 报错 |
| `$a \ast b$` | ❌ | 已转义 |

## 题注提取候选发现（缺陷 8，语义规则，非正则）

判定项：给定内容块内一个候选节点，**是否分类为题注并输出**。非正则可跑，靠转换脚本的候选发现逻辑判定；此表是语义回归清单（人工/fixture 验证），改候选发现范围时必须逐条对照。

规则见 conversion-rules「题注提取」：只认 `figure > figcaption` / `table > caption` / Slate image 容器内 img 已验证同级 `<div>`，排除 UI/wrapper/正文。

| 候选节点 | 期望分类 | 理由 |
|----------|:---:|------|
| Slate image 容器内 img 同级 `<div>图 4-5　权益峰值...</div>` | ✅ 题注 | 已验证直接结构关系，命名性短文本 |
| `<figure>` 内 `<figcaption>系统架构</figcaption>` | ✅ 题注 | 标准结构 |
| `<table>` 内 `<caption>量化口径</caption>` | ✅ 题注 | 标准结构 |
| 图片工具栏 `<div class="toolbar"><button/></div>` | ❌ 排除 | 含 button、UI class |
| resize wrapper `<div><img/></div>` | ❌ 排除 | 含 img，是 wrapper 非题注 |
| 图片后紧随的解释性长段落 `图 4-5 给出了…（多句）` | ❌ 排除 | 内容块父容器外/解释性正文，作正文保留不重复抽 |
| 内容块父容器外的下一普通段落 | ❌ 排除 | 跨出父容器，禁止抓取 |

去重项：同一 DOM 节点被普通段落遍历和题注 pass 同时触达 → `emitted_count == 1`（只输出一次，题注 pass 复用/移动而非重复输出）。

---

## 输出命名合同

命名必须由 `canonical_output_name()` / `numbered_document_name()` 机械生成；目录、
Markdown stem、资源目录和 ZIP stem 复用同一个结果。strict 多文档编号取渲染
DOM 稳定顺序，标题取 DOM 原文。

| 输入 | ordinal | 期望 | 反例/理由 |
|------|:---:|------|------|
| `01 \| AI 量化研究` | 1 | `01-AI-量化研究` | 不得双写为 `01-01-...` |
| `LLM 量化：可复现工作区` | 3 | `03-LLM-量化-可复现工作区` | 不得自由改成 `llm-quant-reproducible-workspace` |
| `05_安全边界` | 5 | `05-安全边界` | 下划线和竖线不能随机混用 |
| `report v1.2` | 无 | `report-v1-2` | 点号转 `-` 是明确合同，不得依赖旧的保留行为 |
| `2026 research` | 1 | `01-2026-research` | `2026` 是标题内容，不是第 1 篇的旧序号 |
| `CON` | 无 | `article-CON` | Windows 保留名不能原样作为 basename |
| `｜／：` | 无 | `article` | 纯标点稳定回退，不得追加随机字符 |

反例：同一输入不得在不同运行间选择中文标题/英文 slug；不得用时间戳、
随机数或 hash 解决重名。重名只用 DOM 顺序 ordinal 消解。

---

## 代码块行换行（缺陷 17，结构规则，非正则）

判定项：Slate/hljs 代码块——每行一个块级 `<div>`（子全 `<span>`，无块子）——提取后各行须以 `\n` 分隔，不得糊成一行。`fast_converter.py::_code_text` 判定，回归 `test_slate_code_block_preserves_line_breaks`。

| 输入结构 | 期望输出 | 理由 |
|------|------|------|
| `<pre data-slate-type="pre">` 内 3 个 `.se-line` div，各含 span 一行 | 三行以 `\n` 分隔（`a\nb\nc`） | 块边界即换行，`get_text()` 会漏 |
| 单个 `<code>` 内含真实 `\n` 文本 | 原样 `get_text()`，不改写 | 反例：非 Slate 布局，无多行 div，不触发 join |
| `<pre>` 内仅 1 个 line div | 退回整体 `get_text()` | 反例：`len(lines) > 1` 才 join，单行不特殊处理 |

## 无语义 wrapper 穿透 inline 上下文（缺陷 13，结构规则，非正则）

判定项：inline 上下文遇 `div/section/article/main`——无 `data-slate` 语义且无块子→穿透；否则 fail-close 路由 strict。`fast_converter.py::inline` 判定。

| 输入结构 | 期望 | 理由 |
|------|------|------|
| Slate 段落内嵌 `<div>wrapped <strong>x</strong> <katex></div>`（无块子） | converted，穿透为 `wrapped **x** $...$` | 正例：等价 span，不该 fail-close |
| 段落内 `<div>` 含 `<p>` 块子 | strict_required | 反例：wrapper 藏真块内容，不能扁平化 |
| 段落内未知 inline 元素 `<custom-widget>` | strict_required | 反例：未知语义仍保守 fail-close，穿透只放行无语义 wrapper |
| 带 `data-slate-type` 的 div | 走对应 slate 分支，不进 wrapper 穿透 | 反例：`not slate` 守卫，有语义的 div 不当透明 wrapper |

## 去水印检测：渐变尖 + 复杂背景 logo（缺陷 19，图像规则，真图 fixture 回归）

判定项：右下角实心站点 logo（橙水滴 icon + 灰字）在两种形态下须完整检测并去净。PR #41 换成"饱和锚点 + fill/aspect 形状过滤"后对这两种变脆（commit 已自登记为待修回归）：

- **渐变/反锯齿尖**：水滴尖端分裂成 sub-threshold 小连通块，anchor bbox 底部止步，弧尖残留。修 `watermark.py::_grow_anchor_down`——anchor 定选后沿其列范围向下吸附饱和像素，capped 半个 icon 高。
- **复杂背景粘连**：logo 压在有色边框/填充上，icon 与边框 8-连通成细长块（fill 低、aspect 极端）被拒 → 漏检回退原图。修 `_find_anchor` 两遍：小 kernel 常规找；失败则 ROI 自适应大 kernel（`_ANCHOR_LINE_BREAK_FRAC`）断细线后重找。

回归 `test_real_solid_logo_on_white_leaves_no_orange_residue`、`test_real_logo_on_colored_frame_is_detected_at_bottom_right`（真图 fixture `tests/fixtures/watermark_*.webp`，**必须整图**——裁片改 ROI 比例会掩盖故障）。

| 场景 | 期望 | 理由 |
|------|------|------|
| 白底实心 logo（渐变尖） | 去净，右下 orange(hue 6-22) 残留=0 | 正例：bbox 向下扩覆盖弧尖 |
| logo 压红框粉底 | 检测到右下 logo（bbox 在 w/h 0.55 外）并去净 | 正例：fallback 断线找回 icon |
| 白底孤立橙 icon（合成 size24） | 去净，small kernel 命中，不触发 fallback | 反例：小 icon 不被大 kernel 腐蚀 |
| 细高橙 bar（aspect<0.5 图表） | 不检测 | 反例：形状过滤仍拒图表内容，fallback 不放宽 fill/aspect 判据 |
| 干净图无 logo | 不检测 | 反例：两遍都找不到合格 anchor |

橙 vs 红判据：OpenCV hue，橙 icon hue~8-15，纯红框/字 hue~0；测试用 hue∈[6,22] 排除红，不能用裸 R/G/B box（会把红误判成橙）。

---

新增规则请按同样格式加小节 + 用例（≥1 正例 + ≥2 反例）。用例是本 skill 的回归测试套件，价值随行数增长。
