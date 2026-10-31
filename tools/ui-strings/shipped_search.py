# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Find KB articles that quote a Settings string that really changed (sumo-linter #27).

search.py searches for the planned wording in the UX sheet. This script
searches for the old texts that Thunderbird really shipped, from the
committed strings, so it finds articles that quote a changed string the
sheet does not name, and it leaves out strings the sheet plans to change
but no version has changed yet.

    python3 -I tools/ui-strings/shipped_search.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv

It writes `affected-settings.md` and `affected-account-settings.md`, ready to
be the body of knowledgebase-issues #247 (Settings) and #249 (Account
Settings). Each has two sections, as Roland decided on #27:

- Changed in 159: edit now. 159 is released.
- Changed in 160: edit when 160 is released. Editing sooner would make the
  article wrong for people on 159.

Where the texts come from: the rows of the 3-column localizer table
(l10n_tables.rows_for), so the same rules apply. Format-only changes do not
count, strings without words are skipped, and the window comes from the
string file. A text counts as changed in a version if it is in the cell of
the previous version and not in the cell of that version.

How the corpus is searched: with search.py's normalisation (bold markers,
quotes, whitespace, case) and whole-word matching, line by line, over the
committed articles and templates. A placeholder such as `{ $name }` or `%S`
matches up to four words. Platform variants ("Choose… (macOS) / Browse…
(Windows, Linux)") are searched separately. A text with a placeholder needs
at least three other words, or "{ $name } content" would match anything.
Texts of one word are listed apart as low confidence, because "Remove" or
"Automatic" occur in many articles in other senses. Articles only for
Thunderbird for Android are not searched: these are desktop strings.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compare  # noqa: E402
import l10n_tables  # noqa: E402
import search  # noqa: E402

VERSIONS = ("153.6.0", "159.0", "160.0")
SECTIONS = (
    (1, "Changed in 159: edit now", "159 is released, so these articles describe the old UI today."),
    (
        2,
        "Changed in 160: edit when 160 is released",
        "Do not edit these yet: until 160 is released, the old text is still right for people on 159.",
    ),
)
PLACEHOLDER = re.compile(r"\{\s*\$[\w-]+\s*\}|%(?:\d+\$)?[SsDd]")
VARIANT = re.compile(r"\s*\((?:macOS|Windows, Linux)\)$")


def lines(cell):
    return [] if cell == l10n_tables.ABSENT else [x for x in cell.split("\n") if x.strip()]


def searchable(text):
    """The texts to search for one visible text: one per platform variant."""
    parts = text.split(" / ") if "(macOS) / " in text else [text]
    return [VARIANT.sub("", p).strip() for p in parts]


def pattern(text):
    """A whole-word regex for a normalised text; a placeholder matches 1-4 words."""
    pieces = PLACEHOLDER.split(as_quoted(text))
    words = sum(len(p.split()) for p in pieces)
    if not words or (len(pieces) > 1 and words < 3):
        return None, 0
    body = r"\S+(?: \S+){0,3}".join(re.escape(p) for p in pieces)
    return re.compile(r"(?<!\w)" + body + r"(?!\w)"), words


def as_quoted(text):
    """How an article would quote a text: normalised, trailing "…", ":" and "." dropped."""
    t = search.norm(text).rstrip(" .:…").strip()
    return t[:-3].strip() if t.endswith("...") else t


def changes(built):
    """For each window and section: {old text: new cell}.

    An old text is left out if the newer version still shows the same text
    in the same window, apart from a trailing "…" or ":". The dialog title
    "Return Receipts" became "Read receipts" in 159, but the button
    "Return Receipts…" stayed, and an article quoting "Return Receipts" may
    mean either, so it is no evidence of a change.
    """
    _, data, terms, *_ = built
    still = {}
    for key, vals in data.items():
        for v, val in vals.items():
            for x in compare.variants(val, terms):
                still.setdefault((l10n_tables.window(key), v), set()).add(as_quoted(compare.same_text(x)))
    out = {}
    for win, _ in l10n_tables.WINDOWS:
        for step, _, _ in SECTIONS:
            now = still.get((win, VERSIONS[step]), set())
            found = {}
            for row in l10n_tables.rows_for(VERSIONS, built, win):
                before, after = row[step - 1], row[step]
                kept = {compare.same_text(y) for y in lines(after)}
                for old in lines(before):
                    if compare.same_text(old) in kept or as_quoted(compare.same_text(old)) in now:
                        continue
                    found.setdefault(old, after)
            out[win, step] = found
    return out


def android_only():
    """Slugs of public articles whose only product is Thunderbird for Android."""
    import json

    with open("corpus/index.public.json", encoding="utf-8") as f:
        index = json.load(f)
    return {a["slug"] for a in index["articles"] if a.get("products") == ["thunderbird-android"]}


def corpus():
    skip = android_only()
    docs = {}
    for p in search.corpus_files():
        if os.path.basename(p)[: -len(".wiki")] in skip:
            continue
        with open(p, encoding="utf-8") as f:
            docs[p] = [search.norm(x) for x in f.read().split("\n")]
    return docs


def find(docs, text):
    """{file: [line numbers]} for every place the text is quoted."""
    hits = {}
    for variant in searchable(text):
        rx, words = pattern(variant)
        if not rx:
            continue
        for p, ls in docs.items():
            ln = [i + 1 for i, line in enumerate(ls) if rx.search(line)]
            if ln:
                hits.setdefault(p, set()).update(ln)
    return {p: sorted(v) for p, v in hits.items()}


def words_of(text):
    return max((pattern(v)[1] for v in searchable(text)), default=0)


def name(p, ln=None):
    slug = os.path.basename(p)[: -len(".wiki")]
    text = f"`{slug}` (template file name)" if "/templates/" in p else f"[`{slug}`]({search.KB}{slug})"
    if ln:
        text += f" (line{'s' if len(ln) > 1 else ''} {', '.join(map(str, ln))})"
    return text


def esc(s):
    return s.replace("|", "\\|").replace("<", "&lt;").replace("\n", "<br>").replace("*", "\\*")


def report(win, title, found, docs, date):
    out = [
        f"{title} texts that changed in Thunderbird 159 or 160 and that KB articles quote. Made by "
        f"`tools/ui-strings/shipped_search.py` (thunderbird/sumo-linter#27) from the strings that "
        f"ship in ESR 153.6.0, Release 159.0 and Beta 160.0, and the corpus snapshot of {date}.",
        "",
        "Every hit is a candidate for human review: a match in ordinary prose does not always refer "
        "to the setting. Line numbers refer to the corpus file, not to the live article. Use the "
        "new text from the table below, or from the wiki copy: "
        f"https://wiki.mozilla.org/User:Rolandtb/strings-153.6.0-159.0-160.0-{win}",
        "",
    ]
    for step, heading, note in SECTIONS:
        sure, weak = [], []
        for old, new in found[win, step].items():
            hits = find(docs, old)
            if not hits:
                continue
            (weak if words_of(old) < 2 else sure).append((old, new, hits))
        arts = {}
        for old, _, hits in sure:
            for p in hits:
                arts.setdefault(p, []).append(old)
        out += [f"## {heading}", "", note, ""]
        out.append(f"{len(arts)} articles quote {len(sure)} changed texts.")
        out.append("")
        for p in sorted(arts, key=lambda p: (-len(arts[p]), p)):
            n = len(arts[p])
            out.append(f"- [ ] {name(p)}: {n} text{'s' if n > 1 else ''}")
        if sure:
            out += ["", "| Old text | New text | Quoted in |", "|---|---|---|"]
            for old, new, hits in sorted(sure, key=lambda x: x[0].lower()):
                where = "<br>".join(name(p, ln) for p, ln in sorted(hits.items()))
                shown = esc(new) if new != l10n_tables.ABSENT else "*(removed, or replaced in another row)*"
                out.append(f"| {esc(old)} | {shown} | {where} |")
        if weak:
            out += [
                "",
                "Low confidence: one word, so the matches are mostly other senses. The number "
                "is the count of matching articles.",
                "",
            ]
            for old, new, hits in sorted(weak, key=lambda x: x[0].lower()):
                out.append(f"- \"{esc(old)}\" → \"{esc(new)}\": {len(hits)}")
        out.append("")
    out += [
        "## Known limits",
        "",
        f"- The corpus is a snapshot from {date}, not the live KB.",
        "- Only en-US source is searched.",
        "- A text that an article paraphrases, or splits with markup such as `{menu}` or a link, "
        "does not match.",
        "- A cell with several texts lists all the texts that changed together for one setting, so "
        "the new text for one old text is among them, not always beside it.",
        "",
    ]
    return "\n".join(out)


def reports(built):
    """{window: report text}."""
    docs = corpus()
    found = changes(built)
    date = search.corpus_date()
    return {win: report(win, title, found, docs, date) for win, title in l10n_tables.WINDOWS}


def write_all(csv_path):
    written = []
    for win, text in reports(compare.build(csv_path)).items():
        path = os.path.join(HERE, f"affected-{win}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written.append((path, text))
    return written


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: shipped_search.py SHEET.csv")
    for path, text in write_all(sys.argv[1]):
        counts = re.findall(r"^(\d+) articles quote (\d+) changed texts", text, re.M)
        print(
            f"{os.path.basename(path)}: "
            + "; ".join(f"{a} articles / {t} texts" for a, t in counts)
            + f", {len(text)} characters",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
