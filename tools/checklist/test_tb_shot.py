# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for tb_shot.py (#39). Standard library only, and no Thunderbird.

    python3 tools/checklist/test_tb_shot.py

What needs Thunderbird, finding a setting and drawing it, was tested by hand
against Thunderbird 159 on macOS; see #39. This file tests the parts that can
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


if __name__ == "__main__":
    unittest.main()
