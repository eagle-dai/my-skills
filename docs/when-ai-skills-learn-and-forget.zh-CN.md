# 仓库说明——不属于博客正文

> **用途：** 本文件包含一篇为发布到 SAP Community 而准备的独立技术博客。
>
> **发布规则：** 只复制 **BLOG ARTICLE STARTS HERE** 标记下方的内容。发布后的文章不得提及、链接到或依赖本仓库中的任何其他文件、目录、实现、Issue、Pull Request 或文档。文章中展示的代码和目录结构都是自包含示例。允许链接到外部官方文档。

## SAP Community 发布材料

**建议的板块/分类**

Technology Blog Posts by Members，或编辑器中最接近的 AI/开发者分类。

**推荐标题**

当 AI 技能学习——也遗忘：构建安全的演进闭环（When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop）

**简短描述**

AI 技能（AI skills）和智能体能力（agent capabilities）可能会悄无声息地发生回归（regressions）：新用例可以正常工作，旧行为却被破坏。本文介绍了一套受测试驱动开发（Test-Driven Development, TDD）启发的实用演进闭环，使用元规则（meta-rules）、验收用例（acceptance cases）、回归测试（regression tests）和评估（evaluations）；同时说明了如何通过把稳定工作迁移到经过验证的代码中，减少模型调用、Token 消耗和延迟。

**建议的 SAP Managed Tags**

- SAP Business AI
- SAP Business Technology Platform

[SAP Community 要求至少使用一个 SAP Managed Tag，并建议不超过三个](https://community.sap.com/t5/what-s-new/enhancements-to-sap-community-september-2025/ba-p/14231974)。发布时只使用编辑器中确实可用且真正相关的标签。

**建议的用户标签**

- agent skills
- AI skills
- skill evolution
- regression testing
- test-driven development
- Claude Code
- GenAI Assisted Content

由于生成式 AI 参与了起草和编辑，应包含 [`GenAI Assisted Content`](https://community.sap.com/t5/welcome-corner-knowledge-base/basic-etiquette-and-tips-for-participating-in-sap-community/ta-p/14147597) 标签。

**建议的封面图**

一张简洁的 600 × 420 图片：展示一个技能获得新能力，同时由受保护的回归测试套件确保原有能力保持完整。除非已获许可，否则避免使用产品 Logo。

**最终发布检查**

1. 从下方文章标题开始复制，不要复制本仓库说明。
2. 如果粘贴到 SAP Community 编辑器后 Markdown 格式未被保留，请重新应用标题和代码块格式。
3. 添加 Managed Tags、用户标签、简短描述和封面图。
4. 在未登录的浏览器中验证每个外部链接。
5. 发布前分别在桌面端和移动端预览文章。

---

<!-- ==================== BLOG ARTICLE START ==================== -->

## BLOG ARTICLE STARTS HERE

*本仓库说明、发布材料和此标记都不属于文章正文。请从下方标题开始复制。*

---

# 当 AI 技能学习——也遗忘：构建安全的演进闭环（When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop）

*在不破坏已有能力的前提下演进 AI 技能的实用方法（A Practical Way to Evolve AI Skills Without Breaking What Already Works）*

**摘要。** 基于文件的 AI 技能（file-based AI skills）可能会悄无声息地发生回归：一次修改可能满足了新请求，却削弱了之前有效的行为，而且往往没有编译错误，也没有明显损坏的输出。本文为可重复、契约驱动（contract-driven）的技能介绍一套受控演进闭环。该方法把技能特定的失败记忆（skill-specific failure memory）与共享元规则（shared meta-rules）结合起来；当行为可以被确定性检查时，采用受测试驱动开发（Test-Driven Development, TDD）启发的测试优先（test-first）方法。对于依赖模型的行为，则用评估用例（evaluation cases）、结构验证器（structural validators）、目标平台测试夹具（target-platform fixtures）或人工评审量规（human-reviewed rubrics）补充或替代精确断言。

每一项拟议修改都从一个边界明确的目的和一个已复现的失败开始，由证据提供保护，并最终反馈到该能力的回归记录，或反馈到指导未来修改的共享规则中。把稳定、可测试的工作从模型驱动执行（model-driven execution）迁移到确定性代码（deterministic code）中，还可以减少重复推理、模型调用、Token 使用量和延迟，同时为模糊用例保留一条更严格的处理路径。

虽然贯穿全文的示例使用的是基于文件的技能，但只要行为能够被版本化、复现和评估，同一生命周期也适用于平台特定技能以及更广义的 AI 智能体（AI agents）。目标不是让系统自主修改自身，而是实现更安全的累积改进：一个具体失败应当改善一项能力，而反复出现的失败模式应当改善所有能力的修改方式。

为了让讨论保持实用，本文按一条简单路径展开。首先讨论静默回归（silent regression）的挑战，然后介绍两层记忆和一个六步演进闭环，再把该方法扩展到完整的能力表面（capability surface）。本文还会分析确定性代码带来的效率收益，把该方法映射到 Claude Code、Codex、SAP Joule 和更广义的 AI 智能体，并以一个具体的 Git 配置和评审检查清单收尾。

上面的概述听起来比这套方法真正的起点正式得多。它最初只是对一个 HTML-to-Markdown 技能做一项很小的改进。请求很简单：删除文章开头类似“Hello everyone”的问候语。

输入如下：

```html
<p>
  Hello everyone.
  <strong>The migration must finish before Friday.</strong>
</p>
```

我希望得到的输出如下：

```markdown
**The migration must finish before Friday.**
```

我的第一个方案会检查段落是否以问候语开头；如果是，就删除整个段落。问候语确实消失了，但有用的句子及其粗体格式也一起消失了。新功能生效了，技能却变得更差。

这种回归很容易被忽略，因为它可能没有异常、没有红色日志，也没有明显损坏的输出。结果看起来仍然流畅，但部分信息可能已经悄悄丢失。

经历了几次类似情况后，我不再把技能修改当成“只需更新提示词（prompt）”。现在，我会更像处理软件修改那样处理它：复现失败、定义边界、编写保护措施（guard）、做出最小且有效的修改，然后确认旧行为仍然存在。这套工作流深受测试驱动开发（Test-Driven Development, TDD）影响：先创建一个失败测试，用最小且合理的修改让它通过，再在回归保护下改进实现。

不过，这并不是纯粹的 TDD。一个基于文件的 AI 技能可能包含自然语言指令、示例、脚本、依赖模型的行为以及目标平台差异。其中一些可以用确定性测试保护，另一些则需要验收用例、评估数据集（evaluation datasets）、量规（rubrics）或人工评审。

本文所说的“技能（skill）”，是指由指令、参考资料、脚本和测试组成的基于文件的能力包，并不特指 Joule Skill。这种方法最适合可重复的行为：其正确性能够被描述，而且看似合理但实际上错误的输出会造成真实成本。对于开放式写作或创造性对话，它不适合作为僵化的测试框架。

## 挑战：为什么技能会悄无声息地回归

第一个挑战是可见性（visibility）：AI 技能中的回归通常看起来像一个可以接受的结果，而不是明显的失败。一个基于文件的技能通常有多个行为来源：

- `SKILL.md` 告诉智能体应当做什么；
- 参考文件描述规则和例外；
- 脚本处理确定性工作；
- 示例会影响解释方式；
- 测试只能保护已经被编码的用例；
- 最终工具或渲染器的行为可能与本地环境不同。

代码无效时通常会报错；自然语言指令不会。删除 `SKILL.md` 中的一句话不会触发编译失败。缩短一条规则可能意外删掉旧的例外；为了一个新示例而扩大正则表达式的范围，可能损坏多个旧用例；Markdown 在 VS Code 中看起来正确，在 GitHub 上却可能以不同方式渲染。危险的结果并不总是毫无意义——它通常看起来仍然合理。

反复出现的原因其实都很普通：

1. 仅根据一个示例就把规则泛化。
2. 为了一个局部缺陷而修改共享规则。
3. 规则写进了文档，却没有测试保护。
4. 实现经过了测试，目标环境却没有。
5. 修复了一个失败，却没有记录未来修改必须保留什么。

在提示词中增加更多文字并不能解决这些问题。有时这只会让提示词更长、更难评审。

## 基础：两层记忆

最有价值的结构性决策，是把两类知识分开：共享元规则（shared meta-rules）和技能特定经验（skill-specific lessons）。第一类知识由多个技能共享，它们是**元规则（meta-rules）**：

> 任何技能应当被允许以什么方式修改？

第二类知识只属于某一个具体技能：

> 这个技能从自身失败中学到了什么？

一个很小的目录结构就可以明确表达这种分离：

```text
_meta/
└── skill-self-improvement.md

html-to-markdown/
├── SKILL.md
├── self-improvement.md
├── acceptance/
│   └── CASES.md
├── scripts/
│   └── converter.py
└── tests/
    ├── test_acceptance.py
    └── test_regressions.py
```

共享文件 `_meta/skill-self-improvement.md` 并不讨论 HTML 转换。它定义修改技能的规则：

- 实现前必须检查什么；
- 哪些捷径不可接受；
- 何时必须添加失败测试；
- 如何选择正向边界和负向边界；
- 哪些权衡应当优先；
- 修改被视为完成前，必须通过什么；
- 何时必须因为不确定性返回 `blocked`，而不是给出看似合理的成功结果。

这个文件不只是文档，它是技能演进策略（policy for skill evolution）。某个具体技能可能会忘记自己的一个用例，但元规则应当防止同一类错误蔓延到整个技能库。

技能特定的 `self-improvement.md` 保存具体的回归知识：

- 失败的输入；
- 预期结果；
- 失败原因；
- 应当匹配的示例；
- 绝不能匹配的示例；
- 目标平台；
- 现在负责保护该行为的测试。

验收用例还应当让非开发者也能理解。用户不需要理解 DOM 选择器或正则表达式，也应当能够知道技能承诺什么；测试则为同一约定提供可执行的一面。

因此，一个技能有两类读者：一类是需要理解预期结果的人，另一类是需要获得可检查内容的机器。可读规则如果没有保护措施，就可能发生漂移；测试如果没有可读意图，就会变得难以评审。

## 方法：六步演进闭环

有了这两层记忆，就可以明确描述演进过程。下面的闭环受 TDD 启发，但它超出了普通单元测试的范围：它把测试优先开发与验收标准（acceptance criteria）、目标环境检查，以及一个用于保存经验的小型记忆系统结合起来。

### 1. 说明目的并限制修改范围

在修改代码或指令之前，先用一句话说明面向用户的目的。对于问候语用例：

> 删除独立的开场问候语，同时不能删除同一容器中的有意义内容或受支持格式。

后半句很重要，因为它定义了这项修改不允许破坏什么。应当提出几个基本问题：

- 当前规则过窄还是过宽？
- 问题是否位于共享组件中？
- 该行为是否只写进了文档，却从未测试？
- 失败是否只会在真实目标环境中出现？
- 这真的只是一项修改，还是正在悄悄变成范围更大的重构？

没有这一步，就很容易只修复可见症状，而让原始机制保持不变。

### 2. 先泛化，再实现

只基于一个示例制定的规则通常值得怀疑。例如，下面这条规则过于宽泛：

> 当段落文本以“Hello everyone”开头时，删除该段落。

段落是结构容器，并不一定是应被删除的语义单元。更好的规则是：

> 只删除独立的问候句。当其父级块还包含有意义的文本或受支持的行内结构时，不要删除父级块。

这里真正的改进并不是更聪明的正则表达式，而是选择了正确的语义单元。在实现之前，应尝试多个边界用例：

- 只包含问候语的段落应被删除；
- 问候语后跟粗体文本时，应保留粗体文本；
- 引用“Hello everyone”的句子应保持不变；
- 包含类似文字的标题不应被视为问候语；
- 标点、字母大小写和全角字符不应导致意外匹配。

正向示例说明规则在哪里生效，负向示例说明规则必须在哪里停止。在实践中，负向示例往往更有价值。

### 3. 采用测试优先、受 TDD 启发的修改方式

对于可重复的技能行为，有一条规则尤其重要：

> 每当技能中新增一条用户可见规则，且该行为可以被确定性检查时，就应在同一次修改中为其添加自动化保护措施（automated guard）。

一个很有用的评审问题是：

> 如果这条规则下个月消失，哪个测试会失败？

如果没有答案，这条规则可能仍然只是一种愿望。

对于上面的回归，首先添加一个失败测试。这是 TDD 中的 **Red（红）** 阶段：

```python
def test_preserves_content_after_greeting() -> None:
    html = """
    <p>
      Hello everyone.
      <strong>The migration must finish before Friday.</strong>
    </p>
    """

    assert convert(html) == (
        "**The migration must finish before Friday.**"
    )
```

然后添加边界：

```python
def test_removes_pure_greeting() -> None:
    assert convert("<p>Hello everyone.</p>") == ""


def test_keeps_quoted_greeting() -> None:
    html = '<p>The guide uses “Hello everyone” as an example.</p>'

    assert convert(html) == (
        'The guide uses “Hello everyone” as an example.'
    )
```

对应的验收用例可以保持简单：

```markdown
### 问候语后跟有意义的内容

- 输入：一个段落，其中包含问候语和有意义的格式化文本
- 预期：只删除问候语
- 绝不能：删除有意义的文本或丢失受支持格式
- 保护测试：`test_preserves_content_after_greeting`
```

接下来，做出能够修复机制的最小修改。这是 **Green（绿）** 阶段。如果实现变得混乱，就在测试保持通过的前提下清理实现；这就是 **Refactor（重构）** 阶段。

对于 AI 技能，这个闭环并不总是以单元测试结束。如果行为依赖模型或渲染器，保护措施也可以是评估用例、目标平台测试夹具、结构验证器或人工评审量规。核心仍然相同：在宣布成功之前先定义证据。

新用例通过后，应运行完整测试套件（full suite）。只运行新测试只能证明报告的用例已被修复，并不能证明没有引入其他问题。默认保留旧回归测试。当旧预期确实错误时，应先记录原因再修改它；否则，删除测试也意味着删除技能的一部分记忆。

### 4. 不要人为制造绿色结果

用错误方式得到绿色结果并不难。常见捷径包括：

- 只为最新输入扩大正则表达式范围；
- 弱化断言，直到当前输出能够通过；
- 只运行新测试文件；
- 因为旧测试变得碍事而删除它；
- 只更新文档，却不添加可执行保护措施；
- 验证尚未完成，却宣称结果成功；
- 不断修改随机值或时间戳，直到某个非确定性用例碰巧通过。

只有当测试仍然代表原始意图时，绿色的持续集成（Continuous Integration, CI）结果才有价值。对于转换技能，“生成了某些 Markdown”并不足够：重要内容和受支持结构必须保留，未知内容也不应悄无声息地消失。有时，明确的状态模型会有所帮助：

```python
from dataclasses import dataclass
from typing import Literal

Status = Literal["converted", "strict_required", "blocked"]


@dataclass(frozen=True)
class ConversionResult:
    status: Status
    markdown: str | None
    reasons: tuple[str, ...] = ()
```

这些状态的含义很简单：

- `converted`：所需检查已经通过；
- `strict_required`：快速确定性路径不够安全；
- `blocked`：可能存在看似合理的输出，但它没有通过契约。

“没有发生异常”并不是足够充分的成功定义。

### 5. 保护边界，并明确表达权衡

一条小规则可能被多个路径甚至多个技能共享，因此局部修复的风险可能比最初看起来更高。我当前采用的权衡优先级是：

```text
fail closed
    > repeatable result
    > structural preservation
    > broader coverage
    > shorter implementation
```

即：失败关闭（fail closed）> 可重复结果（repeatable result）> 结构保留（structural preservation）> 更广覆盖范围（broader coverage）> 更短实现（shorter implementation）。

这个顺序并不具有普适性。它来自转换和企业级用例：在这些场景中，丢失信息比拒绝一个困难输入更糟糕。

当未知结构可能导致信息丢失时，应将它路由到更严格的路径或直接阻止；与其给出自信但受损的结果，不如诚实承认限制。当对每个输入都使用严格路径成本过高时，应把快速路径（fast path）和严格路径（strict path）分开，而不是仅仅为了让理想路径（happy path）更快，就削弱正确性规则。

这一权衡顺序应写入元规则。否则，不同贡献者可能做出不同的局部选择，并逐渐把技能库拉向彼此冲突的方向。

### 6. 保存经验，并把重复经验提升为元规则

实现完成后：

1. 运行完整测试套件和 CI；
2. 检查代码无法良好判断的视觉或语义行为；
3. 搜索重复的选择器、正则表达式和默认规则；
4. 记录原因、风险、验证方法和剩余缺口；
5. 把经验放到正确的位置。

具体失败应写入技能特定记录，反复出现的失败方式则应写入共享元规则。例如：

- 只基于一个示例制定的规则反复表现得过窄；
- 宽泛字符类（broad character classes）反复产生误报（false positives）；
- 本地渲染结果反复与目标平台不同；
- 贡献者反复只运行新测试；
- 只存在于文档中的规则反复消失；
- 依赖模型的检查反复被当作确定性检查。

一个失败应当改善一个技能，而一种重复模式应当改善所有技能的修改方式。正是这一“提升（promotion）”步骤让流程能够自我改进：技能从具体缺陷中学习，技能库则从缺陷类型中学习。

## 完整能力表面（complete capability surface）

只有把完整能力——而不只是最显眼的脚本——视为可变行为，演进闭环才会有效。人们自然会测试转换器或主要编排代码，但指令、参考文件、工具定义、路由规则、权限、记忆行为和模型配置都可能影响结果。因此，完整能力定义也是可执行表面（executable surface）的一部分。

仓库级检查可以验证：

- 文档没有承诺实现仍会阻止的行为；
- 不受支持的输入会返回 `strict_required` 或 `blocked`；
- 文本和代码中的命名规则与回退规则保持一致；
- 每个验收用例都指向一个真实的测试或评估；
- 工具 Schema、权限和审批边界与声明的契约一致；
- 路由和回退行为在不同执行路径中保持一致；
- 共享行为没有在多个技能或智能体中被定义成不同版本；
- 预期遵循元规则的能力确实引用了这些元规则。

测试归属（test ownership）应当跟随能力归属。一个技能或智能体的测试应与该能力放在一起。跨能力一致性测试应位于技能库或平台层。

目标平台也应当成为证据的一部分。在一个预览器中看起来正确的 Markdown，可能会因为渲染流水线不同而在 GitHub 上失败。测试夹具应保留真实的失败机制，而不只是尽可能缩小输入。

第二个真实失败更清楚地说明了这一点。一个包含代码式标识符的公式通过了本地 KaTeX 验证，但发布后失败了，因为 GitHub 在调用数学渲染器之前先转换了 Markdown 转义字符。验证器测试的是源表示（source representation），而不是目标平台实际使用的表示。持久修复方案是在验证路径中复现 GitHub 的预处理。只有当测试模拟了真正执行或渲染结果的环境时，绿色测试才有意义。

## 额外收益：减少模型工作量

回归保护是这套方法最初的动机，但把确定性工作和依赖模型的工作分开，也可以提升运行时效率。当一种行为变得稳定、可重复且可测试时，模型就不应在每次调用时重新发现或重新实现它。这类工作可以迁移到具有明确输入、输出、验证和失败状态的确定性脚本中，把模型留给真正需要解释、规划或判断的部分。

一种实用的执行结构是：

```text
known, testable case
    -> deterministic fast path
    -> mechanical validation
    -> success

ambiguous or unsupported case
    -> strict model-driven path
    -> evaluation or human review
```

其中，已知且可测试的用例进入确定性快速路径（deterministic fast path），经过机械验证（mechanical validation）后成功；模糊或不受支持的用例则进入严格的模型驱动路径（strict model-driven path），再进行评估或人工评审。

这种架构可以减少：

- 为相同机械操作反复进行的模型调用；
- 为反复描述或重新生成确定性逻辑而消耗的提示词和补全 Token；
- 模型生成代码中的细小差异导致的重试；
- 常见输入的端到端延迟；
- 通过缓存和基于内容的去重（content-based deduplication）减少重复验证。

一个真实的转换工作流最初会把每个含图片的页面都发送给严格子智能体（strict subagent）。该子智能体会反复生成用于备份、去水印、压缩和验证的图像处理代码。一次有代表性的转换大约需要 19 分钟。当这个稳定契约被迁移到一个带有失败关闭测试的确定性像素处理层后，受支持的图片可以在几秒内处理一次，而不确定用例仍会被路由到严格路径。

时间改善是直接观察到的。由于减少了模型驱动步骤，Token 节省是合理结果，但仍应实际测量，而不是直接假设。可用指标包括：

- 按流水线阶段统计的实际耗时（wall-clock time）；
- 模型或智能体调用次数；
- 输入和输出 Token；
- 使用严格路径的请求比例；
- 缓存命中率和去重率；
- 重试次数和验证失败次数。

这并不是主张用脆弱代码替代语义判断。只有当一个步骤的行为足够稳定、可观察且受到测试保护时，才应把它迁移到代码中。效率提升来自缩小模型的职责范围，让模型只负责其推理真正能增加价值的部分。

## 在不同技能和智能体中应用该方法

由于这是一种生命周期方法，而不是一种文件格式约定，因此它可以迁移到不同平台。贯穿全文的示例使用基于文件的技能，但该方法并不绑定 Claude Code、`SKILL.md`，甚至不把技能视为唯一的修改单元。只要一项能力具有以下四个属性，这套方法就适用：

1. 其行为由版本化工件（versioned artifacts）定义，例如指令、代码、工具、策略或配置；
2. 失败可以通过测试夹具、执行轨迹（traces）、场景或已记录执行来复现；
3. 至少一部分预期行为可以表达为契约、不变量（invariant）或评估标准；
4. 修改可以通过受控发布流程进行评审和推广。

### Claude Code 和 Codex 技能

Claude Code 提供了一个直接的基于文件示例，因此元规则、验收用例、脚本和测试可以共同放在一个技能目录中。

OpenAI 同样把 [Skills](https://help.openai.com/en/articles/20001066) 描述为包含指令、示例和代码的可复用工作流，并在 Codex 中提供支持。Codex [plugins](https://help.openai.com/en/articles/20001256-plugins-in-codex/) 可以把技能与应用和工作流能力打包在一起。它们的打包模型和权限模型与 Claude Code 不同，但演进问题相同：修改指令、示例、脚本或已连接操作，可能改善一个场景，却让另一个场景回归。

对于这两个系统，演进闭环可以直接映射为：

- 把能力定义纳入版本控制；
- 使用测试夹具或任务场景复现失败；
- 对脚本、转换和工具契约使用确定性测试；
- 对依赖模型的解释和规划使用评估；
- 发布新版本之前运行更广泛的回归测试套件；
- 把反复出现的失败模式提升为共享修改规则。

### SAP Joule Skills、Joule Agents 和 Joule Work

SAP [Joule Studio](https://help.sap.com/docs/Joule_Studio/45f9d2b8914b4f0ba731570ff9a85313/7d6dc3e0d59d43e48f4d7ece55e4c2a3.html?locale=en-US) 区分了定制的、确定性的 Joule Skills，以及用于复杂或多步骤工作的交互式 Joule Agents，并支持管理和部署二者的更新版本。虽然实现工件不同，但这仍让同一演进闭环具有实用价值。

对于确定性的 Joule Skill，最强的保护措施通常是输入/输出契约、API Mock、业务规则测试、权限检查和部署环境验证。SAP 对 [Joule Agents](https://www.sap.com/products/artificial-intelligence/ai-agents.html) 的描述则不同：它们支持非确定性工作流（non-deterministic workflows），并可以在 Joule Skills、其他智能体和第三方应用之间动态选择。对回归保护而言，其实际含义是：一次更新可以合理改变中间计划，但不能丢失该能力的预期行为。因此，测试和评估应保护稳定契约——必需结果、禁止操作、授权或审批边界，以及有效的业务状态转换——而不应把每一条不同的执行轨迹都视为失败。

当这些能力通过 [Joule Work](https://help.sap.com/docs/joule-work-mobile?locale=en-US) 等 Joule 体验呈现时，也可以使用同一生命周期。这是工程方法的迁移，并不是声称 Joule 使用 Claude Code 的目录布局或文件格式。

### 超越技能：AI 智能体开发

即使完全不存在名为“技能”的工件，这套方法仍然适用。一个 AI 智能体可能由系统提示词、工具集、路由图、记忆策略、模型配置、审批工作流和运行环境共同定义；其中任何一项发生变化，都可能改变智能体行为并造成回归。因此，六步闭环也可以在智能体层面运行：

- 使用已记录轨迹或场景复现失败；
- 定义预期不变量以及修改边界；
- 为确定性工具添加单元测试和契约测试；
- 在修改依赖模型的行为之前先定义评估用例；
- 验证端到端编排、权限、状态转换和回退；
- 在局部保存具体经验，并把重复模式提升为共享的智能体开发元规则。

演进单元可以是技能、插件、工具、子智能体、路由策略，也可以是完整智能体。支配原则保持不变：证据应先于信心，重复失败应改善下一次修改所采用的流程。

## 使用 Claude Code 和 Git 的具体实现

下面的配置展示了该方法的一种具体实现。它只是示例，并不是平台要求。对于跨多个项目使用的个人技能，Claude Code 支持以下目录：

```text
~/.claude/skills/
```

[Claude Code 会从个人技能目录加载技能](https://code.claude.com/docs/en/skills#where-skills-live)：`~/.claude/skills/<skill-name>/SKILL.md`。项目特定技能也可以放在项目仓库内的 `.claude/skills/` 下。

对于贯穿全文的示例，目录结构如下：

```text
~/.claude/skills/
├── _meta/
│   └── skill-self-improvement.md
└── html-to-markdown/
    ├── SKILL.md
    ├── self-improvement.md
    ├── acceptance/
    │   └── CASES.md
    ├── scripts/
    │   └── converter.py
    └── tests/
        └── test_acceptance.py
```

`html-to-markdown` 目录就是技能。`_meta` 是用于修改技能的共享策略层；它不是另一个面向用户的技能。

### 把技能库纳入 Git 管理

整个 `~/.claude/skills/` 目录都可以成为一个 Git 仓库。对一名开发者而言，这听起来可能有些重，但它能让每条规则修改都有 Diff，保留回归用例历史，并让同一技能库能够跨机器同步。最小配置如下：

```bash
mkdir -p ~/.claude/skills
cd ~/.claude/skills

git init
git branch -M main
git add .
git commit -m "Initialize personal Claude skills"

# Create an empty GitHub repository first: no README, license, or .gitignore.
git remote add origin git@github.com:<your-account>/<your-skills-repo>.git
git push -u origin main
```

在另一台机器上，只有当该目录尚不存在时，才克隆到同一位置：

```bash
git clone git@github.com:<your-account>/<your-skills-repo>.git ~/.claude/skills
```

如果目录已经包含本地技能，不要覆盖式克隆。应先备份，或有意识地协调两个仓库。

对于很多场景，一个很小的 `.gitignore` 就足够：

```gitignore
.DS_Store
__pycache__/
*.pyc
.venv/
.env
```

不要提交凭据、Token、客户数据、生成的工作文件或机器特定密钥。仓库应主要包含可以安全进行版本控制的指令、参考资料、小型测试夹具、测试和脚本。

对于由团队拥有、且绑定到某个应用的技能，应使用项目级路径：

```text
<project>/.claude/skills/<skill-name>/SKILL.md
```

个人目录是一套可复用工具箱，项目目录则是由某个代码库拥有的行为。

### 技能演进元规则示例

一个最小的 `~/.claude/skills/_meta/skill-self-improvement.md` 可以写成：

```markdown
# 安全地修改技能

在现有技能中添加、删除或修改行为时，请使用本文件。

1. 用一句话说明面向用户的目的和修改边界。
2. 阅读目标技能的 `self-improvement.md` 和 `acceptance/CASES.md`。
3. 添加或找到一个能够复现失败的测试夹具。
4. 对于确定性行为，在修改实现之前先编写一个失败测试。
5. 对于依赖模型的行为，在实现之前先定义评估用例或评审量规。
6. 添加多样化的正向用例和至少两个负向用例。
7. 做出能够修复机制的最小修改，而不只是修复当前示例。
8. 运行完整测试和评估套件。不要通过弱化或删除旧保护措施让结果变绿。
9. 使用保护测试名称更新验收用例和回归记录。
10. 如果失败暴露出一种重复错误，也要更新这些元规则。

当无法确认正确性时，返回 `blocked` 或使用更严格的路径。
```

主文件 `~/.claude/skills/html-to-markdown/SKILL.md` 应聚焦于执行：

```markdown
---
name: html-to-markdown
description: 把保存的 HTML 页面转换为干净的 Markdown，同时保留受支持的内容和结构。
---

# HTML 到 Markdown

转换输入页面，并在报告成功之前验证结果。

修改此技能本身时：

1. 阅读[共享元规则](../_meta/skill-self-improvement.md)。
2. 阅读[回归记录](self-improvement.md)。
3. 阅读[验收用例](acceptance/CASES.md)。
4. 首先添加一个失败的回归测试或评估用例。
5. 修改后运行完整套件。
```

当 `html-to-markdown` 单独分发时，应把共享元规则复制到它自己的 `references/` 目录，或者打包完整技能库。一个技能不应依赖分发包中不存在的同级文件。

## 实用评审检查清单

上面的思想可以压缩成一个紧凑的评审门槛（review gate）。合并技能或智能体能力修改之前，应检查：

- 是否用一句话清楚说明了面向用户的目的和边界？
- 规则是否基于机制，而不只是一个示例？
- 是否包含正向和负向边界用例？
- 是否在实现前复现了失败？
- 对于确定性行为，新测试是否在实现修改前确实失败？
- 对于依赖模型的行为，是否在修改前定义了评估证据？
- 能否把稳定、确定性的工作移出模型驱动路径？
- 如果目标包含效率，是否测量了模型调用、Token、严格路径比例、缓存命中率和延迟？
- 如果新规则消失，哪个保护措施会失败？
- 完整套件是否在没有弱化旧保护措施的情况下通过？
- 修改是否只限于必要区域？
- 不确定性是否会产生 `strict_required` 或 `blocked`，而不是看似合理的成功结果？
- 指令、实现、测试、评估和验收用例是否仍表达同一件事？
- 对于智能体能力，回归证据是否在不假设唯一有效执行路径的前提下，保护了必需结果和业务边界？
- 是否记录了具体经验？
- 如果失败模式反复出现，是否更新了元规则？

并不是每个检查项对每项任务都应具有相同权重。小型个人技能和业务关键型工作流并不相同。当错误结果可能长期隐藏时，应采用更严格的证据标准。

## 结论

随着新模型、新工具、新格式和新用户预期不断出现，AI 技能和智能体也会持续变化。目标不是让一项能力在第一次生效后就被冻结，而是确保每个真实失败都留下有价值的东西：更清晰的边界、回归保护措施或评估，或者一条能改善下一次修改的元规则。

TDD 在这里带来了一项重要纪律：证据先于信心。评估把这项纪律扩展到了依赖模型的行为。确定性代码可以把重复的模型工作移出常见路径，同时提升可靠性和效率；元规则则让一项能力的失败能够改善所有能力的修改方式。
