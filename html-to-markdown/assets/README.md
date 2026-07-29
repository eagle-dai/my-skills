# Bundled assets

## katex.min.js

Pinned local KaTeX runtime for offline formula batch validation
(`formula_batch.py::validation_document` / `copy_katex_runtime`).

- Version: **0.16.9** (`KATEX_VERSION` in `formula_batch.py`)
- Source: `https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js`
- SHA-256: `dc84b296ec3e884de093158f760fd9d45b6c7abe58b5381557f4e138f46a58ae`

Only `katex.min.js` is bundled — no CSS or fonts. Validation calls
`katex.render(latex, node, {throwOnError:true})`; whether it throws depends
solely on LaTeX parsing, which is font-independent. So fonts/CSS (which only
affect visual glyphs) are unnecessary and would bloat the skill ~5 MB.

To re-pin: download the new version, update `KATEX_VERSION`, replace this SHA,
and re-run `tests/test_validation_document.py` (asserts version + bundle size).
