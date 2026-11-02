# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Propose a {for tb159} edit for KB articles that quote changed Settings strings (sumo-linter #28).

    python3 -I tools/ui-strings/propose_edits.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv \
        advanced-panel-settings-in-thunderbird privacy-panel-settings-in-thunderbird

For each article it writes three files to tools/ui-strings/proposals/, or to
DIR with `--out DIR`, which leaves proposals/ alone while a checklist
refers to it:

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
together, or was removed. The guess is the most similar new text in the group.

- A strong guess (at least STRONG similar) replaces the old text in the 159
  branch, and the line ends with `<!-- CHECK the 159 string is correct -->`.
  Measured on the two test articles, these were almost always right.
- A weaker guess is not used. The old text stays in the 159 branch, followed
  by an HTML comment, as Roland decided on #28:

      <old text><!-- CHECK 159: "<old text>" → "<closest new text>"? -->

Headings are not wrapped, because a {for} inside a heading can affect the
table of contents and the heading's anchor. They get the same kind of
comment inside the heading, before the closing run of "=". A match that is
not in the line as written gets the comment at the end of the line. Search
the proposal for "CHECK" to find them all. A forgotten comment is
invisible to readers, but it leaves the old text in the 159 branch.

"Removed" is checked first (#47). 159 rewords some strings under a new ID,
and the localizer table then shows the old string with no new text, in its
own row. So for an old text with no new text, `renames` looks in the same
file for a string that is new in 159, and pairs the most similar ones. The
spreadsheet helps: its record for the old string often plans the new
control's text, for example "Radio button: Leave it in Inbox", and the
shipped string closest to that plan is the rename ("Leave in Inbox"). A
shipped string wins over the plan, which only steers the choice. Each new
string pairs with one old string, best pairs first. Only below RENAMED is the
text "removed". The report says which file, ID and sheet record each such
guess came from.

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


# A new string in the same file is a rename (#47) if it is at least RENAMED
# similar to the old text, or at least PLANNED similar to the spreadsheet's
# plan for the old control. RENAMED is low on purpose: the result is only a
# suggestion in a CHECK comment, unless it is also STRONG, and a question is
# more use to the author than a wrong "removed". Measured on the #28
# articles: 4 of their 5 "removed" were renames, at 0.59 to 0.96, and the
# fifth, the backlogged crash reports, is 0.42 to its likely successor.
RENAMED = 0.4
PLANNED = 0.75
CONTROL = re.compile(r"^\s*(?:•\s*)?([A-Za-z][A-Za-z ]{1,24}):\s+(.*?)\s*$")


def planned(rows, recs, old):
    """The spreadsheet's planned new text for the control that shows `old`.

    In each record, the line of Current content that holds the old text names
    its control, such as "Radio button". The most similar line of New content
    for the same control is the plan. None if no record says.
    """
    best = None
    for i in recs:
        r = rows[i - 1]
        controls = [CONTROL.match(x) for x in r["Current content"].split("\n")]
        kinds = {m.group(1).strip().lower() for m in controls if m and compare.norm(m.group(2)) == compare.norm(old)}
        for line in r["New content"].split("\n"):
            m = CONTROL.match(line)
            if m and m.group(1).strip().lower() in kinds:
                score = similarity(old, m.group(2))
                if best is None or score > best[0]:
                    best = (score, m.group(2).strip(), i)
    return (best[1], best[2]) if best else (None, None)


def renames(built, win=WINDOW):
    """{old text: (new text, how)} for strings that 159 gave a new ID (#47).

    Within one file, an ID only in the old version and an ID only in the new
    one are a rename if their texts are similar, or if the new text is close
    to what the spreadsheet planned for the old control (RENAMED, PLANNED).
    Each ID pairs once, best pairs first.
    """
    _, data, terms, rows, key_recs, _, _, _, _ = built
    v_old, v_new = shipped_search.VERSIONS[STEP - 1], shipped_search.VERSIONS[STEP]
    text = lambda k, v: l10n_tables.show(data[k][v], terms)
    keys = [k for k in data if l10n_tables.window(k) == win]
    gone = [k for k in keys if v_old in data[k] and v_new not in data[k]]
    added = [k for k in keys if v_new in data[k] and v_old not in data[k]]
    scored = []
    for ok in gone:
        old = text(ok, v_old)
        plan, rec = planned(rows, key_recs.get(ok, []), old)
        for nk in added:
            if nk[0] != ok[0]:
                continue
            new = text(nk, v_new)
            by_text, by_plan = similarity(old, new), (similarity(plan, new) if plan else 0)
            if by_text >= RENAMED or by_plan >= PLANNED:
                scored.append((max(by_text, by_plan), ok, nk, old, new, plan, rec))
    out, used_old, used_new = {}, set(), set()
    for score, ok, nk, old, new, plan, rec in sorted(scored, key=lambda x: -x[0]):
        if ok in used_old or nk in used_new or old in out:
            continue
        used_old.add(ok)
        used_new.add(nk)
        how = f"new ID `{nk[1]}` in `{os.path.basename(nk[0])}`, was `{ok[1]}`"
        if plan:
            how += f"; sheet record {rec} planned “{plan}”"
        out[old] = (new, how)
    return out


def pairs(built):
    """{old text: (new cell, one_to_one)} for the Settings texts changed in 159.

    An old text with no new text gets its rename, if `renames` finds one.
    """
    wanted = shipped_search.changes(built)[WINDOW, STEP]
    renamed = renames(built)
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
                new_cell = row[STEP]
                if not shipped_search.lines(new_cell) and old in renamed:
                    new_cell, one = renamed[old][0], False
                out[old] = (new_cell, one)
    return out


def raw_span(line, old):
    """(start, end) of the old text in the raw line, case-insensitive, or None.

    Tries the text as it is, then without a trailing ":" or "…", because
    articles often drop them. Curly and straight apostrophes are equal.
    """
    for cand in (old, old.rstrip(" :…").strip()):
        pat = re.escape(cand).replace("\\'", "['’]").replace("’", "['’]")
        pat = re.sub('\\\\?["“”]', '["“”]', pat)
        m = re.search(pat, line, re.I)
        if m:
            return m.span()
    return None


STRONG = 0.75  # similarity at or above which the closest new text is used (measured on #28)
GUESSED = "<!-- CHECK the 159 string is correct -->"


def similarity(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


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
                if guess != "removed" and similarity(old, guess) >= STRONG:
                    # Strong guess: use it, and ask once per line for a check.
                    new_body = new_body[:a] + guess + new_body[b:]
                    if GUESSED not in tail:
                        tail = GUESSED + tail
                    rows.append((ln, "guessed: check", old, guess))
                    continue
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


def report(slug, rows, before_err, after_err, sources=None):
    count = lambda k: sum(1 for r in rows if r[1] == k)
    lines_changed = len({r[0] for r in rows if r[1] in ("replaced", "guessed: check", "CHECK comment")})
    out = [
        f"# Proposed edit: {slug}",
        "",
        f"Article: https://support.mozilla.org/en-US/kb/{slug}",
        f"Edit: https://support.mozilla.org/en-US/kb/{slug}/edit",
        "",
        f"Made by `tools/ui-strings/propose_edits.py` (thunderbird/sumo-linter#28) from the corpus "
        f"snapshot of {shipped_search.search.corpus_date()}. Paste `{slug}.wiki` into the edit page, "
        "search it for `CHECK` and resolve every comment, check the screenshots, preview with "
        "the version selector "
        "set to 159 and to 153, then submit.",
        "",
        f"- {lines_changed} lines wrapped in `{OLD_FOR}…{{/for}}{NEW_FOR}…{{/for}}`.",
        f"- {count('replaced')} texts replaced automatically (one-for-one changes).",
        f"- {count('guessed: check')} texts replaced by a strong guess (at least {STRONG:.0%} similar), "
        f"each line marked `{GUESSED}`.",
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
    sources = sources or {}
    for ln, kind, old, new in rows:
        # Where a guess for a renamed string came from (#47).
        how = f" ({sources[old][1]})" if old in sources and sources[old][0] == new else ""
        out.append(f"| {ln} | {kind} | {esc(old)} | {esc(new)}{esc(how)} |")
    return "\n".join(out) + "\n"


def main():
    args = sys.argv[1:]
    out_dir = os.path.join(HERE, "proposals")
    if "--out" in args:
        # Somewhere else than proposals/, which a running checklist refers to.
        i = args.index("--out")
        out_dir = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        sys.exit("usage: propose_edits.py [--out DIR] SHEET.csv SLUG...")
    sys.argv[1:] = args
    built = compare.build(sys.argv[1])
    table = pairs(built)
    sources = renames(built)
    docs = shipped_search.corpus()
    os.makedirs(out_dir, exist_ok=True)
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
        base = os.path.join(out_dir, slug)
        with open(base + ".wiki", "w", encoding="utf-8") as f:
            f.write(after)
        with open(base + ".diff", "w", encoding="utf-8") as f:
            f.writelines(
                difflib.unified_diff(
                    [x + "\n" for x in src], [x + "\n" for x in out], f"a/{key}", f"b/{key}"
                )
            )
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(report(slug, rows, before_err, after_err, sources))
        kinds = {}
        for r in rows:
            kinds[r[1]] = kinds.get(r[1], 0) + 1
        print(f"{slug}: {kinds}, lint {before_err} -> {after_err}", file=sys.stderr)


if __name__ == "__main__":
    main()
