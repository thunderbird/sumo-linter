# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Compare extracted Thunderbird strings across versions, and map them to the UX sheet.

Reads every `tools/ui-strings/strings/<version>.tsv` written by extract.py and
the UX string-change sheet, and writes three tables, in GitHub Markdown and in
MediaWiki wikitext (sumo-linter #18):

1. Changed strings: every string ID whose text differs between the versions,
   or that exists in only some of them, with one column per version and the
   CSV records it matches. Rows with a CSV record come first, in record
   order, so an old ID and the new ID that replaces it sit together.
2. CSV records with no matching string ID: planned changes whose text matches
   no string in any version. The sheet paraphrases, or the string lives in a
   file outside extract.py's SCOPE.
3. CSV records that match only unchanged strings: planned changes that no
   listed version has shipped yet.

    python3 -I tools/ui-strings/compare.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv

Thunderbird usually gives a reworded string a new ID (`start-page-label`
became `show-start-page-label`), so a change shows as one ID that ends and
another that starts, not as one ID with two texts. The CSV record is what
links them.

Matching a CSV line to a string, after normalising both sides:

- The widget label (`Checkbox:`) is dropped, ` | ` splits a line into
  several widgets, and markers such as `•`, `[ … ▾ ]` and `Dropdown` go.
- "Daily", "Daily/TB" and similar in the sheet, and `{ -brand-short-name }`,
  `&brandShortName;` and `%brandShortName%` in the strings, all become
  "Thunderbird". Other Fluent terms are resolved from their definitions.
- A Fluent selector (`{ PLATFORM() -> [macos] A *[other] B }`) matches on any
  of its variants.
- Case, curly quotes, `…` against `...`, markup tags and trailing `.`, `:`
  and `…` are ignored.
- A line matches a string if the two are equal, or if one contains the other
  and the shorter has at least four words. Lines of one word are not
  matched: "Remove" or "General" would match dozens of unrelated strings.
  For the same reason, a line that matches more than MAX_HITS string IDs
  ("Learn more") is not used as evidence.
"""

import csv
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 /()-]{0,40}?:\s+(.*)$")
BRAND = re.compile(
    r"\{\s*-brand-(?:short|full|product)-name\s*\}|&brand(?:Short|Full)Name;|%brandShortName%"
)
MAX_HITS = 6  # a sheet line matching more string IDs than this is too generic

SHEET_BRAND = re.compile(r"\b(?:Daily/Thunderbird|Thunderbird/Daily|Daily/TB|TB/Daily|Daily)\b")


def unescape(v):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), v)


def vkey(path):
    return tuple(int(x) for x in re.findall(r"\d+", os.path.basename(path)))


def load_versions():
    paths = sorted(glob.glob(os.path.join(HERE, "strings", "*.tsv")), key=vkey)
    if not paths:
        sys.exit("no strings/*.tsv: run extract.py first")
    versions, data = [], {}
    for p in paths:
        v = os.path.basename(p)[: -len(".tsv")]
        versions.append(v)
        with open(p, encoding="utf-8") as f:
            for line in f:
                file, sid, value = line.rstrip("\n").split("\t", 2)
                data.setdefault((file, sid), {})[v] = unescape(value)
    return versions, data


def norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("…", "...").replace(" ", " ").replace("&amp;", "&")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.rstrip(" .:").strip()


def variants(value, terms):
    """All texts a string can show, with brand and terms resolved."""
    v = BRAND.sub("Thunderbird", value)
    v = re.sub(r"\{\s*(-[\w-]+)\s*\}", lambda m: terms.get(m.group(1), m.group(0)), v)
    m = re.search(r"\{[^{}]*->\s*\n(.*?)\n\s*\}", v, re.S)
    if not m:
        return [v]
    out = []
    for line in m.group(1).split("\n"):
        vm = re.match(r"\s*\*?\[[^\]]+\]\s*(.*)$", line)
        if vm:
            out.append(v[: m.start()] + vm.group(1) + v[m.end() :])
    return out or [v]


def display(value, terms):
    v = BRAND.sub("Thunderbird", value)
    v = re.sub(r"\{\s*(-[\w-]+)\s*\}", lambda m: terms.get(m.group(1), m.group(0)), v)
    return re.sub(r"\s*\n\s*", " ", v).strip()


def fragments(cell):
    """The UI texts in one CSV cell, normalised for matching."""
    out = []
    for line in cell.splitlines():
        for part in line.split(" | "):
            p = part.strip().lstrip("•").strip()
            for _ in range(2):
                m = LABEL.match(p)
                if m:
                    p = m.group(1).strip()
                p = re.sub(r"^(?:Dropdown|Field|Radio button|Checkbox|Button)\b\s*", "", p)
            p = p.strip("[]▾ ").strip()
            p = SHEET_BRAND.sub("Thunderbird", p)
            n = norm(p)
            if len(n.split()) >= 2:
                out.append(n)
    return out


def matches(frag, cand):
    if frag == cand:
        return True
    short, long_ = sorted((frag, cand), key=len)
    return len(short.split()) >= 4 and short in long_


def path_of(r):
    return " > ".join(
        p.strip() for p in ["Settings", r["Pane"], r["Section"], r["Setting"]] if p.strip()
    )


def build(csv_path):
    versions, data = load_versions()
    terms = {}
    for (file, sid), vals in data.items():
        if sid.startswith("-") and "." not in sid:
            terms.setdefault(sid, vals[versions[-1]] if versions[-1] in vals else next(iter(vals.values())))
    cands = {
        key: {norm(x) for val in vals.values() for x in variants(val, terms)}
        for key, vals in data.items()
    }
    changed = {
        key
        for key, vals in data.items()
        if len(vals) < len(versions) or len(set(vals.values())) > 1
    }
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    frag_hits = {}  # fragment -> keys it matches
    rec_keys = {}  # record number -> matched keys
    key_recs = {}  # key -> record numbers
    for i, r in enumerate(rows, 1):
        hit = set()
        for fr in set(fragments(r["Current content"]) + fragments(r["New content"])):
            if fr not in frag_hits:
                frag_hits[fr] = {k for k, cs in cands.items() if any(matches(fr, c) for c in cs)}
            # A generic phrase ("Learn more") matches strings all over the
            # app, so it is no evidence for any one of them.
            if len(frag_hits[fr]) <= MAX_HITS:
                hit |= frag_hits[fr]
        rec_keys[i] = hit
        for key in hit:
            key_recs.setdefault(key, []).append(i)

    def planned(r):
        new = r["New content"].strip()
        return bool(new) and new != r["Current content"].strip()

    def first_version(k):
        return min(versions.index(v) for v in data[k])

    # Within a record, the old ID comes before the ID that replaces it.
    t1 = sorted(changed, key=lambda k: (min(key_recs.get(k, [10**6])), first_version(k), k))
    t2 = [i for i, r in enumerate(rows, 1) if planned(r) and not rec_keys[i]]
    t3 = [i for i, r in enumerate(rows, 1) if planned(r) and rec_keys[i] and not rec_keys[i] & changed]
    return versions, data, terms, rows, key_recs, rec_keys, t1, t2, t3


def esc_md(s):
    return s.replace("|", "\\|").replace("<", "&lt;").replace("\n", "<br>")


def esc_wiki(s):
    s = s.replace("|", "&#124;").replace("<", "&lt;").replace("{{", "&#123;&#123;")
    s = s.replace("[", "&#91;").replace("~~~", "&#126;~~").replace("''", "&#39;'")
    return s.replace("\n", "<br />")


def cell_lines(cell):
    return "\n".join(
        x.strip() for x in cell.splitlines() if x.strip() and set(x.strip()) - set("—-–")
    )


def render(fmt, built, csv_name):
    versions, data, terms, rows, key_recs, rec_keys, t1, t2, t3 = built
    esc = esc_md if fmt == "md" else esc_wiki
    absent = "—"
    out = []

    def table(header, body):
        if fmt == "md":
            out.append("| " + " | ".join(esc(h) for h in header) + " |")
            out.append("|" + "---|" * len(header))
            for row in body:
                out.append("| " + " | ".join(esc(c) if c else " " for c in row) + " |")
        else:
            out.append('{| class="wikitable sortable"')
            out.append("! " + " !! ".join(esc(h) for h in header))
            for row in body:
                out.append("|-")
                out.append("| " + " || ".join(esc(c) for c in row))
            out.append("|}")
        out.append("")

    def heading(text):
        out.append(f"## {text}\n" if fmt == "md" else f"== {text} ==\n")

    def rec(i):
        return f"#{i} {path_of(rows[i - 1])}"

    vs = ", ".join(versions)
    out.append(
        f"Settings and Account Settings strings in Thunderbird {vs}, compared by string ID "
        f"and mapped to the records of {csv_name}. Made by tools/ui-strings/compare.py "
        "(sumo-linter #18). A record number counts CSV rows after the header, from 1.\n"
    )
    heading(f"1. Changed strings ({len(t1)})")
    out.append(
        f"Every string ID whose text differs between the versions, or that exists in only "
        f"some of them. {absent} means the ID does not exist in that version. Rows that "
        "match a CSV record come first.\n"
    )
    body = []
    for key in t1:
        recs = "\n".join(rec(i) for i in key_recs.get(key, []))
        vals = [display(data[key][v], terms) if v in data[key] else absent for v in versions]
        body.append([recs, key[1], *vals, key[0].split("/en-US/")[-1]])
    table(["CSV record", "String ID", *versions, "File"], body)

    heading(f"2. CSV records with no matching string ID ({len(t2)})")
    out.append(
        "Planned changes whose text matches no string in any version. The sheet can "
        "paraphrase, or the string can live in a file that extract.py does not read.\n"
    )
    table(
        ["CSV record", "Current content (sheet)", "New content (sheet)"],
        [[rec(i), cell_lines(rows[i - 1]["Current content"]), cell_lines(rows[i - 1]["New content"])] for i in t2],
    )

    heading(f"3. CSV records that match only unchanged strings ({len(t3)})")
    out.append(
        f"Planned changes whose strings are the same in {vs}: no listed version has "
        "shipped them yet.\n"
    )
    body = []
    for i in t3:
        keys = sorted(rec_keys[i])
        body.append(
            [
                rec(i),
                "\n".join(k[1] for k in keys),
                "\n".join(display(data[k][versions[-1]], terms) for k in keys if versions[-1] in data[k]),
                cell_lines(rows[i - 1]["New content"]),
            ]
        )
    table(["CSV record", "String ID", f"Text in {versions[-1]}", "New content (sheet)"], body)
    return "\n".join(out)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: compare.py SHEET.csv")
    built = build(sys.argv[1])
    versions = built[0]
    stem = os.path.join(HERE, "string-versions")
    name = os.path.basename(sys.argv[1])
    for fmt, ext in (("md", ".md"), ("mediawiki", ".mediawiki")):
        with open(stem + ext, "w", encoding="utf-8") as f:
            f.write(render(fmt, built, name))
    t1, t2, t3 = built[6:]
    mapped = sum(1 for k in t1 if k in built[4])
    print(
        f"{', '.join(versions)}: {len(t1)} changed strings ({mapped} mapped to a record), "
        f"{len(t2)} records with no match, {len(t3)} records not shipped yet",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
