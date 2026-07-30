# Repository Note — Not Part of the Blog Article

> **Purpose:** This file contains a standalone technical blog prepared for publication on SAP Community.
>
> **Publishing rule:** Copy only the content below the **BLOG ARTICLE STARTS HERE** marker. The published article must not mention, link to, or depend on any other file, directory, implementation, issue, pull request, or documentation in this repository. Code and directory structures shown in the article are self-contained examples. Links to external official documentation are allowed.

## SAP Community Publishing Package

**Suggested board/category**

Technology Blog Posts by Members, or the closest AI/developer category available in the editor.

**Recommended title**

When an AI Skill Learns Something New—and Forgets Something Old

**Short description**

A small improvement to an AI skill can quietly break behavior that used to work. This post shares the practical workflow I now use: reproduce the failure, define the boundary, add regression tests, keep the change small, and store the lesson for the next change.

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

# When an AI Skill Learns Something New—and Forgets Something Old

*Some notes from maintaining file-based agent skills with tests and Git*

I once made a very small improvement to an HTML-to-Markdown skill. The request was simple: remove greetings such as “Hello everyone” from the beginning of an article.

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

My first solution checked whether a paragraph started with a greeting. When it did, I removed the paragraph.

The greeting was gone. Unfortunately, the useful sentence and its bold formatting were also gone.

So the new feature worked, but the skill became worse.

This kind of problem is easy to miss. There may be no exception, no red log and no obviously broken output. The result can still look fluent. Only some information has quietly disappeared.

After seeing several similar cases, I stopped treating a skill change as “just update the prompt”. I now handle it more like a software change, although not exactly the same. I want a reproducible failure, a clear boundary, a test for the new behavior, and some evidence that old behavior is still there.

In this article, “skill” means a file-based capability package containing instructions, references, scripts and tests. It does not mean a Joule Skill specifically.

Also, this approach is not useful for every AI task. It works best for repeatable behavior where we can describe what is correct and where a plausible but wrong answer has a real cost. For open-ended writing or creative tasks, human review and evaluation rubrics are usually more suitable.

## Why a skill can forget without telling us

A file-based skill often has several sources of behavior:

- `SKILL.md` tells the agent what to do;
- reference files contain rules and exceptions;
- scripts handle deterministic work;
- examples influence interpretation;
- tests protect only the cases we remembered to write down;
- the final renderer or tool may behave differently from our local environment.

Code normally complains when it is invalid. Natural-language instructions do not.

I can remove one sentence from `SKILL.md` and nothing will fail during compilation. I can rewrite a rule to make it shorter and accidentally remove an old exception. I can expand a regular expression for one new example and damage five old examples. I can also verify Markdown in VS Code and later find that GitHub renders it differently.

For me, the dangerous part is not that the output becomes nonsense. It often still looks reasonable.

The recurring causes I saw were quite ordinary:

1. I generalized a rule from only one example.
2. I changed a shared rule for one local problem.
3. I documented a rule but did not protect it with a test.
4. I tested the implementation but not the target environment.

Adding more text to the prompt did not solve these problems. Sometimes it only made the prompt longer and harder to review.

## Two kinds of memory

One change helped me a lot: I separated shared change rules from the lessons of one particular skill.

The shared part answers:

> How should any skill be changed safely?

The skill-specific part answers:

> What did this skill learn from its own failures?

A small structure can look like this:

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

`_meta/skill-self-improvement.md` is not about HTML conversion. It records the rules for changing skills: what to inspect before implementation, what shortcuts are not acceptable, and what should pass before the change is finished.

The skill's own `self-improvement.md` keeps concrete knowledge from previous failures:

- the failed input;
- the expected result;
- why it failed;
- examples that should match;
- examples that must not match;
- the target platform;
- the test that now protects this behavior.

I also keep acceptance cases in a form that a non-developer can understand. A user should not need to know a DOM selector or a regular expression to understand the promised behavior.

The test is the executable side of the same agreement.

This means the skill has two readers. A person needs to understand the intention, and a machine needs something it can check. Either side alone is not enough.

## The change loop I use now

I call it a six-step loop, but it is not a formal framework. It is simply the sequence that has worked for me.

### 1. Write down the purpose and the boundary

Before changing code or instructions, I try to write the user-visible purpose in one sentence.

For the greeting case, it was:

> Remove a standalone opening greeting, but keep meaningful content and supported formatting in the same container.

The second half is more important than it may look. It tells me what I am not allowed to break.

I also ask a few basic questions:

- Is the current rule too narrow or too broad?
- Is the problem in a shared component?
- Was the behavior only documented but never tested?
- Does the failure appear only in the real target environment?

Without this step, I often fix the visible symptom and leave the original mechanism unchanged.

### 2. Generalize before implementing

A rule based on one example is usually suspicious.

For example, this rule is too broad:

> Remove a paragraph when its text starts with “Hello everyone”.

The paragraph is only a storage container. It is not necessarily the unit that should be removed.

A better rule is:

> Remove only an independent greeting sentence. Do not remove the parent block when it also contains meaningful text or supported inline structure.

The main improvement is not a smarter regular expression. It is selecting the correct unit of meaning.

Before implementation, I normally try several boundary cases:

- a paragraph containing only a greeting should be removed;
- a greeting followed by bold text should keep the bold text;
- a sentence quoting “Hello everyone” should stay unchanged;
- a heading containing similar words should not be treated as a greeting;
- punctuation, letter case and full-width characters should not create accidental matches.

Positive examples show where the rule works. Negative examples show where it must stop. In practice, the negative examples are often more valuable.

### 3. Make the rule executable

I use one fairly strict rule for repeatable skill behavior:

> A user-visible rule added to a skill should have an automated test in the same change.

A useful review question is:

> If this rule disappears next month, which test will fail?

If I cannot answer, the rule is still only a hope.

For the regression above, I first add a failing test:

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

Then I add some boundaries:

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

After the new test passes, I run the full suite. Running only the new test proves that I fixed the reported case. It does not prove that I did not create another problem.

I normally keep old regression tests. When an old expectation is really wrong, I record why before changing it. Otherwise, deleting the test is also deleting part of the skill's memory.

### 4. Do not negotiate with the test until it becomes green

It is easy to produce a green result in the wrong way.

I have seen, and sometimes used, these shortcuts:

- widening a regular expression only for the latest input;
- weakening an assertion until the current output passes;
- running only the new test file;
- deleting an old test because it became inconvenient;
- updating documentation without an executable guard;
- calling the result successful while validation is incomplete.

A green CI result is useful only when the tests still represent the original intention.

For conversion skills, “some Markdown was produced” is not enough. Important content and supported structure must remain. Unknown content should not disappear silently.

Sometimes I make the status explicit:

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

“No exception happened” is not my definition of success.

### 5. Keep the change inside its boundary

A small rule may be shared by several paths or even several skills. This makes local fixes more risky than they first appear.

My current trade-off order is:

```text
fail closed
    > repeatable result
    > structural preservation
    > broader coverage
    > shorter implementation
```

This order is not universal. It comes from conversion and enterprise-oriented use cases where losing information is worse than refusing one difficult input.

When an unknown structure may cause information loss, I send it to a stricter path or block it. I prefer an honest limitation to a confident but damaged result.

When the strict path is too expensive for every input, I separate fast and strict paths. I do not make the correctness rule weaker only to make the happy path faster.

### 6. Store what was learned

After implementation, I do the following:

1. run the full test suite and CI;
2. inspect visual or semantic behavior that code cannot judge well;
3. search for duplicated selectors, regular expressions and default rules;
4. record the cause, risk, verification method and remaining gaps;
5. put the lesson in the correct place.

A concrete failure belongs to the skill-specific record.

A repeated way of failing belongs to the shared change rules. Examples are:

- rules based on one example are repeatedly too narrow;
- broad character classes repeatedly create false positives;
- local rendering repeatedly differs from the target platform;
- contributors repeatedly run only the new tests;
- documentation-only rules repeatedly disappear.

One failure should improve one skill. A repeated pattern should improve how all skills are changed.

## The main script is not the whole skill

It is natural to test the converter or the main script. However, instructions and reference files also influence behavior. In this sense, documentation is part of the executable surface.

Repository-level checks can verify that:

- documentation does not promise behavior that the implementation still blocks;
- unsupported inputs return `strict_required` or `blocked`;
- naming and fallback rules are consistent across text and code;
- each acceptance case points to a real test;
- shared behavior is not defined differently in several skills.

Test ownership should follow capability ownership. Tests for one skill belong with that skill. Cross-skill consistency tests belong at the library level.

The target platform should also be part of the evidence. Markdown that looks correct in one preview may fail on GitHub because the rendering pipeline is different. The fixture should keep the real failure mechanism, not only be as small as possible.

## A concrete setup with Claude Code and Git

For personal skills used across several projects, Claude Code supports this directory:

```text
~/.claude/skills/
```

[Claude Code loads personal skills](https://code.claude.com/docs/en/skills#where-skills-live) from `~/.claude/skills/<skill-name>/SKILL.md`. A project-specific skill can instead live under `.claude/skills/` inside the project repository.

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

The `html-to-markdown` directory is the skill. `_meta` is only a shared reference area; it is not another user-facing skill.

### Put the skill library under Git

The whole `~/.claude/skills/` directory can be a Git repository. This may sound a little heavy for one developer, but I find it useful. Every rule change has a diff, old regression cases have history, and the same skill library can be synchronized across machines.

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

Do not commit credentials, tokens, customer data, generated working files or machine-specific secrets. The repository should mainly contain instructions, references, small fixtures, tests and scripts that are safe to version.

For a team-owned skill tied to one application, I use the project-level path:

```text
<project>/.claude/skills/<skill-name>/SKILL.md
```

The personal directory is a reusable toolbox. The project directory is behavior owned by one codebase.

### Example shared change rules

A minimal `~/.claude/skills/_meta/skill-self-improvement.md` can be:

```markdown
# Changing a skill safely

Use this file when adding, removing or changing behavior in an existing skill.

1. State the user-visible purpose in one sentence.
2. Read the target skill's `self-improvement.md` and `acceptance/CASES.md`.
3. Add or identify a fixture that reproduces the failure.
4. Write a test that fails before changing the implementation.
5. Add varied positive cases and at least two negative cases.
6. Make the smallest change that fixes the mechanism, not only the example.
7. Run the full test suite. Do not weaken or delete old guards to make it green.
8. Update the acceptance case and regression record with the test name.
9. When the failure exposes a recurring mistake, update this shared file too.

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

1. Read the [shared change rules](../_meta/skill-self-improvement.md).
2. Read the [regression record](self-improvement.md).
3. Read the [acceptance cases](acceptance/CASES.md).
4. Add a failing regression test first.
5. Run the full test suite after the change.
```

When I distribute `html-to-markdown` alone, I copy the shared rules into its own `references/` directory or package the complete library. A skill should not depend on a sibling file that is absent from the distributed package.

## Why this may matter for SAP teams

The files above are not a Joule Skill, and this article is not a Joule Studio tutorial.

Still, I think the lifecycle problem is relevant to SAP teams. AI-enabled capabilities can now be created and changed very quickly. This speed is useful, but it also means we can introduce a regression very quickly. In an enterprise workflow, a fluent but wrong result may be more dangerous than an obvious failure because several downstream steps may accept it before a person notices.

SAP has [publicly described Joule Work](https://news.sap.com/2026/05/sap-sapphire-keynote-business-ai-platform-power-autonomous-enterprise/) as providing computer and file access and supporting open standards such as MCP and A2A. Public information does not currently confirm that it uses the same `SKILL.md` or Agent Skills format as Claude Code.

So I would not claim direct compatibility.

If Joule Work supports the Agent Skills specification in the future, a Git-managed library based on standard files may be easier to reuse or migrate. If it does not, most of the engineering habits still transfer:

- version the capability definition;
- keep acceptance criteria readable by people;
- reproduce real failures;
- protect old behavior with tests;
- make fallback and release gates explicit;
- store lessons where the next change can find them.

The file format may change. The lifecycle problem will remain.

## A checklist I actually use

Before merging a skill change, I check:

- Can I explain the user-visible purpose in one sentence?
- Is the rule based on a mechanism, not only one example?
- Do I have positive and negative boundary cases?
- Did I first reproduce the failure?
- Which test will fail if the new rule disappears?
- Did I run the full suite without weakening old guards?
- Is the change limited to the necessary area?
- Will uncertainty produce `strict_required` or `blocked` instead of plausible success?
- Are the instructions, implementation, tests and acceptance cases still saying the same thing?
- Did I store the concrete lesson and any repeated failure pattern?

I do not always execute every item with the same weight. A small personal skill and a business-critical workflow are not the same. But when a wrong result can hide easily, I prefer to be more strict.

## Conclusion

AI skills will continue to change. New models, tools and formats will arrive, and users will ask for new behavior.

I do not want to freeze a skill after it works once. I want each real failure to leave something useful behind: a better boundary, a regression case, or a change rule that prevents the same mistake next time.

This is still evolving in my own work. I am interested in how other SAP developers and architects handle the same problem. Do you keep prompt and skill regressions as tests, evaluation datasets, review checklists, or in another form?
