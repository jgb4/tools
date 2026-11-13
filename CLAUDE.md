# tools

A collection of small web tools, published with GitHub Pages at https://jgb4.github.io/tools/
(repo: github.com/jgb4/tools, branch `main`, served from the repo root).

## Layout

```
index.html              ← landing page: one card per tool
<tool-name>/index.html  ← each tool lives in its own folder → jgb4.github.io/tools/<tool-name>/
```

Current tools: `pdf-converter/`.

## Adding a tool

1. Create `<tool-name>/index.html` (lowercase, hyphenated folder name; it becomes the URL, so don't rename it later).
2. **Add a card for it to the root `index.html`**, copying the existing `<a class="tool">` card: title + one-line description, `href="<tool-name>/"`.
3. Update the "Current tools" list above.

## Rules

- **Static only.** GitHub Pages can't run a server: everything must run in the browser.
  Load libraries from a CDN (cdnjs / jsDelivr) with exact pinned versions.
- **Relative paths only** (`./style.css`, `../index.html`), never `/style.css`: the site lives under `/tools/`.
- **No username in the code.** The account may be renamed again; relative paths keep everything working.
- Match the existing look: same CSS color tokens, light and dark mode, works at phone width.
- Files the user drops into a tool are processed in the browser and never uploaded.

## Deploying

Commit and push to `main`; the site updates in about 30 seconds. Verify the live URL afterwards.
Commit as `jgb4` with the GitHub noreply email (already set in the repo's git config); never use a personal email.

## Optional local server (pdf-converter only)

`pdf-converter/server.py` adds LibreOffice-based conversions when run locally (see `pdf-converter/README.md`).
The page detects it automatically on localhost; the public site never needs it.
