# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for extract.py and compare.py. Standard library only.

    python3 tools/ui-strings/test_ui_strings.py

The last test regenerates string-versions.md from the committed strings and
CSV, and fails if the committed copy differs, so the tables never go stale.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compare  # noqa: E402
import extract  # noqa: E402

CSV = os.path.join(HERE, "tb-desktop-settings-account-settings-changes-158-and-newer.csv")


class Parsers(unittest.TestCase):
    def test_ftl_message_attribute_and_multiline(self):
        text = (
            "# comment\n"
            "start-page-label =\n"
            "    .label = When { -brand-short-name } launches\n"
            "    .accesskey = W\n"
            "\n"
            "intro = First line\n"
            "    second line\n"
            "-brand-short-name = Thunderbird\n"
        )
        got = dict(extract.parse_ftl(text))
        self.assertEqual(got["start-page-label.label"], "When { -brand-short-name } launches")
        self.assertEqual(got["start-page-label.accesskey"], "W")
        self.assertEqual(got["intro"], "First line\nsecond line")
        self.assertEqual(got["-brand-short-name"], "Thunderbird")
        self.assertNotIn("start-page-label", got)  # no value of its own

    def test_dtd_and_properties(self):
        dtd = '<!-- x -->\n<!ENTITY emptyTrashOnExit.label "Empty Trash on Exit">\n'
        self.assertEqual(dict(extract.parse_dtd(dtd)), {"emptyTrashOnExit.label": "Empty Trash on Exit"})
        props = "# c\nkey = Value: with colon\nother=x\n"
        self.assertEqual(dict(extract.parse_properties(props)), {"key": "Value: with colon", "other": "x"})

    def test_escape_round_trip(self):
        v = "a\\b\tc\nd"
        self.assertEqual(compare.unescape(extract.escape(v)), v)

    def test_scope(self):
        self.assertTrue(extract.in_scope("localization/en-US/messenger/preferences/preferences.ftl"))
        self.assertTrue(extract.in_scope("chrome/en-US/locale/en-US/messenger/am-copies.dtd"))
        self.assertFalse(extract.in_scope("localization/en-US/messenger/messenger.ftl"))


class Matching(unittest.TestCase):
    def test_brand_and_selector_variants(self):
        v = "{ PLATFORM() ->\n[macos] Play the following sound file:\n*[other] Play a sound\n}"
        self.assertEqual(compare.variants(v, {}), ["Play the following sound file:", "Play a sound"])
        self.assertEqual(
            compare.variants("Show the Start Page when { -brand-short-name } opens", {}),
            ["Show the Start Page when Thunderbird opens"],
        )

    def test_fragments(self):
        cell = (
            "Checkbox: Always perform this check when starting Daily\n"
            "Radio button: Other | Dropdown\n"
            "• [ Always ▾ ]\n"
            "Title: Scrolling\n"
        )
        self.assertEqual(compare.fragments(cell), ["always perform this check when starting thunderbird"])

    def test_matches(self):
        self.assertTrue(compare.matches("use autoscrolling", "use autoscrolling"))
        # Containment needs four words in the shorter text.
        self.assertTrue(compare.matches("choose the languages to", "choose the languages to display menus"))
        self.assertFalse(compare.matches("learn more", "learn more about this"))


class Committed(unittest.TestCase):
    def test_tables_are_up_to_date(self):
        built = compare.build(CSV)
        for fmt, ext in (("md", ".md"), ("mediawiki", ".mediawiki")):
            with open(os.path.join(HERE, "string-versions" + ext), encoding="utf-8") as f:
                self.assertEqual(
                    f.read(),
                    compare.render(fmt, built, os.path.basename(CSV)),
                    f"string-versions{ext} is stale: run compare.py",
                )

    def test_start_page_maps_to_record_1(self):
        built = compare.build(CSV)
        key_recs = built[4]
        old = ("localization/en-US/messenger/preferences/preferences.ftl", "start-page-label.label")
        new = ("localization/en-US/messenger/preferences/preferences.ftl", "show-start-page-label.label")
        self.assertIn(1, key_recs[old])
        self.assertIn(1, key_recs[new])


if __name__ == "__main__":
    unittest.main()
