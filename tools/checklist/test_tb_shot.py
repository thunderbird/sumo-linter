# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for tb_shot.py (#39). Standard library only, and no Thunderbird.

    python3 tools/checklist/test_tb_shot.py

What needs Thunderbird, finding a setting and drawing it, was tested by hand
against Thunderbird 159 on macOS; see #39. The tour's clicks and screenshots
were tested by hand against 160; see #55 and #56. This file tests the parts that can
break without anyone noticing: the Marionette protocol, the version check, the
prefs that keep a dialog from waiting for a click, and the session protocol
that walk.py speaks.
"""

import io
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tb_shot  # noqa: E402


class FakeMarionette:
    """A Marionette server on localhost that answers from a script."""

    def __init__(self, answers):
        self.answers, self.received = answers, []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        conn, _ = self.server.accept()
        self.server.close()
        conn.sendall(tb_shot.frame({"applicationType": "gecko", "marionetteProtocol": 3}))
        f = conn.makefile("rb")
        try:
            while True:
                kind, msg_id, name, params = tb_shot.read_packet(f.read)
                self.received.append((name, params))
                error, result = self.answers.get(name, (None, {"value": None}))
                # An unrelated packet first, which the client must skip.
                conn.sendall(tb_shot.frame([1, msg_id + 1000, None, {}]))
                conn.sendall(tb_shot.frame([1, msg_id, error, result]))
        except EOFError:
            conn.close()


class Protocol(unittest.TestCase):
    def test_frame_is_length_colon_json(self):
        self.assertEqual(tb_shot.frame([0, 1, "X", {}]), b'15:[0, 1, "X", {}]')

    def test_read_packet_reads_a_body_in_pieces(self):
        data = io.BytesIO(tb_shot.frame({"a": "é" * 50}))
        pieces = lambda n: data.read(min(n, 7))  # noqa: E731
        self.assertEqual(tb_shot.read_packet(pieces), {"a": "é" * 50})

    def test_read_packet_reports_a_closed_connection(self):
        with self.assertRaises(EOFError):
            tb_shot.read_packet(io.BytesIO(b"12:{").read)

    def test_commands_and_results(self):
        fake = FakeMarionette({"WebDriver:ExecuteScript": (None, {"value": 42})})
        m = tb_shot.Marionette(fake.port)
        self.assertEqual(m.js("return 42", "x"), 42)
        self.assertEqual(fake.received[-1], ("WebDriver:ExecuteScript", {"script": "return 42", "args": ["x"]}))
        m.close()

    def test_an_error_is_an_exception(self):
        fake = FakeMarionette({"Marionette:SetContext": ({"error": "unsupported operation",
                                                           "message": "System access is required."}, None)})
        m = tb_shot.Marionette(fake.port)
        with self.assertRaisesRegex(RuntimeError, "System access is required"):
            m.cmd("Marionette:SetContext", {"value": "chrome"})
        m.close()

    def test_no_server_is_a_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "did not open Marionette"):
            tb_shot.Marionette(tb_shot.free_port(), timeout=1)


class Application(unittest.TestCase):
    def make_app(self, version, bundle=True):
        root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        if bundle:
            app = os.path.join(root, "Thunderbird.app")
            os.makedirs(os.path.join(app, "Contents", "Resources"))
            ini = os.path.join(app, "Contents", "Resources", "application.ini")
        else:
            app = os.path.join(root, "thunderbird")
            open(app, "w").close()
            ini = os.path.join(root, "application.ini")
        with open(ini, "w", encoding="utf-8") as f:
            f.write(f"[App]\nVendor=Mozilla\nName=Thunderbird\nVersion={version}\n")
        return app

    def test_the_version_comes_from_application_ini(self):
        # The folder name says 140; the file says 153.6.0, as on Roland's Mac.
        self.assertEqual(tb_shot.version_of(self.make_app("153.6.0")), "153.6.0")
        self.assertEqual(tb_shot.version_of(self.make_app("159.0", bundle=False)), "159.0")

    def test_no_application_ini_is_no_version(self):
        self.assertIsNone(tb_shot.version_of("/nowhere/Thunderbird.app"))

    def test_version_matches(self):
        self.assertTrue(tb_shot.version_matches("159.0", "159"))
        self.assertTrue(tb_shot.version_matches("159.0.1", "159.0"))
        self.assertFalse(tb_shot.version_matches("1590.0", "159"))
        self.assertFalse(tb_shot.version_matches("160.0", "159"))
        self.assertFalse(tb_shot.version_matches(None, "159"))

    def test_a_wrong_version_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "is version 160.0, not 159"):
            tb_shot.Thunderbird(self.make_app("160.0"), expect="159")

    def test_the_program_in_a_bundle(self):
        self.assertEqual(tb_shot.binary_of("/A/Thunderbird.app"), "/A/Thunderbird.app/Contents/MacOS/thunderbird")
        self.assertEqual(tb_shot.binary_of("/usr/bin/thunderbird"), "/usr/bin/thunderbird")


class Prefs(unittest.TestCase):
    def prefs(self, **kw):
        out = {}
        for line in tb_shot.user_js(2829, **kw).splitlines():
            name, value = line[len("user_pref("):-2].split(", ", 1)
            out[json.loads(name)] = json.loads(value)
        return out

    def test_marionette_port(self):
        self.assertEqual(self.prefs()["marionette.port"], 2829)

    def test_offline_asks_nothing(self):
        # 1 is "ask" in OfflineStartup.sys.mjs: a prompt on every start that
        # waits for a click (Roland clicked "Work offline" four times).
        p = self.prefs()
        self.assertEqual(p["offline.startup_state"], 3)
        self.assertEqual(p["offline.download.download_messages"], 2)
        self.assertIs(p["offline.autoDetect"], False)

    def test_online_has_no_offline_prefs(self):
        self.assertNotIn("offline.startup_state", self.prefs(offline=False))


class RealAccount(unittest.TestCase):
    """--account real (#40): a copy of the signed-in profile, never the profile."""

    def test_the_copy_leaves_out_locks_and_caches(self):
        src = tempfile.mkdtemp()
        dst = os.path.join(tempfile.mkdtemp(), "copy")
        self.addCleanup(lambda: [__import__("shutil").rmtree(d, ignore_errors=True)
                                 for d in (src, os.path.dirname(dst))])
        for name in ("prefs.js", "logins.json", "key4.db", ".parentlock", "lock"):
            open(os.path.join(src, name), "w").close()
        os.makedirs(os.path.join(src, "cache2", "entries"))
        os.makedirs(os.path.join(src, "ImapMail", "example"))
        tb_shot.copy_profile(src, dst)
        self.assertEqual(sorted(os.listdir(dst)), ["ImapMail", "key4.db", "logins.json", "prefs.js"])

    def test_no_signed_in_profile_says_run_login(self):
        app = Application.make_app(self, "159.0")
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        open(os.path.join(app, "Contents", "MacOS", "thunderbird"), "w").close()
        with self.assertRaisesRegex(RuntimeError, "run `tb_shot.py login` first"):
            tb_shot.Thunderbird(app, account_profile=tempfile.mkdtemp())

    def test_login_prefs_have_no_marionette_and_stay_online(self):
        js = tb_shot.user_js(None, offline=False)
        self.assertNotIn("marionette", js)
        self.assertNotIn("offline.startup_state", js)

    def test_the_account_profile_is_gitignored(self):
        self.assertTrue(tb_shot.ACCOUNT_PROFILE.startswith(os.path.join(tb_shot.REPO, ".auth") + os.sep))
        with open(os.path.join(tb_shot.REPO, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("/.auth/", f.read().split())


class FakeThunderbird:
    version = "159.0"

    def shot(self, text, path):
        if text == "missing":
            raise LookupError('no setting with the text "missing"')
        with open(path, "wb") as f:
            f.write(b"png")
        return "Settings, paneGeneral", (212, 85)


class Session(unittest.TestCase):
    def run_session(self, *requests):
        out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out))
        lines = iter([*requests, ""])
        written = []
        tb_shot.session(FakeThunderbird(), out, read=lambda: next(lines), write=written.append)
        return out, [json.loads(w) for w in written]

    def test_ready_then_one_answer_per_request(self):
        out, answers = self.run_session(json.dumps({"text": "Enable auto-scrolling", "name": "a-item-3"}) + "\n")
        self.assertEqual(answers[0], {"ok": True, "ready": True, "version": "159.0"})
        self.assertEqual(answers[1]["where"], "Settings, paneGeneral")
        self.assertEqual(answers[1]["path"], os.path.join(out, "a-item-3.png"))
        self.assertTrue(os.path.isfile(answers[1]["path"]))
        self.assertEqual(len(answers), 2)

    def test_a_missing_setting_is_an_answer_not_a_crash(self):
        _, answers = self.run_session(json.dumps({"text": "missing", "name": "x"}) + "\n",
                                      json.dumps({"text": "Enable auto-scrolling", "name": "y"}) + "\n")
        self.assertEqual(answers[1], {"ok": False, "error": 'no setting with the text "missing"'})
        self.assertTrue(answers[2]["ok"])

    def test_a_bad_request(self):
        _, answers = self.run_session("not json\n", json.dumps({"name": "x"}) + "\n")
        self.assertEqual([a["ok"] for a in answers[1:]], [False, False])

    def test_a_name_cannot_leave_the_folder(self):
        out, answers = self.run_session(json.dumps({"text": "t", "name": "../../etc/x"}) + "\n")
        self.assertEqual(os.path.dirname(answers[1]["path"]), out)

    def test_safe_name(self):
        self.assertEqual(tb_shot.safe_name("article-item-3"), "article-item-3")
        self.assertEqual(tb_shot.safe_name("a/b c"), "a-b-c")
        with self.assertRaises(ValueError):
            tb_shot.safe_name("../")


class Png(unittest.TestCase):
    def test_png_size(self):
        header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 595, 93)
        self.assertEqual(tb_shot.png_size(header), (595, 93))


CATEGORIES = [{"id": "category-general", "pane": "paneGeneral", "label": "Allgemein"},
              {"id": "category-compose", "pane": "paneCompose", "label": "Verfassen"}]
ROWS = [{"id": "account1", "page": "am-main.xhtml", "label": "Mail for a|b"},
        {"id": "account1/am-server.xhtml", "page": "am-server.xhtml", "label": "Server"},
        {"id": "smtp", "page": "am-smtp.xhtml", "label": "Outgoing Server"}]


class TourSteps(unittest.TestCase):
    def test_names_come_from_panes_not_labels(self):
        steps = tb_shot.tour_steps(CATEGORIES, ROWS, "Konten")
        self.assertEqual([s["file"] for s in steps], [
            "01-settings-paneGeneral.png", "02-settings-paneCompose.png", "03-account-account1.png",
            "04-account-account1-am-server.png", "05-account-smtp.png"])

    def test_each_step_outlines_the_next_click(self):
        steps = tb_shot.tour_steps(CATEGORIES, ROWS, "Konten")
        self.assertEqual(steps[0]["next"], {"id": "category-compose", "label": "Verfassen", "part": None})
        # The last category leads to the sidebar's Account Settings link.
        self.assertEqual(steps[1]["next"], {"id": "accountButton", "label": "Konten", "part": None})
        # A tree row is clicked, and outlined, by its .container.
        self.assertEqual(steps[2]["next"], {"id": "account1/am-server.xhtml", "label": "Server", "part": ".container"})
        self.assertEqual(steps[1]["next_file"], "02-settings-paneCompose-next.png")

    def test_the_last_step_has_no_next(self):
        last = tb_shot.tour_steps(CATEGORIES, ROWS)[-1]
        self.assertIsNone(last["next"])
        self.assertIsNone(last["next_file"])

    def test_the_rows_do_not_change_the_settings_steps(self):
        # tour() shoots Settings before it knows the rows.
        before = tb_shot.tour_steps(CATEGORIES, [])
        after = tb_shot.tour_steps(CATEGORIES, ROWS)[:2]
        for b, a in zip(before, after):
            self.assertEqual((b["file"], b["next_file"], b["next"]["id"]), (a["file"], a["next_file"], a["next"]["id"]))

    def test_the_folder_is_version_and_locale(self):
        self.assertEqual(tb_shot.tour_folder("out", "160.0", "en-US"), os.path.join("out", "160.0-en-US"))

    def test_index_md_has_a_row_per_step_and_escapes_bars(self):
        md = tb_shot.index_md("160.0", "de", tb_shot.tour_steps(CATEGORIES, ROWS, "Konten"))
        rows = [line for line in md.splitlines() if line.startswith("| ") and line[2].isdigit()]
        self.assertEqual(len(rows), 5)
        self.assertIn("Account Settings › Mail for a\\|b", rows[2])
        self.assertTrue(rows[-1].endswith("| 05-account-smtp.png |  |  |  |"))


class FakeTourThunderbird:
    """The tour's view of Thunderbird, recording each screenshot."""

    version = "160.0"

    def __init__(self, states=None, unlisted=(), file_window=None):
        self.shots = []
        self.m = self
        self.states = states or {}  # item name → item_state answer
        self.unlisted = list(unlisted)
        self.file_window = file_window
        self.proc = None

    def js(self, script, *args):
        if script == tb_shot.TARGET_JS + tb_shot.SCROLL_TO_JS:
            return None
        assert script == tb_shot.ACCOUNT_BUTTON_LABEL_JS
        return "Account Settings"

    def item_state(self, target):
        default = {"exists": True, "shown": True, "disabled": False, "label": None}
        return self.states.get(target.get("id") or target.get("css"), default)

    def unlisted_items(self, targets, frame):
        found, self.unlisted = self.unlisted, []
        return found

    def item_shots(self, target, before, after):
        self.shots.append(("item", os.path.basename(before), os.path.basename(after), target.get("id")))
        for path in (before, after):
            with open(path, "wb") as f:
                f.write(b"png")
        return "tab dialog"

    def click_for_file_dialog(self, target, capture):
        self.shots.append(("file", target["id"]))
        return capture(self.file_window)

    def locale(self):
        return "en-US"

    def open_settings(self):
        return CATEGORIES

    def show_category(self, c):
        self.shots.append(("show", c["id"]))

    def open_account_settings(self):
        return ROWS

    def show_account_row(self, r):
        self.shots.append(("show", r["id"]))

    def view_shot(self, path, target=None):
        self.shots.append((os.path.basename(path), target and target["id"], target and target.get("part")))
        with open(path, "wb") as f:
            f.write(b"png")
        return (620, 375)


class Tour(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.out))
        self.tb = FakeTourThunderbird()
        self.folder, self.steps = tb_shot.tour(self.tb, self.out, say=lambda line: None)

    def test_two_shots_a_step_except_the_last(self):
        self.assertEqual(self.tb.shots[:4], [
            ("show", "category-general"), ("01-settings-paneGeneral.png", None, None),
            ("01-settings-paneGeneral-next.png", "category-compose", None), ("show", "category-compose")])
        self.assertIn(("02-settings-paneCompose-next.png", "accountButton", None), self.tb.shots)
        self.assertIn(("03-account-account1-next.png", "account1/am-server.xhtml", ".container"), self.tb.shots)
        self.assertEqual(self.tb.shots[-2:], [("show", "smtp"), ("05-account-smtp.png", None, None)])
        self.assertEqual(len([s for s in self.tb.shots if s[0] != "show"]), 9)

    def test_the_index_files(self):
        self.assertEqual(self.folder, os.path.join(self.out, "160.0-en-US"))
        with open(os.path.join(self.folder, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual((index["version"], index["locale"], len(index["steps"])), ("160.0", "en-US", 5))
        self.assertEqual(index["steps"][1]["next"]["label"], "Account Settings")
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "index.md")))


class Publish(unittest.TestCase):
    def setUp(self):
        out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out))
        self.folder, _ = tb_shot.tour(FakeTourThunderbird(), out, say=lambda line: None)
        self.calls = []

    def gh(self, view_code=0, view_err="", assets=(), upload_code=0):
        def run(command, capture_output=True, text=True):
            self.calls.append(command)
            if command[:3] == ["gh", "release", "view"]:
                stdout = json.dumps({"assets": [{"name": a} for a in assets]})
                return subprocess_result(view_code, stdout, view_err)
            with zipfile.ZipFile(command[4]) as z:
                self.zipped = sorted(z.namelist())
            return subprocess_result(upload_code, "", "boom" if upload_code else "")
        return run

    def test_the_first_locale_creates_the_release(self):
        tb_shot.publish(self.folder, run=self.gh(1, "release not found"), say=lambda line: None)
        create = self.calls[1]
        self.assertEqual(create[:4], ["gh", "release", "create", "screenshots-160.0"])
        self.assertTrue(create[4].endswith("160.0-en-US.zip"))
        self.assertIn("thunderbird/sumo-linter", create)
        self.assertIn("160.0-en-US/index.md", self.zipped)
        self.assertIn("160.0-en-US/05-account-smtp.png", self.zipped)
        self.assertEqual(len(self.zipped), 9 + 2)

    def test_a_second_locale_is_added(self):
        tb_shot.publish(self.folder, run=self.gh(assets=["160.0-de.zip"]), say=lambda line: None)
        self.assertEqual(self.calls[1][:4], ["gh", "release", "upload", "screenshots-160.0"])
        self.assertNotIn("--clobber", self.calls[1])

    def test_an_existing_zip_is_never_replaced_by_accident(self):
        with self.assertRaisesRegex(RuntimeError, "--replace"):
            tb_shot.publish(self.folder, run=self.gh(assets=["160.0-en-US.zip"]), say=lambda line: None)
        self.assertEqual(len(self.calls), 1)

    def test_replace(self):
        tb_shot.publish(self.folder, replace=True, run=self.gh(assets=["160.0-en-US.zip"]), say=lambda line: None)
        self.assertIn("--clobber", self.calls[1])

    def test_another_gh_error_creates_nothing(self):
        with self.assertRaisesRegex(RuntimeError, "not logged in"):
            tb_shot.publish(self.folder, run=self.gh(1, "not logged in"), say=lambda line: None)
        self.assertEqual(len(self.calls), 1)

    def test_a_failed_upload_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            tb_shot.publish(self.folder, run=self.gh(assets=[], upload_code=1), say=lambda line: None)

    def test_an_unfinished_tour_is_refused(self):
        os.remove(os.path.join(self.folder, "02-settings-paneCompose-next.png"))
        with self.assertRaisesRegex(RuntimeError, "lacks 02-settings-paneCompose-next.png"):
            tb_shot.publish(self.folder, run=self.gh(), say=lambda line: None)
        self.assertEqual(self.calls, [])

    def test_the_screenshots_folder_is_gitignored(self):
        with open(os.path.join(tb_shot.REPO, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("/screenshots/", f.read().split())


def items_tsv(text):
    """A temporary item list with this text, after the header."""
    fd, path = tempfile.mkstemp(suffix=".tsv")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# a comment\npage\ttarget\tgroup\tname\tlabel\n" + text)
    return path


class Items(unittest.TestCase):
    def test_the_160_list(self):
        items = tb_shot.read_items(tb_shot.items_file("160.0"))
        flat = [i for page in items.values() for i in page]
        self.assertEqual(len(flat), 50)
        self.assertEqual(sum(i["group"] == "open" for i in flat), 37)
        self.assertEqual(sum(i["group"] == "file" for i in flat), 6)
        vcard = next(i for i in items["am-main.xhtml"] if i["name"] == "editVCard")
        self.assertEqual(vcard["target"], {"css": 'button[oncommand="editVCard()"]', "frame": True})
        self.assertEqual(items["paneGeneral"][0]["target"], {"id": "addSearchEngine"})

    def test_the_list_file_is_by_major_version(self):
        self.assertTrue(tb_shot.items_file("160.0.1").endswith("tour-items-160.tsv"))

    def test_bad_lists(self):
        for text, message in [("paneGeneral\tx\tclick\tx\tX…\n", "group"),
                              ("paneGeneral\tx\topen\tx\n", "5 tab-separated"),
                              ("paneGeneral\tx\topen\tx\tX…\npaneGeneral\ty\topen\tx\tY…\n", "already used")]:
            path = items_tsv(text)
            self.addCleanup(os.remove, path)
            with self.assertRaisesRegex(ValueError, message):
                tb_shot.read_items(path)

    def test_a_bad_header(self):
        fd, path = tempfile.mkstemp(suffix=".tsv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("page\ttarget\n")
        self.addCleanup(os.remove, path)
        with self.assertRaisesRegex(ValueError, "header"):
            tb_shot.read_items(path)

    def test_entries_have_a_letter_and_file_names(self):
        step = {"name": "01-settings-paneGeneral", "page": "paneGeneral"}
        items = {"paneGeneral": [{"target": {"id": "a"}, "group": "open", "name": "a", "label": "A…"},
                                 {"target": {"id": "b"}, "group": "open", "name": "b", "label": "B…"}]}
        entries = tb_shot.item_entries(step, items)
        self.assertEqual([(e["step"], e["base"]) for e in entries],
                         [("1a", "01a-settings-paneGeneral-a"), ("1b", "01b-settings-paneGeneral-b")])


TOUR_ITEMS = {
    "paneGeneral": [
        {"target": {"id": "catProxiesButton"}, "group": "open", "name": "catProxiesButton", "label": "Connection options…"},
        {"target": {"id": "browseForSound"}, "group": "file", "name": "browseForSound", "label": "Select audio…"},
        {"target": {"id": "editTagButton"}, "group": "open", "name": "editTagButton", "label": "Edit…"},
        {"target": {"id": "gone"}, "group": "open", "name": "gone", "label": "Gone…"},
    ],
    "am-server.xhtml": [
        {"target": {"id": "picker", "frame": True}, "group": "menu", "name": "picker", "label": "Choose Folder…"},
        {"target": {"id": "global", "frame": True}, "group": "goto", "name": "global", "label": "Global…"},
    ],
}
ITEM_STATES = {"editTagButton": {"exists": True, "shown": True, "disabled": True, "label": "Bearbeiten…"},
               "gone": {"exists": False, "shown": False, "disabled": False, "label": None}}
ROWS_WITH_SERVER = [ROWS[0], {"id": "account1/am-server.xhtml", "page": "am-server.xhtml", "label": "Server"}]


class TourItems(unittest.TestCase):
    def run_tour(self, file_dialogs):
        out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out))
        self.tb = FakeTourThunderbird(ITEM_STATES, unlisted=['#new "New…"'], file_window=4242)
        self.tb.open_account_settings = lambda: ROWS_WITH_SERVER
        self.restarts, self.captures, self.said = 0, [], []

        def restart():
            self.restarts += 1
            return self.tb

        def capture(wid, path):
            self.captures.append((wid, os.path.basename(path)))
            with open(path, "wb") as f:
                f.write(b"png")

        return tb_shot.tour(self.tb, out, say=self.said.append, items=TOUR_ITEMS,
                            file_dialogs=file_dialogs, restart=restart, capture=capture)

    def test_an_open_item_gets_two_shots(self):
        _, steps = self.run_tour(False)
        self.assertIn(("item", "01a-settings-paneGeneral-catProxiesButton-next.png",
                       "01a-settings-paneGeneral-catProxiesButton.png", "catProxiesButton"), self.tb.shots)
        e = steps[0]["items"][0]
        self.assertEqual((e["status"], e["file"]), ("tab dialog", "01a-settings-paneGeneral-catProxiesButton.png"))

    def test_skipped_items_say_why_and_have_no_files(self):
        _, steps = self.run_tour(False)
        general = steps[0]["items"]
        self.assertEqual([e["status"] for e in general[1:]],
                         ["a file dialog: needs --file-dialogs", "disabled", "hidden"])
        self.assertEqual(general[2]["label"], "Bearbeiten…")  # the locale's own label
        server = next(s for s in steps if s["page"] == "am-server.xhtml")["items"]
        self.assertEqual([e["status"] for e in server],
                         ["a drop-down menu: not clicked", "goes to a Settings pane: not clicked"])
        self.assertTrue(all(e["file"] is None and e["next_file"] is None for e in general[1:] + server))
        self.assertEqual(self.restarts, 0)

    def test_file_dialogs_come_last_with_a_restart_each(self):
        _, steps = self.run_tour(True)
        self.assertEqual(self.restarts, 1)
        self.assertEqual(self.captures, [(4242, "01b-settings-paneGeneral-browseForSound.png")])
        self.assertEqual(self.tb.shots[-1], ("file", "browseForSound"))
        e = steps[0]["items"][1]
        self.assertEqual((e["status"], e["next_file"]), ("file dialog", "01b-settings-paneGeneral-browseForSound-next.png"))

    def test_an_unlisted_item_is_a_warning(self):
        _, steps = self.run_tour(False)
        self.assertEqual(steps[0]["unlisted"], ['#new "New…"'])
        self.assertIn('  warning: paneGeneral has #new "New…", which is not in the item list', self.said)

    def test_index_md_lists_items_with_their_notes(self):
        folder, _ = self.run_tour(False)
        with open(os.path.join(folder, "index.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| 1a | Settings › Allgemein › Connection options… | 01a-settings-paneGeneral-catProxiesButton-next.png"
                      " | 01a-settings-paneGeneral-catProxiesButton.png |  |  | tab dialog |", md)
        self.assertIn("| 1c | Settings › Allgemein › Bearbeiten… |  |  |  |  | disabled |", md)

    def test_the_zip_has_the_item_files(self):
        folder, _ = self.run_tour(True)
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp))
        path, _, _, count = tb_shot.zip_tour(folder, tmp)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        self.assertIn("160.0-en-US/01b-settings-paneGeneral-browseForSound.png", names)
        self.assertIn("160.0-en-US/01a-settings-paneGeneral-catProxiesButton-next.png", names)
        self.assertEqual(count, 7 + 4)  # 4 steps, the last with one shot; 2 items


class FileDialogs(unittest.TestCase):
    def test_refused_outside_macos(self):
        self.assertIn("only on macOS", tb_shot.file_dialog_refusal("linux", [], "/tmp"))

    def test_refused_for_an_administrator(self):
        self.assertIn("administrator", tb_shot.file_dialog_refusal("darwin", ["staff", "admin"], "/nonexistent"))

    def test_refused_with_icloud_drive(self):
        home = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(home))
        os.makedirs(os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs"))
        self.assertIn("iCloud Drive", tb_shot.file_dialog_refusal("darwin", ["staff"], home))

    def test_allowed_for_an_empty_standard_user(self):
        home = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(home))
        self.assertIsNone(tb_shot.file_dialog_refusal("darwin", ["staff", "everyone"], home))

    def test_native_windows(self):
        calls = []

        def run(command, capture_output=True, text=True):
            calls.append(command)
            return subprocess_result(0, '[{"id": 7, "layer": 0}]', "")
        self.assertEqual(tb_shot.native_windows(123, run=run), [{"id": 7, "layer": 0}])
        self.assertEqual(calls[0][:4], ["osascript", "-l", "JavaScript", "-e"])
        self.assertEqual(calls[0][-1], "123")

    def test_screencapture_scales_and_removes_the_full_size_file(self):
        out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out))
        path = os.path.join(out, "x.png")
        calls = []

        def run(command, capture_output=True, text=True):
            calls.append(command)
            target = command[-1]
            with open(target, "wb") as f:
                f.write(b"png")
            return subprocess_result(0, "", "")
        tb_shot.screencapture(99, path, run=run)
        self.assertEqual(calls[0][:5], ["screencapture", "-x", "-o", "-l", "99"])
        self.assertEqual(calls[1][:3], ["sips", "-Z", "620"])
        self.assertEqual(os.listdir(out), ["x.png"])

    def test_screencapture_without_permission_says_so(self):
        def run(command, capture_output=True, text=True):
            return subprocess_result(1, "", "could not create image from window")
        with self.assertRaisesRegex(RuntimeError, "Screen Recording"):
            tb_shot.screencapture(99, "/tmp/never.png", run=run)


def subprocess_result(code, stdout, stderr):
    return __import__("subprocess").CompletedProcess([], code, stdout, stderr)


if __name__ == "__main__":
    unittest.main()
