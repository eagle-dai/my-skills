from pathlib import Path


path = Path("docs/when-ai-skills-learn-and-forget.md")
text = path.read_text(encoding="utf-8")

old_foundation = """## The foundation: two levels of memory

Preventing this class of regression requires memory at two different levels.

The most useful structural decision is to separate two kinds of knowledge.
"""
new_foundation = """## The foundation: two levels of memory

The most useful structural decision is to separate two kinds of knowledge: shared meta-rules and skill-specific lessons.
"""

old_efficiency = """## An additional benefit: less model work

The same separation between deterministic and model-dependent work creates another practical benefit: efficiency.

Regression protection was the original motivation for this approach, but the same separation can also improve runtime efficiency.
"""
new_efficiency = """## An additional benefit: less model work

Regression protection was the original motivation for this approach, but separating deterministic from model-dependent work can also improve runtime efficiency.
"""

for label, old in (("foundation", old_foundation), ("efficiency", old_efficiency)):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} block, found {count}")

text = text.replace(old_foundation, new_foundation)
text = text.replace(old_efficiency, new_efficiency)
path.write_text(text, encoding="utf-8")
