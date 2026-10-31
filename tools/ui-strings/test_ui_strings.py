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
import l10n_tables  # noqa: E402
import propose_edits  # noqa: E402
import shipped_search  # noqa: E402

CSV = os.path.join(HERE, "tb-desktop-settings-account-settings-changes-158-and-newer.csv")
_BUILT = []


def built():
    """compare.build takes seconds, so the tests share one result."""
    if not _BUILT:
        _BUILT.append(compare.build(CSV))
    return _BUILT[0]


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
        # A slight paraphrase of a long text matches; a different text does not.
        self.assertTrue(
            compare.matches(
                "choose the languages to display menus, messages, and notifications from thunderbird",
                "choose the languages used to display menus, messages, and notifications from thunderbird",
            )
        )
        self.assertFalse(
            compare.matches("newest messages at the top of the list", "oldest messages at the end of the folder")
        )


class FormatOnly(unittest.TestCase):
    def test_same_text_ignores_format(self):
        same = compare.same_text
        self.assertEqual(same("Use %S (default)"), same("Use { $appName } (default)"))
        self.assertEqual(same("What's up?"), same("What\u2019s up?"))
        self.assertEqual(same("Preview in %S"), same("Preview in Thunderbird"))  # Roland, #24
        self.assertEqual(same("&quot;Sent&quot; Folder on:"), same('"Sent" Folder on:'))
        self.assertNotEqual(same("Restore Default"), same("Restore default"))  # case is a change

    def test_has_words(self):
        self.assertFalse(compare.has_words("(%1$S)"))
        self.assertFalse(compare.has_words("%1$S %2$S"))
        self.assertTrue(compare.has_words("%S content"))

    def test_format_only_moves_leave_the_tables(self):
        rows = l10n_tables.rows_for(("153.6.0", "159.0", "160.0"), built(), "settings")
        cells = [c for r in rows for c in r]
        for gone in ("Use %S (default)", "Preview in %S", "What's up?", "(%1$S)"):
            self.assertFalse(any(gone in c for c in cells), gone)


class ShippedSearch(unittest.TestCase):
    def test_placeholder_needs_three_words(self):
        self.assertIsNone(shipped_search.pattern("%S content")[0])
        rx, words = shipped_search.pattern("Use { $appName } as the default app")
        self.assertEqual(words, 5)
        self.assertTrue(rx.search("use thunderbird as the default app"))

    def test_quoted_form_drops_ellipsis_colon_and_bold(self):
        self.assertEqual(shipped_search.as_quoted("Config Editor…"), "config editor")
        self.assertEqual(shipped_search.as_quoted("'''No proxy for:'''"), "no proxy for")

    def test_text_still_shown_is_not_a_change(self):
        # Settings kept the button "Return Receipts…" while the dialog title
        # became "Read receipts", so "Return Receipts" is no evidence.
        found = shipped_search.changes(built())
        self.assertNotIn("Return Receipts", found["settings", 1])
        self.assertIn("Use autoscrolling", found["settings", 1])
        self.assertIn("Security Settings", found["account-settings", 2])

    def test_android_articles_are_not_searched(self):
        docs = shipped_search.corpus()
        self.assertFalse(any("stop-screen-brightness-dimming-thunderbird-android" in p for p in docs))
        self.assertTrue(any(p.endswith("/advanced-panel-settings-in-thunderbird.wiki") for p in docs))

    def test_reports_are_up_to_date(self):
        for win, text in shipped_search.reports(built()).items():
            with open(os.path.join(HERE, f"affected-{win}.md"), encoding="utf-8") as f:
                self.assertEqual(f.read(), text, f"affected-{win}.md is stale: run shipped_search.py")


class ProposeEdits(unittest.TestCase):
    def test_comment_never_lands_inside_a_macro_or_link(self):
        text = "click {button Clear Now}: frees space"
        self.assertEqual(propose_edits.after_markup(text, text.index("Now") + 3), text.index("}") + 1)
        link = "see [http://example.com Proxy settings] here"
        self.assertEqual(propose_edits.after_markup(link, link.index("settings") + 8), link.index("]") + 1)
        self.assertEqual(propose_edits.after_markup("plain text", 5), 5)

    def test_check_comment_is_well_formed(self):
        c = propose_edits.check("A -- B", "C", "heading")
        self.assertTrue(c.startswith("<!-- CHECK 159, heading:") and c.endswith(" -->"))
        self.assertNotIn("--", c[4:-3])

    def test_one_for_one_is_replaced_and_both_versions_kept(self):
        table = propose_edits.pairs(built())
        self.assertEqual(table["Use autoscrolling"], ("Enable auto-scrolling", True))
        src, out, rows = propose_edits.propose(
            "advanced-panel-settings-in-thunderbird", {"Use autoscrolling": [27]}, table
        )
        self.assertEqual(len(src), len(out))
        bold = "'" * 3
        self.assertTrue(out[26].startswith(f"* {{for not tb159}}{bold}Use autoscrolling{bold}"))
        self.assertIn(f"{{/for}}{{for tb159}}{bold}Enable auto-scrolling{bold}", out[26])


class Committed(unittest.TestCase):
    def test_tables_are_up_to_date(self):
        b = built()
        for fmt, ext in (("md", ".md"), ("mediawiki", ".mediawiki")):
            with open(os.path.join(HERE, "string-versions" + ext), encoding="utf-8") as f:
                self.assertEqual(
                    f.read(),
                    compare.render(fmt, b, os.path.basename(CSV)),
                    f"string-versions{ext} is stale: run compare.py",
                )

    def test_start_page_maps_to_record_1(self):
        key_recs = built()[4]
        old = ("localization/en-US/messenger/preferences/preferences.ftl", "start-page-label.label")
        new = ("localization/en-US/messenger/preferences/preferences.ftl", "show-start-page-label.label")
        self.assertIn(1, key_recs[old])
        self.assertIn(1, key_recs[new])


class Localizer(unittest.TestCase):
    def test_platform_variants_are_spelled_out(self):
        v = "{ PLATFORM() ->\n[macos] Choose…\n*[other] Browse…\n}"
        self.assertEqual(l10n_tables.show(v, {}), "Choose… (macOS) / Browse… (Windows, Linux)")

    def test_start_page_is_one_paired_row(self):
        rows = l10n_tables.rows_for(("153.6.0", "159.0"), built(), "settings")
        self.assertIn(
            [
                "When Thunderbird launches, show the Start Page in the message area",
                "Show the Start Page when Thunderbird opens",
            ],
            rows,
        )

    def test_unchanged_text_is_left_out(self):
        # "Empty Trash on Exit" is the same in all three versions.
        for versions in l10n_tables.TABLES:
            for win, _ in l10n_tables.WINDOWS:
                rows = l10n_tables.rows_for(versions, built(), win)
                self.assertFalse(any("Empty Trash on Exit" in c for r in rows for c in r))
                self.assertTrue(all(len(set(r)) > 1 for r in rows))

    def test_changed_words_are_bold_in_the_version_that_changed(self):
        three = ("153.6.0", "159.0", "160.0")
        changed_in, cells = l10n_tables.decorate(three, ["Restore Default", "Restore default", "Restore default"])
        self.assertEqual(changed_in, "159")
        self.assertEqual(cells[1], ("text", [("Restore", False), ("default", True)], True))
        self.assertEqual(cells[2], ("same", "159"))

    def test_same_as_names_the_first_version_with_the_text(self):
        three = ("153.6.0", "159.0", "160.0")
        changed_in, cells = l10n_tables.decorate(three, ["A b", "A b", "A c"])
        self.assertEqual(changed_in, "160")
        self.assertEqual(cells[1], ("same", "153"))
        changed_in, cells = l10n_tables.decorate(three, ["—", "—", "New text"])
        self.assertEqual(cells[1][1], [("—", False)])  # still absent is "—", not "same as"

    def test_no_word_marks_for_new_removed_or_multiline(self):
        self.assertEqual(l10n_tables.mark_words("—", "New text"), [("New text", False)])
        self.assertEqual(l10n_tables.mark_words("Old", "—"), [("—", False)])
        self.assertEqual(l10n_tables.mark_words("A\nB", "A\nC"), [("A\nC", False)])

    def test_rendered_markers(self):
        rows = [["Restore Default", "Restore default", "Restore default"]]
        three = ("153.6.0", "159.0", "160.0")
        md = l10n_tables.render("md", three, rows, "Settings")
        self.assertIn("| 159 | Restore Default | Restore **default** | *same as 159* |", md)
        wiki = l10n_tables.render("mediawiki", three, rows, "Settings")
        self.assertIn(
            "| 159 || Restore Default || style=\"background:#fff3c4\" | Restore \'\'\'default\'\'\' || \'\'same as 159\'\'",
            wiki,
        )
        two = l10n_tables.render("md", ("153.6.0", "159.0"), [rows[0][:2]], "Settings")
        self.assertIn("| Restore Default | Restore **default** |", two)
        self.assertNotIn("Changed in", two)

    def test_window_is_decided_by_file(self):
        account = [
            "chrome/en-US/locale/en-US/messenger/am-offline.dtd",
            "chrome/en-US/locale/en-US/messenger/prefs.properties",
            "localization/en-US/messenger/preferences/am-copies.ftl",
            "localization/en-US/messenger/openpgp/openpgp.ftl",
            "localization/en-US/messenger/accountManager.ftl",
            "localization/en-US/messenger/accountSettings.ftl",
            "localization/en-US/messenger/retention.ftl",
        ]
        settings = [
            "localization/en-US/messenger/preferences/preferences.ftl",
            "localization/en-US/messenger/preferences/receipts.ftl",
            "localization/en-US/calendar/preferences.ftl",
            "chrome/en-US/locale/en-US/messenger/preferences/preferences.properties",
            "localization/en-US/toolkit/preferences/preferences.ftl",
            "localization/en-US/messenger/aboutDialog.ftl",
        ]
        for f in account:
            self.assertEqual(l10n_tables.window((f, "x")), "account-settings", f)
        for f in settings:
            self.assertEqual(l10n_tables.window((f, "x")), "settings", f)

    def test_shared_text_is_judged_per_window(self):
        # "Disk Space" is in both windows. Settings renamed it in 159
        # ("Temporary storage"). Account Settings still shows it in 160, as
        # the name of the account-tree page, so its tables must not list it.
        def has(versions, win):
            return any("Disk Space" in r[0] for r in l10n_tables.rows_for(versions, built(), win))

        for versions in l10n_tables.TABLES:
            self.assertTrue(has(versions, "settings"), versions)
            self.assertFalse(has(versions, "account-settings"), versions)

    def test_tables_are_up_to_date(self):
        for versions in l10n_tables.TABLES:
            for win, title in l10n_tables.WINDOWS:
                rows = l10n_tables.rows_for(versions, built(), win)
                stem = os.path.join(HERE, "strings-" + "-".join(versions) + "-" + win)
                for fmt, ext in (("md", ".md"), ("mediawiki", ".mediawiki")):
                    with open(stem + ext, encoding="utf-8") as f:
                        self.assertEqual(
                            f.read(),
                            l10n_tables.render(fmt, versions, rows, title),
                            f"{os.path.basename(stem)}{ext} is stale: run l10n_tables.py",
                        )

if __name__ == "__main__":
    unittest.main()
