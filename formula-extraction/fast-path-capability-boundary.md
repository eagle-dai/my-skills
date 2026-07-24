# Formula fast-path capability matrix

This file records the deterministic `html-to-markdown` integration boundary. The skill may describe stricter/manual reconstruction strategies beyond this matrix, but it must not present them as implemented fast-path behavior.

| Source kind from preflight | Current batch behavior |
|---|---|
| `annotation` | Uses `original_latex` directly |
| `data-tex` / `data-latex` / `data-math` / `alttext` | Uses `original_latex` directly |
| `math-tex-script` | Uses `original_latex` directly |
| `katex-html-only` | Parses with `formula_batch.py`, then requires matching browser validation |
| `mathml` | Fail closed: deterministic MathML parser is not implemented |
| `unknown` | Fail closed with structured diagnostics |

When this matrix changes, update `formula-extraction/SKILL.md`, the executable resolver, and regression tests in the same PR.
