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
        [--shots DIR --thunderbird APP [--expect VERSION] [--real-account]]

URL is an issue comment, for example
https://github.com/thunderbird/sumo-linter/issues/28#issuecomment-6549440976,
or an issue, which walks the issue body. The script shows each unchecked
`- [ ]` item with the headings above it, and asks:

    c  check it. With --web, an item without a guess also loses its
       `<!-- CHECK the 159 string is correct -->` comment in the web app
    g  use the guess, with --web (see below). `g some text` adds a comment
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
is kept in the browser's storage.

With `--web`, an item that ends with `(possible 159 text: "GUESS")` also
offers `g` (#34). The web app then replaces the old text and its
`<!-- CHECK 159: … -->` comment on that line with GUESS, undoably. Only if
the page reports that the edit worked does the script check the item and add
the note `Used the guess "GUESS".`, followed by your comment if you typed
one after the g, for example `g then I shortened it`. In the same way, `c` on
an item without a guess deletes `<!-- CHECK the 159 string is correct -->`
from the item's line in the web app, and checks the item only after the page
says so. A line without that comment is checked as usual. The changes are in
the web app only: save or copy the text from there. Build the linter first with
tools/build-web.sh, or the page shows only the preview.

`--shots DIR --thunderbird APP` also takes a screenshot of the setting that
each item is about (#39), with tools/checklist/tb_shot.py, and saves it as
DIR/<heading>-item-<N>.png. The setting is found by its 159 text: the text
after `→`, or the possible 159 text, or `(shot: "TEXT")` anywhere in the
item, which wins over both. tb_shot.py runs a second Thunderbird with an empty
profile, so a Thunderbird you already use is not involved; see its docstring.
Each new screenshot opens in the image viewer, behind the terminal, so the
next answer can be typed at once. `--expect 159` refuses an APP that is not
version 159. `--real-account` uses
the signed-in test account of `tb_shot.py login` instead of a dummy one (#40).

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
GUESS = re.compile(r'\(possible 159 text: "(.*)"\)\s*$')
SHOT = re.compile(r'\(shot: "(.*?)"\)')
NEW = re.compile(r'^Line \d+: ".*?" → "(.*?)"')
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


def guess(item):
    """The possible 159 text of an item, or None (#34).

    "removed" is not text, so it is not offered as a guess.
    """
    m = GUESS.search(item["text"])
    if not m or m.group(1) == "removed" or not target(item)["find"]:
        return None
    return m.group(1)


def shot_text(item):
    """The text of the setting to screenshot for an item, or None (#39).

    `(shot: "TEXT")` wins; then the new text after `→`; then the possible
    159 text, unless it is "removed".
    """
    for pattern in (SHOT, NEW, GUESS):
        m = pattern.search(item["text"])
        if m and m.group(1) and m.group(1) != "removed":
            return m.group(1)
    return None


def open_file(path):
    """Open a file in its viewer, without taking focus from the terminal."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-g", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass  # the path is printed anyway


class Shots:
    """Screenshots of each item's setting, by tools/checklist/tb_shot.py (#39).

    One `tb_shot.py session` runs for the whole walk, with its own Thunderbird.
    A separate program, because walk.py must stay one file (#32).
    """

    def __init__(self, folder, app, expect=None, command=None, real=False, opener=None):
        self.folder, self.done = folder, {}
        self.opener = opener or open_file
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tb_shot.py")
        if command is None:  # tests pass a fake
            command = [sys.executable, script, "session", "--app", app, "--out", folder]
            if expect:
                command += ["--expect", expect]
            if real:
                command += ["--account", "real"]
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        ready = self.proc.stdout.readline()
        try:
            hello = json.loads(ready)
        except ValueError:
            hello = {}
        if not hello.get("ready"):
            self.stop()
            raise RuntimeError("tb_shot.py did not start Thunderbird (see the message above)")
        self.version = hello.get("version")

    def show(self, item, number):
        """Take the item's screenshot once. Returns a line for the terminal, or None."""
        text = shot_text(item)
        if not text:
            return None
        if number not in self.done:
            name = f"{item['heading'] or 'item'}-item-{number}"
            self.proc.stdin.write(json.dumps({"text": text, "name": name}) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("tb_shot.py stopped")
            self.done[number] = json.loads(line)
            if self.done[number].get("ok"):
                self.opener(self.done[number]["path"])
        r = self.done[number]
        if r.get("ok"):
            return f"  screenshot: {r['path']} ({r['where']})"
        return f"  no screenshot: {r.get('error')}"

    def stop(self):
        """Close its input, so it quits Thunderbird, and wait for it."""
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            self.proc.wait()
        self.proc.stdout.close()


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
        self.results = {}  # edit id -> (ok, message), from the page
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

            def do_POST(self):
                if self.path != "/walk/result":
                    return self.send_error(404)
                return app.result(self)

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

    def edit(self, item, edit, timeout=10):
        """Ask the page to make an edit on the item's line.

        Returns (ok, message, removed), where `removed` says whether the page
        changed the text. The page answers on /walk/result. No answer is a
        failure: an edit that was never made must not look like one that was.
        """
        t = target(item)
        with self.changed:
            self.version += 1
            edit_id = self.version
            self.current = {**t, "edit": {"id": edit_id, **edit}}
            self.changed.notify_all()
            got = self.changed.wait_for(lambda: edit_id in self.results, timeout=timeout)
            # A page that connects later must not make the edit again.
            self.current = t
            if not got:
                return False, "the web app did not answer. Is its page open?", False
            return self.results.pop(edit_id)

    def use_guess(self, item, timeout=10):
        """Ask the page to use the item's guess (#34). Returns (ok, message)."""
        t, g = target(item), guess(item)
        if not g or not self.path_of(t["file"] or ""):
            return False, "there is no guess to use"
        ok, message, _ = self.edit(item, {"kind": "guess", "old": t["find"], "guess": g}, timeout)
        return ok, message

    def confirm(self, item, timeout=10):
        """Ask the page to delete the "string is correct" comment on the item's line.

        Returns (ok, message, removed). An item without a line, or whose file
        is not in the folder, needs no edit: (True, "", False).
        """
        t = target(item)
        if not t["line"] or not self.path_of(t["file"] or ""):
            return True, "", False
        return self.edit(item, {"kind": "confirm"}, timeout)

    def result(self, handler):
        try:
            data = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", 0))))
            edit_id, ok, message = int(data["id"]), bool(data["ok"]), str(data.get("message", ""))
            removed = bool(data.get("removed", False))
        except (ValueError, KeyError, TypeError):
            return handler.send_error(400)
        with self.changed:
            self.results[edit_id] = (ok, message, removed)
            self.changed.notify_all()
        handler.send_response(204)
        handler.end_headers()

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


def walk(store, label, ask=input, say=print, show=None, use_guess=None, shots=None, confirm=None):
    """The interactive loop. `ask` and `say` are parameters so tests can drive it.

    `show(item)`, if given, is called before each question, and any line it
    returns is printed. `use_guess(item)` makes the edit for `g` and returns
    (ok, message). `--web` passes WebApp.show and WebApp.use_guess.
    `shots(item, number)`, if given, takes the item's screenshot and returns a
    line for the terminal; `--shots` passes Shots.show. `confirm(item)`
    deletes the line's "string is correct" comment for `c` on an item without
    a guess, and returns (ok, message, removed); `--web` passes WebApp.confirm.
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
    if use_guess:
        say("Where an item has a possible 159 text, g uses it in the web app and checks the item.")
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
        if shots:
            extra = shots(it, todo[pos] + 1)
            if extra:
                say(extra)
        offer = guess(it) if use_guess else None
        if offer:
            say(f'  g: use the guess "{offer}"')
        word, _, comment = ask("c/g/n/s/u/q? " if offer else "c/n/s/u/q? ").strip().partition(" ")
        answer, comment = word.lower(), comment.strip()
        if comment and answer not in ("g", "guess"):
            # Dropping the text silently would lose what the author typed.
            say("Only g takes a comment after it. For a note, answer n.")
            continue
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
            body, last_pos, kind, guessed = history.pop()
            store.write(body)
            counts[kind] -= 1
            pos = last_pos
            say("Undone. Cmd+Z in the web app takes back the edit there." if guessed else "Undone.")
            continue
        guessed = False
        if answer in ("c", "check", "y", "yes"):
            if confirm and not offer:
                if store.read() != body:
                    say("The text changed on GitHub since the last save. Stopping, so nothing is lost.")
                    break
                ok, message, removed = confirm(it)
                if not ok:
                    say(f"Not checked: {message} Nothing saved.")
                    continue
                if removed:
                    guessed = True  # an edit in the web app, which undo points at
                    say("Deleted the CHECK comment on that line in the web app.")
            new, kind = check(body, it["line"]), "checked"
        elif answer in ("g", "guess") and offer:
            if store.read() != body:
                say("The text changed on GitHub since the last save. Stopping, so nothing is lost.")
                break
            ok, message = use_guess(it)
            if not ok:
                say(f"The guess was not used: {message} Nothing saved.")
                continue
            note = f'Used the guess "{offer}".' + (f" {comment}" if comment else "")
            new = add_note(check(body, it["line"]), it["line"], note)
            kind, guessed = "checked", True
            say(f'Used the guess "{offer}" in the web app.')
        elif answer in ("n", "note"):
            note = ask("Note: ").strip()
            if not note:
                say("Empty note: nothing saved.")
                continue
            new, kind = add_note(body, it["line"], note), "noted"
        else:
            say("Please answer c, g, n, s, u or q." if offer else "Please answer c, n, s, u or q.")
            continue
        if store.read() != body:
            say("The text changed on GitHub since the last save. Stopping, so nothing is lost.")
            break
        store.write(new)
        history.append((body, pos, kind, guessed))
        counts[kind] += 1
        body = new
        pos += 1
    say("")
    say(f"Done: {counts['checked']} checked, {counts['noted']} noted, {counts['skipped']} skipped.")
    return counts


def option(args, flag):
    """The value after `flag`, removed from args, or None."""
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        sys.exit(__doc__)
    value = args.pop(i + 1)
    args.pop(i)
    return value


def main():
    args, dry_run, folder = sys.argv[1:], False, None
    shots_dir, app, expect = None, None, None
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
    shots_dir, tb_app, expect = option(args, "--shots"), option(args, "--thunderbird"), option(args, "--expect")
    real = "--real-account" in args
    if real:
        args.remove("--real-account")
    if bool(shots_dir) != bool(tb_app) or ((expect or real) and not shots_dir):
        sys.exit("--shots and --thunderbird go together, and --expect and --real-account need them.")
    if len(args) != 1:
        sys.exit(__doc__)
    app, shots = None, None
    try:
        path, label = parse_url(args[0])
        if folder:
            app = WebApp(folder)
            app.start()
            print(f"Web app: {app.url}")
            if not os.path.isfile(os.path.join(WEB, "sumo_lint_wasm.wasm")):
                print("The linter is not built, so the page shows only the preview. Run tools/build-web.sh.")
            webbrowser.open(app.url)
        if shots_dir:
            os.makedirs(shots_dir, exist_ok=True)
            print("Starting a separate Thunderbird for the screenshots…")
            shots = Shots(shots_dir, tb_app, expect, real=real)
            print(f"Thunderbird {shots.version}: screenshots go to {shots_dir}")
        walk(GitHub(path, dry_run), label, show=app.show if app else None,
             use_guess=app.use_guess if app else None, shots=shots.show if shots else None,
             confirm=app.confirm if app else None)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Every answer so far is saved.")
    finally:
        if app:
            app.stop()
        if shots:
            shots.stop()


if __name__ == "__main__":
    main()
