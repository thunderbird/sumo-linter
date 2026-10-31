# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Find the KB articles that quote UI strings a Thunderbird release changes.

Input is a UX string-change sheet exported as CSV, with the columns
`Setting`, `Current content`, `New content`, `Pane` and `Section`. Output is
a JSON file of every string and its matches, and a Markdown report ready to
paste into a GitHub issue (knowledgebase-issues #247 was made with it).

Usage, from the repository root:

    python3 -I tools/ui-strings/search.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv \
        --json /tmp/results.json --markdown /tmp/report.md

Standard library only. It searches the *committed* corpus (`git ls-files`),
never the working tree, because `corpus/en-US/` also holds gitignored
non-public drafts that must not be named in a public issue.

Lessons for the markup-aware search engine (sumo-linter #6). This tool works
on text, with regexes. #6 will work on the lexer's token stream instead, and
these are the points it has to keep:

1. A UI string in an article is often bold: `'''Use smooth scrolling'''`.
   Text search must drop `'''`/`''` runs, or it misses most real hits. On
   tokens, match the text inside a bold span as if the markers were absent.
2. Normalise curly quotes, `…` against `...`, non-breaking spaces and runs of
   whitespace, and match case-insensitively. The sheet and the articles
   disagree on all of these.
3. Match whole words. A substring search makes "Play" match "display" and
   "Date" match "update": 223 of 600 strings "matched" before this rule.
4. Single words ("Advanced", "Composition") match ordinary prose in dozens of
   articles. Report them apart from multi-word strings, as low confidence.
5. Search line by line, so a string split across lines does not match. Kitsune
   joins the lines of a paragraph, so #6 can do better by matching across the
   newline tokens inside one paragraph.
6. A string that is split by markup (`{menu}`, a link, `{for}`) or paraphrased
   does not match at all. Only a token-level search can see through markup.
7. A template is not addressable by a slug derived from its file name (see
   "A template's slug cannot be derived" in CLAUDE.md), so the report names
   templates by file and never links them.
8. Line numbers belong to the corpus snapshot. They go stale when the live
   article changes, so a report must give the corpus date.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys

# Cell lines look like `Checkbox: Use smooth scrolling`. The label before the
# colon describes the widget, so it is dropped. It is at most a few words.
LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 /()-]{0,40}?:\s+(.*)$")

# Annotations in the sheet that look like strings but describe the UI.
NOISE = {"Checkboxes", "Meter", "Dropdown", "Field", "true"}

KB = "https://support.mozilla.org/en-US/kb/"


def norm(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("…", "...").replace(" ", " ")
    s = re.sub(r"'{2,}", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def strings(cell):
    """Yield the UI strings in one cell, one per line."""
    for line in cell.splitlines():
        line = line.strip()
        if not line or set(line) <= set("—-–"):
            continue
        m = LABEL.match(line)
        if m:
            line = m.group(1).strip()
        line = line.rstrip(" .…:").strip()
        if len(line) >= 4:
            yield line


def corpus_files():
    out = subprocess.run(
        ["git", "ls-files", "corpus/en-US/*.wiki", "corpus/templates/en-US/*.wiki"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    if not out:
        sys.exit("no committed corpus files found: run from the repository root")
    return sorted(out)


def search(rows, files):
    docs = {}
    for p in files:
        with open(p, encoding="utf-8") as f:
            docs[p] = [norm(line) for line in f.read().split("\n")]
    results, seen = [], set()
    for r in rows:
        new = norm(r["New content"])
        for s in strings(r["Current content"]):
            key = norm(s)
            if key in seen:
                continue
            seen.add(key)
            rx = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)")
            hits = []
            for p, lines in docs.items():
                ln = [i + 1 for i, line in enumerate(lines) if rx.search(line)]
                if ln:
                    hits.append([p, ln])
            # A string changes if its row has new content without it. An empty
            # "New content" means the row is unchanged.
            changed = bool(r["New content"].strip()) and not rx.search(new)
            results.append(
                dict(
                    pane=r["Pane"],
                    section=r["Section"],
                    setting=r["Setting"].strip(),
                    string=s,
                    words=len(s.split()),
                    changed=changed,
                    hits=hits,
                )
            )
    return results


def name(p, lines=None):
    slug = os.path.basename(p)[: -len(".wiki")]
    if "/templates/" in p:
        text = f"`{slug}` (template file name)"
    else:
        text = f"[`{slug}`]({KB}{slug})"
    if lines:
        text += f" (line{'s' if len(lines) > 1 else ''} {', '.join(map(str, lines))})"
    return text


def corpus_date():
    """The snapshot date recorded in corpus/README.md, or "unknown"."""
    try:
        with open("corpus/README.md", encoding="utf-8") as f:
            m = re.search(r"Snapshot taken:\*\* (\S+)", f.read())
    except OSError:
        return "unknown"
    return m.group(1) if m else "unknown"


def markdown(results, csv_name, n_articles, date):
    ch = [x for x in results if x["changed"] and x["hits"] and x["string"] not in NOISE]
    multi = [x for x in ch if x["words"] >= 2]
    single = [x for x in ch if x["words"] < 2]
    panes = []
    for x in multi:
        if x["pane"] not in panes:
            panes.append(x["pane"])
    multi.sort(key=lambda x: panes.index(x["pane"]))
    arts = {}
    for x in multi:
        for p, _ in x["hits"]:
            arts.setdefault(p, []).append(x["string"])
    n_changed = sum(1 for x in results if x["changed"])

    out = []
    a = out.append
    a("## Summary\n\n")
    a(
        "This report lists the Thunderbird KB articles whose wiki source contains "
        f"a string from the **Current content** column of `{csv_name}` that the "
        "release changes.\n\n"
    )
    a(f"- **{len(arts)} articles** contain at least one changed string of two words or more.\n")
    a(
        f"- {len(multi)} changed multi-word strings match at least one article. "
        f"{len(single)} changed single words also match. They are listed apart, "
        "because single words give many false hits.\n"
    )
    a(f"- The CSV gives {len(results)} distinct strings. {n_changed} of them change.\n")
    a(f"- The search covers {n_articles} committed corpus files, from the snapshot of {date}.\n\n")
    a("## Method\n\n")
    a("Produced by `tools/ui-strings/search.py`. Its docstring gives the matching rules.\n\n")
    a(
        "Every hit is a candidate for human review. A match in ordinary prose does "
        "not always refer to the setting. Line numbers refer to the corpus file, "
        "not to the live article.\n\n"
    )
    a("## Articles to review\n\n")
    for p in sorted(arts, key=lambda p: (-len(arts[p]), p)):
        n = len(arts[p])
        a(f"- [ ] {name(p)}: {n} string{'s' if n > 1 else ''}\n")
    a("\n## Changed strings, with matching articles\n")
    cur = None
    for x in multi:
        if x["pane"] != cur:
            cur = x["pane"]
            a(f"\n### {cur}\n\n")
        a(
            f"- \"{x['string']}\" (setting: {x['setting']}): "
            + "; ".join(name(p, ln) for p, ln in x["hits"])
            + "\n"
        )
    a("\n## Changed single words (low confidence)\n\n")
    a("The number is the count of matching files.\n\n")
    for x in single:
        a(f"- \"{x['string']}\" ({x['pane']}, setting: {x['setting']}): {len(x['hits'])}\n")
    a("\n## Known limits\n\n")
    a(f"- The corpus is a snapshot from {date}, not the live KB.\n")
    a("- Only en-US source is searched. Localized articles need the same review after the en-US articles change.\n")
    a("- A string that is paraphrased, or split by markup such as `{menu}` or a link, does not match.\n")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv")
    ap.add_argument("--json", help="write every string and its matches here")
    ap.add_argument("--markdown", help="write the issue-ready report here")
    args = ap.parse_args()
    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    files = corpus_files()
    results = search(rows, files)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, ensure_ascii=False)
    report = markdown(results, os.path.basename(args.csv), len(files), corpus_date())
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(report)
    else:
        sys.stdout.write(report)
    hit = sum(1 for x in results if x["hits"])
    print(f"{len(results)} strings, {hit} with matches, {len(files)} files", file=sys.stderr)


if __name__ == "__main__":
    main()
