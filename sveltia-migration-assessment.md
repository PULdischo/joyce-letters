# Assessment: Migrating the James Joyce Letters XML to Sveltia CMS (Markdown + YAML)

Source corpus: 279 TEI XML letters fetched from https://joyceletters.uantwerpen.be into [xml/](xml/).
Site platform: eXist-db + TEI Publisher (confirmed from source, see below).

## 1. Platform the source site runs on

- **Database/server:** eXist-db, native XML database. Confirmed via:
  - `Server: Jetty(9.4.44.v20210927)` response header (Jetty ships embedded with eXist-db)
  - `Created`/`Last-Modified` headers on REST document fetches (eXist-db exposes DB resource metadata as HTTP headers)
  - `X-XQuery-Cached: true` header (eXist-db-specific)
  - URL structure `/exist/apps/...`, `/exist/rest/db/...`
- **Application framework:** TEI Publisher (github.com/eeditiones/tei-publisher-app + eeditiones/tei-publisher-lib)
  - Front end built from `@teipublisher/pb-components` Web Components (`pb-page`, `pb-document`, `pb-view`, `pb-load`, `pb-tabs`, etc.)
  - `Access-Control-Expose-Headers: pb-start, pb-total` (TEI Publisher-specific headers)
  - `/exist/apps/jjletters/api.html` serves "TEI Publisher API Documentation"
  - App maintains a custom ODD (`odd="JJletters"`), the mechanism TEI Publisher uses to compile TEI markup → HTML/CSS rendering rules, with an admin "Recompile ODD" control in the page source
- **No static build step** — every page (except the pre-rendered correspondence table) is XQuery executing against the database per request, applying the ODD-compiled transform live.

## 2. Corpus structure

- 279 letters, ~3.1 MB total XML
- `teiHeader` (title, correspondents, format, repository, contributors) is present and uniform in all 279 files — good fit for YAML frontmatter
- Every letter's body carries TEI's scholarly apparatus: authority-keyed entity mentions, inline annotation anchors, and (in about half the corpus) editorial/textual-critical markup

## 3. What migrates cleanly to Sveltia fields

Sveltia's `object` and `relation` widgets (confirmed via official docs: object accepts subfields of any widget type including nesting relation inside object; relation supports `multiple: true` for arrays) are a good fit for the **structured header metadata**:

```yaml
fields:
  - {name: title, widget: string}
  - name: correspondence
    widget: object
    fields:
      - {name: sender, widget: relation, collection: people, value_field: "{{key}}", search_fields: [name]}
      - {name: recipient, widget: relation, collection: people, value_field: "{{key}}", search_fields: [name]}
      - {name: date, widget: datetime}
      - {name: sentFrom, widget: relation, collection: places, value_field: "{{key}}"}
  - {name: format, widget: select, options: [ALS, APCS, Telegram, ...]}
  - {name: repository, widget: string}
  - name: contributors
    widget: list
    fields:
      - {name: role, widget: select, options: [Transcription, Annotations, Encoding]}
      - {name: name, widget: string}
  - name: peopleMentioned
    widget: relation
    collection: people
    multiple: true
    value_field: "{{key}}"
  - name: placesMentioned
    widget: relation
    collection: places
    multiple: true
  - name: worksMentioned
    widget: relation
    collection: works
    multiple: true
  - name: notes
    widget: list
    fields:
      - {name: id, widget: string}
      - {name: text, widget: markdown}
  - {name: body, widget: markdown}
```

Cross-letter references (`<rs type="letter" key="L_70011">`, found in 131/279 files) also migrate cleanly via a `relation` field pointing back into the letters collection itself.

**Prerequisite:** Sveltia's `relation` widget "cannot create new related entries directly from the UI," so `people`/`places`/`works` collections must be pre-populated by extracting every distinct `@key` from the corpus before editors can use these fields.

## 4. What does not migrate cleanly — verified against JJletters' own deployed ODD

Two separate pieces of ground truth were used here, and it matters which is which:

- **JJletters' actual, deployed ODD** — fetched directly from their instance at `/exist/rest/db/apps/jjletters/resources/odd/JJletters.odd` (same REST mechanism used to fetch the letters). This tells us exactly what the *live site* renders today.
- **TEI Publisher's generic built-in XML→Markdown export function** (`dapi:markdown` → `markdown-functions.xql`, in `tei-publisher-lib`) — the framework authors' own sanctioned degradation path. This is a *hypothetical* reference for how you might design your own Sveltia converter — it isn't running on the live site, and several JJletters customizations (see the `<note>` row below) mean it wouldn't even work correctly here without modification.

| Apparatus | Live site behavior (confirmed from JJletters' own ODD) | Generic TEI Publisher Markdown export behavior | Corpus prevalence | Verdict |
|---|---|---|---|---|
| `<hi rend="bold">` | `font-weight: 800` — visible | `**text**` | — | Portable |
| `<hi rend="italic">` | `font-style: italic` — visible | `_text_` | 145 occurrences | Portable |
| `<hi rend="strike-through">` | `text-decoration: line-through` — visible | Falls back to raw `<del>` HTML-in-Markdown | 8 occurrences | Portable, not pure Markdown |
| `<hi rend="underline">` | **Confirmed visible** — explicit `text-decoration: underline;` rule in their ODD | **No case in the generic transform — silently dropped, no fallback** | **585 occurrences — most common rendition value in the corpus** | Visible today; **would be lost if a Markdown converter is built the same way TEI Publisher's own is** |
| `<hi rend="superscript">` | `vertical-align: super; font-size: 0.8em` — visible | No case in the generic transform | 68 occurrences | Same as underline: visible now, no plain-Markdown equivalent |
| `<choice><sic>/<corr></choice>` | Custom `behaviour="jjl-alt"` widget — a bespoke component labeling both readings "sic" / "for", built specifically for this project | Generic exporter keeps only the default (`corr`) reading, discards the alternate entirely | 78 files (28%), listed in [choice_toggle_files.txt](choice_toggle_files.txt) | **Confirmed loss if migrated** — and it's a real custom feature, not a generic default, so the loss is more deliberate-feeling than "Markdown just can't do this" |
| `<gap>` with `@reason` | Custom `behaviour="jjl-edit-gap"` widget | Generic bracket-text fallback (`[...]`) | 18 files | More sophisticated live behavior than a plain Markdown convention can replicate exactly, though a bracket-text fallback is a reasonable approximation |
| `rend="printed"` | Custom `behaviour="jjl-alt-printed"` — shows two labeled variants ("orig"/"writing") on ordinary letters, but is **entirely omitted** when the letter's format is a Telegram | No equivalent | 47 occurrences | Context-dependent custom behavior — not a simple style, harder to replicate than the table below suggested |
| `<seg type="note-anchor">` + `<note type="commentary">` | Custom `behaviour="jj-note"`/`"jj-note-global"` — highlighted anchor span, resolves via the sidebar Notes tab | Generic exporter produces `[^id]` + footnote block, **but only for the unmodified `note` behavior** — JJletters overrode it, so the generic exporter would likely fail to map `jj-note`/`jj-note-global` if actually run against this content | ~231/279 files | The `[^n]` footnote convention is still the right *design* for a Sveltia body field, but it's logic your own conversion script has to implement — not something inherited for free from the framework |
| `persName`/`rs` with resolvable `@key` | Builds the "People" tab | `[text](uri)` Markdown link | 279/279 files | Portable, **only if the key resolves** |
| `<unclear>` (standalone) | Custom handling (`jjl-edit-reason`/`jjl-alt`) is **commented out (dead code)** in their own ODD — falls through to plain inline, no visual treatment | No special handling | 5 files | Confirmed: already plain text on-site — nothing lost |
| `<foreign xml:lang="...">` | `<model behaviour="inline"/>` — explicitly no styling in their own ODD | No Markdown equivalent | 86 occurrences / 45 files | Confirmed: already invisible on-site — safe to drop |
| `encodingDesc/projectDesc` | Not shown per-letter | — | 279/279 files, **byte-for-byte identical boilerplate** | Fully prunable |
| `profileDesc/langUsage` | Not shown anywhere found | — | Inconsistent/dirty values across corpus (`eng`, `Eng`, `ENG`, `English`, `undefined`, unfilled placeholder) | Safe to drop or fix separately |
| `profileDesc/correspDesc` | Not on the letter page, but **does** drive the correspondence table's date/format/recipient columns and facets | — | 279/279 files | Not redundant with body `dateline` (regularized date differs from the letter's own wording) — needed if replicating the browse/sort table |

### Headline findings
1. **Zero of 279 letters convert with full fidelity.** Every file carries authority-keyed entity mentions (`persName`/`placeName`/`rs @key`) that have no native Markdown/YAML equivalent.
2. **`rend="underline"` (585 occurrences) and `choice/sic/corr` (78 files) are both genuinely visible, functioning features on the live site today** — confirmed from JJletters' own deployed ODD, not inferred. They would be the two biggest visible regressions in a Markdown-based migration. `L_68643.xml` (25 choice instances), `L_71291.xml` (19), `L_71710.xml` (14), and `L_71603.xml` (13) carry the heaviest apparatus.
3. **The footnote convention (`[^n]`) for notes and Markdown links for entity mentions are the right design**, consistent with how TEI Publisher's own generic exporter handles unmodified TEI — but JJletters' notes use custom behaviors, so this logic has to be built into your own conversion script rather than reused from the framework.
4. **`unclear` and `foreign` cost less than expected** — confirmed via their own ODD to already be visually inert on the live site (one has its custom handling commented out as dead code), so migrating them away isn't a visible regression.
5. **`ID_MISSING` placeholder keys (1,849 occurrences across 119/279 files, 43% of the corpus)** block the entity-linking plan for nearly half the letters — Sveltia's `relation` widget requires a resolvable target entry; TEI tolerates a dangling reference, Sveltia does not.
6. **143/279 files (51%)** have no textual-critical apparatus at all (no choice/sic/corr/gap/unclear/supplied/table) — the cleanest subset for a single, judgment-free conversion script.
7. **`rend="printed"` and the note apparatus are more custom-built than generic TEI Publisher behavior** — both use bespoke `jjl-*`/`jj-note*` widgets specific to this project, meaning their current interactive behavior (telegram-aware omission, dual-reading display) has no off-the-shelf equivalent in either Markdown or TEI Publisher's own default tooling.

## 5. Recommendation

- Use `object` + `relation` fields for header metadata (sender/recipient/date/format/repository/contributors) — this is a genuine improvement over the source, since `relation` gives structured, filterable links where TEI just had string keys.
- Represent annotation notes as a `list` of `{id, text}` objects, referenced from the body via `[^id]` footnote markers — matches TEI Publisher's own convention.
- Convert entity mentions with a resolvable key to Markdown links; leave `ID_MISSING` mentions as plain text (119 files affected) until the authority list is completed.
- Accept as losses: `rend="underline"`, the `sic`/`abbr`/`orig` alternate reading in `choice`, and physical-layout fidelity (`<lb/>`, superscript, etc.) — log every dropped instance during conversion so nothing disappears silently.
- Keep the original TEI XML as the archival source of truth; treat the Sveltia/Markdown copy as a simplified reading/editing layer, not a replacement.

## 6. POC build and the canonical People register

A working POC was built (Eleventy + Pagefind + Sveltia config in the project root; see `scripts/convert.py`). While wiring up the `people` collection it became clear the site has a proper canonical data source beyond the thin `@key`+display-name stubs scraped from inline letter mentions: the **"List of People Mentioned" register** at `/exist/apps/jjletters/people` — 202 fully server-rendered biography records (name, VIAF/OCLC ids, birth/death dates, gender, and a prose bio), each fetchable individually via the same `api/document/{key}.xml` endpoint used for letters.

- Fetched via `fetch_people.sh` → `xml/people/*.xml` (202/202 succeeded)
- Parsed by `convert_person()` in `scripts/convert.py`, reusing the same `render_inline`/`render_block` logic as letters (so entity links and the same apparatus-loss logging apply consistently)
- **202 registered vs. 258 keys scraped from the 279-letter sample**: only 140 keys overlap. 118 keys mentioned inline in letters have no register entry (kept as name-only stubs); 62 register entries (including people with full biographies) aren't mentioned in this particular 279-letter sample at all — logged as `person-not-in-register` in `scripts/conversion_report.csv`.
- James Joyce himself (`joyc82`) is **not** in the register — sensible, since it's a register of people *mentioned*, not the letter-writer — so his stub stays name-only by design, not by omission.
- `admin/config.yml`'s `people` collection now includes `viaf`, `oclc`, `birthDate`, `deathDate`, `gender` as optional fields to match the real data shape.

## 7. No equivalent register for places or works; two front-matter documents worth keeping

Checked whether **places** or **works** have a canonical register the way people does: `/exist/apps/jjletters/places` and `/exist/apps/jjletters/works` both 500 (no such template exists on the site) — confirmed there's nothing beyond what's already scraped from inline `placeName`/`rs[@type=work]` mentions. `/exist/apps/jjletters/repositories` does exist (200), but it's a flat, server-rendered list of 15 distinct institution name strings, not individual records — already fully captured by the per-letter `repository` string field, nothing new to extract.

Two front-matter documents (`FM_03` "Editorial Procedures", `FM_05` "Abbreviations Used") did turn out to be worth fetching, saved to `xml/frontmatter/`:

- **FM_05** is a cleanly structured TEI `<table>` (not prose) defining the controlled vocabularies for `format` and `categoryOfCorrespondence`, plus a bibliography of citation abbreviations (`LI`, `JJ`, `Pound/Joyce`, etc.) used throughout the commentary notes. Cross-checked its correspondence-category list against all 279 letters directly (not just the document's prose) to build the final option sets now in `admin/config.yml`.
- **FM_03 confirms two things independently of the ODD analysis in §4**: the "for" label on the site's custom `choice`/`sic`/`corr` widget is literally the editors' own documented term ("a corrected spelling is provided in a box under the designation 'for'"), and underline is a deliberate, meaningful transcription choice ("render[s] Joyce's underscoring as underscores, not as italics") — reinforcing that flattening `rend="underline"` in a Markdown conversion is a real edit to editorial meaning, not just a missing decoration.

**Bug found and fixed in the process:** cross-referencing FM_05 surfaced that `note[@type="coc_abbr"]` — a second, more granular format field present in the source (`ALS`, `APCS`, `TLS`, etc., separate from the broad `note[@type="format"]` category) — was being silently dropped by `convert.py`, not converted *and* not logged. Fixed; now captured as `categoryOfCorrespondence`, confirmed against the full corpus: `ALS` (115), `APCS` (75), `Telegram` (23), `APCI` (19), `TL` (18), `AL` (8), `TLS` (7), `ALI` (5), `ACS` (3), `ANI`/`APC`/`ANS`/`ACI`/`TCL` (1 each).
