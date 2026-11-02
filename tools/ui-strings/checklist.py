# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write the staging checklist for proposed edits (sumo-linter #28, #48).

    python3 -I tools/ui-strings/checklist.py SLUG... [--carry OLD.md] > checklist.md

It reads proposals/<slug>.md, the reports of propose_edits.py, and writes a
GitHub checklist in the form of the #28 one, which walk.py walks: per article,
the lines to confirm, the lines to write by hand, the headings, the automatic
replacements, and the steps before saving; then the evaluation.

`--carry OLD.md` takes the answers from an earlier checklist: an item that is
the same as before stays checked, keeps its `  - Note:` lines, and keeps a
`shot: "…"` that the author added. A line item is the same if it has the same
article, line number and old text, even if its suggestion changed, because
the author has already dealt with that line. Any other item is the same if its
text is the same.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOB = "https://github.com/thunderbird/sumo-linter/blob/main/tools/ui-strings/proposals"
ROW = re.compile(r"^\| (\d+) \| ([^|]+) \| (.*) \|$")
SOURCE = re.compile(r" \(new ID `.*\)$")  # the report's note on where a rename came from
ITEM = re.compile(r"^(\s*)- \[( |x|X)\] (.*)$")
NOTE = re.compile(r"^\s+- Note: ")
SHOT = re.compile(r'\(?\bshot: "(.*?)"\)?')
LINE_OLD = re.compile(r'^Line (\d+): "(.*?)"(?= →| \(| shot: "|$)')


def split_cells(row):
    """The cells of a report table row; `\\|` is a | inside a cell."""
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", row.strip())[1:-1]]


def report_rows(slug, folder=None):
    """(line, kind, old, new) for each row of proposals/<slug>.md."""
    path = os.path.join(folder or os.path.join(HERE, "proposals"), f"{slug}.md")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not re.match(r"^\| \d+ \|", line):
                continue
            ln, kind, old, new = split_cells(line)
            out.append((int(ln), kind, old, SOURCE.sub("", new)))
    return out


def q(s):
    return f'"{s}"'


def article(slug, rows):
    """The checklist section for one article."""
    confirm = [r for r in rows if r[1] == "guessed: check"]
    write = [r for r in rows if r[1] in ("CHECK comment", "not found as written: CHECK comment")]
    heads = [r for r in rows if r[1].startswith("heading")]
    auto = [r for r in rows if r[1] == "replaced"]
    out = [
        f"### {slug}",
        "",
        f"- [ ] Open https://support.allizom.org/en-US/kb/{slug}/edit and paste the whole of "
        f"[{slug}.wiki]({BLOB}/{slug}.wiki). The [report]({BLOB}/{slug}.md) and the "
        f"[diff]({BLOB}/{slug}.diff) are beside it.",
        "",
    ]
    if confirm:
        out += [f"**Confirm the guessed 159 text** ({len(confirm)}). Each line ends with "
                "`<!-- CHECK the 159 string is correct -->`. Delete that comment once the line is right.", ""]
        out += [f"- [ ] Line {ln}: {q(old)} → {q(new)}" for ln, _, old, new in confirm] + [""]
    if write:
        out += [f"**Write the 159 text yourself** ({len(write)}). The old text is still in the `{{for tb159}}` "
                "branch, with a `<!-- CHECK 159: … -->` comment that names the closest new text, shown below as "
                '"possible 159 text". It is often wrong. If the match is ordinary prose, such as "disk space" in a '
                "sentence, keep the text and delete the comment.", ""]
        out += [f"- [ ] Line {ln}: {q(old)} (possible 159 text: {q(new)})" for ln, _, old, new in write] + [""]
    if heads:
        out += [f"**Headings** ({len(heads)}). They are not wrapped in `{{for}}`. Decide whether each heading "
                "needs a 159 version, and delete the comment.", ""]
        out += [f"- [ ] Line {ln}: {q(old)} (possible 159 text: {q(new)})" for ln, _, old, new in heads] + [""]
    if auto:
        out += [f"**Skim the automatic replacements** ({len(auto)}). These are one-for-one changes from the strings.", ""]
        out += [f"- [ ] Line {ln}: {q(old)} → {q(new)}" for ln, _, old, new in auto] + [""]
    out += [
        "**Before saving**",
        "",
        "- [ ] Search the edit box for `CHECK`: no comment is left.",
        "- [ ] Screenshots: replace those that show the old Settings UI, inside the same `{for}` branches where needed.",
        "- [ ] Preview with the sidebar version at 159: only the new text shows.",
        "- [ ] Preview with the sidebar version at 153: only the old text shows.",
        "- [ ] Headings, their anchors and the table of contents look right.",
        "- [ ] Optional: paste the result into the [web app](https://thunderbird.github.io/sumo-linter/) for "
        "sumo-lint errors and its preview.",
        '- [ ] Save on staging with the summary "Update Settings strings for Thunderbird 159 (#247)".',
        "",
    ]
    return out


EVALUATE = [
    "### Evaluate, then report here",
    "",
    "- [ ] Was the default version on staging the latest release (159)?",
    "- [ ] Did the `{for not tb159}`/`{for tb159}` pairs render and switch correctly?",
    "- [ ] Was the doubled text acceptable, or should the `{for}` blocks be smaller (only the changed label, not the whole item)?",
    "- [ ] How long did one article take, and how many guesses were wrong?",
    "- [ ] Go or no-go for the other #247 articles, and any change to the script first.",
]


def key(heading, text):
    """What makes two items the same, for carrying answers over."""
    m = LINE_OLD.match(text)
    if m:
        return (heading, int(m.group(1)), m.group(2))
    return (heading, text)


def answers(old_md):
    """{key: (checked, notes, shot)} from an earlier checklist."""
    out, heading = {}, ""
    lines = old_md.split("\n")
    for i, line in enumerate(lines):
        h = re.match(r"^#{1,6}\s+(.*)$", line)
        if h:
            heading = h.group(1).strip()
            continue
        m = ITEM.match(line)
        if not m:
            continue
        notes, j = [], i + 1
        while j < len(lines) and NOTE.match(lines[j]):
            notes.append(NOTE.sub("", lines[j]))
            j += 1
        shot = SHOT.search(m.group(3))
        out.setdefault(key(heading, m.group(3)), (m.group(2) != " ", notes, shot.group(1) if shot else None))
    return out


def carry(new_md, old_md):
    """new_md with the answers of old_md. Returns (text, how many carried)."""
    old = answers(old_md)
    out, heading, carried = [], "", 0
    for line in new_md.split("\n"):
        h = re.match(r"^#{1,6}\s+(.*)$", line)
        if h:
            heading = h.group(1).strip()
        m = ITEM.match(line)
        if not m or key(heading, m.group(3)) not in old:
            out.append(line)
            continue
        checked, notes, shot = old[key(heading, m.group(3))]
        text = m.group(3)
        if shot and not SHOT.search(text) and not text.endswith(f' → "{shot}"'):
            # The author's label replaces a suggestion that was wrong.
            text = re.sub(r' \(possible 159 text: ".*"\)$', "", text) + f' shot: "{shot}"'
        out.append(f"{m.group(1)}- [{'x' if checked else ' '}] {text}")
        out += [f"{m.group(1)}  - Note: {n}" for n in notes]
        carried += 1 if checked or notes or shot else 0
    return "\n".join(out), carried


def checklist(slugs, intro, folder=None):
    out = ["## Checklist for the test articles", "", intro, ""]
    for slug in slugs:
        out += article(slug, report_rows(slug, folder))
    return "\n".join(out + EVALUATE) + "\n"


def main():
    args = sys.argv[1:]
    old = None
    if "--carry" in args:
        i = args.index("--carry")
        with open(args[i + 1], encoding="utf-8") as f:
            old = f.read()
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    intro = ("Work through this list for each article on **staging (support.allizom.org)**, "
             "then report back here.")
    text = checklist(args, intro)
    if old is not None:
        text, n = carry(text, old)
        print(f"{n} answers carried over", file=sys.stderr)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
