# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for walk.py. Standard library only; GitHub is replaced by a fake store.

    python3 tools/checklist/test_walk.py
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import walk  # noqa: E402

BODY = """## Checklist

### article-one

- [ ] Open the edit page

**Confirm the guessed 159 text** (2).

- [ ] Line 21: "Old" → "New"
- [x] Line 42: already done
- [ ] Line 104: "A" → "B"

```
- [ ] not an item, it is in a code block
```

### Evaluate

- [ ] Go or no-go?
"""


class Store:
    """A fake GitHub body. `other` simulates an edit in the browser."""

    def __init__(self, body):
        self.body, self.writes, self.dry_run, self.other, self.reads = body, [], False, None, 0

    def read(self):
        self.reads += 1
        if self.other and self.reads > 1:  # after the walk has started
            self.body, self.other = self.other(self.body), None
        return self.body

    def write(self, body):
        self.body = body
        self.writes.append(body)


def run(store, answers):
    queue = list(answers)
    said = []
    counts = walk.walk(store, "test", ask=lambda prompt: queue.pop(0), say=said.append)
    return counts, said


class Parsing(unittest.TestCase):
    def test_url(self):
        self.assertEqual(
            walk.parse_url("https://github.com/thunderbird/sumo-linter/issues/28#issuecomment-6549440976")[0],
            "repos/thunderbird/sumo-linter/issues/comments/6549440976",
        )
        self.assertEqual(walk.parse_url("https://github.com/o/r/issues/7")[0], "repos/o/r/issues/7")
        with self.assertRaises(ValueError):
            walk.parse_url("https://example.com/")

    def test_items_and_context(self):
        its = walk.items(BODY)
        self.assertEqual([it["checked"] for it in its], [False, False, True, False, False])
        self.assertEqual(its[1]["context"], "article-one / Confirm the guessed 159 text")
        self.assertEqual(its[4]["context"], "Evaluate")
        self.assertFalse(any("code block" in it["text"] for it in its))

    def test_check_and_note(self):
        line = walk.items(BODY)[1]["line"]
        self.assertIn('- [x] Line 21: "Old" → "New"', walk.check(BODY, line))
        noted = walk.add_note(BODY, line, "wrong:\n159 says   Other")
        self.assertIn('- [ ] Line 21: "Old" → "New"\n  - Note: wrong: 159 says Other\n', noted)
        twice = walk.add_note(noted, line, "second")
        self.assertIn("  - Note: wrong: 159 says Other\n  - Note: second\n", twice)
        self.assertEqual(walk.items(twice)[1]["notes"], ["wrong: 159 says Other", "second"])
        self.assertEqual(len(walk.items(twice)), 5)  # notes are not items

    def test_readable(self):
        self.assertEqual(walk.readable("see [the report](https://x/y.md) and `code`"), "see the report <https://x/y.md> and code")


class Walking(unittest.TestCase):
    def test_check_note_skip_and_quit_save_each_answer(self):
        store = Store(BODY)
        counts, _ = run(store, ["c", "n", "159 says Other", "s", "q"])
        self.assertEqual(counts, {"checked": 1, "noted": 1, "skipped": 1})
        self.assertEqual(len(store.writes), 2)  # saved after each answer, not at the end
        self.assertIn("- [x] Open the edit page", store.body)
        self.assertIn('- [ ] Line 21: "Old" → "New"\n  - Note: 159 says Other', store.body)
        self.assertIn('- [ ] Line 104: "A" → "B"', store.body)

    def test_undo_restores_the_previous_text(self):
        store = Store(BODY)
        counts, said = run(store, ["n", "a note", "u", "c", "q"])
        self.assertIn("Undone.", said)
        self.assertNotIn("Note: a note", store.body)
        self.assertIn("- [x] Open the edit page", store.body)  # undo went back to item 1
        self.assertEqual(counts["noted"], 0)

    def test_rerun_continues_with_unchecked_items(self):
        store = Store(BODY)
        run(store, ["c", "c", "c", "c"])
        self.assertEqual([it["checked"] for it in walk.items(store.body)], [True] * 5)
        counts, said = run(store, [])
        self.assertIn("test: 0 unchecked of 5 items.", said)

    def test_stops_if_the_text_changed_on_github(self):
        store = Store(BODY)
        store.other = lambda b: b + "\nedited in the browser\n"
        counts, said = run(store, ["c"])
        self.assertTrue(any("changed on GitHub" in s for s in said))
        self.assertEqual(store.writes, [])

    def test_empty_note_and_bad_answer_save_nothing(self):
        store = Store(BODY)
        counts, said = run(store, ["n", "", "x", "q"])
        self.assertIn("Empty note: nothing saved.", said)
        self.assertIn("Please answer c, n, s, u or q.", said)
        self.assertEqual(store.writes, [])


class Targets(unittest.TestCase):
    def test_line_and_quoted_text(self):
        its = walk.items(BODY)
        self.assertEqual(walk.target(its[1]), {"file": "article-one.wiki", "line": 21, "find": "Old"})
        self.assertEqual(walk.target(its[0]), {"file": "article-one.wiki", "line": None, "find": None})

    def test_curly_quotes_inside_and_a_comment_after(self):
        def t(text):
            return walk.target({"heading": "a", "text": text})

        self.assertEqual(t('Line 21: "Move it to my “Sent” folder" → "Move to Sent folder"')["find"], "Move it to my “Sent” folder")
        self.assertEqual(t('Line 18: "Leave it" (possible 159 text: "removed")')["find"], "Leave it")
        self.assertEqual(t('Line 31: "System Integration"')["find"], "System Integration")
        self.assertEqual(t("Line 9: no quote"), {"file": "a.wiki", "line": 9, "find": None})
        self.assertEqual(t("See line 9")["line"], None)

    def test_heading_that_is_not_a_file_name(self):
        for heading in ("Evaluate this", "", "../x", ".hidden"):
            self.assertIsNone(walk.target({"heading": heading, "text": "Line 1:"})["file"], heading)


class Guesses(unittest.TestCase):
    def test_guess_is_offered_only_for_real_text(self):
        def g(text):
            return walk.guess({"heading": "a", "text": text})

        self.assertEqual(g('Line 41: "Enable Global Search and Indexer" (possible 159 text: "Search & performance")'), "Search & performance")
        self.assertEqual(g('Line 31: "System Integration" (possible 159 text: "System settings")'), "System settings")
        self.assertIsNone(g('Line 18: "Leave it" (possible 159 text: "removed")'))
        self.assertIsNone(g('Line 21: "Old" → "New"'))
        self.assertIsNone(g("Search the edit box for CHECK"))

    def test_g_checks_and_notes_only_after_the_page_says_it_worked(self):
        body = '### article-one\n\n- [ ] Line 4: "Old" (possible 159 text: "New")\n'
        answers = [(False, "the text before the comment is not \"Old\"."), (True, "")]
        store = Store(body)
        counts, said = run_with(store, ["g", "g", "q"], use_guess=lambda it: answers.pop(0))
        self.assertIn('  g: use the guess "New"', said)
        self.assertIn('The guess was not used: the text before the comment is not "Old". Nothing saved.', said)
        self.assertEqual(len(store.writes), 1)
        self.assertIn('- [x] Line 4: "Old" (possible 159 text: "New")\n  - Note: Used the guess "New".', store.body)
        self.assertEqual(counts["checked"], 1)
        self.assertIn('Used the guess "New" in the web app.', said)

    def test_g_with_a_comment_keeps_its_case(self):
        body = '### a\n\n- [ ] Line 4: "Old" (possible 159 text: "New")\n'
        store = Store(body)
        run_with(store, ["G  Then I changed it to Newer  "], use_guess=lambda it: (True, ""))
        self.assertIn('  - Note: Used the guess "New". Then I changed it to Newer\n', store.body)

    def test_a_comment_after_another_answer_saves_nothing(self):
        store = Store(BODY)
        counts, said = run(store, ["c looks fine", "q"])
        self.assertIn("Only g takes a comment after it. For a note, answer n.", said)
        self.assertEqual(store.writes, [])

    def test_g_is_not_an_answer_without_a_guess_or_without_web(self):
        body = '### article-one\n\n- [ ] Line 4: "Old" (possible 159 text: "New")\n'
        store = Store(body)
        counts, said = run_with(store, ["g", "q"])
        self.assertIn("Please answer c, n, s, u or q.", said)
        self.assertEqual(store.writes, [])

    def test_undo_of_a_guess_points_at_cmd_z(self):
        body = '### a\n\n- [ ] Line 4: "Old" (possible 159 text: "New")\n- [ ] Next\n'
        store = Store(body)
        counts, said = run_with(store, ["g", "u", "q"], use_guess=lambda it: (True, ""))
        self.assertIn("Undone. Cmd+Z in the web app takes back the guess.", said)
        self.assertEqual(store.body, body)


def run_with(store, answers, **kwargs):
    queue = list(answers)
    said = []
    counts = walk.walk(store, "test", ask=lambda prompt: queue.pop(0), say=said.append, **kwargs)
    return counts, said


class Web(unittest.TestCase):
    """The local server, over real HTTP on 127.0.0.1."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.web, self.dir = os.path.join(self.root, "web"), os.path.join(self.root, "proposals")
        os.mkdir(self.web)
        os.mkdir(self.dir)
        with open(os.path.join(self.web, "index.html"), "w") as f:
            f.write("page")
        with open(os.path.join(self.dir, "article-one.wiki"), "w", encoding="utf-8") as f:
            f.write("=“Sent”=\n")
        with open(os.path.join(self.root, "secret.wiki"), "w") as f:
            f.write("outside")
        self.app = walk.WebApp(self.dir, web=self.web)
        self.app.start()
        self.base = self.app.url.split("/?")[0]

    def tearDown(self):
        self.app.stop()
        shutil.rmtree(self.root)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    def test_serves_the_page_and_the_article(self):
        self.assertTrue(self.app.url.startswith("http://127.0.0.1:"))
        self.assertEqual(self.get("/?walk=1"), (200, "page"))
        self.assertEqual(self.get("/walk/file/article-one.wiki"), (200, "=“Sent”=\n"))

    def test_serves_no_other_file(self):
        for path in ("/walk/file/secret.wiki", "/walk/file/..%2Fsecret.wiki", "/walk/file/../secret.wiki",
                     "/walk/file/missing.wiki", "/walk/file/"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as e:
                self.get(path)
            self.assertEqual(e.exception.code, 404, path)

    def test_events_send_the_current_item_then_each_change(self):
        its = walk.items(BODY)
        self.assertIsNone(self.app.show(its[1]))
        with urllib.request.urlopen(self.base + "/walk/events", timeout=5) as r:
            self.assertEqual(r.headers["Content-Type"], "text/event-stream")
            first = r.readline().decode()
            self.assertEqual(json.loads(first[len("data: "):]), {"file": "article-one.wiki", "line": 21, "find": "Old"})
            r.readline()  # the blank line that ends the event
            self.app.show(its[3])
            self.assertEqual(json.loads(r.readline().decode()[len("data: "):])["line"], 104)

    def test_a_missing_file_is_reported_and_not_sent(self):
        said = self.app.show({"heading": "no-such-article", "text": "Line 3:"})
        self.assertIn("no file", said)
        self.assertIsNone(self.app.current)
        self.assertIsNone(self.app.show({"heading": "Evaluate this", "text": "Go?"}))
        self.assertIsNone(self.app.current)

    def post(self, data):
        req = urllib.request.Request(self.base + "/walk/result", data=json.dumps(data).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status

    def test_use_guess_sends_the_edit_and_waits_for_the_page(self):
        item = {"heading": "article-one", "text": 'Line 1: "Sent" (possible 159 text: "Kept")'}

        def page():
            with self.app.changed:
                self.app.changed.wait_for(lambda: isinstance(self.app.current, dict) and "edit" in self.app.current, timeout=5)
                edit = self.app.current["edit"]
            self.assertEqual((edit["old"], edit["guess"]), ("Sent", "Kept"))
            self.assertEqual(self.post({"id": edit["id"], "ok": False, "message": "no comment."}), 204)

        threading.Thread(target=page).start()
        self.assertEqual(self.app.use_guess(item), (False, "no comment."))
        self.assertNotIn("edit", self.app.current)  # a page that connects later does nothing

    def test_no_answer_is_a_failure(self):
        item = {"heading": "article-one", "text": 'Line 1: "Sent" (possible 159 text: "Kept")'}
        ok, message = self.app.use_guess(item, timeout=0.2)
        self.assertFalse(ok)
        self.assertIn("did not answer", message)

    def test_a_bad_result_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post({"ok": True})
        self.assertEqual(e.exception.code, 400)

    def test_walk_calls_show_before_each_question(self):
        shown = []
        queue = ["s", "s", "q"]
        said = []
        walk.walk(Store(BODY), "t", ask=lambda p: queue.pop(0), say=said.append,
                  show=lambda it: shown.append(it["text"]) or "extra line")
        self.assertEqual(shown, ["Open the edit page", 'Line 21: "Old" → "New"', 'Line 104: "A" → "B"'])
        self.assertEqual(said.count("extra line"), 3)


# A stand-in for `tb_shot.py session`: it says it is ready, then answers each
# request, with a failure for the text "missing".
FAKE_SESSION = r"""
import json, sys
print(json.dumps({"ok": True, "ready": True, "version": "159.0"}), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    if req["text"] == "missing":
        print(json.dumps({"ok": False, "error": "no setting with the text \"missing\""}), flush=True)
    else:
        print(json.dumps({"ok": True, "path": "shots/" + req["name"] + ".png",
                          "where": "Settings, paneGeneral", "text": req["text"]}), flush=True)
"""


class Screenshots(unittest.TestCase):
    def item(self, text, heading="article-one"):
        return {"text": text, "heading": heading}

    def test_the_text_to_find(self):
        self.assertEqual(walk.shot_text(self.item('Line 27: "Use autoscrolling" → "Enable auto-scrolling"')),
                         "Enable auto-scrolling")
        self.assertEqual(walk.shot_text(self.item('Line 43: "Old" (possible 159 text: "Use graphics acceleration")')),
                         "Use graphics acceleration")
        self.assertIsNone(walk.shot_text(self.item('Line 18: "Old" (possible 159 text: "removed")')))
        self.assertIsNone(walk.shot_text(self.item("Open the edit page")))

    def test_an_explicit_shot_wins(self):
        self.assertEqual(walk.shot_text(self.item('Line 1: "A" → "B" (shot: "Another label")')), "Another label")
        self.assertEqual(walk.shot_text(self.item('Line 18: "Old" (possible 159 text: "removed") (shot: "X")')), "X")

    def shots(self):
        s = walk.Shots("shots", None, command=[sys.executable, "-c", FAKE_SESSION])
        self.addCleanup(s.stop)
        return s

    def test_session_starts_and_answers(self):
        s = self.shots()
        self.assertEqual(s.version, "159.0")
        self.assertEqual(s.show(self.item('Line 27: "A" → "Enable auto-scrolling"'), 3),
                         "  screenshot: shots/article-one-item-3.png (Settings, paneGeneral)")
        self.assertEqual(s.show(self.item('Line 1: "A" → "missing"'), 4),
                         '  no screenshot: no setting with the text "missing"')
        self.assertIsNone(s.show(self.item("Open the edit page"), 5))

    def test_each_item_is_taken_once(self):
        s = self.shots()
        first = s.show(self.item('Line 27: "A" → "B"'), 3)
        s.proc.stdin.close()  # a second request would now fail
        self.assertEqual(s.show(self.item('Line 27: "A" → "B"'), 3), first)

    def test_a_session_that_does_not_start_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "did not start Thunderbird"):
            walk.Shots("shots", None, command=[sys.executable, "-c", "print('Thunderbird is version 160.0')"])

    def test_walk_shows_each_items_screenshot(self):
        s = self.shots()
        queue, said = ["s", "s", "q"], []
        walk.walk(Store(BODY), "t", ask=lambda p: queue.pop(0), say=said.append, shots=s.show)
        shots = [line for line in said if "screenshot" in line]
        # Item 1 has no 159 text; items 2 and 4 ("New", "B") do. Numbers are
        # positions in the whole list, so they do not change as items are checked.
        self.assertEqual(shots, ["  screenshot: shots/article-one-item-2.png (Settings, paneGeneral)",
                                 "  screenshot: shots/article-one-item-4.png (Settings, paneGeneral)"])


if __name__ == "__main__":
    unittest.main()
