# Repository Note — Not Part of the Blog Article

> **Purpose:** This file contains a standalone technical blog prepared for publication on SAP Community.
>
> **Publishing rule:** Copy only the content below the **BLOG ARTICLE STARTS HERE** marker. The published article must not mention, link to, or depend on any other file, directory, implementation, issue, pull request, or documentation in this repository. Code and directory structures shown in the article are self-contained examples. Links to external official documentation are allowed.

## SAP Community Publishing Package

**Suggested board/category**

Technology Blog Posts by Members, or the closest AI/developer category available in the editor.

**Recommended title**

When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop

**Short description**

AI skills and agent capabilities can regress silently: a new case works while older behavior breaks. This post presents a practical, TDD-inspired evolution loop using meta-rules, acceptance cases, regression tests, and evaluations—and shows how moving stable work into validated code can also reduce model calls, tokens, and latency.

**Suggested SAP Managed Tags**

- SAP Business AI
- SAP Business Technology Platform

[SAP Community requires at least one SAP Managed Tag and recommends using no more than three](https://community.sap.com/t5/what-s-new/enhancements-to-sap-community-september-2025/ba-p/14231974). Use only tags that are available and genuinely relevant when publishing.

**Suggested user tags**

- agent skills
- AI skills
- skill evolution
- regression testing
- test-driven development
- Claude Code
- GenAI Assisted Content

[`GenAI Assisted Content`](https://community.sap.com/t5/welcome-corner-knowledge-base/basic-etiquette-and-tips-for-participating-in-sap-community/ta-p/14147597) should be included because generative AI was used to assist with drafting and editing.

**Suggested cover image**

A simple 600 × 420 image showing a skill gaining a new capability while a protected regression suite keeps existing capabilities intact. Avoid product logos unless their use is permitted.

**Final publishing checks**

1. Copy from the article title below, not from this repository note.
2. Reapply heading and code-block formatting in the SAP Community editor if Markdown is not preserved when pasted.
3. Add the managed tags, user tags, short description, and cover image.
4. Verify every external link from a logged-out browser.
5. Preview the post on desktop and mobile before publishing.

---

<!-- ==================== BLOG ARTICLE START ==================== -->

## BLOG ARTICLE STARTS HERE

*The repository note, publishing package, and this marker are not part of the article. Start copying from the title below.*

---

# When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop

*A Practical Way to Evolve AI Skills Without Breaking What Already Works*

**Abstract.** File-based AI skills can regress silently: a change may satisfy a new request while weakening behavior that previously worked, often without compilation errors or visibly broken output. This article presents a controlled evolution loop for repeatable, contract-driven skills. The approach combines skill-specific failure memory with shared meta-rules, and uses a Test-Driven Development (TDD)-inspired, test-first approach where behavior can be checked deterministically. For model-dependent behavior, exact assertions are complemented or replaced by evaluation cases, structural validators, target-platform fixtures, or human-reviewed rubrics.

Each proposed change begins with a bounded purpose and a reproduced failure, is protected by evidence, and is fed back into either the capability's regression record or the shared rules for future changes. Moving stable, testable work from model-driven execution into deterministic code can also reduce repeated reasoning, model calls, token usage, and latency while preserving a stricter path for ambiguous cases.

Although the running example uses a file-based skill, the same lifecycle applies to platform-specific skills and broader AI agents when their behavior can be versioned, reproduced, and evaluated. The goal is not autonomous self-modification, but safer cumulative improvement: a concrete failure should improve one capability, while a recurring failure pattern should improve how all capabilities are changed.

To keep the discussion practical, the article follows a simple progression. It begins with the challenge of silent regression, introduces two levels of memory and a six-step evolution loop, and then expands the method to the complete capability surface. It also examines the efficiency benefit of deterministic code, maps the approach across Claude Code, Codex, SAP Joule, and broader AI agents, and closes with a concrete Git setup and review checklist.

That summary sounds more formal than the way the approach actually began. It started with a very small improvement to an HTML-to-Markdown skill. The request was simple: remove greetings such as “Hello everyone” from the beginning of an article.

This was the input:

```html
<p>
  Hello everyone.
  <strong>The migration must finish before Friday.</strong>
</p>
```

And this was the output I wanted:

```markdown
**The migration must finish before Friday.**
```

My first solution checked whether a paragraph started with a greeting and removed the whole paragraph when it did. The greeting was gone, but so were the useful sentence and its bold formatting. The new feature worked, yet the skill had become worse.

This kind of regression is easy to miss because there may be no exception, no red log, and no obviously broken output. The result may still look fluent while some information has quietly disappeared.

After seeing several cases like this, I stopped treating a skill change as “just update the prompt”. I now handle it more like a software change: reproduce the failure, define the boundary, write the guard, make the smallest useful change, and then check that older behavior is still there. This workflow is strongly influenced by Test-Driven Development (TDD): create a failing test, make it pass with the smallest reasonable change, and then improve the implementation under regression protection.

This is not pure TDD, however. A file-based AI skill may contain natural-language instructions, examples, scripts, model-dependent behavior, and target-platform differences. Some of these can be protected by deterministic tests, while others need acceptance cases, evaluation datasets, rubrics, or human review.

In this article, “skill” means a file-based capability package containing instructions, references, scripts, and tests; it does not mean a Joule Skill specifically. The approach is most useful for repeatable behavior where correctness can be described and a plausible but wrong output has a real cost. It is less suitable as a rigid test framework for open-ended writing or creative conversation.

## The challenge: why skills can regress silently

The first challenge is visibility: a regression in an AI skill often looks like an acceptable result rather than an obvious failure. A file-based skill normally has several sources of behavior:

- `SKILL.md` tells the agent what to do;
- reference files describe rules and exceptions;
- scripts handle deterministic work;
- examples influence interpretation;
- tests protect only the cases that have been encoded;
- the final tool or renderer may behave differently from the local environment.

Code usually complains when it is invalid; natural-language instructions do not. Removing one sentence from `SKILL.md` causes no compilation failure. Shortening a rule can accidentally remove an old exception, broadening a regular expression for one new example can damage several older cases, and Markdown may look correct in VS Code while rendering differently on GitHub. The dangerous result is not always nonsense—it often still looks reasonable.

The recurring causes are quite ordinary:

1. A rule is generalized from only one example.
2. A shared rule is changed for one local defect.
3. A rule is documented but not protected by a test.
4. The implementation is tested, but the target environment is not.
5. One failure is fixed without recording what future changes must preserve.

Adding more prose to the prompt does not solve these problems. Sometimes it only makes the prompt longer and harder to review.

## The foundation: two levels of memory

The most useful structural decision is to separate two kinds of knowledge: shared meta-rules and skill-specific lessons. The first kind is shared across skills. These are **meta-rules**:

> How is any skill allowed to change?

The second kind belongs to one particular skill:

> What did this skill learn from its own failures?

A small structure can make the separation explicit:

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

The shared `_meta/skill-self-improvement.md` file is not about HTML conversion. It defines the rules for changing skills:

- what must be checked before implementation;
- which shortcuts are not acceptable;
- when a failing test must be added;
- how positive and negative boundaries are chosen;
- which trade-offs take priority;
- what must pass before the change is considered complete;
- when uncertainty must produce `blocked` instead of a plausible success.

This file is more than documentation. It is the policy for skill evolution. A concrete skill may forget one of its own cases, but the meta-rules should prevent the same type of mistake from spreading across the whole skill library.

The skill-specific `self-improvement.md` keeps concrete regression knowledge:

- the failed input;
- the expected result;
- why it failed;
- examples that should match;
- examples that must not match;
- the target platform;
- the test that now protects this behavior.

Acceptance cases should also remain understandable to a non-developer. A user should not need to understand a DOM selector or regular expression to know what the skill promises, while the test provides the executable side of the same agreement.

A skill therefore has two readers: a person who needs to understand the intended outcome, and a machine that needs something it can check. A readable rule without a guard can drift; a test without readable intent becomes difficult to review.

## The method: a six-step evolution loop

With those two memory layers in place, the evolution process can be made explicit. The loop below is TDD-inspired, but it extends beyond ordinary unit tests by combining test-first development with acceptance criteria, target-environment checks, and a small memory system for lessons learned.

### 1. State the purpose and limit the change

Before changing code or instructions, state the user-visible purpose in one sentence. For the greeting case:

> Remove a standalone opening greeting without deleting meaningful content or supported formatting in the same container.

The second half is important because it defines what the change is not allowed to break. Ask a few basic questions:

- Is the current rule too narrow or too broad?
- Is the problem in a shared component?
- Was the behavior only documented but never tested?
- Does the failure appear only in the real target environment?
- Is this really one change, or is it quietly becoming a wider refactoring?

Without this step, it is easy to fix the visible symptom and leave the original mechanism unchanged.

### 2. Generalize before implementing

A rule based on one example is usually suspicious. For example, this rule is too broad:

> Remove a paragraph when its text starts with “Hello everyone”.

The paragraph is a structural container, not necessarily the semantic unit that should be removed. A better rule is:

> Remove only an independent greeting sentence. Do not remove its parent block when the block also contains meaningful text or supported inline structure.

The main improvement is not a smarter regular expression; it is selecting the correct unit of meaning. Before implementation, try several boundary cases:

- a paragraph containing only a greeting should be removed;
- a greeting followed by bold text should keep the bold text;
- a sentence quoting “Hello everyone” should remain unchanged;
- a heading containing similar words should not be treated as a greeting;
- punctuation, letter case, and full-width characters should not create accidental matches.

Positive examples show where the rule works. Negative examples show where it must stop. In practice, the negative examples are often more valuable.

### 3. Use a test-first, TDD-inspired change

For repeatable skill behavior, one rule is particularly important:

> A user-visible rule added to a skill should have an automated guard in the same change whenever the behavior can be checked deterministically.

A useful review question is:

> If this rule disappears next month, which test will fail?

If there is no answer, the rule may still be only a hope.

For the regression above, first add a failing test. This is the **Red** step in TDD:

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

Then add boundaries:

```python
def test_removes_pure_greeting() -> None:
    assert convert("<p>Hello everyone.</p>") == ""


def test_keeps_quoted_greeting() -> None:
    html = '<p>The guide uses “Hello everyone” as an example.</p>'

    assert convert(html) == (
        'The guide uses “Hello everyone” as an example.'
    )
```

The matching acceptance case can stay simple:

```markdown
### Greeting followed by meaningful content

- Input: one paragraph containing a greeting and meaningful formatted text
- Expected: remove only the greeting
- Must not: delete meaningful text or lose supported formatting
- Guard: `test_preserves_content_after_greeting`
```

Next, make the smallest change that fixes the mechanism. This is the **Green** step. If the implementation becomes messy, clean it up while the tests are green; that is the **Refactor** step.

For AI skills, the loop does not always end with a unit test. If behavior depends on a model or renderer, the guard may instead be an evaluation case, a target-platform fixture, a structural validator, or a human-reviewed rubric. The important point remains the same: define the evidence before declaring success.

After the new case passes, run the full suite. Running only the new test proves that the reported case was fixed, not that another problem was not introduced. Keep old regression tests by default. When an old expectation is genuinely wrong, record why before changing it; otherwise, deleting the test also deletes part of the skill's memory.

### 4. Do not manufacture a green result

It is easy to produce a green result in the wrong way. Common shortcuts include:

- widening a regular expression only for the latest input;
- weakening an assertion until the current output passes;
- running only the new test file;
- deleting an old test because it became inconvenient;
- updating documentation without an executable guard;
- calling the result successful while validation is incomplete;
- changing random values or timestamps until a nondeterministic case happens to pass.

A green CI result is useful only when the tests still represent the original intention. For conversion skills, “some Markdown was produced” is not enough: important content and supported structure must remain, and unknown content should not disappear silently. Sometimes an explicit status model helps:

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

The meanings are simple:

- `converted`: the required checks passed;
- `strict_required`: the fast deterministic path is not safe enough;
- `blocked`: a plausible output may exist, but it did not pass the contract.

“No exception happened” is not a sufficient definition of success.

### 5. Protect the boundary and make trade-offs explicit

A small rule may be shared by several paths or even several skills, which makes local fixes more risky than they first appear. My current trade-off order is:

```text
fail closed
    > repeatable result
    > structural preservation
    > broader coverage
    > shorter implementation
```

This order is not universal. It comes from conversion and enterprise-oriented use cases where losing information is worse than refusing one difficult input.

When an unknown structure may cause information loss, route it to a stricter path or block it; prefer an honest limitation to a confident but damaged result. When the strict path is too expensive for every input, separate fast and strict paths rather than weakening the correctness rule only to make the happy path faster.

This trade-off order belongs in the meta-rules. Otherwise, different contributors may make different local choices and slowly pull the skill library in conflicting directions.

### 6. Store the lesson, and promote repeated lessons to meta-rules

After implementation:

1. run the full test suite and CI;
2. inspect visual or semantic behavior that code cannot judge well;
3. search for duplicated selectors, regular expressions, and default rules;
4. record the cause, risk, verification method, and remaining gaps;
5. put the lesson in the correct place.

A concrete failure belongs to the skill-specific record, while a repeated way of failing belongs to the shared meta-rules. Examples are:

- rules based on one example are repeatedly too narrow;
- broad character classes repeatedly create false positives;
- local rendering repeatedly differs from the target platform;
- contributors repeatedly run only the new tests;
- documentation-only rules repeatedly disappear;
- model-dependent checks are repeatedly treated as deterministic.

One failure should improve one skill, while a repeated pattern should improve how all skills are changed. This promotion step is what makes the process self-improving: the skill learns from a concrete defect, and the skill library learns from the type of defect.

## The complete capability surface

The evolution loop is effective only when the complete capability—not just its most visible script—is treated as changeable behavior. It is natural to test the converter or the main orchestration code, but instructions, reference files, tool definitions, routing rules, permissions, memory behavior, and model configuration can all influence the result. The complete capability definition is therefore part of the executable surface.

Repository-level checks can verify that:

- documentation does not promise behavior that the implementation still blocks;
- unsupported inputs return `strict_required` or `blocked`;
- naming and fallback rules are consistent across text and code;
- each acceptance case points to a real test or evaluation;
- tool schemas, permissions, and approval boundaries match the stated contract;
- routing and fallback behavior remain consistent across execution paths;
- shared behavior is not defined differently in several skills or agents;
- meta-rules are referenced by the capabilities that are expected to follow them.

Test ownership should follow capability ownership. Tests for one skill or agent belong with that capability. Cross-capability consistency tests belong at the library or platform level.

The target platform should also be part of the evidence. Markdown that looks correct in one preview may fail on GitHub because the rendering pipeline is different. A fixture should keep the real failure mechanism, not only be as small as possible.

A second real failure made this point more clearly. A formula containing a code-like identifier passed local KaTeX validation but failed after publication because GitHub transformed the Markdown escapes before invoking its math renderer. The validator had tested the source representation rather than the representation used by the target platform. The durable fix was to reproduce GitHub's preprocessing inside the validation path. A green test is meaningful only when it models the environment that will actually execute or render the result.

## An additional benefit: less model work

Regression protection was the original motivation for this approach, but separating deterministic from model-dependent work can also improve runtime efficiency. When a behavior becomes stable, repeatable, and testable, the model should not need to rediscover or reimplement it on every invocation. That work can move into a deterministic script with explicit inputs, outputs, validation, and failure states, leaving the model for the parts that genuinely require interpretation, planning, or judgment.

A useful execution shape is:

```text
known, testable case
    -> deterministic fast path
    -> mechanical validation
    -> success

ambiguous or unsupported case
    -> strict model-driven path
    -> evaluation or human review
```

This architecture can reduce:

- repeated model calls for the same mechanical operation;
- prompt and completion tokens spent restating or regenerating deterministic logic;
- retries caused by small variations in model-generated code;
- end-to-end latency for common inputs;
- duplicated validation through caching and content-based deduplication.

One real conversion workflow originally sent every page containing an image to a strict subagent. The subagent repeatedly generated image-processing code for backup, watermark removal, compression, and validation. A representative conversion took about 19 minutes. Once that stable contract was moved into a deterministic pixel-processing layer with fail-closed tests, supported images could be processed once in seconds, while uncertain cases still routed to the strict path.

The time improvement was directly observed. Token savings follow from doing fewer model-driven steps, but they should still be measured rather than assumed. Useful metrics include:

- wall-clock time by pipeline stage;
- number of model or agent calls;
- input and output tokens;
- percentage of requests using the strict path;
- cache-hit and deduplication rates;
- retries and validation failures.

This is not an argument for replacing semantic judgment with brittle code. Move a step into code only when its behavior is sufficiently stable, observable, and protected by tests. The efficiency gain comes from shrinking the model's responsibility to the part where model reasoning adds value.

## Applying the method across skills and agents

Because this is a lifecycle method rather than a file-format convention, it can be transferred across platforms. The running example uses a file-based skill, but the method is not tied to Claude Code, `SKILL.md`, or even to skills as the only unit of change. It applies whenever a capability has four properties:

1. its behavior is defined by versioned artifacts such as instructions, code, tools, policies, or configuration;
2. failures can be reproduced through fixtures, traces, scenarios, or recorded executions;
3. at least part of the expected behavior can be expressed as a contract, invariant, or evaluation criterion;
4. changes can be reviewed and promoted through a controlled release process.

### Claude Code and Codex skills

Claude Code provides a direct file-based example, so the meta-rules, acceptance cases, scripts, and tests can live together in one skill directory.

OpenAI similarly describes [Skills](https://help.openai.com/en/articles/20001066) as reusable workflows containing instructions, examples, and code, with support in Codex. Codex [plugins](https://help.openai.com/en/articles/20001256-plugins-in-codex/) can package skills together with apps and workflow capabilities. The packaging and permission model differ from Claude Code, but the evolution problem is the same: a change to instructions, examples, scripts, or connected actions can improve one scenario while regressing another.

For both systems, the loop maps directly:

- keep the capability definition under version control;
- reproduce failures as fixtures or task scenarios;
- use deterministic tests for scripts, transformations, and tool contracts;
- use evaluations for model-dependent interpretation and planning;
- run the broader regression suite before publishing a new version;
- promote repeated failure patterns into shared change rules.

### SAP Joule Skills, Joule Agents, and Joule Work

SAP [Joule Studio](https://help.sap.com/docs/Joule_Studio/45f9d2b8914b4f0ba731570ff9a85313/7d6dc3e0d59d43e48f4d7ece55e4c2a3.html?locale=en-US) distinguishes tailored, deterministic Joule Skills from interactive Joule Agents for complex or multi-step work, and supports managing and deploying updated versions of both. This makes the same evolution loop useful even though the implementation artifacts are different.

For a deterministic Joule Skill, the strongest guards are usually input/output contracts, API mocks, business-rule tests, permission checks, and deployment-environment validation.

[SAP describes Joule Agents](https://www.sap.com/products/artificial-intelligence/ai-agents.html) as supporting non-deterministic workflows: they may choose among Joule skills, other agents, and third-party applications to carry out a plan, then reflect on the results. This distinction changes what a regression guard should assert. A test that requires one exact sequence of tool calls may reject a different but still valid plan; checking only the final answer is too weak. The durable contract should focus on invariants: the allowed tool and action set, the business objects that may be read or changed, required approval points, acceptable state transitions, and the final business outcome.

[SAP's governance model for Joule Agents](https://www.sap.com/documents/2026/06/526001c1-567f-0010-bca6-c68f7e60039b.html) makes several of those invariants concrete. A Joule Agent acts through a provisioned identity, cannot exceed the delegating user's authorization scope, and remains inside the same role-based authorizations, approval workflows, and audit controls as human activity. For evolution testing, a “correct” result is therefore not enough if it was produced under the wrong identity, bypassed an approval, or left an unauditable state change. These checks fit naturally into the article's existing acceptance cases and regression record: store the role and process context with the fixture, evaluate the variable reasoning path, and assert the governed business postconditions.

The same lifecycle can be used when these capabilities are surfaced through Joule experiences such as [Joule Work](https://help.sap.com/docs/joule-work-mobile?locale=en-US). This is a transfer of engineering method, not a claim that Joule uses Claude Code's directory layout or file format.

### Beyond skills: AI agent development

The method also applies when there is no named skill artifact at all. An AI agent may be defined by a system prompt, tool set, routing graph, memory policy, model configuration, approval workflow, and runtime environment; any one of these can change the agent's behavior and create a regression. The six-step loop can therefore operate at the agent level:

- reproduce the failure with a recorded trace or scenario;
- define the intended invariant and the boundary of the change;
- add unit and contract tests for deterministic tools;
- define evaluation cases before changing model-dependent behavior;
- verify end-to-end orchestration, permissions, state transitions, and fallbacks;
- store the concrete lesson locally and promote recurring patterns into shared agent-development meta-rules.

The unit of evolution may be a skill, plugin, tool, subagent, routing policy, or complete agent. The governing principle remains the same: evidence should precede confidence, and repeated failures should improve the process used for the next change.

## A practical implementation with Claude Code and Git

The following setup shows one concrete implementation of the method. It is an example, not a platform requirement. For personal skills used across several projects, Claude Code supports this directory:

```text
~/.claude/skills/
```

[Claude Code loads personal skills](https://code.claude.com/docs/en/skills#where-skills-live) from `~/.claude/skills/<skill-name>/SKILL.md`. A project-specific skill can instead live under `.claude/skills/` inside the project repository.

For the running example, the structure would be:

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

The `html-to-markdown` directory is the skill. `_meta` is the shared policy layer for changing skills; it is not another user-facing skill.

### Put the skill library under Git

The whole `~/.claude/skills/` directory can be a Git repository. This may sound a little heavy for one developer, but it gives every rule change a diff, preserves the history of regression cases, and allows the same skill library to be synchronized across machines. A minimal setup is:

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

On another machine, clone into the same location only when the directory does not already exist:

```bash
git clone git@github.com:<your-account>/<your-skills-repo>.git ~/.claude/skills
```

When the directory already contains local skills, do not clone over it. Back it up or reconcile the repositories deliberately.

A small `.gitignore` is enough for many cases:

```gitignore
.DS_Store
__pycache__/
*.pyc
.venv/
.env
```

Do not commit credentials, tokens, customer data, generated working files, or machine-specific secrets. The repository should mainly contain instructions, references, small fixtures, tests, and scripts that are safe to version.

For a team-owned skill tied to one application, use the project-level path:

```text
<project>/.claude/skills/<skill-name>/SKILL.md
```

The personal directory is a reusable toolbox. The project directory is behavior owned by one codebase.

### Example meta-rules for skill evolution

A minimal `~/.claude/skills/_meta/skill-self-improvement.md` can be:

```markdown
# Changing a skill safely

Use this file when adding, removing, or changing behavior in an existing skill.

1. State the user-visible purpose and the change boundary in one sentence.
2. Read the target skill's `self-improvement.md` and `acceptance/CASES.md`.
3. Add or identify a fixture that reproduces the failure.
4. For deterministic behavior, write a failing test before changing the implementation.
5. For model-dependent behavior, define the evaluation case or review rubric before implementation.
6. Add varied positive cases and at least two negative cases.
7. Make the smallest change that fixes the mechanism, not only the example.
8. Run the full test and evaluation suite. Do not weaken or delete old guards to make it green.
9. Update the acceptance case and regression record with the guard name.
10. If the failure exposes a recurring mistake, update these meta-rules too.

Stop with `blocked` or use a stricter path when correctness cannot be established.
```

The main `~/.claude/skills/html-to-markdown/SKILL.md` should stay focused on execution:

```markdown
---
name: html-to-markdown
description: Convert saved HTML pages into clean Markdown while preserving supported content and structure.
---

# HTML to Markdown

Convert the input page and validate the result before reporting success.

When changing this skill itself:

1. Read the [shared meta-rules](../_meta/skill-self-improvement.md).
2. Read the [regression record](self-improvement.md).
3. Read the [acceptance cases](acceptance/CASES.md).
4. Add a failing regression test or evaluation case first.
5. Run the full suite after the change.
```

When `html-to-markdown` is distributed alone, copy the shared meta-rules into its own `references/` directory or package the complete library. A skill should not depend on a sibling file that is absent from the distributed package.

## Practical review checklist

The ideas above can be reduced to a compact review gate. Before merging a skill or agent-capability change, check:

- Is the user-visible purpose and boundary clear in one sentence?
- Is the rule based on a mechanism, not only one example?
- Are positive and negative boundary cases included?
- Was the failure reproduced before implementation?
- For deterministic behavior, did the new test fail before the implementation changed?
- For model-dependent behavior, was the evaluation evidence defined before the change?
- Can stable, deterministic work be moved out of the model-driven path?
- If efficiency is a goal, were model calls, tokens, strict-path rate, cache hits, and latency measured?
- Which guard will fail if the new rule disappears?
- Did the full suite pass without weakening old guards?
- Is the change limited to the necessary area?
- Will uncertainty produce `strict_required` or `blocked` instead of plausible success?
- Are the instructions, implementation, tests, evaluations, and acceptance cases still saying the same thing?
- For non-deterministic agents, does the evidence protect business invariants without requiring one exact valid tool sequence?
- For governed enterprise actions, does it verify the acting identity, delegated authorization scope, required approvals, auditable trace, and postconditions in the system of record?
- Was the concrete lesson recorded?
- If the failure pattern is recurring, were the meta-rules updated?

Not every item needs the same weight for every task. A small personal skill and a business-critical workflow are not the same. Stricter evidence is appropriate when an incorrect result can remain hidden.

## Conclusion

AI skills and agents will continue to change as new models, tools, formats, and user expectations arrive. The goal is not to freeze a capability after it works once, but to ensure that each real failure leaves something useful behind: a clearer boundary, a regression guard or evaluation, or a better meta-rule for the next change.

TDD contributes an important discipline here: evidence before confidence. Evaluations extend that discipline to model-dependent behavior. Deterministic code can remove repeated model work from the common path, improving both reliability and efficiency, while meta-rules allow one capability's failure to improve how every capability is changed.
