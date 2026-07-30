# When AI Skills Learn—and Forget: Engineering a Safe Evolution Loop

A skill normally becomes more useful step by step. We add one rule, support one more input, or handle one more edge case. Then one day, a new improvement quietly breaks something that already worked.

I met this problem while improving a small HTML-to-Markdown skill. One requirement was simple: remove unhelpful greetings from the beginning of an article.

```html
<p>
  Hello everyone.
  <strong>The migration must finish before Friday.</strong>
</p>
```

The expected Markdown was:

```markdown
**The migration must finish before Friday.**
```

A first implementation checked whether a paragraph started with a greeting. If yes, it removed the paragraph. The greeting disappeared, but so did the meaningful sentence and its bold formatting.

The new feature worked. The skill became worse.

A skill does not only accumulate capabilities. It also accumulates interactions between natural-language instructions, Python code, regular expressions, tools, fallback paths, and platform-specific behavior.

This article shares the structure I now use to improve skills more safely:

> Every real failure should become a durable rule, a regression case, and an executable test. If the same kind of failure happens repeatedly, it should also improve the rules for changing the skill itself.

This is not autonomous self-modification. It is a controlled engineering loop.

## Why skills can forget silently

Traditional code has compilers, type systems, interfaces, and tests. A skill is different because its behavior is often defined by both text and code:

- instructions describe what the agent should do;
- reference documents explain rules and exceptions;
- Python implements deterministic parts;
- examples influence how the model interprets the instructions;
- tests cover only cases that somebody remembered to encode.

The text part does not fail loudly. A deleted rule in a Markdown file causes no compilation error. A rewritten instruction may look cleaner but lose an old exception. A broader regular expression may fix one input and damage several others.

The output can still look fluent and complete. This makes the regression dangerous.

In practice, I saw three recurring causes:

1. **A rule is generalized from one example.** It matches the surface, not the mechanism.
2. **A shared rule is changed for one defect and breaks an older scenario.** The new test passes, but another behavior regresses.
3. **A rule exists only in documentation.** Later, the document is rewritten and the rule disappears without any CI failure.

These problems need a change process, not more instructions.

## Separate shared rules from skill-specific knowledge

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

The shared meta-rule file does not explain HTML conversion. It defines the change workflow, generalization checks, forbidden shortcuts, trade-off priorities, and release requirements.

The skill-specific `self-improvement.md` records concrete regression knowledge: the input, expected result, positive and negative examples, mechanism, target platform, and protecting test.

The acceptance file is written from the user's point of view. A user describes the visible effect, not the selector, regular expression, or routing logic.

The tests are the machine side of the same rule.

A skill therefore has two readers:

- the user cares about the visible result;
- the machine needs an executable contract.

Both sides are needed. A user-readable rule without a test can drift. A test without a readable intent becomes hard to review.

## A six-step evolution loop

### 1. Be clear why the skill must change

A change should either produce a visible improvement or fix a regression that really happened.

For the example, the reason is:

> Remove a pure opening greeting without deleting meaningful content or supported formatting in the same container.

This sentence also limits the scope. The change is not a general refactoring of paragraph handling.

Before coding, classify the problem. Is the rule too narrow? Too broad? Did a shared component affect another path? Was the rule documented but not tested?

Without this step, we often fix the symptom and keep the root cause.

### 2. Generalize before implementing: Gate One

The first gate asks whether the proposed rule can survive another input.

I use five questions:

1. **Are the examples varied enough?** Consider languages, punctuation, full-width and half-width characters, letter case, or different HTML structures.
2. **Does the rule describe a mechanism?** A DOM relationship, rendering rule, or format standard is stronger than “this string looked wrong.”
3. **Are there negative examples?** Every detection rule should have at least two cases that must not match.
4. **Is the boundary precise?** Broad classes such as `.` or `\S` are often warning signs.
5. **Is the target platform explicit?** GitHub, VS Code, KaTeX, MathJax, and local renderers may behave differently.

For the greeting example, this rule is too broad:

> Remove a paragraph if its text starts with “Hello everyone”.

A better rule is:

> Remove only an independent greeting sentence. Do not remove its parent block when the block also contains meaningful text or supported inline structure.

The key is not a smarter regular expression. It is the correct unit of meaning. The wrong rule uses the whole paragraph as the deletion unit. The better rule uses the pure greeting sentence.

Useful boundaries include:

- a paragraph containing only a greeting should be removed;
- a greeting followed by meaningful bold text should keep the text;
- a sentence quoting “Hello everyone” should stay unchanged;
- a title containing similar words should not be treated as a greeting.

Positive cases prove that a rule can act. Negative cases define where it must stop.

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

The user-readable case can point back to the test:

```markdown
### Greeting followed by meaningful content

- Input: a greeting and meaningful formatted text in one paragraph
- Expected: remove only the greeting
- Must not: delete meaningful text or lose supported formatting
- Guard: `test_preserves_content_after_greeting`
```

After the new test passes, run the complete suite, not only the new file.

The new test proves that this defect was fixed. The full suite checks that the fix did not become the next defect.

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

Success is not the absence of an exception. Success means the required evidence exists.

### 5. Protect the boundary and make trade-offs explicit

A skill change should touch only what is needed for its stated purpose. This matters when rules are shared across fast paths, strict paths, post-processing stages, or several skills.

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

This final feedback is what closes the loop.

A concrete failure improves the skill. A recurring failure pattern improves the way the skill is improved.

## Test more than the converter

The converter is only one part of the skill. Instructions and reference documents also affect agent behavior, so documentation is part of the executable surface.

Useful repository-level checks can verify that:

- documentation does not claim support that the implementation still blocks;
- unsupported structures produce `strict_required` or `blocked`;
- naming and fallback rules stay consistent across documents and code;
- every acceptance case points to a real test;
- several skills do not describe contradictory contracts for shared behavior.

Test ownership should follow capability ownership. Tests for one skill's modules or documentation belong to that skill. Cross-skill consistency tests belong at repository level.

The target platform also matters. Markdown that looks correct in one local preview may fail on GitHub because the processing pipeline is different. Test the real target semantics, or reproduce them as closely as possible.

A fixture should be minimal but still faithful. The right fixture is the smallest one that preserves the real failure mechanism, not simply the smallest file.

## A brief connection to Joule Studio

The technical artifact described here is not the same as a Joule Skill. However, the lifecycle problem is similar. SAP documentation describes Joule Skills as tailored, deterministic tasks, while Joule Agents handle more complex or multi-step work. Joule Studio also supports managing and deploying updated versions of these capabilities.

As SAP moves toward faster, intent-based development in the newly announced Joule Studio, capability creation can become faster. This makes regression evidence more important, not less. Acceptance cases, executable contracts, versioned tests, controlled fallback, and release gates are still needed when a capability evolves.

For current product details, see [What is Joule Studio?](https://help.sap.com/docs/Joule_Studio/45f9d2b8914b4f0ba731570ff9a85313/6af9c49f47cc4da1bc012c049df92569.html) and [New Joule Studio for Enterprise Scale Agentic Development](https://news.sap.com/2026/05/new-joule-studio-enterprise-scale-agentic-development/).

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

A skill will continue to change. New models, tools, formats, and user expectations will keep arriving. The goal is not to stop this change.

The goal is to make every improvement leave evidence, and every failure make the next improvement safer.
