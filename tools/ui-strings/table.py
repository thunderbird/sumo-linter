# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write an old-string/new-string table from a UX string-change sheet.

One table row per CSV record that changes, with three columns: the click
path, the old strings and the new strings. Output is GitHub Markdown or
MediaWiki wikitext (for wiki.mozilla.org).

    python3 -I tools/ui-strings/table.py SHEET.csv --records 1-225 \
        --format md > settings-158.md
    python3 -I tools/ui-strings/table.py SHEET.csv --records 1-225 \
        --format mediawiki > settings-158.mediawiki

Each cell lists only the lines that differ between "Current content" and
"New content", and keeps the widget label (`Checkbox:`, `Title:`). The lines
are not paired one to one: in 25 of the 110 changed Settings records, the new
content adds, drops or reorders lines, so a pairing would be a guess. A
record with an empty "New content" is unchanged and is left out.

The click path is "Settings > Pane > Section > Setting", from the sheet's
columns. The last step names the setting. It is not always a menu item.
"""

import argparse
import csv
import re
import sys


def lines(cell):
    return [x.strip() for x in cell.splitlines() if x.strip() and set(x.strip()) - set("—-–")]


def changed_rows(rows):
    for r in rows:
        if not r["New content"].strip():
            continue
        old, new = lines(r["Current content"]), lines(r["New content"])
        o = [x for x in old if x not in new]
        n = [x for x in new if x not in old]
        if not o and not n:
            continue
        path = " > ".join(
            p.strip() for p in ["Settings", r["Pane"], r["Section"], r["Setting"]] if p.strip()
        )
        yield path, o, n


def md_cell(items):
    if not items:
        return "*(none)*"
    return "<br>".join(x.replace("|", "\\|").replace("<", "&lt;") for x in items)


def wiki_cell(items):
    if not items:
        return "''(none)''"
    esc = lambda x: x.replace("|", "&#124;").replace("<", "&lt;").replace("{{", "&#123;&#123;")
    return "<br />".join(esc(x) for x in items)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv")
    ap.add_argument("--records", help="use only CSV records FIRST-LAST, counted from 1")
    ap.add_argument("--format", choices=["md", "mediawiki"], default="md")
    ap.add_argument("--old", default="old string (157 and older)")
    ap.add_argument("--new", default="new string (158 and newer)")
    args = ap.parse_args()
    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.records:
        m = re.fullmatch(r"(\d+)-(\d+)", args.records)
        if not m or not 1 <= int(m.group(1)) <= int(m.group(2)) <= len(rows):
            sys.exit(f"--records must be FIRST-LAST within 1-{len(rows)}")
        rows = rows[int(m.group(1)) - 1 : int(m.group(2))]
    out = []
    data = list(changed_rows(rows))
    if args.format == "md":
        out.append(f"| Click path | {args.old} | {args.new} |")
        out.append("|---|---|---|")
        for path, o, n in data:
            out.append(f"| {md_cell([path])} | {md_cell(o)} | {md_cell(n)} |")
    else:
        out.append('{| class="wikitable sortable"')
        out.append(f"! Click path !! {args.old} !! {args.new}")
        for path, o, n in data:
            out.append("|-")
            out.append(f"| {wiki_cell([path])} || {wiki_cell(o)} || {wiki_cell(n)}")
        out.append("|}")
    sys.stdout.write("\n".join(out) + "\n")
    print(f"{len(data)} changed records", file=sys.stderr)


if __name__ == "__main__":
    main()
