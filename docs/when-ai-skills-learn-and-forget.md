# Repository Note — Not Part of the Blog Article

> **Purpose:** This file contains a standalone technical blog prepared for publication on SAP Community.
>
> **Publishing rule:** Copy only the content below the **BLOG ARTICLE STARTS HERE** marker. The published article must not mention, link to, or depend on any other file, directory, implementation, issue, pull request, or documentation in this repository. Code and directory structures shown in the article are self-contained examples. Links to external official documentation are allowed.

## SAP Community Publishing Package

**Suggested board/category**

Technology Blog Posts by Members, or the closest AI/developer category available in the editor.

**Recommended title**

How I Evolve AI Skills Without Breaking Existing Behavior

**Short description**

AI skills can regress silently: a new case works while older behavior breaks. This post presents a practical six-step evolution loop that turns real failures into acceptance cases, regression tests, and reusable change rules, with a Git-managed Claude Code setup as a concrete example.

**Suggested SAP Managed Tags**

- SAP Business AI
- SAP Business Technology Platform

[SAP Community requires at least one SAP Managed Tag and recommends using no more than three](https://community.sap.com/t5/what-s-new/enhancements-to-sap-community-september-2025/ba-p/14231974). Use only tags that are available and genuinely relevant when publishing.

**Suggested user tags**

- agent skills
- AI skills
- skill evolution
- regression testing
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

# How I Evolve AI Skills Without Breaking Existing Behavior

*A regression-safe workflow for file-based agent skills using acceptance cases, tests, and Git*

AI skills are easy to improve in a demo and surprisingly hard to improve safely.

The failure mode that bothers me most is not a new feature that simply does not work. It is a new feature that works exactly as requested while an older capability quietly gets worse.

I ran into this while improving a small HTML-to-Markdown skill. One request sounded harmless: remove unhelpful greetings from the beginning of an article.

Consider this HTML:

```html
<p>
  Hello everyone.
  <strong>The migration must finish before Friday.</strong>
</p>
```

The expected Markdown is:

```markdown
**The migration must finish before Friday.**
```

My first implementation checked whether a paragraph started with a greeting. If it did, the code removed the paragraph.

The greeting disappeared. So did the useful sentence and its bold formatting.

The new feature worked. The existing behavior did not.

That small defect changed the way I maintain skills. I now treat a skill change much more like a software change: the request needs a boundary, the failure needs a reproducible example, and the fix needs evidence that it did not damage what was already working.

In this post, I will show:

- why file-based skills can regress without obvious errors;
- how I separate shared change rules from skill-specific lessons;
- the six-step evolution loop I use;
- a concrete Claude Code directory and Git setup;
- why the same discipline is useful for SAP-oriented AI workflows and potentially for Joule Work in the future.

> **Terminology note:** In this article, “skill” means a file-based agent capability package containing instructions, references, scripts, and tests. It does not mean a Joule Skill specifically.

## Why skills can forget silently

Normal software already has regression problems, but file-based skills add another layer: behavior is often defined by both text and code.

- Natural-language instructions tell the agent what to do.
- Reference files describe rules and exceptions.
- Python or another language handles deterministic steps.
- Examples influence how a model interprets an instruction.
- Tests cover only the cases somebody remembered to encode.
- Tool and renderer behavior can vary across environments.

The code may fail loudly. The text often does not.

Deleting a sentence from `SKILL.md` causes no compilation error. Rewriting an instruction can make it cleaner while dropping an old exception. A broader regular expression can fix one input and damage several others. A local Markdown preview can look correct while the target platform renders it differently.

The output may still look fluent and complete. That is what makes the regression dangerous: a plausible result can already have lost information.

I repeatedly saw three causes:

1. **A rule was generalized from one example.** It matched the surface pattern, not the underlying mechanism.
2. **A shared rule was changed for one defect.** The new test passed, but another path regressed.
3. **A rule existed only in documentation.** The document was later rewritten, and the rule disappeared without any CI failure.

Adding more prose to the prompt did not solve this. I needed a repeatable change process.

## Keep two kinds of memory

The most useful structural decision was to separate two kinds of knowledge.

The first is shared across skills:

> How are skills allowed to change?

The second belongs to one particular skill:

> What has this skill learned from its own failures?

A minimal layout looks like this:

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

The shared `_meta/skill-self-improvement.md` file does not explain HTML conversion. It defines how any skill should be changed: what must be checked before implementation, which shortcuts are forbidden, how trade-offs are resolved, and what must pass before release.

The skill-specific `self-improvement.md` records concrete regression knowledge:

- the failed input;
- the expected result;
- the mechanism behind the failure;
- positive and negative examples;
- the target platform;
- the test that protects the behavior.

The acceptance file describes the visible behavior from the user's point of view. It should not require the reader to understand a selector, regular expression, or routing rule.

The automated test is the machine-readable side of the same agreement.

A skill therefore has two readers:

- a person needs to understand the intended outcome;
- a machine needs an executable contract.

A readable rule without a test can drift. A test without readable intent becomes difficult to review.

## The six-step evolution loop

### 1. State the purpose and limit the change

A change should either create a visible improvement or fix a failure that actually occurred.

For the greeting example, I wrote the purpose as one sentence:

> Remove a standalone opening greeting without deleting meaningful content or supported formatting in the same container.

This sentence also defines what the change is not. It is not a general refactoring of paragraph handling.

Before coding, I try to classify the failure:

- Was the rule too narrow?
- Was it too broad?
- Did a shared component affect another path?
- Was the rule documented but never tested?
- Did the target platform behave differently from the local environment?

Without this step, it is easy to patch the symptom and preserve the root cause.

### 2. Generalize before implementing

Before I accept a proposed rule, I ask whether it can survive a different input.

I use five questions:

1. **Are the examples varied enough?** Consider languages, numbers, punctuation, full-width and half-width characters, letter case, and different document structures.
2. **Does the rule describe a mechanism?** A DOM relationship, renderer behavior, or format standard is stronger than “this string looked wrong.”
3. **Are there negative examples?** Every detection rule should include cases that must not match.
4. **Is the boundary precise?** Broad classes such as `.` or `\S` are warning signs unless the intended boundary is genuinely broad.
5. **Is the target environment explicit?** GitHub, VS Code, KaTeX, MathJax, and local renderers may behave differently.

For the greeting example, this rule is too broad:

> Remove a paragraph when its text starts with “Hello everyone”.

A better rule is:

> Remove only an independent greeting sentence. Do not remove its parent block when the block also contains meaningful text or supported inline structure.

The important improvement is not a more complicated regular expression. It is choosing the correct unit of meaning.

Useful boundary cases include:

- a paragraph containing only a greeting should be removed;
- a greeting followed by meaningful bold text should keep the meaningful text;
- a sentence quoting “Hello everyone” should remain unchanged;
- a title containing similar words should not be treated as a greeting.

The positive cases show that the rule works. The negative cases show where it must stop.

### 3. Turn the rule into executable evidence

My second hard rule is:

> Any user-visible rule added to a skill must be backed by an automated test in the same change.

A useful review question is:

> If this rule disappeared tomorrow, which test would fail?

If there is no answer, the rule has not really become part of the skill.

For the regression above, I first write a failing test:

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

Then I add the boundaries:

```python
def test_removes_pure_greeting() -> None:
    assert convert("<p>Hello everyone.</p>") == ""


def test_keeps_quoted_greeting() -> None:
    html = '<p>The guide uses “Hello everyone” as an example.</p>'

    assert convert(html) == (
        'The guide uses “Hello everyone” as an example.'
    )
```

The corresponding acceptance case can remain understandable to a non-developer:

```markdown
### Greeting followed by meaningful content

- Input: one paragraph containing a greeting and meaningful formatted text
- Expected: remove only the greeting
- Must not: delete meaningful text or lose supported formatting
- Guard: `test_preserves_content_after_greeting`
```

The acceptance case says what the user needs. The test ensures the implementation continues to respect it.

After the new test passes, I run the full suite, not only the new test file. The new test proves that the reported defect was fixed. The full suite checks that the fix did not become the next defect.

I normally keep old regression cases. If an old expectation is genuinely wrong, I record why before changing or deleting it. Otherwise, deleting a regression test is deleting part of the skill's memory.

### 4. Do not manufacture a green result

Green CI is useful only when the tests still protect the original intent.

Common shortcuts include:

- widening a regular expression only to include the latest failing input;
- weakening an assertion until the current output passes;
- running only the new test;
- deleting an old test because it became red;
- updating documentation without an executable guard;
- reporting success when validation is incomplete;
- using timestamps or random values to hide nondeterministic behavior.

For an HTML-to-Markdown pipeline, producing some Markdown is not enough. Meaningful content and supported structure must remain. Unresolved content must not disappear silently.

A small result model can make this explicit:

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

- `converted`: the output passed the required checks;
- `strict_required`: the input exceeded the safe deterministic path;
- `blocked`: a plausible output may exist, but it did not pass the contract and must not be delivered as success.

“No exception was thrown” is not a useful definition of success. The output should have passed the checks that matter for the skill.

### 5. Protect the boundary and make trade-offs explicit

A change should touch only what is needed for its stated purpose. This matters when a rule is shared across fast paths, strict paths, post-processing stages, or several skills.

A small regular-expression change can affect many behaviors. Duplicate copies of a selector or default rule can also drift apart.

The trade-off order I use is:

```text
fail closed
    > repeatable result
    > structural preservation
    > broader coverage
    > shorter implementation
```

If an unknown document structure may cause information loss, I route it to a stricter path or block it. I do not guess and report success.

If a deterministic path is too slow for every input, I separate fast and strict paths. I do not weaken correctness to gain speed.

If a new rule increases coverage but damages structural preservation, coverage loses.

### 6. Verify and store the lesson

After implementation, I:

1. run the full test suite and CI;
2. inspect semantic or visual behavior that code cannot judge reliably;
3. search for duplicated selectors, regular expressions, or default rules;
4. record the root cause, risk, verification method, and known gaps;
5. save the lesson in the correct place.

A concrete failure belongs to the skill-specific regression record:

- failed input;
- expected outcome;
- mechanism;
- positive and negative boundaries;
- protecting test.

A recurring way of failing belongs to the shared change rules:

- one-example rules are repeatedly too narrow;
- broad character classes repeatedly create false positives;
- local rendering repeatedly disagrees with the target platform;
- contributors repeatedly run only the new tests;
- documentation-only rules repeatedly disappear.

The concrete case improves one skill. A recurring pattern should improve the way every skill is changed.

## Test more than the main script

The converter is only one part of the skill. Instructions and reference files also affect behavior, so documentation is part of the executable surface.

Repository-level checks can verify that:

- documentation does not claim support that the implementation still blocks;
- unsupported structures produce `strict_required` or `blocked`;
- naming and fallback rules remain consistent across text and code;
- every acceptance case points to a real test;
- multiple skills do not define contradictory contracts for shared behavior.

Test ownership should follow capability ownership. Tests for one skill's files belong to that skill. Cross-skill consistency tests belong at the library level.

The target environment matters too. Markdown that looks correct in one local preview may fail on GitHub because its processing pipeline differs. Test the real target semantics, or reproduce them as closely as practical.

A fixture should be small but faithful. The right fixture is the smallest example that preserves the real failure mechanism, not simply the smallest file.

## Where this approach works well

This method is most useful when four conditions are present:

1. the task is repeated rather than one-off;
2. some behavior can be stated as a stable contract or invariant;
3. a failure can be reproduced with a fixture or recorded execution;
4. a plausible but wrong result has a real cost.

Examples include:

- document conversion, parsing, extraction, normalization, and validation;
- code or configuration generation with schemas and structural rules;
- tool-based workflows with known inputs, outputs, states, or approvals;
- enterprise tasks with stable business rules and versioned APIs;
- skills with several execution paths or platform-specific behavior;
- agent workflows where tool calls and intermediate states can be checked.

For SAP teams, that can include skills that validate integration payloads, produce configuration files, transform business documents, guide repeatable developer workflows, or generate structured artifacts for CAP, SAPUI5, or other development environments. The point is not the specific technology. The point is that the output has contracts worth protecting.

This method is less suitable as a strict test-driven framework for one-off creative writing, open brainstorming, or tasks where many very different outputs are equally correct. Human review, rubric-based evaluation, and comparison across several samples are usually more useful there.

Some principles still apply widely: keep changes bounded, preserve known failures, record environment differences, and do not claim success without evidence. The heavier regression machinery is worthwhile only when repeatable behavior exists.

## A concrete setup with Claude Code and Git

For skills I use across several projects, I keep them in Claude Code's personal skill directory:

```text
~/.claude/skills/
```

[Claude Code loads personal skills](https://code.claude.com/docs/en/skills#where-skills-live) from `~/.claude/skills/<skill-name>/SKILL.md`, making them available across the user's projects. A project-specific skill can instead live under `.claude/skills/` when its behavior belongs to one repository or should be reviewed together with that repository's code.

For the running example, I would use:

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

The `html-to-markdown` directory is the actual skill. The `_meta` directory is a shared reference area for how skills should be changed; it is not another user-facing skill.

### Put the personal skill library under Git

The entire `~/.claude/skills/` directory can be a Git repository. This is useful even for one developer: every rule change has a diff, every regression case has a history, and the same skill library can be synchronized across machines.

A minimal setup is:

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

On another machine, clone into the same location only when the target directory does not already exist:

```bash
git clone git@github.com:<your-account>/<your-skills-repo>.git ~/.claude/skills
```

If the directory already contains local skills, do not clone over it. Back it up or reconcile the repositories deliberately.

A small `.gitignore` is enough for many libraries:

```gitignore
.DS_Store
__pycache__/
*.pyc
.venv/
.env
```

Do not commit credentials, tokens, customer data, machine-specific paths, or generated working files. Keep the repository focused on instructions, references, small fixtures, tests, and scripts that are safe to version.

For a team-owned skill tied to one application, use the project-level path:

```text
<project>/.claude/skills/<skill-name>/SKILL.md
```

The personal directory is a reusable toolbox. The project directory is behavior owned by one codebase.

### Reference implementation: shared change rules

A minimal `~/.claude/skills/_meta/skill-self-improvement.md` can be:

```markdown
# Changing a skill safely

Use this file when adding, removing, or changing behavior in an existing skill.

1. State the user-visible purpose in one sentence.
2. Read the target skill's `self-improvement.md` and `acceptance/CASES.md`.
3. Add or identify a fixture that reproduces the failure.
4. Write a test that fails before changing the implementation.
5. Add varied positive cases and at least two negative cases.
6. Make the smallest change that fixes the mechanism, not only the example.
7. Run the full test suite. Do not weaken or delete old guards to make it green.
8. Update the acceptance case and regression record with the test name.
9. If the failure exposes a recurring mistake, update this shared file too.

Stop with `blocked` or route to a stricter path when correctness cannot be established.
```

### Reference implementation: the skill file

The main `~/.claude/skills/html-to-markdown/SKILL.md` should stay focused on execution:

```markdown
---
name: html-to-markdown
description: Convert saved HTML pages into clean Markdown while preserving supported content and structure.
---

# HTML to Markdown

Convert the input page and validate the result before reporting success.

When changing this skill itself:

1. Read the [shared change rules](../_meta/skill-self-improvement.md).
2. Read the [regression record](self-improvement.md).
3. Read the [acceptance cases](acceptance/CASES.md).
4. Add a failing regression test first.
5. Run the full test suite after the change.
```

If I distribute `html-to-markdown` by itself, I copy the shared change rules into its own `references/` directory or package the whole library. The skill should not depend on a sibling file that is missing from the distributed package.

## Why I think this matters for SAP teams

The file package shown above is not a Joule Skill, and this post is not a Joule Studio tutorial.

The lifecycle problem is still relevant to SAP teams. As AI-enabled capabilities become faster to create, they also become easier to change. In enterprise workflows, a fluent but wrong result can be more damaging than an obvious failure because it may pass through several downstream steps before somebody notices.

SAP has [publicly described Joule Work](https://news.sap.com/2026/05/sap-sapphire-keynote-business-ai-platform-power-autonomous-enterprise/) as providing computer and file access and supporting open standards such as MCP and A2A. Public documentation does not currently confirm compatibility with the same `SKILL.md` or Agent Skills format used in the Claude Code example.

If Joule Work adopts the Agent Skills specification in the future, a Git-managed skill library built from standard files should be easier to reuse or migrate. If it does not, the core engineering practices still transfer:

- version the capability definition;
- keep user-readable acceptance criteria;
- reproduce failures;
- protect old behavior with tests;
- use explicit fallback and release gates;
- store lessons where future changes will find them.

The file format may change. The need for controlled evolution will not.

## Practical checklist

Before merging a skill change, I ask:

- Can I state the user-visible purpose in one sentence?
- Is the rule based on a mechanism rather than one example?
- Are there varied positive cases and at least two negative cases?
- Did I write a failing regression test before changing the implementation?
- If the documented rule disappeared, would a test fail?
- Did I run the full suite without weakening or deleting old guards?
- Is the change limited to the required boundary?
- Does uncertainty lead to `strict_required` or `blocked` rather than plausible success?
- Are instructions, implementation, tests, and acceptance cases aligned?
- Did I store the concrete failure in the skill's regression record?
- Did I add any recurring failure pattern to the shared change rules?
- Does this task have repeatable behavior worth protecting?

## Conclusion

AI skills will keep changing. New models, tools, formats, and user expectations will keep arriving. The goal is not to freeze a skill once it works.

My goal is simpler: every improvement should leave evidence, and every real failure should make the next change safer.

I am interested in how other SAP developers and architects handle this problem. Do you keep prompt and skill regressions as executable tests, evaluation datasets, review checklists, or something else?
