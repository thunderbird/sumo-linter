# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Extract the en-US Settings and Account Settings strings from a Thunderbird app.

Reads `Contents/Resources/omni.ja` (a zip file) of each macOS app given, and
writes `tools/ui-strings/strings/<version>.tsv`, one string per line:

    <file> TAB <string ID> TAB <value>

The version comes from the app's Info.plist. The app is only read, never
started or changed. Lines are sorted, so comparing two versions is a plain
diff, and the files are committed (sumo-linter #18).

    python3 -I tools/ui-strings/extract.py \
        /Applications/THUNDERBIRD_ESR_140/Thunderbird.app \
        /Applications/THUNDERBIRD_MONTHLY_RELEASE/Thunderbird.app \
        "/Applications/THUNDERBIRD_BETA/Thunderbird Beta.app"

Three string formats are read:

- Fluent (`.ftl`): `id = value`, indented continuation lines, and attributes
  as `id.attr`. Values stay raw, so `{ -brand-short-name }` is kept as it is.
  compare.py resolves it.
- DTD (`.dtd`): `<!ENTITY id "value">`.
- Properties (`.properties`): `key = value`.

Access keys and key shortcuts (`.accesskey`, `.key`, `.commandkey`) and
`.style` attributes are left out: they are not text that an article quotes.
Newlines, tabs and backslashes in a value are written as `\\n`, `\\t`, `\\\\`.

SCOPE lists the files that hold Settings and Account Settings strings. It was
chosen by searching every en-US string file for the lines of the UX sheet,
and keeping the files where they occur.
"""

import os
import plistlib
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

SCOPE = (
    "localization/en-US/messenger/preferences/",
    "localization/en-US/messenger/accountManager.ftl",
    "localization/en-US/messenger/otr/am-im-otr.ftl",
    "localization/en-US/messenger/openpgp/",
    "localization/en-US/calendar/preferences.ftl",
    "chrome/en-US/locale/en-US/messenger/am-",
    "chrome/en-US/locale/en-US/messenger/preferences/",
    "chrome/en-US/locale/en-US/messenger/prefs.properties",
    "chrome/en-US/locale/en-US/messenger-newsblog/am-newsblog.dtd",
)

SKIP_SUFFIX = (".accesskey", ".key", ".commandkey", ".style", ".accessKey", ".commandKey")


def in_scope(name):
    return name.endswith((".ftl", ".dtd", ".properties")) and name.startswith(SCOPE)


def parse_ftl(text):
    """Yield (id, value) for every message, term and attribute."""
    cur = None  # (id, [lines]) being collected
    attr_of = None  # message id the current attribute belongs to

    def flush():
        if cur and any(x.strip() for x in cur[1]):
            yield cur[0], "\n".join(x.strip() for x in cur[1]).strip()

    for line in text.split("\n"):
        if not line.strip() or line.startswith("#"):
            if not line.strip() and cur:
                # A blank line inside a value is allowed. Keep collecting.
                continue
            yield from flush()
            cur, attr_of = None, None if line.startswith("#") else attr_of
            continue
        m = re.match(r"^(-?[A-Za-z][\w-]*)\s*=\s?(.*)$", line)
        if m and not line[0].isspace():
            yield from flush()
            attr_of = m.group(1)
            cur = (m.group(1), [m.group(2)])
            continue
        m = re.match(r"^\s+\.([\w-]+)\s*=\s?(.*)$", line)
        if m and attr_of:
            yield from flush()
            cur = (f"{attr_of}.{m.group(1)}", [m.group(2)])
            continue
        if cur and line[0].isspace():
            cur[1].append(line)
    yield from flush()


def parse_dtd(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for m in re.finditer(r"<!ENTITY\s+(\S+)\s+([\"'])(.*?)\2\s*>", text, re.S):
        yield m.group(1), m.group(3)


def parse_properties(text):
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(("#", "!")):
            continue
        m = re.match(r"^([^=:\s]+)\s*[=:]\s*(.*)$", s)
        if m:
            yield m.group(1), m.group(2)


def escape(v):
    return v.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def extract(app):
    with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
        version = plistlib.load(f)["CFBundleShortVersionString"]
    out = []
    with zipfile.ZipFile(os.path.join(app, "Contents", "Resources", "omni.ja")) as z:
        for name in sorted(n for n in z.namelist() if in_scope(n)):
            text = z.read(name).decode("utf-8")
            if name.endswith(".ftl"):
                pairs = parse_ftl(text)
            elif name.endswith(".dtd"):
                pairs = parse_dtd(text)
            else:
                pairs = parse_properties(text)
            for sid, value in pairs:
                if sid.endswith(SKIP_SUFFIX):
                    continue
                out.append(f"{name}\t{sid}\t{escape(value)}")
    if not out:
        sys.exit(f"{app}: no strings found in scope")
    return version, sorted(set(out))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    os.makedirs(os.path.join(HERE, "strings"), exist_ok=True)
    for app in sys.argv[1:]:
        version, lines = extract(app)
        path = os.path.join(HERE, "strings", f"{version}.tsv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        files = len({x.split("\t", 1)[0] for x in lines})
        print(f"{version}: {len(lines)} strings from {files} files -> {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
