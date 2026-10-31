# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write simple old-text/new-text tables for SUMO localizers (sumo-linter #19).

Each table has one column per version and shows visible text only: no
string IDs, files or CSV records. Each version set gets one table for the
Settings window and one for Account Settings, in GitHub Markdown and
MediaWiki wikitext:

    strings-153.6.0-159.0-settings.{md,mediawiki}                ESR 153 -> 159
    strings-153.6.0-159.0-account-settings.{md,mediawiki}
    strings-153.6.0-159.0-160.0-settings.{md,mediawiki}          ESR 153 -> 159 -> 160
    strings-153.6.0-159.0-160.0-account-settings.{md,mediawiki}

The string file decides the window (see `window()`), not the CSV record,
because the same text can appear in both: "Disk Space" is in the Settings
file preferences.ftl and in the Account Settings file am-offline.dtd.

    python3 -I tools/ui-strings/l10n_tables.py \
        tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv

How rows are built, from the strings compare.py already loads and maps:

- A text that appears in every version of the table, in the same window, is
  unchanged and left out, even if its string ID or file changed. A localizer sees no difference.
- A string ID whose text changes is one row, and the pairing is exact.
- When Thunderbird gives a reworded string a new ID, the CSV record links
  the old ID and the new one. If the record has exactly one old and one new
  text, they form one row. If it has more, they share one row and each cell
  lists its texts, one per line, because pairing them one by one would be a
  guess.
- A changed text that matches no CSV record gets a row of its own, with `—`
  in the versions where it does not exist.

Rows that match a CSV record come first, in record order.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compare  # noqa: E402

TABLES = (("153.6.0", "159.0"), ("153.6.0", "159.0", "160.0"))
LABELS = {"153.6.0": "ESR 153.6.0", "159.0": "Release 159.0", "160.0": "Beta 160.0"}
ABSENT = "—"
WINDOWS = (("settings", "Settings"), ("account-settings", "Account Settings"))

# Files of the Account Settings window. Every other file extract.py reads
# belongs to the Settings window.
ACCOUNT_FILES = re.compile(
    r"/messenger/am-[^/]+$"  # chrome am-*.dtd and am-*.properties
    r"|/messenger-newsblog/am-newsblog\.dtd$"
    r"|/messenger/prefs\.properties$"  # account manager and wizard
    r"|/messenger/accountManager\.ftl$"
    r"|/messenger/accountSettings\.ftl$"
    r"|/messenger/retention\.ftl$"  # deletion settings, Disk Space page
    r"|/messenger/smime/smime\.ftl$"
    r"|/messenger/otr/am-im-otr\.ftl$"
    r"|/messenger/preferences/am-[^/]+\.ftl$"
    r"|/messenger/openpgp/[^/]+\.ftl$"  # end-to-end encryption page, key manager
)


def window(key):
    return "account-settings" if ACCOUNT_FILES.search(key[0]) else "settings"


def show(value, terms):
    """Visible text, with platform variants spelled out."""
    v = compare.BRAND.sub("Thunderbird", value)
    v = re.sub(r"\{\s*(-[\w-]+)\s*\}", lambda m: terms.get(m.group(1), m.group(0)), v)
    m = re.search(r"\{\s*PLATFORM\(\)\s*->\s*\n(.*?)\n\s*\}", v, re.S)
    if m:
        parts = []
        for line in m.group(1).split("\n"):
            vm = re.match(r"\s*\*?\[([^\]]+)\]\s*(.*)$", line)
            if vm:
                name = {"macos": "macOS", "other": "Windows, Linux"}.get(vm.group(1), vm.group(1))
                parts.append(f"{vm.group(2).strip()} ({name})")
        v = v[: m.start()] + " / ".join(parts) + v[m.end() :]
    return re.sub(r"\s*\n\s*", " ", v).strip()


def rows_for(versions, built, win):
    _, data, terms, _, key_recs, _, _, _, _ = built
    text = {
        k: {v: show(data[k][v], terms) for v in versions if v in data[k]}
        for k in data
        if window(k) == win
    }
    common = set.intersection(*({t[v] for t in text.values() if v in t} for v in versions))

    def changed(k):
        t = text[k]
        if not t or all(x in common for x in t.values()):
            return False
        return len(t) < len(versions) or len(set(t.values())) > 1

    keys = sorted(k for k in text if changed(k))
    by_rec, loose = {}, []
    for k in keys:
        recs = key_recs.get(k)
        if recs:
            by_rec.setdefault(min(recs), []).append(k)
        else:
            loose.append(k)

    def cells(ks):
        return [
            "\n".join(dict.fromkeys(text[k][v] for k in ks if v in text[k] and text[k][v] not in common))
            or ABSENT
            for v in versions
        ]

    out = []
    for rec in sorted(by_rec):
        ks = by_rec[rec]
        whole = [k for k in ks if len(text[k]) == len(versions)]  # same ID, new text
        partial = [k for k in ks if len(text[k]) < len(versions)]  # ID replaced
        out += [cells([k]) for k in whole]
        if partial:
            out.append(cells(partial))
    out += [cells([k]) for k in loose]
    seen, rows = set(), []
    for r in out:
        if tuple(r) not in seen and len(set(r)) > 1:
            seen.add(tuple(r))
            rows.append(r)
    return rows


def render(fmt, versions, rows, title):
    esc = compare.esc_md if fmt == "md" else compare.esc_wiki
    names = [LABELS.get(v, v) for v in versions]
    intro = (
        f"{title} texts that changed between Thunderbird "
        f"{' and '.join(names) if len(names) == 2 else ', '.join(names[:-1]) + ' and ' + names[-1]}, "
        f"in en-US. {ABSENT} means the text does not exist in that version. A cell with several "
        "lines lists all the texts that changed together for one setting. Made by "
        "tools/ui-strings/l10n_tables.py (sumo-linter #19)."
    )
    out = [intro, ""]
    if fmt == "md":
        out.append("| " + " | ".join(names) + " |")
        out.append("|" + "---|" * len(names))
        out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    else:
        out.append('{| class="wikitable sortable"')
        out.append("! " + " !! ".join(names))
        for r in rows:
            out += ["|-", "| " + " || ".join(esc(c) for c in r)]
        out.append("|}")
    return "\n".join(out) + "\n"


def write_all(csv_path):
    built = compare.build(csv_path)
    have = built[0]
    written = []
    for versions in TABLES:
        missing = [v for v in versions if v not in have]
        if missing:
            sys.exit(f"no strings/{missing[0]}.tsv: run extract.py first")
        for win, title in WINDOWS:
            rows = rows_for(versions, built, win)
            stem = os.path.join(HERE, "strings-" + "-".join(versions) + "-" + win)
            for fmt, ext in (("md", ".md"), ("mediawiki", ".mediawiki")):
                with open(stem + ext, "w", encoding="utf-8") as f:
                    f.write(render(fmt, versions, rows, title))
            written.append((versions, title, len(rows)))
    return written


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: l10n_tables.py SHEET.csv")
    for versions, title, n in write_all(sys.argv[1]):
        print(f"{' -> '.join(versions)}, {title}: {n} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
