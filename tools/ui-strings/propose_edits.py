# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Propose a {for tb159} edit for KB articles that quote changed Settings strings (sumo-linter #28).

    python3 -I tools/ui-strings/propose_edits.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv \
        advanced-panel-settings-in-thunderbird privacy-panel-settings-in-thunderbird

For each article it writes three files to tools/ui-strings/proposals/:

- `<slug>.wiki`: the whole article with the proposed edit, ready to paste
  into the SUMO edit page.
- `<slug>.diff`: a unified diff against the committed corpus file.
- `<slug>.md`: what was changed automatically and what needs a person.

The edit keeps both versions, as Roland decided on #28. Each line that
quotes a changed string becomes, on the same line:

    <list markers>{for not tb159}<original text>{/for}{for tb159}<new text>{/for}

The line count stays the same, because localizers diff by line, and list
markers stay outside the tags, so numbering and bullets survive.

What is replaced automatically: a one-for-one change only, where the row of
the localizer table has exactly one old text and one new text, without
placeholders ("Use autoscrolling" -> "Enable auto-scrolling"). Every other
match is a guess: the old text belongs to a group of strings that changed
together, or was removed. In the 159 branch the old text stays, followed by
an HTML comment, as Roland decided on #28:

    <old text><!-- CHECK 159: "<old text>" → "<closest new text>"? -->

Headings are not wrapped, because a {for} inside a heading can affect the
table of contents and the heading's anchor. They get the same kind of
comment inside the heading, before the closing run of "=". A match that is
not in the line as written gets the comment at the end of the line. Search
the proposal for "CHECK 159" to find them all. A forgotten comment is
invisible to readers, but it leaves the old text in the 159 branch.

The matches come from shipped_search.py (Settings window, changed in 159).
The proposal must pass sumo-lint, with no new errors.
"""

import difflib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import compare  # noqa: E402
import l10n_tables  # noqa: E402
import shipped_search  # noqa: E402

WINDOW, STEP = "settings", 1  # Settings strings that changed in 159
OLD_FOR, NEW_FOR = "{for not tb159}", "{for tb159}"
MARKERS = re.compile(r"^([*#:;]+\s*)")
HEADING = re.compile(r"^=+.*=+\s*$")


def pairs(built):
    """{old text: (new cell, one_to_one)} for the Settings texts changed in 159."""
    wanted = shipped_search.changes(built)[WINDOW, STEP]
    out = {}
    for row in l10n_tables.rows_for(shipped_search.VERSIONS, built, WINDOW):
        before = shipped_search.lines(row[STEP - 1])
        after = shipped_search.lines(row[STEP])
        for old in before:
            if old in wanted and old not in out:
                one = (
                    len(before) == 1
                    and len(after) == 1
                    and not shipped_search.PLACEHOLDER.search(old + after[0])
                )
                out[old] = (row[STEP], one)
    return out


def raw_span(line, old):
    """(start, end) of the old text in the raw line, case-insensitive, or None.

    Tries the text as it is, then without a trailing ":" or "…", because
    articles often drop them. Curly and straight apostrophes are equal.
    """
    for cand in (old, old.rstrip(" :…").strip()):
        pat = re.escape(cand).replace("\\'", "['’]").replace("’", "['’]")
        m = re.search(pat, line, re.I)
        if m:
            return m.span()
    return None


def closest(old, new_cell):
    options = shipped_search.lines(new_cell)
    if not options:
        return "removed"
    return max(options, key=lambda o: difflib.SequenceMatcher(None, old.lower(), o.lower()).ratio())


def propose(slug, matches, table):
    """(new lines, report rows) for one article."""
    path = os.path.join(REPO, "corpus", "en-US", f"{slug}.wiki")
    with open(path, encoding="utf-8") as f:
        src = f.read().split("\n")
    out = list(src)
    rows = []  # (line, kind, old, new)
    by_line = {}
    for old, lns in matches.items():
        for ln in lns:
            by_line.setdefault(ln, []).append(old)
    for ln in sorted(by_line):
        line = src[ln - 1]
        if HEADING.match(line.strip()):
            notes = ""
            for old in by_line[ln]:
                guess = closest(old, table[old][0])
                notes += check(old, guess, "heading")
                rows.append((ln, "heading: CHECK comment", old, guess))
            m = re.match(r"^(.*?)(\s*=+\s*)$", line)
            out[ln - 1] = m.group(1) + notes + m.group(2)
            continue
        m = MARKERS.match(line)
        prefix, body = (m.group(1), line[m.end():]) if m else ("", line)
        new_body = body
        tail = ""
        # Longest first, so "Disk Space" does not cut into "Network & Disk Space".
        for old in sorted(by_line[ln], key=len, reverse=True):
            span = raw_span(new_body, old)
            if not span:
                guess = closest(old, table[old][0])
                tail += check(old, guess, "not found as written")
                rows.append((ln, "not found as written: CHECK comment", old, guess))
                continue
            new_cell, one = table[old]
            a, b = span
            if one:
                new_body = new_body[:a] + new_cell + new_body[b:]
                rows.append((ln, "replaced", old, new_cell))
            else:
                guess = closest(old, new_cell)
                at = after_markup(new_body, b)
                new_body = new_body[:at] + check(old, guess) + new_body[at:]
                rows.append((ln, "CHECK comment", old, guess))
        if new_body != body:
            out[ln - 1] = f"{prefix}{OLD_FOR}{body}{{/for}}{NEW_FOR}{new_body}{{/for}}{tail}"
        elif tail:
            out[ln - 1] = line + tail
    return src, out, rows


def after_markup(text, pos):
    """The first position at or after pos that is outside every {…} and […].

    A comment inside a macro breaks it: SUMO documents `{<!-- -->button}` as
    the way to show a macro literally. So a comment that would land inside
    `{button Clear Now}` or a link goes after the closing brace instead.
    """
    depth = 0
    for ch in text[:pos]:
        if ch in "{[":
            depth += 1
        elif ch in "}]" and depth:
            depth -= 1
    i = pos
    while depth and i < len(text):
        if text[i] in "{[":
            depth += 1
        elif text[i] in "}]":
            depth -= 1
        i += 1
    return i


def check(old, guess, where=None):
    """An HTML comment for a person to resolve. "--" may not appear inside one."""
    clean = lambda s: s.replace("--", "–").replace("\n", " ")
    label = f"CHECK 159{', ' + where if where else ''}"
    return f'<!-- {label}: "{clean(old)}" → "{clean(guess)}"? -->'


def lint_errors(text):
    """Number of sumo-lint errors in a text, or None if sumo-lint is not built."""
    exe = os.path.join(REPO, "target", "release", "sumo-lint")
    if not os.path.exists(exe):
        return None
    tmp = os.path.join(HERE, "proposals", ".lint.wiki")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    res = subprocess.run([exe, tmp], capture_output=True, text=True)
    os.remove(tmp)
    m = re.search(r"(\d+) errors?", res.stdout + res.stderr)
    return int(m.group(1)) if m else 0


def report(slug, rows, before_err, after_err):
    count = lambda k: sum(1 for r in rows if r[1] == k)
    lines_changed = len({r[0] for r in rows if r[1] in ("replaced", "CHECK comment")})
    out = [
        f"# Proposed edit: {slug}",
        "",
        f"Article: https://support.mozilla.org/en-US/kb/{slug}",
        f"Edit: https://support.mozilla.org/en-US/kb/{slug}/edit",
        "",
        f"Made by `tools/ui-strings/propose_edits.py` (thunderbird/sumo-linter#28) from the corpus "
        f"snapshot of {shipped_search.search.corpus_date()}. Paste `{slug}.wiki` into the edit page, "
        "search it for `CHECK 159` and resolve every comment, check the screenshots, preview with "
        "the version selector "
        "set to 159 and to 153, then submit.",
        "",
        f"- {lines_changed} lines wrapped in `{OLD_FOR}…{{/for}}{NEW_FOR}…{{/for}}`.",
        f"- {count('replaced')} texts replaced automatically (one-for-one changes).",
        f"- {count('CHECK comment')} texts with a `CHECK 159` comment: the new text is a guess, "
        "decide by hand.",
        f"- {sum(1 for r in rows if r[1].startswith('heading'))} heading matches and "
        f"{sum(1 for r in rows if r[1].startswith('not found'))} matches not found as written, "
        "each with a `CHECK 159` comment.",
        f"- sumo-lint errors: {before_err} before, {after_err} after."
        if after_err is not None
        else "- sumo-lint was not run: build it with `cargo build --release`.",
        "",
        "| Line | What | Old text | New text, or closest new text |",
        "|---|---|---|---|",
    ]
    esc = lambda s: s.replace("|", "\\|").replace("\n", " ")
    for ln, kind, old, new in rows:
        out.append(f"| {ln} | {kind} | {esc(old)} | {esc(new)} |")
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: propose_edits.py SHEET.csv SLUG...")
    built = compare.build(sys.argv[1])
    table = pairs(built)
    docs = shipped_search.corpus()
    os.makedirs(os.path.join(HERE, "proposals"), exist_ok=True)
    for slug in sys.argv[2:]:
        path = os.path.join(REPO, "corpus", "en-US", f"{slug}.wiki")
        key = os.path.relpath(path, REPO)
        if key not in docs:
            sys.exit(f"{slug}: not in the committed corpus")
        matches = {}
        for old in table:
            if shipped_search.words_of(old) < 2:
                continue  # one word: too weak to act on
            hit = shipped_search.find({key: docs[key]}, old)
            if hit:
                matches[old] = hit[key]
        src, out, rows = propose(slug, matches, table)
        assert len(src) == len(out), "the line count must not change"
        before, after = "\n".join(src), "\n".join(out)
        before_err, after_err = lint_errors(before), lint_errors(after)
        base = os.path.join(HERE, "proposals", slug)
        with open(base + ".wiki", "w", encoding="utf-8") as f:
            f.write(after)
        with open(base + ".diff", "w", encoding="utf-8") as f:
            f.writelines(
                difflib.unified_diff(
                    [x + "\n" for x in src], [x + "\n" for x in out], f"a/{key}", f"b/{key}"
                )
            )
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(report(slug, rows, before_err, after_err))
        kinds = {}
        for r in rows:
            kinds[r[1]] = kinds.get(r[1], 0) + 1
        print(f"{slug}: {kinds}, lint {before_err} -> {after_err}", file=sys.stderr)


if __name__ == "__main__":
    main()
