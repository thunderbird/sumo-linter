# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Walk through the unchecked items of a GitHub checklist (sumo-linter #30).

    python3 -I tools/checklist/walk.py URL [--dry-run]

URL is an issue comment, for example
https://github.com/thunderbird/sumo-linter/issues/28#issuecomment-6549440976,
or an issue, which walks the issue body. The script shows each unchecked
`- [ ]` item with the headings above it, and asks:

    c  check it
    n  leave it unchecked, with a note
    s  skip it for now
    u  undo the last answer
    q  quit

A note goes under its item as an indented line, `  - Note: …`. Every answer
is saved to GitHub at once, so quitting or a crash loses nothing, and running
the script again continues with the items still unchecked. Before each save
the script reads the text again and stops if someone changed it meanwhile,
for example in the browser. `--dry-run` saves nothing.

It uses the `gh` command (signed in with `gh auth login`), so it needs no
token of its own. Python standard library only.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/(?:issues|pull)/(\d+)(?:#issuecomment-(\d+))?")
ITEM = re.compile(r"^(\s*)[-*] \[( |x|X)\] (.*)$")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
BOLD = re.compile(r"^\*\*(.+?)\*\*")
NOTE = re.compile(r"^\s+- Note: ")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def parse_url(url):
    """(api path, label) for a comment or issue URL."""
    m = URL.search(url)
    if not m:
        raise ValueError(f"not a GitHub issue or comment URL: {url}")
    owner, repo, number, comment = m.groups()
    if comment:
        return f"repos/{owner}/{repo}/issues/comments/{comment}", f"{owner}/{repo}#{number} comment {comment}"
    return f"repos/{owner}/{repo}/issues/{number}", f"{owner}/{repo}#{number}"


def items(body):
    """Every checklist item: dicts with line, checked, text, context, notes.

    The context is the nearest heading above the item and the nearest bold
    line ("**Before saving**") below that heading. Items inside ``` code
    blocks are not checklist items.
    """
    out, heading, bold, fence = [], "", "", False
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        h = HEADING.match(line)
        if h:
            heading, bold = h.group(1).strip(), ""
            continue
        b = BOLD.match(line)
        if b and not ITEM.match(line):
            bold = b.group(1).strip()
            continue
        m = ITEM.match(line)
        if m:
            notes = []
            j = i + 1
            while j < len(lines) and NOTE.match(lines[j]):
                notes.append(NOTE.sub("", lines[j]))
                j += 1
            out.append(
                {
                    "line": i,
                    "checked": m.group(2) != " ",
                    "text": m.group(3),
                    "context": " / ".join(x for x in (heading, bold) if x),
                    "notes": notes,
                }
            )
    return out


def check(body, line):
    """The body with the item on `line` checked."""
    lines = body.split("\n")
    m = ITEM.match(lines[line])
    if not m:
        raise ValueError(f"line {line} is not a checklist item")
    lines[line] = lines[line].replace("[ ]", "[x]", 1)
    return "\n".join(lines)


def add_note(body, line, note):
    """The body with a note under the item on `line`, after any earlier notes."""
    lines = body.split("\n")
    m = ITEM.match(lines[line])
    if not m:
        raise ValueError(f"line {line} is not a checklist item")
    at = line + 1
    while at < len(lines) and NOTE.match(lines[at]):
        at += 1
    note = " ".join(note.split())  # one line, so the list stays intact
    lines.insert(at, f"{m.group(1)}  - Note: {note}")
    return "\n".join(lines)


def readable(text):
    """Item text for a terminal: links as "text <url>", code marks dropped."""
    return LINK.sub(r"\1 <\2>", text).replace("`", "")


class GitHub:
    """Reads and writes one body through `gh api`."""

    def __init__(self, path, dry_run=False):
        self.path, self.dry_run = path, dry_run
        self.local = None  # in a dry run, the text as it would be on GitHub

    def read(self):
        if self.dry_run and self.local is not None:
            return self.local
        res = subprocess.run(["gh", "api", self.path], capture_output=True, text=True)
        if res.returncode:
            raise RuntimeError(res.stderr.strip() or "gh api failed")
        return json.loads(res.stdout)["body"] or ""

    def write(self, body):
        if self.dry_run:
            self.local = body
            return
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(body)
        try:
            res = subprocess.run(
                ["gh", "api", "-X", "PATCH", self.path, "-F", f"body=@{f.name}"],
                capture_output=True,
                text=True,
            )
        finally:
            os.remove(f.name)
        if res.returncode:
            raise RuntimeError(res.stderr.strip() or "gh api failed")


def walk(store, label, ask=input, say=print):
    """The interactive loop. `ask` and `say` are parameters so tests can drive it."""
    body = store.read()
    history = []  # bodies before each saved answer, for undo
    counts = {"checked": 0, "noted": 0, "skipped": 0}
    # Items are tracked by their position in the list, which notes and checks
    # do not change, unlike line numbers.
    todo = [k for k, it in enumerate(items(body)) if not it["checked"]]
    total = len(todo)
    say(f"{label}: {total} unchecked of {len(items(body))} items." + (" Dry run: nothing is saved." if store.dry_run else ""))
    say("Answer c (check), n (note, leave unchecked), s (skip), u (undo), q (quit).")
    pos = 0
    while pos < len(todo):
        it = items(body)[todo[pos]]
        say("")
        say(f"[{pos + 1}/{total}] {it['context']}")
        say(f"  {readable(it['text'])}")
        for n in it["notes"]:
            say(f"  Note so far: {n}")
        answer = ask("c/n/s/u/q? ").strip().lower()
        if answer in ("q", "quit"):
            break
        if answer in ("s", "skip", ""):
            counts["skipped"] += 1
            pos += 1
            continue
        if answer in ("u", "undo"):
            if not history:
                say("Nothing to undo.")
                continue
            if store.read() != body:
                say("The text changed on GitHub since the last save. Stopping, so nothing is lost.")
                break
            body, last_pos, kind = history.pop()
            store.write(body)
            counts[kind] -= 1
            pos = last_pos
            say("Undone.")
            continue
        if answer in ("c", "check", "y", "yes"):
            new, kind = check(body, it["line"]), "checked"
        elif answer in ("n", "note"):
            note = ask("Note: ").strip()
            if not note:
                say("Empty note: nothing saved.")
                continue
            new, kind = add_note(body, it["line"], note), "noted"
        else:
            say("Please answer c, n, s, u or q.")
            continue
        if store.read() != body:
            say("The text changed on GitHub since the last save. Stopping, so nothing is lost.")
            break
        store.write(new)
        history.append((body, pos, kind))
        counts[kind] += 1
        body = new
        pos += 1
    say("")
    say(f"Done: {counts['checked']} checked, {counts['noted']} noted, {counts['skipped']} skipped.")
    return counts


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if len(args) != 1:
        sys.exit(__doc__)
    try:
        path, label = parse_url(args[0])
        walk(GitHub(path, "--dry-run" in sys.argv), label)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Every answer so far is saved.")


if __name__ == "__main__":
    main()
