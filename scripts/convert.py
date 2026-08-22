#!/usr/bin/env python3
"""
Convert James Joyce letters TEI XML -> Markdown + YAML frontmatter for Sveltia CMS.

POC scope: converts a sample of letter files fully, and extracts
people/places/works stub collections from the WHOLE corpus (cheap metadata
pass) so Sveltia's `relation` fields have real targets to point at.

Every apparatus feature that can't be represented in Markdown (dropped
choice/sic alternates, rend=underline, unresolved ID_MISSING entities, etc.)
is written to conversion_report.csv instead of silently disappearing.
"""
import csv
import glob
import re
import sys
from pathlib import Path

import yaml
from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI}

# recover=True: a few source files have duplicate xml:id attributes (e.g.
# L_68890.xml, "ID DVH already defined") which libxml2 treats as a hard
# error by default even without a DTD. Recovering keeps the rest of the
# document usable instead of aborting the whole corpus pass.
XML_PARSER = etree.XMLParser(recover=True)


def parse(path):
    tree = etree.parse(str(path), parser=XML_PARSER)
    return tree

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "xml"
CONTENT_DIR = ROOT / "content"
REPORT_PATH = ROOT / "scripts" / "conversion_report.csv"

SAMPLE_FILES = [
    "L_68205.xml",
    "L_68212.xml",
    "L_68643.xml",
    "L_68352.xml",
    "L_71617.xml",
    "L_68671.xml",
]


def local(tag):
    return etree.QName(tag).localname


def norm(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


class Report:
    def __init__(self):
        self.rows = []

    def log(self, file, kind, detail):
        self.rows.append({"file": file, "kind": kind, "detail": detail})

    def write(self, path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "kind", "detail"])
            w.writeheader()
            w.writerows(self.rows)


# ---------------------------------------------------------------------------
# Pass 1: entity extraction across the WHOLE corpus (people / places / works)
# ---------------------------------------------------------------------------

def extract_entities(all_files, report):
    people, places, works = {}, {}, {}
    for f in all_files:
        tree = parse(f)
        root = tree.getroot()
        for el in root.iter():
            key = el.get("key")
            if not key:
                continue
            tag = local(el.tag)
            typ = el.get("type")
            text = norm("".join(el.itertext()))
            if key == "ID_MISSING":
                report.log(f.name, "unresolved-entity-key", text[:80])
                continue
            if tag == "persName" or (tag in ("name", "rs") and typ == "person"):
                people.setdefault(key, text)
            elif tag in ("name", "rs") and typ == "geo":
                places.setdefault(key, text)
            elif tag in ("name", "rs") and typ == "work":
                works.setdefault(key, text)
            # rs type="letter" references another letter entry directly;
            # no separate collection needed, handled inline as a relation
            # to the letters collection itself.
    return people, places, works


def write_stub_collection(entries, out_dir, kind):
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, name in sorted(entries.items()):
        fm = {"key": key, "name": name}
        path = out_dir / f"{key}.md"
        path.write_text(
            "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n",
            encoding="utf-8",
        )
    print(f"  wrote {len(entries)} {kind} stub(s) -> {out_dir}")


# ---------------------------------------------------------------------------
# Pass 2: full letter conversion (sample only, for the POC)
# ---------------------------------------------------------------------------

class FootnoteCollector:
    def __init__(self):
        self.order = []  # list of xml:id in document order
        self.map = {}  # xml:id -> assigned number

    def assign(self, seg_id):
        if seg_id not in self.map:
            self.order.append(seg_id)
            self.map[seg_id] = len(self.order)
        return self.map[seg_id]


def entity_href(key, typ, people, places, works):
    if typ == "geo" or key in places:
        return f"/places/{key}/"
    if typ == "work" or key in works:
        return f"/works/{key}/"
    if typ == "letter" or key.startswith("L_"):
        return f"/letters/{key}/"
    return f"/people/{key}/"


def collapse_ws(text):
    """The source XML is pretty-printed with significant embedded newlines
    and indentation inside mixed content; HTML/CSS collapses runs of
    whitespace to a single space when rendering, so we replicate that here
    rather than reproducing the raw indentation in the Markdown output."""
    if not text:
        return text
    return re.sub(r"\s+", " ", text)


def tidy(text):
    """Final cosmetic pass: source whitespace collapsing (collapse_ws) is
    applied per text-node, so runs spanning a tag boundary (e.g. a seg's
    own leading space plus its preceding tail space) can still double up,
    and link/emphasis wrappers can retain a leading/trailing space from
    the original pretty-printed markup."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\[ +", "[", text)
    text = re.sub(r" +\]", "]", text)
    text = re.sub(r"<u> +", "<u>", text)
    text = re.sub(r" +</u>", "</u>", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    return text


def render_inline(el, fc, report, fname, people, places, works):
    parts = []
    if el.text:
        parts.append(collapse_ws(el.text))
    for child in el:
        tag = local(child.tag)
        if tag == "hi":
            rend = child.get("rend", "")
            inner = render_inline(child, fc, report, fname, people, places, works)
            if rend == "bold":
                parts.append(f"**{inner}**")
            elif rend == "italic":
                parts.append(f"_{inner}_")
            elif rend == "strike-through":
                parts.append(f"~~{inner}~~")
            elif rend == "underline":
                parts.append(f"<u>{inner}</u>")
                report.log(fname, "rend-underline (HTML passthrough, verify in Sveltia)", inner[:60])
            elif rend == "superscript":
                parts.append(f"<sup>{inner}</sup>")
                report.log(fname, "rend-superscript (HTML passthrough, verify in Sveltia)", inner[:60])
            else:
                parts.append(inner)
                if rend:
                    report.log(fname, f"rend-unhandled:{rend}", inner[:60])
        elif tag == "seg" and child.get("type") == "note-anchor":
            inner = render_inline(child, fc, report, fname, people, places, works)
            seg_id = child.get(f"{{{XML_NS}}}id")
            n = fc.assign(seg_id)
            parts.append(f"{inner}[^{n}]")
        elif tag in ("persName", "name", "rs"):
            key = child.get("key")
            typ = child.get("type")
            inner = render_inline(child, fc, report, fname, people, places, works)
            if key and key != "ID_MISSING":
                href = entity_href(key, typ, people, places, works)
                parts.append(f"[{inner}]({href})")
            else:
                parts.append(inner)
                if key == "ID_MISSING":
                    report.log(fname, "unresolved-entity-inline", inner[:60])
        elif tag == "choice":
            default_el = None
            alt_el = None
            for default_tag, alt_tag in (("corr", "sic"), ("expan", "abbr"), ("reg", "orig")):
                d = child.find(f"tei:{default_tag}", NS)
                a = child.find(f"tei:{alt_tag}", NS)
                if d is not None:
                    default_el, alt_el = d, a
                    break
            default_text = (
                render_inline(default_el, fc, report, fname, people, places, works)
                if default_el is not None
                else norm("".join(child.itertext()))
            )
            if alt_el is not None:
                # Visible instead of an invisible HTML comment: GFM
                # strikethrough is a markdown-it core feature (no plugin
                # needed) *and* a confirmed Sveltia RichText toolbar
                # button (bold/italic/strikethrough/code/link/headings/
                # lists/quote are the only documented ones), so this is
                # the one apparatus-recovery change made without gambling
                # on unconfirmed syntax surviving Sveltia's WYSIWYG
                # round-trip. Mirrors the source site's own "sic"/"for"
                # editorial convention (see FM_03 in xml/frontmatter/)
                # instead of hiding the discarded reading entirely.
                alt_text = norm("".join(alt_el.itertext()))
                parts.append(f"~~{alt_text}~~ {default_text}")
                report.log(fname, "choice-alternate-recovered-as-strikethrough", f'{alt_text!r} -> {default_text!r}')
            else:
                parts.append(default_text)
        elif tag == "gap":
            reason = child.get("reason", "")
            extent = child.get("extent") or child.get("quantity") or ""
            unit = child.get("unit", "")
            label_bits = " ".join(b for b in (reason, extent, unit) if b)
            label = f"[{label_bits}]" if label_bits else "[...]"
            parts.append(label)
            report.log(fname, "gap", label)
        elif tag == "unclear":
            # confirmed no visual distinction on the live site (dead code in
            # JJletters' own ODD) -- rendered as plain text, matching source
            parts.append(render_inline(child, fc, report, fname, people, places, works))
        elif tag == "supplied":
            inner = render_inline(child, fc, report, fname, people, places, works)
            parts.append(f"[{inner}]")
            report.log(fname, "supplied", inner[:60])
        elif tag == "foreign":
            # confirmed no visual distinction of its own on the live site
            parts.append(render_inline(child, fc, report, fname, people, places, works))
        elif tag == "lb":
            parts.append("  \n")
        else:
            parts.append(render_inline(child, fc, report, fname, people, places, works))
        if child.tail:
            parts.append(collapse_ws(child.tail))
    return "".join(parts)


# tags that are pure structural containers -- recurse into their children
# as further blocks rather than treating the container itself as a leaf
BLOCK_CONTAINER_TAGS = {"div", "ab", "opener", "closer", "postscript"}
PARAGRAPH_TAGS = {"p", "salute", "dateline", "signed"}


def render_block(el, fc, report, fname, people, places, works):
    """Render p/opener/closer/salute/dateline/address as markdown paragraphs."""
    blocks = []
    for child in el:
        tag = local(child.tag)
        if tag == "address":
            lines = []
            for addr_line in child.findall("tei:addrLine", NS):
                text = render_inline(addr_line, fc, report, fname, people, places, works).strip()
                if text:
                    lines.append(text)
            if lines:
                blocks.append("> " + "\n> ".join(lines))
        elif tag in PARAGRAPH_TAGS:
            text = render_inline(child, fc, report, fname, people, places, works).strip()
            if text:
                blocks.append(text)
        elif tag in BLOCK_CONTAINER_TAGS:
            blocks.extend(render_block(child, fc, report, fname, people, places, works))
        else:
            text = render_inline(child, fc, report, fname, people, places, works).strip()
            if text:
                blocks.append(text)
    return blocks


def extract_frontmatter(root, fname, report):
    header = root.find(".//tei:teiHeader", NS)
    title = norm(header.findtext(".//tei:titleStmt/tei:title", namespaces=NS))
    fmt = norm(header.findtext('.//tei:notesStmt/tei:note[@type="format"]', namespaces=NS))
    # note[@type="coc_abbr"] ("category of correspondence" abbreviation --
    # ALS, APCS, TLS, etc., defined in FM_05 "Abbreviations Used") is a
    # separate, more granular field from note[@type="format"] and was
    # being silently dropped entirely until this fix -- neither converted
    # nor logged. Caught by cross-referencing the source site's own
    # front-matter documentation, not by inspecting the letters alone.
    coc_abbr = norm(header.findtext('.//tei:notesStmt/tei:note[@type="coc_abbr"]', namespaces=NS))
    repo = norm(header.findtext(".//tei:sourceDesc/tei:msDesc/tei:msIdentifier/tei:repository", namespaces=NS))
    if not coc_abbr:
        report.log(fname, "missing-coc_abbr", "")

    contributors = []
    for rs in header.findall(".//tei:titleStmt/tei:respStmt", NS):
        role = norm(rs.findtext("tei:resp", namespaces=NS))
        for name in rs.findall("tei:name", NS):
            if name.text:
                contributors.append({"role": role, "name": name.text.strip()})

    def action_info(type_):
        action = header.find(f'.//tei:correspDesc/tei:correspAction[@type="{type_}"]', NS)
        if action is None:
            return None, None, None
        pers = action.find("tei:persName", NS)
        key = pers.get("key") if pers is not None else None
        name = norm("".join(pers.itertext())) if pers is not None else None
        date_el = action.find("tei:date", NS)
        date = None
        if date_el is not None:
            date = date_el.get("when") or date_el.get("notBefore")
        return key, name, date

    sender_key, sender_name, sent_date = action_info("sent")
    recipient_key, recipient_name, _ = action_info("received")

    if not sender_key:
        report.log(fname, "missing-sender-key", "")
    if not recipient_key:
        report.log(fname, "missing-recipient-key", "")

    fm = {
        "title": title,
        "correspondence": {
            "sender": sender_key or sender_name,
            "recipient": recipient_key or recipient_name,
            "date": sent_date,
        },
        "format": fmt,
        "categoryOfCorrespondence": coc_abbr,
        "repository": repo,
        "contributors": contributors,
    }
    return fm


def convert_letter(path, people, places, works, report):
    fname = path.name
    tree = parse(path)
    root = tree.getroot()

    fm = extract_frontmatter(root, fname, report)

    letter_div = root.find('.//tei:body/tei:div[@type="letter"]', NS)
    fc = FootnoteCollector()
    blocks = render_block(letter_div, fc, report, fname, people, places, works) if letter_div is not None else []
    body_md = tidy("\n\n".join(blocks))

    # global (untargeted) notes -> a frontmatter field, not a footnote
    notes_div = root.find('.//tei:body/tei:div[@type="notes"]', NS)
    global_notes = []
    footnote_lines = []
    if notes_div is not None:
        for note in notes_div.findall("tei:note", NS):
            target = note.get("target")
            note_type = note.get("type")
            text = tidy(render_inline(note, fc, report, fname, people, places, works).strip())
            if target and target.lstrip("#") in fc.map:
                n = fc.map[target.lstrip("#")]
                footnote_lines.append((n, text))
            elif note_type == "global":
                global_notes.append(text)
            else:
                # note exists but its seg-anchor was never encountered in the
                # rendered body (e.g. anchor lives outside div[@type='letter'])
                report.log(fname, "orphaned-note", text[:60])

    footnote_lines.sort(key=lambda t: t[0])
    footnote_md = "\n\n".join(f"[^{n}]: {text}" for n, text in footnote_lines)

    if global_notes:
        fm["editorialNotes"] = global_notes

    full_body = body_md
    if footnote_md:
        full_body += "\n\n---\n\n" + footnote_md

    out_dir = CONTENT_DIR / "letters"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = fname.replace(".xml", "")
    out_path = out_dir / f"{stem}.md"
    frontmatter_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    out_path.write_text(f"---\n{frontmatter_yaml}---\n\n{full_body}\n", encoding="utf-8")
    print(f"  wrote {out_path.relative_to(ROOT)}")


PEOPLE_XML_DIR = ROOT / "xml" / "people"


def convert_person(path, people, places, works, report):
    """Convert a canonical person-register record (site's 'List of People
    Mentioned') into content/people/{key}.md, overwriting the thin stub
    extracted from inline letter mentions with real biographical data."""
    key = path.stem
    tree = parse(path)
    root = tree.getroot()
    ab = root.find('.//tei:body/tei:ab', NS)

    name_full = None
    if ab is not None:
        full_el = ab.find('tei:persName[@type="full"]', NS)
        if full_el is not None:
            name_full = norm("".join(full_el.itertext()))
    if not name_full:
        name_full = norm(root.findtext(".//tei:titleStmt/tei:title", namespaces=NS)) or key
        report.log(f"{key}.xml", "person-missing-full-name", name_full)

    fm = {"key": key, "name": name_full}

    if ab is not None:
        for idno in ab.findall("tei:idno", NS):
            typ = idno.get("type")
            if typ and idno.text:
                fm[typ.lower()] = idno.text.strip()
        for date_el in ab.findall("tei:date", NS):
            typ = date_el.get("type")
            when = date_el.get("when")
            if typ and when:
                fm[f"{typ}Date"] = when
        gender = ab.findtext('tei:note[@type="gender"]', namespaces=NS)
        if gender:
            fm["gender"] = gender.strip()

    bio_div = root.find('.//tei:div[@type="bio"]', NS)
    fc = FootnoteCollector()  # unused here (no note-anchor apparatus in
                              # person records observed), reused only so
                              # render_inline's signature stays uniform
    body = ""
    if bio_div is not None:
        blocks = render_block(bio_div, fc, report, f"{key}.xml", people, places, works)
        body = tidy("\n\n".join(blocks))
    else:
        report.log(f"{key}.xml", "person-missing-bio", "")

    out_path = CONTENT_DIR / "people" / f"{key}.md"
    frontmatter_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    out_path.write_text(f"---\n{frontmatter_yaml}---\n\n{body}\n", encoding="utf-8")


def main():
    all_files = sorted(XML_DIR.glob("*.xml"))
    report = Report()

    print(f"Pass 1: extracting entities from all {len(all_files)} letters...")
    people, places, works = extract_entities(all_files, report)
    write_stub_collection(people, CONTENT_DIR / "people", "people")
    write_stub_collection(places, CONTENT_DIR / "places", "places")
    write_stub_collection(works, CONTENT_DIR / "works", "works")

    print(f"Pass 2: converting {len(SAMPLE_FILES)} sample letters...")
    for name in SAMPLE_FILES:
        convert_letter(XML_DIR / name, people, places, works, report)

    person_files = sorted(PEOPLE_XML_DIR.glob("*.xml")) if PEOPLE_XML_DIR.exists() else []
    if person_files:
        print(f"Pass 3: converting {len(person_files)} canonical person records...")
        register_keys = set()
        for p in person_files:
            convert_person(p, people, places, works, report)
            register_keys.add(p.stem)
        # keys mentioned inline in letters but with no dedicated register
        # entry on the site -- their thin (name-only) stub from pass 1
        # stands as-is; flagged here so it's a visible, reviewable gap
        # rather than a silent difference between the two sources.
        unregistered = set(people) - register_keys
        for k in sorted(unregistered):
            report.log("(corpus-wide)", "person-not-in-register", f"{k} -> {people[k]!r}")
        print(f"  {len(register_keys)} in canonical register, "
              f"{len(unregistered)} mentioned in letters but not registered "
              f"(kept as name-only stubs)")

    report.write(REPORT_PATH)
    print(f"\nConversion report: {len(report.rows)} logged items -> {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
