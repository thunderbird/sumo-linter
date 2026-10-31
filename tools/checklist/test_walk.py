# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for walk.py. Standard library only; GitHub is replaced by a fake store.

    python3 tools/checklist/test_walk.py
"""

import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
