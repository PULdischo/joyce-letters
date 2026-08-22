# James Joyce Letters — Sveltia/Eleventy POC

A proof-of-concept migration of the [University of Antwerp James Joyce
correspondence edition](https://joyceletters.uantwerpen.be/) (TEI XML,
served by eXist-db + TEI Publisher) into Markdown + YAML frontmatter,
editable via [Sveltia CMS](https://sveltiacms.app/) and built as a static
site with [Eleventy](https://www.11ty.dev/) and
[Pagefind](https://pagefind.app/) search.

This is a **scoped POC, not a full migration**: 6 sample letters are fully
converted (chosen to exercise different apparatus — editorial corrections,
gaps, a telegram, heavy foreign-language content), plus every `people`
record from the source site's canonical register, and stub `places`/`works`
entries extracted from all 279 source letters. See
[`sveltia-migration-assessment.md`](sveltia-migration-assessment.md) for
the full investigation behind these decisions — what the source platform
actually is, what does and doesn't survive a Markdown conversion, and why.

## Quick start

```bash
npm install
npm start                       # Eleventy dev server at localhost:8080
```

Open `http://localhost:8080/admin/index.html` in a **Chromium-based**
browser and click **"Work with Local Repository"** to edit content through
Sveltia CMS directly against your local checkout (File System Access API,
no proxy server needed). See [`admin/config.yml`](admin/config.yml) for
the token-based auth path used on the deployed site instead.

## Data pipeline

```
xml/*.xml            279 letters, fetched by fetch_letters.sh
xml/people/*.xml      202 canonical person records, fetched by fetch_people.sh
xml/frontmatter/*.xml Two reference documents (editorial procedures, abbreviations)
        │
        │  scripts/convert.py
        ▼
content/letters/*.md  6 fully-converted sample letters
content/people/*.md   320 people (202 with real biographies, 118 name-only stubs)
content/places/*.md   113 places (name-only stubs)
content/works/*.md    53 works (name-only stubs)
```

- **Fetching**: `./fetch_letters.sh` and `./fetch_people.sh` pull XML
  directly from the source site's `api/document/{id}.xml` endpoint (the
  same one TEI Publisher's own web UI uses — chosen because it works for
  every document, unlike the raw REST path, which 401s on ~18 letters).
  Both scripts are idempotent — safe to re-run, they skip files already
  on disk.
- **Converting**: `python3 scripts/convert.py` regenerates everything
  under `content/`. It parses TEI, extracts `teiHeader` metadata into YAML
  frontmatter, and walks the letter body converting to Markdown — entity
  mentions with a resolvable `@key` become links (`/people/{key}/` etc.),
  commentary notes become standard `[^n]` Markdown footnotes, and anything
  with no Markdown equivalent (dropped `choice`/`sic` alternates,
  `rend="underline"`, unresolved `ID_MISSING` entities, etc.) is **logged,
  not silently dropped** — see `scripts/conversion_report.csv` after each
  run (2,561 items logged as of the last run; kind-by-kind breakdown in
  §4–§7 of the assessment doc).

Re-running `convert.py` overwrites everything under `content/` except
files it doesn't generate a version of — if you've hand-edited a
converted file through Sveltia, regenerating will clobber that edit.

## Site

- `eleventy.config.js` — Eleventy config. Reads `content/` as the input
  directory; `content/{letters,people,places,works}/*.json` set each
  directory's default layout/permalink. Raw inline HTML (`<u>`, `<sup>`)
  is enabled in the Markdown renderer, since underline/superscript have no
  native Markdown syntax and are dropped by TEI Publisher's own Markdown
  exporter too (confirmed in the assessment doc). `markdown-it-footnote`
  is also enabled — without it, `[^n]` renders as literal bracket text,
  not a footnote (this was a real, confirmed bug, since fixed). Neither
  raw HTML nor `[^n]` are documented as round-trip-safe in Sveltia's
  RichText editor, so both come with an explicit raw-mode-editing note in
  `admin/config.yml` — see §8 of the assessment doc for the full reasoning
  and the maintainer discussion that informed it.
- `npm run build` — Eleventy build only, to `_site/`.
- `npm run build:search` — build, then index with Pagefind
  (`_site/pagefind/`). Run this, not just `build`, before serving `_site/`
  if you want `/search/` to work.
- GitHub Pages project sites serve from `/<repo-name>/`, not the domain
  root, but every internal link here — including ones baked directly into
  converted Markdown — is root-absolute. `eleventy.config.js` rewrites
  `href`/`src` at build time via `PATH_PREFIX` (see the CI workflow) so
  local dev and the deployed site both work without touching content.

## CMS (Sveltia)

`admin/config.yml` defines four collections (`letters`, `people`,
`places`, `works`) matching the real shape of the converted files —
`object`/`relation` fields for structured metadata like sender/recipient,
`select` fields for `format`/`categoryOfCorrespondence` with vocabularies
confirmed against the full 279-letter corpus (not just the 6 converted
samples), and `list` for repeatable contributors/editorial notes.

Two ways to sign in, no OAuth app or proxy server needed for either — see
the comment block at the top of `config.yml` for details:

1. **Local** (`npm start` → "Work with Local Repository")
2. **Deployed** → "Sign In with Token" (GitHub personal access token,
   scopes pre-selected by Sveltia at login time)

## Deployment

`.github/workflows/deploy.yml` builds and deploys to GitHub Pages on push
to `main` (or manual dispatch). **Requires GitHub Pages set to "GitHub
Actions" as the source** in repo Settings → Pages — the workflow has
nowhere to publish to otherwise.

## Further reading

- [`sveltia-migration-assessment.md`](sveltia-migration-assessment.md) —
  the full investigation: what platform the source site runs on, what TEI
  apparatus does and doesn't survive a Markdown conversion (verified
  against the source site's own deployed config, not guessed), the
  canonical people-register discovery, and open questions.
- `scripts/conversion_report.csv` — every apparatus feature the converter
  couldn't represent cleanly, one row per instance, regenerated on every
  `convert.py` run.
- [`choice_toggle_files.txt`](choice_toggle_files.txt) — the 78 letters
  using the source site's interactive sic/corr correction toggle, the
  single biggest fidelity loss in a Markdown conversion.
