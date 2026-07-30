# Repository Note — Not Part of the Blog Article

> **Publishing rule:** This file contains a standalone blog article. When publishing it, copy only the content below the **BLOG ARTICLE STARTS HERE** marker.
>
> The published article must not link to, mention, or depend on any other file, directory, implementation, issue, pull request, or documentation in this repository. Code and directory structures shown in the article are self-contained examples. Links to external official documentation are allowed.

---

<!-- ==================== BLOG ARTICLE START ==================== -->

## BLOG ARTICLE STARTS HERE

*The repository note and this marker are not part of the article. Start copying from the title below.*

---

# When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop

*A Practical Way to Evolve AI Skills Without Breaking What Already Works*

One of the most frustrating problems in skill development is not that a new feature fails. It is that the new feature works, while something old quietly stops working.

This happens more often than expected. We add one rule, support one more input, or handle one more edge case. The new example passes. The change looks successful. Several days later, an older scenario produces a worse result, sometimes without any error message.

I met this problem while improving a small HTML-to-Markdown skill. One requirement was simple: remove unhelpful greetings from the beginning of an article.

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

A first implementation checked whether a paragraph started with a greeting. If yes, it removed the paragraph. The greeting disappeared, but so did the meaningful sentence and its bold formatting.

The new feature worked. The old capability did not.

This is the central difficulty of skill evolution. A skill does not only accumulate capabilities. It also accumulates interactions between natural-language instructions, deterministic code, regular expressions, tools, fallback paths, and platform-specific behavior.

After being bitten by this a few times, I settled on one working rule:

> Every real failure should become a durable rule, a regression case, and an executable test. If the same kind of failure happens repeatedly, it should also improve the rules for changing the skill itself.

I do not let the skill rewrite and release itself. The loop is still reviewed, tested, and committed like other engineering work.

## Why skills can forget silently

Normal software already has regression problems, but skills add another difficulty: their behavior is often defined by both text and code.

- Natural-language instructions describe what the agent should do.
- Reference documents explain rules and exceptions.
- Python or another language implements deterministic parts.
- Examples influence how the model interprets the instructions.
- Tests cover only the cases that somebody remembered to encode.

The text part does not fail loudly. Removing a sentence from a skill document causes no compilation error. Rewriting an instruction may make it shorter but lose an old exception. A broader regular expression may fix one input and damage several others.

The output can still look fluent and complete. This makes the regression dangerous: a plausible result may already have lost information.

In practice, I saw three recurring causes:

1. **A rule is generalized from one example.** It matches the surface, not the mechanism.
2. **A shared rule is changed for one defect and breaks an older scenario.** The new test passes, but another behavior regresses.
3. **A rule exists only in documentation.** Later, the document is rewritten and the rule disappears without any CI failure.

These problems need a change process, not more instructions.

## Separate shared improvement rules from skill-specific knowledge

A useful structural decision is to separate two kinds of knowledge.

The first kind is shared across all skills: **how a skill is allowed to change**.

The second kind belongs to one skill: **what this skill has learned from its own failures**.

A minimal layout can look like this:

```text
_meta/
└── skill-self-improvement.md

html-to-markdown/
├── SKILL.md
├── self-improvement.md
├── acceptance/
│   └── CASES.md
├── converter.py
└── tests/
    ├── test_acceptance.py
    └── test_regressions.py
```

The shared meta-rule file does not explain HTML conversion. It defines the workflow for changing any skill: generalization checks, forbidden shortcuts, trade-off priorities, and release requirements.

The skill-specific `self-improvement.md` records concrete regression knowledge: the failed input, expected result, mechanism, positive and negative examples, target platform, and protecting test.

The acceptance file is written from the user's point of view. The user describes the visible effect, not a selector, regular expression, or routing rule.

The automated test is the machine side of the same rule.

A skill therefore has two readers:

- the user cares about the visible result;
- the machine needs an executable contract.

Both sides are needed. A readable rule without a test can drift. A test without a readable intent becomes difficult to review.

## A six-step evolution loop

### 1. Be clear why the skill must change

A change should either produce a visible improvement or fix a regression that really happened.

For the example, the purpose is:

> Remove a pure opening greeting without deleting meaningful content or supported formatting in the same container.

This sentence also limits the scope. The change is not a general refactoring of paragraph handling.

Before coding, identify the failure pattern. Is the rule too narrow? Too broad? Did a shared component affect another path? Was the rule documented but not tested?

Without this step, it is easy to fix the symptom and keep the root cause.

### 2. Generalize before implementing: Gate One

The first gate asks whether the proposed rule can survive another input.

I use five questions:

1. **Are the examples varied enough?** Consider languages, numbers, punctuation, full-width and half-width characters, letter case, or different HTML structures.
2. **Does the rule describe a mechanism?** A DOM relationship, renderer behavior, or format standard is stronger than “this string looked wrong.”
3. **Are there negative examples?** Every detection rule should have at least two cases that must not match.
4. **Is the boundary precise?** Broad classes such as `.` or `\S` are warning signs. The rule should know whether it is dealing with letters, CJK characters, punctuation, whitespace, or structural nodes.
5. **Is the target platform explicit?** GitHub, VS Code, KaTeX, MathJax, and local renderers may behave differently.

For the greeting example, this rule is too broad:

> Remove a paragraph if its text starts with “Hello everyone”.

A better rule is:

> Remove only an independent greeting sentence. Do not remove its parent block when the block also contains meaningful text or supported inline structure.

The important change is not a more complicated regular expression. It is the correct unit of meaning. The wrong rule treats the paragraph as the deletion unit. The better rule treats only the pure greeting sentence as removable.

Useful boundaries include:

- a paragraph containing only a greeting should be removed;
- a greeting followed by meaningful bold text should keep the text;
- a sentence quoting “Hello everyone” should stay unchanged;
- a title containing similar words should not be treated as a greeting.

The positive cases show that the rule does its job. The negative cases are usually more valuable: they show where it must stop.

### 3. Turn every rule into executable evidence: Gate Two

The second gate is a hard rule:

> Any user-visible rule written into the skill must be backed by a CI test in the same change.

A useful check is:

> If this rule disappeared tomorrow, which test would fail?

If there is no answer, the rule has not really become part of the skill.

This is where test-driven development matters. Write the regression test before changing the implementation, and confirm that it fails first.

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

Then add positive and negative boundaries:

```python
def test_removes_pure_greeting() -> None:
    assert convert("<p>Hello everyone.</p>") == ""


def test_keeps_quoted_greeting() -> None:
    html = '<p>The guide uses “Hello everyone” as an example.</p>'
    assert convert(html) == (
        'The guide uses “Hello everyone” as an example.'
    )
```

The user-readable acceptance case can point back to the test:

```markdown
### Greeting followed by meaningful content

- Input: a greeting and meaningful formatted text in one paragraph
- Expected: remove only the greeting
- Must not: delete meaningful text or lose supported formatting
- Guard: `test_preserves_content_after_greeting`
```

The acceptance case says what the user wants. The test makes sure the system continues to respect it.

After the new test passes, run the complete suite, not only the new file.

The new test proves that the reported defect was fixed. The full suite checks that the fix did not become the next defect.

Old regression cases should normally not be deleted. If an old expectation is proven wrong, record the reason before changing it. Otherwise, deleting a test is deleting part of the skill's memory.

### 4. Do not manufacture a green result

A green CI result is useful only when the tests still protect the original intent.

Common shortcuts include:

- widening a regular expression only to include the failing example;
- weakening an assertion until the current output passes;
- running only the new test;
- deleting an old test because it became red;
- updating documentation without adding an executable guard;
- returning success when validation is incomplete;
- using timestamps or random values to hide nondeterministic behavior.

For an HTML-to-Markdown pipeline, producing some Markdown is not enough. Meaningful content must remain, supported structures must remain, and unresolved items must not be silently discarded.

A simple result model can make this explicit:

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
- `blocked`: a working result may exist, but it did not pass the contract and must not be delivered as success.

In other words, 'no exception was thrown' is not a useful definition of success. The output should have passed the checks that matter for this skill.

### 5. Protect the boundary and make trade-offs explicit

A change should touch only what is needed for its stated purpose. This matters when rules are shared across fast paths, strict paths, post-processing stages, or several skills.

A small regular-expression change can affect many behaviors. Duplicate copies of the same selector or default rule can also drift apart.

The trade-off order I use is:

```text
fail closed
    > repeatable result
    > structural preservation
    > broader coverage
    > shorter implementation
```

If an unknown HTML structure may cause information loss, route it to a strict path or block it. Do not guess and report success.

If the deterministic path is too slow for every input, separate fast and strict paths. Do not weaken correctness to gain speed.

If a new rule increases coverage but damages structure preservation, coverage must lose.

### 6. Verify and store the lesson back

After implementation:

1. run the full test suite and CI;
2. manually inspect semantic or visual behavior that code cannot judge reliably;
3. search for duplicated selectors, regular expressions, or default rules and remove conflicts;
4. record the root cause, risk, verification method, and known gaps;
5. store the lesson in the correct place.

A concrete failure belongs to the skill-specific regression knowledge:

- failed input;
- expected outcome;
- mechanism;
- positive and negative boundaries;
- protecting test.

A recurring way of failing belongs to the shared meta-rules:

- one-example rules are repeatedly too narrow;
- broad character classes repeatedly create false positives;
- local rendering repeatedly disagrees with the target platform;
- contributors repeatedly run only new tests;
- documentation-only rules repeatedly disappear.

The concrete case goes into the skill's regression record. If the same kind of mistake keeps returning, the change process itself needs a new rule.

## Test more than the converter

The converter is only one part of the skill. Instructions and reference documents also affect agent behavior, so documentation is part of the executable surface.

Useful repository-level checks can verify that:

- documentation does not claim support that the implementation still blocks;
- unsupported structures produce `strict_required` or `blocked`;
- naming and fallback rules stay consistent across documents and code;
- every acceptance case points to a real test;
- several skills do not describe contradictory contracts for shared behavior.

Test ownership should follow capability ownership. Tests for one skill's modules or documentation belong to that skill. Cross-skill consistency tests belong at repository level.

The target platform also matters. Markdown that looks correct in one local preview may fail on GitHub because its processing pipeline is different. Test the real target semantics, or reproduce them as closely as possible.

A fixture should be minimal but still faithful. The right fixture is the smallest one that preserves the real failure mechanism, not simply the smallest file.

## Where this approach works best

This method is most useful when four conditions are present:

1. the task is repeated, not one-off;
2. some behavior can be stated as a stable contract or invariant;
3. a failure can be reproduced with a fixture or recorded execution;
4. a plausible but wrong result has a real cost.

Typical examples include:

- document conversion, parsing, extraction, normalization, and validation;
- code or configuration generation with schemas and structural rules;
- tool-based workflows with known inputs, outputs, states, or approval steps;
- enterprise tasks with stable business rules and versioned APIs;
- skills with several execution paths, shared rules, or platform-specific behavior;
- agent tasks where tool calls or intermediate states can be checked, not only the final wording.

The method is less suitable as a strict TDD framework for one-off creative writing, open brainstorming, or tasks where many very different outputs are equally correct. In such cases, there may be no stable expected output to protect. Human review, rubric-based evaluations, or comparison across several samples are often more useful.

Some parts still apply widely: keep changes bounded, preserve known failures, record platform differences, and do not claim success without evidence. But the heavier regression machinery is valuable only when the task has repeatable behavior worth protecting.

## Put the skill where the tool can find it

For skills that I want to use across several projects, I prefer the personal Claude Code directory:

```text
~/.claude/skills/
```

[Claude Code loads a personal skill](https://code.claude.com/docs/en/skills#where-skills-live) from `~/.claude/skills/<skill-name>/SKILL.md`, making it available in all projects for the same user. A project-specific skill can still live under `.claude/skills/`, but that is a better fit when the behavior belongs to one repository or should be reviewed together with that repository's code.

For the running example, I would keep a small personal skill library like this:

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

The `html-to-markdown` directory is the actual skill. The `_meta` directory is only a shared reference area for how skills should be changed; it is not another user-facing skill.

### Put the personal skill library under Git

The whole `~/.claude/skills/` directory can be a Git repository. This is useful even for one person: every rule change has a diff, regression cases have history, and the same library can be used on another machine.

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

On another machine, clone the repository into the same location, but only when `~/.claude/skills` does not already exist:

```bash
git clone git@github.com:<your-account>/<your-skills-repo>.git ~/.claude/skills
```

If the directory already contains local skills, do not clone over it. Back it up first, or initialize it as a repository and reconcile the two histories deliberately.

I also keep a small `.gitignore` at the root:

```gitignore
.DS_Store
__pycache__/
*.pyc
.venv/
.env
```

Do not put credentials, tokens, machine-specific paths, private customer data, or generated working files into this repository. Keep it focused on skill instructions, references, small fixtures, tests, and scripts that are safe to version.

If a team needs to share a skill together with one application, use the project-level path instead:

```text
<project>/.claude/skills/<skill-name>/SKILL.md
```

That version naturally travels with the application repository and its pull requests. The personal directory is better for a reusable toolbox; the project directory is better for behavior owned by one codebase.

### Reference: the shared change rules

A minimal `~/.claude/skills/_meta/skill-self-improvement.md` can be written like this:

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

### Reference: the actual skill

The main `~/.claude/skills/html-to-markdown/SKILL.md` should stay focused on execution. It can point to the maintenance files when the skill itself is being changed:

```markdown
---
name: html-to-markdown
description: Convert saved HTML pages into clean Markdown while preserving supported content and structure.
---

# HTML to Markdown

Convert the input page and validate the result before reporting success.

When changing this skill itself:

1. Read the [shared change rules](../_meta/skill-self-improvement.md).
2. Read the [regression record](self-improvement.md) and [acceptance cases](acceptance/CASES.md).
3. Add a failing regression test first and run the full suite after the change.
```

### Reference: a user-readable acceptance case

The acceptance file should describe effects, not implementation details:

```markdown
### Greeting followed by meaningful content

- Input: one paragraph containing a greeting and meaningful formatted text
- Expected: remove only the greeting
- Must not: delete meaningful text or lose supported formatting
- Guard: `test_preserves_content_after_greeting`
```

Claude Code is only one place to use this structure. Its [skills follow the open Agent Skills format](https://code.claude.com/docs/en/skills), so keeping the package mostly standard makes future reuse easier. One caveat: the shared `_meta` file sits outside the individual skill package. If I distribute `html-to-markdown` by itself, I copy that rule into the skill's own `references/` directory or package the whole library, so the skill does not depend on a missing sibling file. SAP has [publicly described Joule Work](https://news.sap.com/2026/05/sap-sapphire-keynote-business-ai-platform-power-autonomous-enterprise/) as adding computer and file access and support for open standards such as MCP and A2A. Public documentation does not yet confirm support for the same `SKILL.md` format. If Joule Work later adopts the Agent Skills specification, a Git-managed skill library like this should be much easier to reuse or migrate. Even before that happens, the same governance pattern remains useful anywhere capabilities are stored as files and evolve through reviewed versions.

## Practical checklist

Before merging a skill change, ask:

- Can the user-visible purpose be stated in one sentence?
- Is the rule based on a mechanism rather than one example?
- Are there varied positive cases and at least two negative cases?
- Was a failing regression test written before the implementation change?
- If the documented rule disappeared, would a test fail?
- Was the complete suite run without weakening or deleting old guards?
- Is the change limited to the required boundary?
- Does uncertainty lead to `strict_required` or `blocked`, rather than plausible success?
- Are instructions, implementation, tests, and acceptance cases aligned?
- Was the concrete failure stored in the skill's regression knowledge?
- Was any recurring failure pattern stored in the shared meta-rules?
- Does this task have repeatable behavior that is worth protecting?

A skill will continue to change. New models, tools, formats, and user expectations will keep arriving. The goal is not to stop this change.

The goal is to make every improvement leave evidence, and every failure make the next improvement safer.
