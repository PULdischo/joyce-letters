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

*(Illustrative schema from early in the investigation — good for showing what `object`/`relation`/`list` composition is capable of, but `admin/config.yml` is the actual, current schema and has since diverged in specifics: `notes` ended up embedded in the body as `[^n]` footnotes rather than a separate list field (§5), `format`'s real options are `[Card, Letter, Note, Pneumatique, Postcard, Telegram]` confirmed against the full corpus rather than the placeholder `[ALS, APCS, Telegram, ...]` shown here — `categoryOfCorrespondence` is the separate field that actually holds the ALS/APCS-style codes (§7) — and contributor `role` is a plain string, not `select`, since its vocabulary hadn't been corpus-checked at config-writing time. Read this section for the concepts, `admin/config.yml` for what's real.)*

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
| `<hi rend="underline">` | **Confirmed visible** — explicit `text-decoration: underline;` rule in their ODD | **No case in the generic transform — silently dropped, no fallback** | **585 occurrences — most common rendition value in the corpus** | **Implemented, not lost** — kept via raw `<u>` HTML passthrough in `convert.py`/`eleventy.config.js` (confirmed rendering correctly on our built site). Round-trip safety inside Sveltia's `rich_text` editor is unconfirmed either way — see §8 — and source-code review (§9) confirms underline can never be added as a Sveltia toolbar button, so raw-mode editing is the only mitigation, not a temporary gap |
| `<hi rend="superscript">` | `vertical-align: super; font-size: 0.8em` — visible | No case in the generic transform | 68 occurrences | Same treatment and same caveat as underline: kept via `<sup>` HTML passthrough, Sveltia round-trip unconfirmed, no toolbar button exists or can be added without patching Sveltia's source |
| `<choice><sic>/<corr></choice>` | Custom `behaviour="jjl-alt"` widget — a bespoke component labeling both readings "sic" / "for", built specifically for this project | Generic exporter keeps only the default (`corr`) reading, discards the alternate entirely | 78 files (28%), listed in [choice_toggle_files.txt](choice_toggle_files.txt) | **Recovered, not lost** — `convert.py` now renders the discarded reading as visible strikethrough before the kept one (`~~Gioacchino~~ Gioachino`), using only GFM strikethrough, a *confirmed* Sveltia toolbar button (§9). Still short of the live site's labeled "sic"/"for" interactive widget, and it's a flatter presentation than the original — but both readings are visible on the built site now, where before this fix neither the assessment nor the conversion preserved the alternate at all |
| `<gap>` with `@reason` | Custom `behaviour="jjl-edit-gap"` widget | Generic bracket-text fallback (`[...]`) | 18 files | More sophisticated live behavior than a plain Markdown convention can replicate exactly; `convert.py` uses the bracket-text fallback (`[reason extent unit]`), a reasonable approximation |
| `rend="printed"` | Custom `behaviour="jjl-alt-printed"` — shows two labeled variants ("orig"/"writing") on ordinary letters, but is **entirely omitted** when the letter's format is a Telegram | No equivalent | 47 occurrences | Context-dependent custom behavior, not implemented in `convert.py` — confirmed as a known simplification when the Telegram sample (`L_71617.md`) was converted; the omission logic specifically was never built |
| `<seg type="note-anchor">` + `<note type="commentary">` | Custom `behaviour="jj-note"`/`"jj-note-global"` — highlighted anchor span, resolves via the sidebar Notes tab | Generic exporter produces `[^id]` + footnote block, **but only for the unmodified `note` behavior** — JJletters overrode it, so the generic exporter would likely fail to map `jj-note`/`jj-note-global` if actually run against this content | ~231/279 files | **Implemented**: `convert.py` produces `[^n]`/`[^n]: text`, and `eleventy.config.js` now runs `markdown-it-footnote` so it renders as real superscript-linked footnotes on the built site (this needed adding — CommonMark/markdown-it-core has no native footnote syntax, and `[^n]` rendered as literal bracket text before the fix). Sveltia round-trip safety is unconfirmed, same as underline — see §8 |
| `persName`/`rs` with resolvable `@key` | Builds the "People" tab | `[text](uri)` Markdown link | 279/279 files | Portable, **only if the key resolves** |
| `<unclear>` (standalone) | Custom handling (`jjl-edit-reason`/`jjl-alt`) is **commented out (dead code)** in their own ODD — falls through to plain inline, no visual treatment | No special handling | 5 files | Confirmed: already plain text on-site — nothing lost |
| `<foreign xml:lang="...">` | `<model behaviour="inline"/>` — explicitly no styling in their own ODD | No Markdown equivalent | 86 occurrences / 45 files | Confirmed: already invisible on-site — safe to drop |
| `encodingDesc/projectDesc` | Not shown per-letter | — | 279/279 files, **byte-for-byte identical boilerplate** | Fully prunable |
| `profileDesc/langUsage` | Not shown anywhere found | — | Inconsistent/dirty values across corpus (`eng`, `Eng`, `ENG`, `English`, `undefined`, unfilled placeholder) | Safe to drop or fix separately |
| `profileDesc/correspDesc` | Not on the letter page, but **does** drive the correspondence table's date/format/recipient columns and facets | — | 279/279 files | Not redundant with body `dateline` (regularized date differs from the letter's own wording) — needed if replicating the browse/sort table |

### Headline findings

*(Updated after the POC build in §6–§9 — items 2 and 3 below describe the built state, not the original migration-only analysis; superseded language struck through rather than deleted, so the reasoning trail stays visible.)*

1. **Zero of 279 letters convert with full fidelity.** Every file carries authority-keyed entity mentions (`persName`/`placeName`/`rs @key`) that have no native Markdown/YAML equivalent.
2. **`rend="underline"` (585 occurrences) and `choice/sic/corr` (78 files) are both genuinely visible, functioning features on the live site today** — confirmed from JJletters' own deployed ODD, not inferred. ~~They would be the two biggest visible regressions in a Markdown-based migration.~~ **Both are now implemented in the POC** — underline via HTML passthrough, `choice`/`sic` as visible strikethrough (§8) — though underline's survival inside Sveltia's own editor remains unconfirmed (§9). `L_68643.xml` (25 choice instances), `L_71291.xml` (19), `L_71710.xml` (14), and `L_71603.xml` (13) carry the heaviest apparatus.
3. **The footnote convention (`[^n]`) for notes and Markdown links for entity mentions are the right design** — ~~consistent with how TEI Publisher's own generic exporter handles unmodified TEI~~ **now implemented and rendering correctly** (`markdown-it-footnote` was needed; `[^n]` has no native CommonMark support and rendered as literal text before that fix, §8) — but JJletters' notes use custom behaviors, so this logic had to be built into the conversion script rather than reused from the framework.
4. **`unclear` and `foreign` cost less than expected** — confirmed via their own ODD to already be visually inert on the live site (one has its custom handling commented out as dead code), so migrating them away isn't a visible regression.
5. **`ID_MISSING` placeholder keys (1,849 occurrences across 119/279 files, 43% of the corpus)** block the entity-linking plan for nearly half the letters — Sveltia's `relation` widget requires a resolvable target entry; TEI tolerates a dangling reference, Sveltia does not.
6. **143/279 files (51%)** have no textual-critical apparatus at all (no choice/sic/corr/gap/unclear/supplied/table) — the cleanest subset for a single, judgment-free conversion script.
7. **`rend="printed"` and the note apparatus are more custom-built than generic TEI Publisher behavior** — both use bespoke `jjl-*`/`jj-note*` widgets specific to this project. The note apparatus was reimplemented independently in the POC (item 3); the telegram-aware `printed` omission logic was not (still an open gap, see the table above).
8. **Sveltia's toolbar button set is closed, not extensible via config** — confirmed by reading Sveltia's own source (`BUTTON_NAME_MAP` in `src/lib/services/contents/fields/rich-text/index.js`, §9), not inferred from docs. `underline` cannot be added as a button short of patching Sveltia itself; raw-mode editing (documented by the maintainer as the sanctioned fallback) is the only mitigation available at the config level.

## 5. Recommendation

*(As originally written, before the POC in §6–§9 existed. Left in place as the reasoning trail; where the POC's actual implementation diverged, that's noted inline rather than silently edited away.)*

- Use `object` + `relation` fields for header metadata (sender/recipient/date/format/repository/contributors) — this is a genuine improvement over the source, since `relation` gives structured, filterable links where TEI just had string keys. **Implemented as planned** — see `admin/config.yml`.
- ~~Represent annotation notes as a `list` of `{id, text}` objects, referenced from the body via `[^id]` footnote markers.~~ **Built differently**: notes are embedded directly in the body as standard `[^n]`/`[^n]: text` Markdown footnotes, not as a separate structured list field — simpler for editors than keeping a marker and a separate list in sync by hand, at the cost of notes not being independently queryable. See the comment above the `letters.body` field in `admin/config.yml` for the full rationale.
- Convert entity mentions with a resolvable key to Markdown links; leave `ID_MISSING` mentions as plain text (119 files affected) until the authority list is completed. **Implemented as planned.**
- ~~Accept as losses: `rend="underline"`, the `sic`/`abbr`/`orig` alternate reading in `choice`, and physical-layout fidelity.~~ **Both recovered instead of accepted as losses** (§8): underline via HTML passthrough, the `choice`/`sic` alternate as visible strikethrough. What's actually still an accepted loss: physical-layout fidelity (`<lb/>`), and the `rend="printed"` telegram-omission behavior (table in §4). Whatever is dropped or uncertain should still be logged during conversion so nothing disappears silently — `scripts/conversion_report.csv` does this (2,561 rows as of the last run).
- Keep the original TEI XML as the archival source of truth; treat the Sveltia/Markdown copy as a simplified reading/editing layer, not a replacement. **Unchanged** — still the right framing; see §9 for why Sveltia's own extensibility limits reinforce this rather than removing the need for it.

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

## 8. Markdown extensions: what's safe given Sveltia's own round-trip constraints

Two rendering pipelines consume the same `.md` files independently — Eleventy's build (our own `markdown-it` instance) and Sveltia's RichText editor (Lexical-based, `[rich_text, raw]` mode toggle) — and they don't necessarily agree on what syntax is safe, since Sveltia's docs only confirm `bold, italic, strikethrough, code, link, headings, lists, blockquote` as toolbar buttons (i.e., syntax with a documented Lexical↔Markdown transformer). Raw HTML passthrough and footnote syntax are undocumented either way. Per the Sveltia maintainer directly, in [discussion #560](https://github.com/sveltia/sveltia-cms/discussions/560): *"Perhaps you have to switch to raw Markdown mode to edit the content"* — the sanctioned fallback for anything outside that confirmed set, not something invented for this project. [Discussion #339](https://github.com/sveltia/sveltia-cms/discussions/339) confirms this extensibility (custom inline components) is still pre-1.0/actively evolving.

Given that, two changes were made:

- **Added `markdown-it-footnote`** to the Eleventy build. This fixed a real, confirmed bug — `[^1]` was rendering as literal bracket text, not a footnote, since CommonMark/markdown-it-core has no native footnote syntax. Deliberately *not* switching to an alternative like `markdown-it-ins`/`-sup`/`-mark`/`-attrs` for the underline/superscript apparatus: they add no rendering capability we don't already have via raw HTML passthrough, and their custom syntax is exactly as unconfirmed against Sveltia's Lexical parser as raw HTML is — swapping doesn't reduce risk.
- **Recovered the `choice`/`sic` alternate reading as visible strikethrough** (`~~Gioacchino~~ Gioachino`) instead of an invisible HTML comment — previously listed in §4 as a confirmed total loss. This is the one apparatus fix made without gambling on unconfirmed syntax: GFM strikethrough is both a markdown-it core feature and a confirmed Sveltia toolbar button. `admin/config.yml`'s `letters.body` field documents this distinction directly and keeps `modes: [rich_text, raw]` explicit, so editors touching underline/superscript/footnotes know to use the raw-mode toggle for that edit specifically.

This doesn't resolve the underline/footnote uncertainty — it just stops it from being silent. Confirming whether raw HTML and `[^n]` actually survive a save-and-reopen cycle in Sveltia's `rich_text` mode needs a real Chromium browser session (same open item flagged when the POC was first built) rather than further doc research.

## 9. Sveltia's toolbar button set is closed — confirmed from source, not docs

§8 left open whether underline could simply be added to the RichText toolbar the way a CKEditor plugin might add one. It can't, and this is now source-verified rather than inferred from documentation gaps: cloned `github.com/sveltia/sveltia-cms` directly and read `src/lib/services/contents/fields/rich-text/index.js`.

Two fixed exports govern the `buttons` config option entirely:

```js
export const DEFAULT_BUTTONS = [
  'bold', 'italic', 'strikethrough', 'code', 'link',
  'heading-one', 'heading-two', 'heading-three', 'heading-four', 'heading-five', 'heading-six',
  'bulleted-list', 'numbered-list', 'quote',
];

export const BUTTON_NAME_MAP = {
  bold: 'bold', italic: 'italic', strikethrough: 'strikethrough', code: 'code', link: 'link',
  'heading-one': 'heading-1', /* ...through heading-six */
  'bulleted-list': 'bulleted-list', 'numbered-list': 'numbered-list', quote: 'blockquote',
  'code-block': 'code-block',
};
```

`underline` does not appear in either list, or anywhere else in the repository (a full-repo grep for "underline" returned zero matches). This isn't an undocumented-but-possibly-supported gap — it's genuinely absent from the implementation. The editor itself is Lexical (`lexical` + `@sveltia/ui` in `package.json`, not CKEditor as originally guessed when this question came up), and Lexical's own core *does* have a built-in `underline` text-format type — but Sveltia never wired it to a toolbar button or a Markdown serialization choice, which is the part that would actually matter for round-tripping through `.md` files.

**Practical consequence:** `buttons:` in `admin/config.yml` can only reorder or hide the 14 button types above — it is not an open extensibility point. Adding underline support would mean patching or forking Sveltia CMS itself (new Lexical node registration, new button, and a decision about which Markdown syntax represents it on save — the same "no CommonMark syntax exists" problem from §4, just moved into Sveltia's codebase instead of ours). That's a materially larger undertaking than "a small editor config change," confirming raw-mode editing (§8) as the only mitigation actually available without taking on upstream development work. If this matters enough to pursue, the concrete next step is a feature request against `sveltia/sveltia-cms` — this exact gap doesn't yet have an open discussion or issue as of this check.

## 10. Leaning into raw mode changes the calculus — reconsidering §8/§9 from that angle

§8 and §9 both treat Sveltia's `rich_text` mode as the primary editing surface and raw mode as an escape hatch editors are expected to remember to reach for on the apparatus-heavy parts. It's worth asking the reverse question directly, since Sveltia supports it as a first-class config, not a workaround: **what if raw mode is the default, not the exception?**

**What raw mode actually removes.** It's a plain source textarea — there's no Lexical parse-then-reserialize step, so whatever the editor types is what gets saved. This means the entire "is this syntax a confirmed Sveltia toolbar button" question from §8/§9 stops applying *during editing*: `<u>`, `[^n]`, custom shortcodes, anything — none of it is at risk of being silently stripped, escaped, or reformatted, because nothing is parsing it into an internal document model in the first place. Confirmed as configurable and defaulting correctly: `modes: [raw, rich_text]` loads raw mode first (order determines default, per Sveltia's own docs), while still leaving `rich_text` reachable via the mode toggle for editors who prefer it. This is inference from what "raw/source mode" means architecturally plus the maintainer's own framing of it as the sanctioned fallback (§8) — the docs don't explicitly confirm byte-for-byte save behavior, so this is still worth a live check, not a certainty upgraded from the rest of this document's evidence bar.

**One thing raw mode does *not* change: the published site.** Eleventy's `markdown-it` pipeline renders the final HTML regardless of which mode an editor used to write it — raw-mode-primary is purely an editing-safety and ergonomics decision, orthogonal to rendering. Worth being explicit about this, since it's easy to conflate "safe to edit" with "renders well" in a two-pipeline setup like this one.

**What becomes worth reconsidering, given that:**

- The §8 argument against `markdown-it-ins`/`-sup`/`-mark` ("switching doesn't reduce risk, since neither raw HTML nor plugin syntax is confirmed safe in `rich_text` mode") only holds *if* `rich_text` is where editing actually happens. If raw is default, the deciding factor flips from *round-trip safety* (a wash between the two) to *plain-text editing ergonomics* (not a wash at all) — `text^sup^` or a lightweight underline convention is easier to type, read, and diff by hand in a bare textarea than `<sup>text</sup>`/`<u>text</u>`. This wasn't reconsidered when §8 was written because rich_text-primary was the implicit frame at the time.
- The `choice`/`sic` strikethrough recovery (§8) doesn't have to stay flat. With no round-trip constraint, a custom markdown-it rule of our own — not necessarily an off-the-shelf plugin — could render something closer to the live site's actual labeled "sic"/"for" widget (§4, §7's FM_03 citation), while still being plain, hand-typable text in raw mode. Not built in this POC; flagged here as the concrete next step this reframing opens up, not a limitation of the reframing itself.
- `[^n]` footnotes need no reconsideration — already a well-established, easily hand-typed convention independent of any of this; raw-mode-primary just removes the last shred of doubt about it.

**What it costs.** Non-technical editors lose the toolbar for the large fraction of a typical letter that's just plain prose (bold/italic/links — all confirmed-safe in `rich_text`, per §9's button map) — a real approachability cost for editors who'd otherwise never need raw mode at all. There's also no live visual feedback in raw mode the way a WYSIWYG gives it — a mistyped `[^3]` or an unbalanced `~~` won't visually flag itself. (Though note this "protection" from `rich_text` mode was never confirmed to exist in the first place — per §8/§9, Sveltia's documented transformer support doesn't cover footnotes or raw HTML either way, so this isn't a loss relative to a confirmed-safe alternative, just relative to a hoped-for one.)

**Recommendation, given the corpus:** footnotes appear in ~231/279 letters (83%) and `underline` is the single most common `rend` value in the corpus (585 occurrences) — meaning a large share of real editing sessions on `letters.body` would touch raw-mode-only apparatus at some point regardless. That tips the balance toward `modes: [raw, rich_text]` (raw-default, `rich_text` still reachable) for `letters.body` specifically, rather than leaving `rich_text` as the default and hoping editors remember to switch. `people`/`places`/`works` `body` fields are lower-apparatus, mostly-prose biography/description text — no change recommended there; `rich_text`-default stays the more approachable choice for that lower-risk content.

## 11. The road not taken: render TEI XML directly to HTML via Eleventy, skip Markdown entirely

Everything above assumes the pipeline is TEI XML → Markdown/YAML (lossy, one-time conversion) → Eleventy → HTML, with Sveltia editing the Markdown/YAML in the middle. It's worth asking directly whether skipping the middle stage — have Eleventy read the TEI XML itself and render HTML straight from it — is simply the better architecture. Short answer: **it's a large fidelity win and a near-total loss of the Sveltia editing story**, and which one matters more depends on a question this whole document has implicitly answered one way (make the letters *editable*) without ever testing the alternative (make them *faithfully published*, editing being rare or out of scope). Worth stating plainly rather than assuming.

### How it would actually work

Eleventy has no built-in TEI/XML template type, but it's genuinely extensible to one — this isn't a workaround, it's a documented mechanism:

- **`eleventyConfig.addExtension("xml", { compile: ... })`** — registers `.xml` as a template type Eleventy processes directly, similar to how it already handles `.md`/`.njk` here. The compile function gets the raw XML and returns a render function producing HTML.
- **Or `.11ty.js` template files** — the more idiomatic fit for this specific shape of problem: one template (a `letter.11ty.js` class/function with `data()` and `render(data)`) applied via pagination across a *data* collection of parsed XML documents, structurally the same pattern already used here for the Markdown collections, just with parsed XML objects as the data source instead of frontmatter + Markdown body.
- **XSLT specifically** — TEI→HTML is XSLT's home turf, and it's what TEI Publisher itself effectively does (its ODD compiles to transform rules, §1). A Node XSLT processor (e.g. `xslt-processor`, or `saxon-js` for fuller XSLT 3.0 support) could run inside either of the above, potentially informed by or adapted from patterns in standard TEI stylesheet toolchains. More portable (any XSLT engine could reuse the transform outside Eleventy) and more idiomatic to how TEI practitioners usually solve this problem — at the cost of adding XSLT as a second language/skillset the team needs, rather than staying in JS end-to-end.

### Fidelity: recovers nearly everything §4 lists as lost or approximated

This is the real payoff. Every apparatus row in §4's table that Markdown genuinely can't represent stops being a constraint, because there's no Markdown in the pipeline to be constrained by:

- `rend="underline"`/`"superscript"` — a `<span>` with the exact CSS, no HTML-passthrough workaround needed, no Sveltia round-trip question to even ask (§8, §9 become moot for this content).
- `choice`/`sic`/`corr` — could reproduce something close to the live site's actual labeled "sic"/"for" interactive widget (§4, FM_03 in §7), not the flattened `~~sic~~ corr` strikethrough approximation built in §8. Full fidelity, not recovery-by-approximation.
- `gap`/`unclear`/`supplied` — exact semantics, including a real hover/tooltip for `@reason`, matching the site's `jjl-edit-gap` behavior instead of a bracket-text stand-in.
- `rend="printed"` telegram-omission — this is the one piece of apparatus §4 flagged as *not even attempted* in the POC (the conditional-on-format omission logic). Trivial here: it's just a conditional in the render function, checking the same `note[@type='format']` value already being parsed.
- Physical layout (`<lb/>`), footnotes (native, no `markdown-it-footnote` needed), entity links — all straightforward, and no different in difficulty from what `convert.py` already does for these.

In effect, this closes essentially every gap this document has spent ten sections documenting and mitigating.

### Editability: this is where it costs the most

Sveltia's entire content model — `object`/`relation`/`select`/`datetime`/`markdown` fields, the whole reason it was chosen (§3) — is built around parsing structured frontmatter plus a Markdown/rich-text body. It has no concept of editing arbitrary nested XML with mixed content and TEI-specific apparatus. Pointed at raw TEI, the best it could offer is a generic text/code widget showing the whole file as an unstructured blob — which is a plain-text editor with extra steps, not meaningfully different from opening the file directly, and a total regression from the relation pickers, `select` dropdowns, and structured metadata fields designed across §3–§9.

Practically: choosing this path means either abandoning Sveltia (and, likely, any general-purpose Git-based headless CMS — none of the mainstream ones are TEI-aware) in favor of whatever tooling the letters' original scholarly workflow already uses for XML editing (eXist-db itself, oXygen, or similar), or accepting that this rendering path is **read-only publishing**, with editing — if it happens at all — occurring upstream in the XML, not in this pipeline.

### Effort and maintenance

Writing a Markdown converter (`convert.py`) only has to produce a mostly-linear text stream — comparatively simple, and it shows: a few hundred lines handled the full corpus's structural variety. A presentational TEI→HTML transform with correct nesting, accessibility, and interactive components for `choice`/`gap`/`printed` is a materially bigger and more open-ended undertaking — closer in scope to reimplementing a meaningful slice of TEI Publisher's own `tei-publisher-lib` (`html-functions.xql`, `model.xql`, and JJletters' own `jjl-*`/`jj-note*` custom behaviors, §4) than to writing a converter. That's real, ongoing engineering and design work (matching every apparatus type's visual treatment, keeping it accessible, keeping it maintained as new letters are added) duplicating effort the source site has already done — just re-hosted in a different stack.

### What doesn't change

- **Pagefind** indexes whatever HTML Eleventy outputs, regardless of how it was generated — no difference either way.
- **The `peopleMentioned`/`placesMentioned`-style relation indexes** (§3) were designed as Sveltia-managed frontmatter fields a human keeps in sync. Rendering straight from XML, this indexing becomes *free* instead: an Eleventy build-time pass over the parsed XML can derive "every letter mentioning entity X" directly from the authoritative `@key` references, with no human bookkeeping and no risk of drift between the field and the actual content — arguably more robust than the Sveltia-managed version, not just a wash.

### A middle path worth naming

The two options aren't mutually exclusive across the whole project. Letters, once transcribed and annotated by TEI-fluent editors, are plausibly edited rarely — most ongoing work is more likely adding *new* letters than routine copyediting of finished ones. If that's true, optimizing the letters' body specifically for faithful, XML-direct publication (this section) while keeping Sveltia+Markdown (§3–§10) for genuinely high-churn, low-apparatus content — `people`/`places`/`works` biographies, front-matter pages, metadata corrections — is a defensible split rather than an all-or-nothing choice. It does mean maintaining two rendering pipelines instead of one, which is its own cost; not a free compromise, just a different tradeoff than picking either extreme.
