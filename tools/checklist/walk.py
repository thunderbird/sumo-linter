#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Walk through the unchecked items of a GitHub checklist (sumo-linter #30).

    uv run tools/checklist/walk.py URL [--dry-run] [--web DIR]

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

`--web DIR` also opens the web app on this computer and moves its cursor to
the line that the current item names (#31). The item `Line 21: "Old" → "New"`
under the heading `### some-article` selects "Old" on line 21 of
DIR/some-article.wiki, or the whole line if "Old" is not on it. An item with no
line number only loads the file of its heading. Save to file suggests
`some-article-edited.wiki`, so it never replaces the file in DIR, and nothing
is kept in the browser's storage. Build the linter first with
tools/build-web.sh, or the page shows only the preview.

It uses the `gh` command (signed in with `gh auth login`), so it needs no
token of its own. Python standard library only, so `uv run` installs nothing
(#32). `python3 -I tools/checklist/walk.py …` works too.
"""

import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/(?:issues|pull)/(\d+)(?:#issuecomment-(\d+))?")
ITEM = re.compile(r"^(\s*)[-*] \[( |x|X)\] (.*)$")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
BOLD = re.compile(r"^\*\*(.+?)\*\*")
NOTE = re.compile(r"^\s+- Note: ")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
LINE = re.compile(r'^Line (\d+):(?: "(.*?)"(?= →| \(|$))?')
WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")


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
                    "heading": heading,
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


def target(item):
    """Where the web app should go for an item (#31): {file, line, find}.

    The file is the heading plus `.wiki`, and None if the heading cannot be a
    file name. The line is the number after `Line` at the start of the item,
    and `find` is the quoted text after it. Both are None if the item does not
    start with `Line N:`.
    """
    h = item["heading"]
    name = f"{h}.wiki" if re.fullmatch(r"[A-Za-z0-9][\w.-]*", h) else None
    m = LINE.match(item["text"])
    return {
        "file": name,
        "line": int(m.group(1)) if m else None,
        "find": m.group(2) if m and m.group(2) else None,
    }


class WebApp:
    """The web app on localhost, and the item it shows (#31).

    The page listens on /walk/events, a Server-Sent Events stream: one JSON
    event each time the target changes, and the current one on connecting.
    It fetches the article from /walk/file/NAME, which serves only `.wiki`
    files directly in `folder`. Everything else is a file of web/.
    """

    def __init__(self, folder, web=WEB):
        self.folder, self.web = os.path.realpath(folder), web
        self.changed = threading.Condition()
        self.current, self.version = None, 0
        app = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm"}

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=app.web, **kwargs)

            def log_message(self, *args):
                pass  # the terminal belongs to the checklist

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/walk/events":
                    return app.events(self)
                if path.startswith("/walk/file/"):
                    return app.file(self, path[len("/walk/file/"):])
                return super().do_GET()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/?walk=1"

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        with self.changed:
            self.current, self.version = "stop", self.version + 1
            self.changed.notify_all()
        time.sleep(0.2)  # time to tell the page, so it says that the walk ended
        self.server.shutdown()
        self.server.server_close()

    def path_of(self, name):
        """The file for `name`, or None if it is not a .wiki file in the folder."""
        if not name or "/" in name or "\\" in name or not name.endswith(".wiki"):
            return None
        path = os.path.realpath(os.path.join(self.folder, name))
        if os.path.dirname(path) != self.folder or not os.path.isfile(path):
            return None
        return path

    def show(self, item):
        """Send the page to the item. Returns a line for the terminal, or None."""
        t = target(item)
        if not t["file"]:
            return None
        if not self.path_of(t["file"]):
            return f"  (web app: no file {os.path.join(self.folder, t['file'])})"
        with self.changed:
            self.current, self.version = t, self.version + 1
            self.changed.notify_all()
        return None

    def file(self, handler, name):
        path = self.path_of(name)
        if not path:
            return handler.send_error(404)
        with open(path, "rb") as f:
            data = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def events(self, handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        seen = -1
        try:
            while True:
                with self.changed:
                    if self.version == seen:
                        self.changed.wait(timeout=15)
                    version, current = self.version, self.current
                if current == "stop":
                    handler.wfile.write(b"event: stop\ndata: {}\n\n")
                    handler.wfile.flush()
                    return
                if version != seen and current is not None:
                    handler.wfile.write(f"data: {json.dumps(current)}\n\n".encode())
                else:
                    handler.wfile.write(b": still here\n\n")  # finds a closed tab
                handler.wfile.flush()
                seen = version
        except (BrokenPipeError, ConnectionResetError):
            return


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


def walk(store, label, ask=input, say=print, show=None):
    """The interactive loop. `ask` and `say` are parameters so tests can drive it.

    `show(item)`, if given, is called before each question, and any line it
    returns is printed. `--web` passes WebApp.show.
    """
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
        if show:
            extra = show(it)
            if extra:
                say(extra)
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
    args, dry_run, folder = sys.argv[1:], False, None
    if "--dry-run" in args:
        args.remove("--dry-run")
        dry_run = True
    if "--web" in args:
        i = args.index("--web")
        if i + 1 >= len(args):
            sys.exit(__doc__)
        folder = args.pop(i + 1)
        args.pop(i)
        if not os.path.isdir(folder):
            sys.exit(f"--web: not a folder: {folder}")
    if len(args) != 1:
        sys.exit(__doc__)
    app = None
    try:
        path, label = parse_url(args[0])
        if folder:
            app = WebApp(folder)
            app.start()
            print(f"Web app: {app.url}")
            if not os.path.isfile(os.path.join(WEB, "sumo_lint_wasm.wasm")):
                print("The linter is not built, so the page shows only the preview. Run tools/build-web.sh.")
            webbrowser.open(app.url)
        walk(GitHub(path, dry_run), label, show=app.show if app else None)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Every answer so far is saved.")
    finally:
        if app:
            app.stop()


if __name__ == "__main__":
    main()
