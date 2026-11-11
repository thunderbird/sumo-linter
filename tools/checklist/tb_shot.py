#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Screenshots of Thunderbird settings for SUMO articles (sumo-linter #39).

    uv run tools/checklist/tb_shot.py shot --app APP --text TEXT --out FILE.png
    uv run tools/checklist/tb_shot.py session --app APP --out DIR
    uv run tools/checklist/tb_shot.py login --app APP
    uv run tools/checklist/tb_shot.py tour --app APP --out DIR [--file-dialogs]
    uv run tools/checklist/tb_shot.py publish DIR/VERSION-LOCALE [--replace]

APP is a Thunderbird application: `/Applications/…/Thunderbird.app` on macOS,
or the `thunderbird` program elsewhere. The script starts a second copy of it
with a new, empty profile, so a Thunderbird that is already running, and its
mail, are never involved. It drives that copy with Marionette, the remote
protocol that Thunderbird shares with Firefox, and quits it at the end.

`shot` finds the setting whose text is TEXT, first in Settings and then in
Account Settings, and saves a screenshot of it in SUMO's style ("How to make
screenshots"): a square #f71701 outline around the setting, the setting
centered, and at most 620 pixels each way. Account Settings needs an account,
so the profile gets a dummy IMAP account, `dummy@example.invalid`. The
`.invalid` domain never resolves and Thunderbird runs offline, so nothing
connects anywhere.

`session` is for walk.py (`--shots`): it keeps one Thunderbird open and reads
requests from standard input, one JSON object per line,
`{"text": "Enable auto-scrolling", "name": "some-article-item-3"}`, and
answers each with one line, `{"ok": true, "path": …, "where": …}` or
`{"ok": false, "error": …}`. It quits Thunderbird when its input closes.

`--expect VERSION` refuses to run unless the application is that version, for
example 159. The version comes from the application's `application.ini`,
never from its folder name, which can be wrong.

`--account real` uses a real account instead (#40), for screenshots that need
one. `login` sets it up once: it opens Thunderbird with a profile of its own,
.auth/thunderbird-profile (gitignored, never commit it), and waits while you
add the test account. Its sign-in may open in Firefox; sign in there, wait
until Thunderbird shows the account's folders, and quit Thunderbird. Then
`shot` and `session` with `--account real` run a temporary copy of that
profile, online, so a screenshot run cannot change the signed-in profile, and
they delete the copy at the end because it holds the account's tokens. The
script never types a password and never composes or sends mail. If the sign-in
has expired, run `login` again. Use a test account: its address will be in
some screenshots, and SUMO's screenshots must contain no personal data.

`tour` (#55) clicks through every Settings category and every Account
Settings page, as a person does, and saves two screenshots of each: the pane
as it first shows, and the same pane with the next item to click outlined.
The order is the Settings sidebar, then its Account Settings link, then every
row of the Account Settings tree. The files go to DIR/VERSION-LOCALE, for
example screenshots/160.0-en-US, named by pane, never by visible text, so a
step has the same file name in every locale. index.md and index.json there
list the steps with the labels in the locale's own words. Each screenshot is
the whole tab, scaled down to fit SUMO's 620 pixels, as SUMO's guide says to
resize a large screenshot; the outline is drawn thicker by the same factor,
so it is still OUTLINE_PX in the file. /screenshots/ is gitignored.

In each pane, the tour also clicks every item whose label ends with an
ellipsis, such as "Connection options…" (#56). The items come from
tour-items-<major version>.tsv next to this script, by element ID, so the
same list works in every locale; the tour warns about an ellipsis item that
is not in the list. For each item it saves the pane with the item outlined
(`01c-settings-paneGeneral-catProxiesButton-next.png`) and the dialog that
the click opens (`…-catProxiesButton.png`): a dialog in the tab, a separate
window, or an HTML dialog. It closes each dialog without OK. Hidden and
disabled items, drop-down menus and links to another pane are listed in
index.md but not clicked.

Items that open the operating system's file dialog are captured only with
--file-dialogs, on macOS, with `screencapture`, which needs the Screen
Recording permission. macOS shows the user's own folders, iCloud Drive and
tags in that dialog, so --file-dialogs refuses to run in a macOS user that is
an administrator or has iCloud Drive: use a separate, empty, standard user
(#56). Each file dialog needs its own Thunderbird start, because only a key
press closes it, so the tour takes them last.

`publish` puts a tour folder on GitHub as a release asset, with `gh`: one
release per Thunderbird version (tag screenshots-VERSION) and one zip per
locale (VERSION-LOCALE.zip). It creates the release if it is missing and adds
the zip otherwise, and it never replaces a zip that is already there unless
you give --replace. Release assets are outside the git history, so a clone of
this repo never downloads them.

Python standard library only, like walk.py. It is a separate file because
walk.py must stay one file (#32).
"""

import base64
import configparser
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

# SUMO's rules, from "How to make screenshots" (corpus-other/markup-docs).
OUTLINE_COLOR = "#f71701"
OUTLINE_PX = 6  # 4.5 pt, inside SUMO's 4 to 8 pt
MAX_PX = 620
MARGIN_PX = 24  # room around the outline

DUMMY_EMAIL = "dummy@example.invalid"

# The window size of a tour (#55), in CSS pixels. The tab's content is then
# about 955 by 580, which scales to 620 by 376.
TOUR_WINDOW = (1000, 720)
RELEASE_REPO = "thunderbird/sumo-linter"

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The signed-in profile for --account real (#40). /.auth/ is gitignored.
ACCOUNT_PROFILE = os.path.join(REPO, ".auth", "thunderbird-profile")
# Not copied: a copy must not look locked, and caches are rebuilt.
NOT_COPIED = {"lock", ".parentlock", "parent.lock", "cache2", "startupCache", "crashes", "minidumps"}

# The dialogs that Settings opens, searched after its panes. Proxy and
# offline settings, for example, are only in these.
SETTINGS_DIALOGS = [
    "connection.xhtml", "offline.xhtml", "receipts.xhtml", "fonts.xhtml",
    "attachmentReminder.xhtml", "notifications.xhtml", "dockoptions.xhtml",
]

# Account Settings pages, searched in this order after Settings.
ACCOUNT_PAGES = [
    "am-main.xhtml", "am-server.xhtml", "am-copies.xhtml", "am-addressing.xhtml",
    "am-junk.xhtml", "am-offline.xhtml", "am-e2e.xhtml", "am-mdn.xhtml",
]


# --- Marionette ---------------------------------------------------------------

def frame(message):
    """A Marionette packet: the JSON length, a colon, the JSON."""
    body = json.dumps(message).encode()
    return str(len(body)).encode() + b":" + body


def read_packet(read):
    """One Marionette packet, from `read(n)`, which returns up to n bytes."""
    size = b""
    while True:
        c = read(1)
        if not c:
            raise EOFError("Marionette closed the connection")
        if c == b":":
            break
        size += c
    data = b""
    while len(data) < int(size):
        chunk = read(int(size) - len(data))
        if not chunk:
            raise EOFError("Marionette closed the connection")
        data += chunk
    return json.loads(data)


class Marionette:
    """A minimal client: commands in, results out, errors as exceptions."""

    def __init__(self, port, timeout=60):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=60)
                break
            except OSError:
                if time.time() > deadline:
                    raise RuntimeError(f"Thunderbird did not open Marionette on port {port}")
                time.sleep(0.5)
        self.file = self.sock.makefile("rb")
        self.id = 0
        hello = read_packet(self.file.read)
        if hello.get("applicationType") != "gecko":
            raise RuntimeError(f"not Marionette on port {port}: {hello}")

    def cmd(self, name, params=None):
        self.id += 1
        self.sock.sendall(frame([0, self.id, name, params or {}]))
        while True:
            kind, msg_id, error, result = read_packet(self.file.read)
            if kind == 1 and msg_id == self.id:
                if error:
                    raise RuntimeError(f"{name}: {error.get('message', error)}")
                return result

    def js(self, script, *args):
        return self.cmd("WebDriver:ExecuteScript", {"script": script, "args": list(args)}).get("value")

    def js_async(self, script, *args):
        return self.cmd("WebDriver:ExecuteAsyncScript", {"script": script, "args": list(args)}).get("value")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# --- The application and its profile -------------------------------------------

def binary_of(app):
    """The program to run for APP: a macOS .app bundle or the program itself."""
    if app.rstrip("/").endswith(".app"):
        return os.path.join(app, "Contents", "MacOS", "thunderbird")
    return app


def ini_of(app):
    """application.ini, which says the real version."""
    if app.rstrip("/").endswith(".app"):
        return os.path.join(app, "Contents", "Resources", "application.ini")
    return os.path.join(os.path.dirname(os.path.realpath(app)), "application.ini")


def version_of(app):
    """The application's version, for example "159.0", or None."""
    ini = configparser.ConfigParser()
    try:
        with open(ini_of(app), encoding="utf-8") as f:
            ini.read_file(f)
        return ini.get("App", "Version")
    except (OSError, configparser.Error):
        return None


def version_matches(version, expected):
    """True if `version` is the `expected` one: "159" matches "159.0" and "159.0.1"."""
    if version is None:
        return False
    return version == expected or version.startswith(expected + ".")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def user_js(port, offline=True):
    """The prefs of a screenshot profile. No port: no Marionette pref."""
    prefs = {} if port is None else {"marionette.port": port}
    prefs.update({
        "mail.shell.checkDefaultClient": False,
        "datareporting.policy.dataSubmissionEnabled": False,
        "toolkit.telemetry.reportingpolicy.firstRun": False,
        "app.update.auto": False,
        "app.update.disabledForTesting": True,
        "mail.provider.suppress_dialog_on_startup": True,
        "mail.spotlight.firstRunDone": True,
        "mailnews.start_page.enabled": False,
    })
    if offline:
        prefs.update({
            # 3 is "always offline" in OfflineStartup.sys.mjs. 1 is "ask", which
            # shows a prompt on every start that waits for a click.
            "offline.startup_state": 3,
            "offline.autoDetect": False,
            # Without these, going offline with an account asks whether to
            # download messages first ("Work offline"), and waits for a click.
            "offline.download.download_messages": 2,
            "offline.send.unsent_messages": 2,
        })
    lines = [f"user_pref({json.dumps(k)}, {json.dumps(v)});" for k, v in prefs.items()]
    return "\n".join(lines) + "\n"


def copy_profile(src, dst):
    """Copy a profile, without its lock files and caches."""
    shutil.copytree(src, dst, ignore=lambda folder, names: [n for n in names if n in NOT_COPIED])


def profile_in_use(profile):
    """True if a running Thunderbird has this profile open (macOS and Linux)."""
    try:
        res = subprocess.run(["pgrep", "-f", "--", f"-profile {profile}"], capture_output=True, text=True)
    except OSError:
        return False
    return res.returncode == 0


def login(app, profile=ACCOUNT_PROFILE, run=subprocess.run, say=print):
    """Open Thunderbird with the account profile, and wait until it quits."""
    if profile_in_use(profile):
        raise RuntimeError(f"a Thunderbird already has {profile} open: quit it first")
    if not os.path.isfile(binary_of(app)):
        raise RuntimeError(f"no Thunderbird program at {binary_of(app)}")
    os.makedirs(profile, exist_ok=True)
    with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as f:
        f.write(user_js(None, offline=False))
    say(f"Opening Thunderbird {version_of(app)} with the profile {profile}.")
    say("Add the test account there (not your own). If its sign-in opens in Firefox,")
    say("sign in there and come back. When Thunderbird shows the account's folders,")
    say("quit Thunderbird, and this script ends.")
    run([binary_of(app), "-no-remote", "-new-instance", "-profile", profile],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    say("Done. `--account real` now uses this account.")


class Thunderbird:
    """A copy of Thunderbird with its own profile, driven through Marionette.

    With `account_profile`, a temporary copy of that signed-in profile runs
    online (#40). Without it, a new empty profile runs offline, with a dummy
    account.
    """

    def __init__(self, app, expect=None, account_profile=None):
        if expect and not version_matches(version_of(app), expect):
            raise RuntimeError(f"{app} is version {version_of(app)}, not {expect}")
        if not os.path.isfile(binary_of(app)):
            raise RuntimeError(f"no Thunderbird program at {binary_of(app)}")
        real = account_profile is not None
        if real:
            if not os.path.isfile(os.path.join(account_profile, "prefs.js")):
                raise RuntimeError(f"no signed-in profile at {account_profile}: run `tb_shot.py login` first")
            if profile_in_use(account_profile):
                raise RuntimeError(f"a Thunderbird has {account_profile} open: quit it first")
        self.app = app
        self.version = version_of(app)
        self.profile = tempfile.mkdtemp(prefix="tb-shot-")
        self.proc = None
        if real:
            os.rmdir(self.profile)
            copy_profile(account_profile, self.profile)
        port = free_port()
        # user.js wins over the copy's prefs.js, and it is the copy's own file.
        with open(os.path.join(self.profile, "user.js"), "w", encoding="utf-8") as f:
            f.write(user_js(port, offline=not real))
        env = dict(os.environ, MOZ_REMOTE_ALLOW_SYSTEM_ACCESS="1")
        command = [binary_of(app), "-no-remote", "-new-instance", "-profile", self.profile, "--marionette"]
        self.proc = subprocess.Popen(
            command + ([] if real else ["-offline"]),
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            self.m = Marionette(port)
            self.m.cmd("WebDriver:NewSession", {"capabilities": {}})
            self.m.cmd("Marionette:SetContext", {"value": "chrome"})
            self.m.cmd("WebDriver:SetTimeouts", {"script": 30000})
            self.wait_for_main_window()
            if not real:
                self.add_dummy_account()
        except Exception:
            self.quit()
            raise

    def wait_for_main_window(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.m.js("return !!document.getElementById('tabmail')"):
                return
            time.sleep(0.5)
        raise RuntimeError("Thunderbird's main window did not open")

    def add_dummy_account(self):
        """An IMAP account that never connects, for Account Settings."""
        self.m.js(ADD_DUMMY_ACCOUNT_JS, DUMMY_EMAIL)

    def windows(self):
        return self.m.cmd("WebDriver:GetWindowHandles")

    def quit(self):
        try:
            self.m.cmd("Marionette:Quit", {"flags": ["eForceQuit"]})
        except Exception:
            pass
        if self.proc:
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if getattr(self, "m", None):
            self.m.close()
        shutil.rmtree(self.profile, ignore_errors=True)

    def shot(self, text, path):
        """Find the setting with `text`, and save its screenshot to `path`.

        Returns where it was found, for example "Settings, paneGeneral" or
        "Account Settings, am-server.xhtml".
        """
        if len(self.windows()) > 1:
            raise RuntimeError("Thunderbird shows a dialog that waits for an answer")
        self.m.js(CLOSE_DIALOGS_JS)  # a dialog left open by the last shot
        where = self.find_in_settings(text) or self.find_in_account_settings(text)
        if not where:
            raise LookupError(f'no setting with the text "{text}" in Settings or Account Settings')
        data = self.m.js_async(SNAPSHOT_JS, OUTLINE_COLOR, OUTLINE_PX, MAX_PX, MARGIN_PX)
        if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
            raise RuntimeError(f"the screenshot failed: {data}")
        self.m.js(CLOSE_DIALOGS_JS)
        png = base64.b64decode(data.split(",", 1)[1])
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
        return where, png_size(png)

    def find_in_settings(self, text):
        self.m.js("window.openPreferencesTab('paneGeneral')")
        if not self.wait_for(PREFS_READY_JS):
            raise RuntimeError("Settings did not open")
        # Every pane is in the one document, so one search finds the panes; but
        # gotoPref shows a pane asynchronously, so each is shown before its
        # match is checked.
        for pane in self.m.js(PANES_WITH_TEXT_JS + FIND_JS, text) or []:
            self.m.js("document.getElementById('tabmail').currentTabInfo.browser"
                      ".contentWindow.gotoPref(arguments[0])", pane)
            if self.wait_for(PICK_IN_PANE_JS + FIND_JS, text, pane, timeout=5):
                time.sleep(0.3)  # the scroll
                return f"Settings, {pane}"
        for dialog in SETTINGS_DIALOGS:
            self.m.js(OPEN_DIALOG_JS, dialog)
            if not self.wait_for(DIALOG_READY_JS, dialog, timeout=10):
                self.m.js(CLOSE_DIALOGS_JS)
                continue
            if self.m.js(FIND_IN_DIALOG_JS + FIND_JS, text):
                time.sleep(0.3)
                return f"Settings, {dialog}"
            self.m.js(CLOSE_DIALOGS_JS)
        return None

    def find_in_account_settings(self, text):
        self.m.js("window.MsgAccountManager(null)")
        if not self.wait_for(ACCOUNTS_READY_JS):
            raise RuntimeError("Account Settings did not open")
        for page in ACCOUNT_PAGES:
            self.m.js(SELECT_ACCOUNT_PAGE_JS, page)
            if not self.wait_for(ACCOUNT_PAGE_READY_JS, page):
                continue
            if self.m.js(FIND_IN_ACCOUNT_PAGE_JS + FIND_JS, text):
                time.sleep(0.5)
                return f"Account Settings, {page}"
        return None

    # --- The tour (#55) ---

    def locale(self):
        """The language that Thunderbird shows, for example "en-US"."""
        return self.m.js("return Services.locale.appLocaleAsBCP47")

    def open_settings(self):
        self.m.cmd("WebDriver:SetWindowRect", {"width": TOUR_WINDOW[0], "height": TOUR_WINDOW[1]})
        self.m.js(CLOSE_DIALOGS_JS)
        self.m.js("window.openPreferencesTab('paneGeneral')")
        if not self.wait_for(PREFS_READY_JS):
            raise RuntimeError("Settings did not open")
        if not self.wait_for(SETTINGS_CATEGORIES_JS):
            raise RuntimeError("Settings shows no categories")
        return self.m.js(SETTINGS_CATEGORIES_JS)

    def click(self, target):
        """Click an element of the tab, as a person does.

        `target` is {id or css, part, frame}: see TARGET_JS. The click runs
        after this call returns, so a dialog that it opens cannot hold up
        Marionette.
        """
        if len(self.windows()) > 1:
            raise RuntimeError("Thunderbird shows a dialog that waits for an answer")
        if not self.m.js(TARGET_JS + CLICK_JS, target):
            raise LookupError(f"no element {target_name(target)} to click")

    def show_category(self, category):
        self.click({"id": category["id"]})
        if not self.wait_for(CATEGORY_SHOWN_JS, category["id"], category["pane"]):
            raise RuntimeError(f"the Settings category {category['pane']} did not show")
        time.sleep(0.5)  # Fluent fills in the pane's text

    def open_account_settings(self):
        """Click the Account Settings link at the foot of the Settings sidebar."""
        self.click({"id": "accountButton"})
        if not self.wait_for(ACCOUNTS_READY_JS):
            raise RuntimeError("Account Settings did not open")
        if not self.wait_for(ACCOUNT_ROWS_JS):
            raise RuntimeError("Account Settings shows no accounts")
        return self.m.js(ACCOUNT_ROWS_JS)

    def show_account_row(self, row):
        self.click({"id": row["id"], "part": ".container"})
        if not self.wait_for(ACCOUNT_ROW_SHOWN_JS, row["id"], row["page"]):
            raise RuntimeError(f"the Account Settings page {row['id']} did not show")
        time.sleep(0.5)

    def view_shot(self, path, target=None):
        """Save the whole tab, scaled to fit MAX_PX, with `target` outlined."""
        return save_png(self.m.js_async(TARGET_JS + VIEW_SNAPSHOT_JS, OUTLINE_COLOR, OUTLINE_PX, MAX_PX, target), path)

    def item_state(self, target):
        """{exists, shown, disabled, label} of an item in the shown pane."""
        return self.m.js(TARGET_JS + ITEM_STATE_JS, target)

    def unlisted_items(self, targets, frame):
        """Labels of shown ellipsis items in the pane that `targets` misses."""
        return self.m.js(TARGET_JS + UNLISTED_JS, targets, frame)

    def item_shots(self, target, before_path, after_path, timeout=10):
        """Outline `target`, click it, and save the dialog that it opens.

        The dialog can be a separate window (a prompt, for example), a
        dialog in the tab (gSubDialog), or an HTML <dialog>. It is closed
        without OK. Returns which kind it was.
        """
        self.m.js(TARGET_JS + SCROLL_TO_JS, target)
        time.sleep(0.3)
        self.view_shot(before_path, target)
        main = self.m.cmd("WebDriver:GetWindowHandle")["value"]
        before = set(self.windows())
        self.click(target)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.25)
            # A command in the main window while a prompt window is open
            # fails ("Unexpected prompt dialog"), so new windows come first.
            new = [h for h in self.windows() if h not in before]
            if new:
                self.m.cmd("WebDriver:SwitchToWindow", {"handle": new[0]})
                try:
                    if not self.wait_for(WINDOW_READY_JS, timeout=10):
                        raise RuntimeError(f"the window that {target_name(target)} opened did not load")
                    time.sleep(0.5)
                    save_png(self.m.js_async(WINDOW_SNAPSHOT_JS, MAX_PX), after_path)
                finally:
                    self.m.js("window.close()")
                    time.sleep(0.3)
                    self.m.cmd("WebDriver:SwitchToWindow", {"handle": main})
                return "window"
            kind = self.m.js(OPEN_DIALOG_KIND_JS)
            if kind:
                time.sleep(0.7)  # the dialog's opening animation, and Fluent
                self.view_shot(after_path)
                self.m.js(CLOSE_ANY_DIALOG_JS)
                time.sleep(0.3)
                return kind
        raise RuntimeError(f"{target_name(target)} opened nothing in {timeout} s")

    def click_for_file_dialog(self, target, capture, timeout=10):
        """Click `target`, wait for the native file dialog, and `capture` it.

        `capture(window_id)` saves the picture. The dialog stays open: the
        caller quits this Thunderbird.
        """
        before = {w["id"] for w in native_windows(self.proc.pid)}
        self.click(target)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            new = [w for w in native_windows(self.proc.pid) if w["id"] not in before and w["layer"] == 0]
            if new:
                time.sleep(1)  # the dialog's opening animation
                return capture(new[0]["id"])
        raise RuntimeError(f"{target_name(target)} opened no file dialog in {timeout} s")

    def wait_for(self, script, *args, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.m.js(script, *args):
                return True
            time.sleep(0.25)
        return False


def save_png(data, path):
    """Save a PNG data URL from a snapshot script; returns its size."""
    if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
        raise RuntimeError(f"the screenshot failed: {data}")
    png = base64.b64decode(data.split(",", 1)[1])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return png_size(png)


def target_name(target):
    """A target for messages: #id, or the CSS selector."""
    name = f"#{target['id']}" if target.get("id") else target.get("css", "?")
    return name + (f" {target['part']}" if target.get("part") else "")


def png_size(png):
    """(width, height) of a PNG."""
    return struct.unpack(">II", png[16:24])


# --- The scripts that run inside Thunderbird ------------------------------------

ADD_DUMMY_ACCOUNT_JS = """
const [email] = arguments;
const { MailServices } = ChromeUtils.importESModule("resource:///modules/MailServices.sys.mjs");
Services.io.offline = true;
if (MailServices.accounts.findServer("dummy", "imap.invalid", "imap")) return;
const server = MailServices.accounts.createIncomingServer("dummy", "imap.invalid", "imap");
server.loginAtStartUp = false;
server.doBiff = false;
const identity = MailServices.accounts.createIdentity();
identity.email = email;
identity.fullName = "Dummy";
const account = MailServices.accounts.createAccount();
account.incomingServer = server;
account.addIdentity(identity);
"""

PREFS_READY_JS = """
const t = document.getElementById('tabmail').currentTabInfo;
const doc = t.browser && t.browser.contentDocument;
return !!(doc && doc.readyState == 'complete' && doc.defaultView.gotoPref);
"""

ACCOUNTS_READY_JS = """
const t = document.getElementById('tabmail').currentTabInfo;
const doc = t.browser && t.browser.contentDocument;
return !!(doc && doc.readyState == 'complete' && doc.defaultView.selectServer);
"""

SELECT_ACCOUNT_PAGE_JS = """
const [page] = arguments;
const { MailServices } = ChromeUtils.importESModule("resource:///modules/MailServices.sys.mjs");
// The first account that is not Local Folders: the dummy one, or the real one.
const server = MailServices.accounts.accounts.find(a => a.incomingServer.type != 'none').incomingServer;
document.getElementById('tabmail').currentTabInfo.browser.contentWindow.selectServer(server, page);
"""

ACCOUNT_PAGE_READY_JS = """
const [page] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const f = doc.getElementById('contentFrame');
return !!(f && f.contentDocument && f.contentDocument.readyState == 'complete'
          && f.contentDocument.location.href.endsWith(page));
"""

# Finds the element whose text is the wanted text, and keeps it in
# window.__tbShot for SNAPSHOT_JS. The text can be in a `label` or `value`
# attribute (XUL, and what Fluent fills in) or in the element's own text. An
# exact match wins over one that differs only in case, spacing, quote marks or
# a trailing colon or ellipsis. A match inside a checkbox, radio, button or
# menulist stands for that control.
FIND_JS = """
function norm(s) {
  return (s || '').replace(/[\\u2018\\u2019]/g, "'").replace(/[\\u201c\\u201d]/g, '"')
    .replace(/\\s+/g, ' ').trim().replace(/(\\s*(:|…|\\.\\.\\.))+$/, '').toLowerCase();
}
function textsOf(e) {
  const out = [e.getAttribute('label'), e.getAttribute('value')];
  if (!e.firstElementChild || /^(label|h[1-6]|description|button|span|a)$/.test(e.localName)) {
    out.push(e.textContent);
  }
  return out.filter(t => t && t.trim());
}
function control(e) {
  return e.closest('checkbox, radio, button, menulist, toolbarbutton') || e;
}
function shown(e) {
  const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}
function find(doc, wanted, filter) {
  const exact = [], loose = [];
  for (const e of doc.querySelectorAll('*')) {
    if (filter && !filter(e)) continue;
    for (const t of textsOf(e)) {
      if (t.trim() == wanted.trim()) { exact.push(control(e)); break; }
      if (norm(t) == norm(wanted)) { loose.push(control(e)); break; }
    }
  }
  return exact.concat(loose);
}
"""

PANES_WITH_TEXT_JS = """
const [wanted] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
// Every pane is in the one document; its elements carry data-category.
const panes = [];
for (const el of find(doc, wanted, e => e.closest('[data-category]'))) {
  const pane = el.closest('[data-category]').getAttribute('data-category');
  if (!panes.includes(pane)) panes.push(pane);
}
return panes;
"""

PICK_IN_PANE_JS = """
const [wanted, pane] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
for (const el of find(doc, wanted, e => {
  const c = e.closest('[data-category]');
  return c && c.getAttribute('data-category') == pane;
})) {
  if (!shown(el)) continue;
  el.scrollIntoView({ block: 'center' });
  window.__tbShot = { el, frame: null };
  return true;
}
return false;
"""

OPEN_DIALOG_JS = """
const [name] = arguments;
const win = document.getElementById('tabmail').currentTabInfo.browser.contentWindow;
win.gSubDialog.open('chrome://messenger/content/preferences/' + name);
"""

DIALOG_READY_JS = """
const [name] = arguments;
const t = document.getElementById('tabmail').currentTabInfo;
const d = t.browser && t.browser.contentWindow.gSubDialog && t.browser.contentWindow.gSubDialog._topDialog;
const doc = d && d._frame.contentDocument;
return !!(doc && doc.readyState == 'complete' && doc.location.href.endsWith(name));
"""

CLOSE_DIALOGS_JS = """
const t = document.getElementById('tabmail').currentTabInfo;
const sub = t.browser && t.browser.contentWindow && t.browser.contentWindow.gSubDialog;
// SubDialog.sys.mjs in 159 has no abortAll, so close them one by one.
for (let i = 0; sub && sub._dialogs && sub._dialogs.length && i < 10; i++) sub._topDialog.close();
"""

FIND_IN_DIALOG_JS = """
const [wanted] = arguments;
const frame = document.getElementById('tabmail').currentTabInfo.browser.contentWindow.gSubDialog._topDialog._frame;
for (const el of find(frame.contentDocument, wanted)) {
  if (!shown(el)) continue;
  el.scrollIntoView({ block: 'center' });
  window.__tbShot = { el, frame };
  return true;
}
return false;
"""

FIND_IN_ACCOUNT_PAGE_JS = """
const [wanted] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const frame = doc.getElementById('contentFrame');
for (const el of find(frame.contentDocument, wanted)) {
  if (!shown(el)) continue;
  el.scrollIntoView({ block: 'center' });
  window.__tbShot = { el, frame };
  return true;
}
return false;
"""

# Outlines the element, crops around it with the element centered, at most
# MAX pixels each way, and returns a PNG data URL. drawSnapshot renders the
# page at scale 1, so 620 here means 620 pixels in the file, also on a 2x
# screen.
SNAPSHOT_JS = """
const [color, width, max, margin, resolve] = arguments;
const { el, frame } = window.__tbShot;
const browser = document.getElementById('tabmail').currentTabInfo.browser;
const doc = browser.contentDocument;
// A checkbox or radio box stretches across its row, so outline what it shows:
// the text, and any image such as the check box.
function tight(e) {
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  const add = (r) => {
    if (r.width <= 0 || r.height <= 0) return;
    x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);
    x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
  };
  for (const n of [e, ...e.querySelectorAll('*')]) {
    if (n.firstElementChild) continue;
    if ((n.textContent || '').trim()) {
      const range = n.ownerDocument.createRange();
      range.selectNodeContents(n);
      add(range.getBoundingClientRect());
    } else if (n != e) {
      add(n.getBoundingClientRect());
    }
  }
  return x1 < x2 ? new DOMRect(x1, y1, x2 - x1, y2 - y1) : e.getBoundingClientRect();
}
const win = el.ownerDocument.defaultView;
win.requestAnimationFrame(() => win.requestAnimationFrame(() => {
  const f = frame ? frame.getBoundingClientRect() : { x: 0, y: 0 };
  const t = tight(el);
  const r = new DOMRect(f.x + t.x, f.y + t.y, t.width, t.height);
  // The outline is drawn over the whole page, so a dialog or an iframe that
  // ends at the setting's edge cannot cut it off.
  const gap = 4;
  const box = doc.createElementNS('http://www.w3.org/1999/xhtml', 'div');
  box.style.cssText = `position: fixed; z-index: 2147483647; pointer-events: none;
    box-sizing: border-box; border: ${width}px solid ${color}; border-radius: 0;
    left: ${r.x - gap - width}px; top: ${r.y - gap - width}px;
    width: ${r.width + 2 * (gap + width)}px; height: ${r.height + 2 * (gap + width)}px;`;
  doc.documentElement.appendChild(box);
  doc.defaultView.requestAnimationFrame(() => doc.defaultView.requestAnimationFrame(() => {
    const around = width + gap + margin;
    const fullW = r.width + 2 * around, fullH = r.height + 2 * around;
    const w = Math.min(max, fullW), h = Math.min(max, fullH);
    // Wider than the crop: start at the setting's left edge, so its text shows.
    const x = fullW > max ? r.x - around : r.x + r.width / 2 - w / 2;
    const y = r.y + r.height / 2 - h / 2;
    const rect = new DOMRect(x + doc.defaultView.scrollX, y + doc.defaultView.scrollY, w, h);
    browser.browsingContext.currentWindowGlobal.drawSnapshot(rect, 1, 'white').then((bitmap) => {
      box.remove();
      const c = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
      c.width = bitmap.width;
      c.height = bitmap.height;
      c.getContext('2d').drawImage(bitmap, 0, 0);
      resolve(c.toDataURL('image/png'));
    }, (e) => { box.remove(); resolve('error ' + e); });
  }));
}));
"""


# The tour (#55). Both Settings and Account Settings are the document of the
# current tab.

SETTINGS_CATEGORIES_JS = """
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const items = [...doc.querySelectorAll('#categories > richlistitem')]
  .filter(e => !e.hidden && e.getBoundingClientRect().height > 0)
  .map(e => ({ id: e.id, pane: e.value, label: e.textContent.trim() }));
return items.length && items.every(i => i.label) ? items : null;
"""

ACCOUNT_ROWS_JS = """
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const rows = [...doc.querySelectorAll('#accounttree li')]
  .filter(li => li.querySelector('.container') && li.querySelector('.container').getBoundingClientRect().height > 0)
  .map(li => ({ id: li.id, page: li.getAttribute('PageTag'),
                label: (li.querySelector('.container .name') || li.querySelector('.container')).textContent.trim() }));
return rows.length && rows.every(r => r.label) ? rows : null;
"""

# Finds a target in the current tab: {id} or {css}, optionally a `part`
# inside it (a CSS selector), and with `frame` in the Account Settings page
# (#contentFrame) instead of the tab's own document. Returns the element and
# the offset of its document within the tab, or null.
TARGET_JS = """
function targetOf(t) {
  const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
  let d = doc, dx = 0, dy = 0;
  if (t.frame) {
    const f = doc.getElementById('contentFrame');
    if (!f || !f.contentDocument) return null;
    d = f.contentDocument;
    const r = f.getBoundingClientRect();
    dx = r.x; dy = r.y;
  }
  let el = t.id ? d.getElementById(t.id) : d.querySelector(t.css);
  if (el && t.part) el = el.querySelector(t.part);
  return el ? { el, dx, dy } : null;
}
"""

# A click that the element's own handlers see: the mouse events a person
# makes. It runs after the script returns, because a click that opens a modal
# window would otherwise hold up the script until the window closes.
CLICK_JS = """
const [t] = arguments;
const found = targetOf(t);
if (!found) return false;
const el = found.el;
el.scrollIntoView({ block: 'nearest' });
const win = el.ownerGlobal || el.ownerDocument.defaultView;
win.setTimeout(() => {
  for (const type of ['mousedown', 'mouseup', 'click']) {
    el.dispatchEvent(new win.MouseEvent(type, { bubbles: true, cancelable: true, view: win, button: 0, detail: 1 }));
  }
}, 0);
return true;
"""

SCROLL_TO_JS = """
const [t] = arguments;
const found = targetOf(t);
if (found) found.el.scrollIntoView({ block: 'center' });
"""

ITEM_STATE_JS = """
const [t] = arguments;
const found = targetOf(t);
if (!found) return { exists: false, shown: false, disabled: false, label: null };
const el = found.el;
const r = el.getBoundingClientRect();
return { exists: true, shown: r.width > 0 && r.height > 0,
         disabled: !!(el.disabled || el.hasAttribute('disabled')),
         label: (el.getAttribute('label') || el.textContent || '').trim() };
"""

# The shown items with an ellipsis that no target in the list finds. Menu
# items are left out: they are inside menus, never clicked directly.
UNLISTED_JS = """
const [targets, frame] = arguments;
const listed = new Set(targets.map(t => { const f = targetOf(t); return f && f.el; }).filter(Boolean));
let doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
if (frame) doc = doc.getElementById('contentFrame').contentDocument;
const out = [];
for (const e of doc.querySelectorAll('button, menulist, toolbarbutton, a')) {
  const label = (e.getAttribute('label') || e.textContent || '').trim();
  const r = e.getBoundingClientRect();
  if (/(\u2026|\\.\\.\\.)$/.test(label) && r.width > 0 && r.height > 0 && !listed.has(e)) {
    const c = e.closest('[data-category]');
    if (!frame && c && c.hidden) continue;
    out.push((e.id ? '#' + e.id : e.localName) + ' "' + label + '"');
  }
}
return out;
"""

WINDOW_READY_JS = """
return document.readyState == 'complete' && location.href != 'about:blank';
"""

# A separate window, the whole of it, scaled to fit `max` pixels each way.
WINDOW_SNAPSHOT_JS = """
const [max, resolve] = arguments;
const w = window.innerWidth, h = window.innerHeight;
const scale = Math.min(1, max / w, max / h);
window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
  window.browsingContext.currentWindowGlobal.drawSnapshot(new DOMRect(0, 0, w, h), scale, 'white').then((bitmap) => {
    const c = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
    c.width = bitmap.width;
    c.height = bitmap.height;
    c.getContext('2d').drawImage(bitmap, 0, 0);
    resolve(c.toDataURL('image/png'));
  }, (e) => resolve('error ' + e));
}));
"""

# Which dialog is open in the tab: "tab dialog" (gSubDialog, loaded), "html
# dialog" (a <dialog> in the tab or in the Account Settings page), or null.
OPEN_DIALOG_KIND_JS = """
const b = document.getElementById('tabmail').currentTabInfo.browser;
const w = b && b.contentWindow;
const top = w && w.gSubDialog && w.gSubDialog._topDialog;
if (top) {
  const d = top._frame.contentDocument;
  return d && d.readyState == 'complete' && d.location.href != 'about:blank' ? 'tab dialog' : null;
}
const docs = [b.contentDocument];
const f = b.contentDocument.getElementById('contentFrame');
if (f && f.contentDocument) docs.push(f.contentDocument);
return docs.some(d => d.querySelector('dialog[open]')) ? 'html dialog' : null;
"""

# Closes the tab's dialogs without OK: gSubDialog ones, and a <dialog> by its
# form's reset (Cancel), which also runs the page's own clean-up.
CLOSE_ANY_DIALOG_JS = """
const b = document.getElementById('tabmail').currentTabInfo.browser;
const sub = b.contentWindow && b.contentWindow.gSubDialog;
for (let i = 0; sub && sub._dialogs && sub._dialogs.length && i < 10; i++) sub._topDialog.close();
const docs = [b.contentDocument];
const f = b.contentDocument.getElementById('contentFrame');
if (f && f.contentDocument) docs.push(f.contentDocument);
for (const d of docs) {
  for (const dialog of d.querySelectorAll('dialog[open]')) {
    const form = dialog.querySelector('form');
    if (form) form.reset();
    if (dialog.open) dialog.close();
  }
}
"""

CATEGORY_SHOWN_JS = """
const [id, pane] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const list = doc.getElementById('categories');
const shown = [...doc.querySelectorAll('[data-category="' + pane + '"]')].some(e => !e.hidden && e.getBoundingClientRect().height > 0);
return !!(list.selectedItem && list.selectedItem.id == id && shown);
"""

ACCOUNT_ROW_SHOWN_JS = """
const [id, page] = arguments;
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
const tree = doc.getElementById('accounttree');
const f = doc.getElementById('contentFrame');
return !!(tree.selectedRow && tree.selectedRow.id == id && f && f.contentDocument
          && f.contentDocument.readyState == 'complete' && f.contentDocument.location.href.endsWith(page));
"""

# The whole visible tab, as a PNG data URL, scaled to fit `max` pixels each
# way. With a target, that element gets SUMO's outline, drawn 1/scale
# thicker so it is `width` pixels in the file, and kept inside the picture.
VIEW_SNAPSHOT_JS = """
const [color, width, max, t, resolve] = arguments;
const browser = document.getElementById('tabmail').currentTabInfo.browser;
const doc = browser.contentDocument;
const win = doc.defaultView;
const w = win.innerWidth, h = win.innerHeight;
const scale = Math.min(1, max / w, max / h);
let box = null;
if (t) {
  const found = targetOf(t);
  if (!found) { resolve('error: no element ' + JSON.stringify(t)); return; }
  const e = found.el.getBoundingClientRect();
  const r = new DOMRect(e.x + found.dx, e.y + found.dy, e.width, e.height);
  // The border sits on the element's edge, half inside and half outside, so
  // in a list of 28-pixel rows it covers the padding of this row and of its
  // neighbours, never their text.
  const bw = width / scale;
  const x1 = Math.max(0, r.left - bw / 2), y1 = Math.max(0, r.top - bw / 2);
  const x2 = Math.min(w, r.right + bw / 2), y2 = Math.min(h, r.bottom + bw / 2);
  box = doc.createElementNS('http://www.w3.org/1999/xhtml', 'div');
  box.style.cssText = `position: fixed; z-index: 2147483647; pointer-events: none;
    box-sizing: border-box; border: ${bw}px solid ${color}; border-radius: 0;
    left: ${x1}px; top: ${y1}px; width: ${x2 - x1}px; height: ${y2 - y1}px;`;
  doc.documentElement.appendChild(box);
}
win.requestAnimationFrame(() => win.requestAnimationFrame(() => {
  const rect = new DOMRect(win.scrollX, win.scrollY, w, h);
  browser.browsingContext.currentWindowGlobal.drawSnapshot(rect, scale, 'white').then((bitmap) => {
    if (box) box.remove();
    const c = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
    c.width = bitmap.width;
    c.height = bitmap.height;
    c.getContext('2d').drawImage(bitmap, 0, 0);
    resolve(c.toDataURL('image/png'));
  }, (e) => { if (box) box.remove(); resolve('error ' + e); });
}));
"""


# --- Native windows and the file dialogs (#56) -------------------------------------

# The on-screen windows of one process, from CoreGraphics, through
# osascript's JavaScript, so this script keeps to the standard library.
NATIVE_WINDOWS_JXA = """
ObjC.import('CoreGraphics');
function run(argv) {
  const pid = Number(argv[0]);
  const list = ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID));
  const out = [];
  for (let i = 0; i < list.count; i++) {
    const w = list.objectAtIndex(i);
    if (ObjC.unwrap(w.objectForKey('kCGWindowOwnerPID')) != pid) continue;
    out.push({ id: ObjC.unwrap(w.objectForKey('kCGWindowNumber')),
               layer: ObjC.unwrap(w.objectForKey('kCGWindowLayer')) });
  }
  return JSON.stringify(out);
}
"""


def native_windows(pid, run=subprocess.run):
    """[{id, layer}] of the process's on-screen windows (macOS)."""
    res = run(["osascript", "-l", "JavaScript", "-e", NATIVE_WINDOWS_JXA, str(pid)],
              capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"osascript could not list windows: {res.stderr.strip()}")
    return json.loads(res.stdout)


def file_dialog_refusal(platform=sys.platform, groups=None, home=None):
    """Why --file-dialogs must not run in this macOS user, or None.

    The file dialog shows the user's folders, iCloud Drive and tags, so it is
    captured only in a separate, empty, standard user (#56).
    """
    if platform != "darwin":
        return "--file-dialogs works only on macOS"
    if groups is None:
        res = subprocess.run(["id", "-Gn"], capture_output=True, text=True, check=False)
        groups = res.stdout.split()
    home = home or os.path.expanduser("~")
    if "admin" in groups:
        return ("--file-dialogs refuses to run in an administrator user, because the file dialog shows "
                "that user's own folders: run it in a separate, empty, standard user (#56)")
    if os.path.isdir(os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs")):
        return ("--file-dialogs refuses to run in a user with iCloud Drive, because the file dialog shows it: "
                "run it in a separate user with no Apple Account (#56)")
    return None


def screencapture(window_id, path, run=subprocess.run):
    """Save a native window, scaled to fit MAX_PX, with screencapture and sips."""
    raw = path + ".full.png"
    res = run(["screencapture", "-x", "-o", "-l", str(window_id), raw], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"screencapture failed ({res.stderr.strip()}): give the terminal the Screen Recording "
                           "permission in System Settings › Privacy & Security")
    try:
        res = run(["sips", "-Z", str(MAX_PX), raw, "--out", path], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"sips could not scale the screenshot: {res.stderr.strip()}")
    finally:
        if os.path.exists(raw):
            os.remove(raw)
    return path


# --- The tour, apart from Thunderbird (#55) --------------------------------------

def tour_steps(categories, rows, account_label=None):
    """The steps of a tour: what each one clicks, and what it outlines next.

    `categories` are the Settings sidebar items ({id, pane, label}), `rows`
    the Account Settings tree rows ({id, page, label}). The last category's
    next item is the sidebar's Account Settings link, labelled
    `account_label`; the last row has none. The rows are known only after
    the Settings steps, and they do not change the Settings steps.
    """
    steps = []
    for c in categories:
        steps.append({"kind": "settings", "id": c["id"], "page": c["pane"], "label": c["label"],
                      "name": safe_name(f"settings-{c['pane']}")})
    for r in rows:
        steps.append({"kind": "account", "id": r["id"], "page": r["page"], "label": r["label"],
                      "name": safe_name("account-" + r["id"].replace(".xhtml", ""))})
    for i, step in enumerate(steps):
        step["name"] = f"{i + 1:02d}-{step['name']}"
        step["file"] = step["name"] + ".png"
        if i + 1 < len(steps) and steps[i + 1]["kind"] == step["kind"]:
            following = steps[i + 1]
            step["next"] = {"id": following["id"], "label": following["label"],
                            "part": ".container" if following["kind"] == "account" else None}
        elif step["kind"] == "settings":
            step["next"] = {"id": "accountButton", "label": account_label, "part": None}
        else:
            step["next"] = None
        step["next_file"] = step["name"] + "-next.png" if step["next"] else None
    return steps


ITEM_GROUPS = ("open", "file", "menu", "goto")


def items_file(version):
    """tour-items-<major>.tsv next to this script."""
    major = (version or "").split(".")[0]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"tour-items-{major}.tsv")


def read_items(path):
    """The ellipsis items of a version, {page: [item]}, from its TSV file."""
    items = {}
    with open(path, encoding="utf-8") as f:
        rows = [line.rstrip("\n") for line in f if line.strip() and not line.startswith("#")]
    header = rows[0].split("\t")
    if header != ["page", "target", "group", "name", "label"]:
        raise ValueError(f"{path}: the header must be page, target, group, name, label")
    names = set()
    for n, line in enumerate(rows[1:], 2):
        cells = line.split("\t")
        if len(cells) != 5 or not all(cells[:4]):
            raise ValueError(f"{path}: row {n} needs 5 tab-separated cells: {line!r}")
        page, target, group, name, label = cells
        if group not in ITEM_GROUPS:
            raise ValueError(f"{path}: row {n}: group {group!r} is not one of {', '.join(ITEM_GROUPS)}")
        if (page, name) in names:
            raise ValueError(f"{path}: row {n}: the name {name!r} is already used in {page}")
        names.add((page, name))
        spec = {"css": target[4:]} if target.startswith("css:") else {"id": target}
        if page.startswith("am-"):
            spec["frame"] = True
        items.setdefault(page, []).append({"target": spec, "group": group, "name": safe_name(name), "label": label})
    return items


def item_entries(step, items):
    """The item entries of a step, each with its letter and file names."""
    page_items = items.get(step["page"], [])
    if len(page_items) > 26:
        raise ValueError(f"{step['page']} has more than 26 items")
    entries = []
    for letter, item in zip("abcdefghijklmnopqrstuvwxyz", page_items):
        base = step["name"][:2] + letter + step["name"][2:] + "-" + item["name"]
        entries.append(dict(item, step=step["name"][:2].lstrip("0") + letter, file=None, next_file=None,
                            base=base, status=None))
    return entries


def tour_folder(out, version, locale):
    return os.path.join(out, safe_name(f"{version}-{locale}"))


def index_md(version, locale, steps):
    """index.md of a tour folder: one line per step and item, in the locale's words."""
    lines = [f"# Thunderbird {version}, {locale}: Settings and Account Settings", "",
             "Made by `tools/checklist/tb_shot.py tour` (sumo-linter #55, #56). Each step has the pane",
             "as it first shows and, if there is a next step, the same pane with the next item",
             "to click outlined. A step with a letter is an item whose label ends with an ellipsis:",
             "first the pane with the item outlined, then what the click opens.", "",
             "| Step | Clicked | Item outlined | Screenshot | Next item | With the next item outlined | Note |",
             "|---|---|---|---|---|---|---|"]

    def row(cells):
        lines.append("| " + " | ".join((c or "").replace("|", "\\|") for c in cells) + " |")

    for i, s in enumerate(steps, 1):
        where = "Settings" if s["kind"] == "settings" else "Account Settings"
        row([str(i), f"{where} › {s['label']}", "", s["file"], s["next"]["label"] if s["next"] else "",
             s["next_file"], ""])
        for e in s.get("items", []):
            row([e["step"], f"{where} › {s['label']} › {e['label']}", e["next_file"], e["file"], "", "", e["status"]])
    return "\n".join(lines) + "\n"


def tour(tb, out, say=print, items=None, file_dialogs=False, restart=None, capture=None):
    """Click through Settings and Account Settings, two screenshots a step.

    `items` are the ellipsis items ({page: [item]}, from read_items). Items
    that open a file dialog are taken last, with `restart()` giving a new
    Thunderbird for each one and `capture(window_id, path)` saving it.
    """
    items = items or {}
    locale = tb.locale()
    folder = tour_folder(out, tb.version, locale)
    os.makedirs(folder, exist_ok=True)
    pending = []  # the file dialogs, taken last

    def do_items(step, where):
        step["items"] = item_entries(step, items)
        for e in step["items"]:
            state = tb.item_state(e["target"])
            if state.get("label"):
                e["label"] = state["label"]
            if not state["exists"] or not state["shown"]:
                e["status"] = "hidden"
            elif e["group"] == "menu":
                e["status"] = "a drop-down menu: not clicked"
            elif e["group"] == "goto":
                e["status"] = "goes to a Settings pane: not clicked"
            elif state["disabled"]:
                e["status"] = "disabled"
            elif e["group"] == "file" and not file_dialogs:
                e["status"] = "a file dialog: needs --file-dialogs"
            elif e["group"] == "file":
                e["next_file"] = e["base"] + "-next.png"
                tb.m.js(TARGET_JS + SCROLL_TO_JS, e["target"])
                time.sleep(0.3)
                tb.view_shot(os.path.join(folder, e["next_file"]), e["target"])
                pending.append((step, where, e))
                continue
            else:
                e["next_file"], e["file"] = e["base"] + "-next.png", e["base"] + ".png"
                kind = tb.item_shots(e["target"], os.path.join(folder, e["next_file"]), os.path.join(folder, e["file"]))
                e["status"] = kind
                say(f"  {e['file']}: {e['label']} ({kind})")
                continue
            say(f"  {e['step']} {e['label']}: {e['status']}")
        targets = [e["target"] for e in step["items"]]
        unlisted = tb.unlisted_items(targets, step["kind"] == "account")
        for u in unlisted:
            say(f"  warning: {step['page']} has {u}, which is not in the item list")
        step["unlisted"] = unlisted

    settings_steps = []
    categories = tb.open_settings()
    for c, step in zip(categories, tour_steps(categories, [])):
        tb.show_category(c)
        tb.view_shot(os.path.join(folder, step["file"]))
        tb.view_shot(os.path.join(folder, step["next_file"]), step["next"])
        say(f"{step['file']}: {c['label']}")
        do_items(step, c)
        settings_steps.append(step)
    account_label = tb.m.js(ACCOUNT_BUTTON_LABEL_JS)
    rows = tb.open_account_settings()
    steps = tour_steps(categories, rows, account_label)
    for done, step in zip(settings_steps, steps):
        step["items"], step["unlisted"] = done["items"], done["unlisted"]
    for r, step in zip(rows, steps[len(categories):]):
        tb.show_account_row(r)
        tb.view_shot(os.path.join(folder, step["file"]))
        if step["next"]:
            tb.view_shot(os.path.join(folder, step["next_file"]), step["next"])
        say(f"{step['file']}: {r['label']}")
        do_items(step, r)
    for old_step, where, e in pending:
        # e is the same object as in `steps`, so its file name lands there.
        tb = restart()
        if old_step["kind"] == "settings":
            tb.open_settings()
            tb.show_category(where)
        else:
            tb.open_settings()
            tb.open_account_settings()
            tb.show_account_row(where)
        e["file"] = e["base"] + ".png"
        tb.click_for_file_dialog(e["target"], lambda wid, e=e: capture(wid, os.path.join(folder, e["file"])))
        e["status"] = "file dialog"
        say(f"  {e['file']}: {e['label']} (file dialog)")
    with open(os.path.join(folder, "index.md"), "w", encoding="utf-8") as f:
        f.write(index_md(tb.version, locale, steps))
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": tb.version, "locale": locale, "steps": steps}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return folder, steps


ACCOUNT_BUTTON_LABEL_JS = """
const doc = document.getElementById('tabmail').currentTabInfo.browser.contentDocument;
return doc.getElementById('accountButton').textContent.trim();
"""


# --- Publishing a tour as a GitHub release asset (#55) ----------------------------

def release_tag(version):
    return f"screenshots-{version}"


def zip_tour(folder, dest_dir):
    """VERSION-LOCALE.zip of a tour folder, from its index.json."""
    try:
        with open(os.path.join(folder, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        version, locale, steps = index["version"], index["locale"], index["steps"]
    except (OSError, ValueError, KeyError) as e:
        raise RuntimeError(f"{folder} is not a finished tour (index.json: {e})")
    files = ["index.md", "index.json"] + [x[k] for s in steps for x in [s, *s.get("items", [])]
                                          for k in ("file", "next_file") if x[k]]
    missing = [n for n in files if not os.path.isfile(os.path.join(folder, n))]
    if missing:
        raise RuntimeError(f"{folder} lacks {', '.join(missing)}")
    name = f"{version}-{locale}"
    path = os.path.join(dest_dir, name + ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in files:
            z.write(os.path.join(folder, n), f"{name}/{n}")
    return path, version, locale, len(files) - 2


def release_notes(version):
    return (f"Screenshots of every Settings category and Account Settings page in Thunderbird {version}, "
            "one zip per locale, made by `tools/checklist/tb_shot.py tour` (#55). Each zip has an "
            "index.md that lists the steps.\n")


def publish(folder, replace=False, run=subprocess.run, say=print, repo=RELEASE_REPO):
    """Add a tour folder's zip to the release of its version, creating it if needed."""
    with tempfile.TemporaryDirectory() as tmp:
        path, version, _locale, count = zip_tour(folder, tmp)
        tag, asset = release_tag(version), os.path.basename(path)
        view = run(["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
                   capture_output=True, text=True)
        if view.returncode != 0:
            if "release not found" not in (view.stderr or ""):
                raise RuntimeError(f"gh release view {tag} failed: {(view.stderr or '').strip()}")
            command = ["gh", "release", "create", tag, path, "--repo", repo,
                       "--title", f"Thunderbird {version} screenshots", "--notes", release_notes(version)]
            action = "created the release"
        else:
            names = [a["name"] for a in json.loads(view.stdout or "{}").get("assets", [])]
            if asset in names and not replace:
                raise RuntimeError(f"{tag} already has {asset}: give --replace to replace it")
            command = ["gh", "release", "upload", tag, path, "--repo", repo] + (["--clobber"] if asset in names else [])
            action = "replaced" if asset in names else "added"
        res = run(command, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"{' '.join(command[:3])} failed: {(res.stderr or '').strip()}")
    say(f"{tag}: {action} {asset} ({count} screenshots), https://github.com/{repo}/releases/tag/{tag}")
    return command


# --- Commands -------------------------------------------------------------------

def session(tb, out, read=sys.stdin.readline, write=None):
    """Answer screenshot requests, one JSON line each, until the input ends."""
    write = write or (lambda line: (sys.stdout.write(line + "\n"), sys.stdout.flush()))
    write(json.dumps({"ok": True, "ready": True, "version": tb.version}))
    while True:
        line = read()
        if not line:
            return
        try:
            req = json.loads(line)
            text, name = str(req["text"]), safe_name(str(req["name"]))
        except (ValueError, KeyError, TypeError):
            write(json.dumps({"ok": False, "error": "bad request"}))
            continue
        path = os.path.join(out, name + ".png")
        try:
            where, size = tb.shot(text, path)
            write(json.dumps({"ok": True, "path": path, "where": where, "size": size}))
        except (LookupError, RuntimeError) as e:
            write(json.dumps({"ok": False, "error": str(e)}))


def safe_name(name):
    """A file name with no folders in it."""
    name = "".join(c if c.isalnum() or c in "-_." else "-" for c in name).strip(".-")
    if not name:
        raise ValueError("empty name")
    return name


def option(args, flag, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 >= len(args):
            sys.exit(__doc__)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("shot", "session", "login", "tour", "publish"):
        sys.exit(__doc__)
    command = args.pop(0)
    if command == "publish":
        replace = "--replace" in args
        args = [a for a in args if a != "--replace"]
        if len(args) != 1 or args[0].startswith("-"):
            sys.exit(__doc__)
        try:
            publish(args[0], replace)
        except RuntimeError as e:
            sys.exit(str(e))
        return
    app = option(args, "--app")
    out = option(args, "--out")
    text = option(args, "--text")
    expect = option(args, "--expect")
    account = option(args, "--account", "dummy")
    file_dialogs = "--file-dialogs" in args
    args = [a for a in args if a != "--file-dialogs"]
    if command == "login":
        if not app or args or out or text:
            sys.exit(__doc__)
        try:
            login(app)
        except RuntimeError as e:
            sys.exit(str(e))
        return
    if not app or not out or args or (command == "shot") != bool(text) or account not in ("dummy", "real"):
        sys.exit(__doc__)
    if file_dialogs and command != "tour":
        sys.exit(__doc__)
    if file_dialogs and file_dialog_refusal():
        sys.exit(file_dialog_refusal())
    items = {}
    if command == "tour":
        path = items_file(version_of(app))
        if os.path.isfile(path):
            try:
                items = read_items(path)
            except ValueError as e:
                sys.exit(str(e))
        else:
            print(f"No {os.path.basename(path)}: items with an ellipsis are not clicked.")

    def start():
        return Thunderbird(app, expect, ACCOUNT_PROFILE if account == "real" else None)

    try:
        tb = start()
    except RuntimeError as e:
        sys.exit(str(e))
    current = [tb]  # the Thunderbird to quit at the end, after any restart

    def restart():
        current[0].quit()
        current[0] = start()
        return current[0]

    try:
        if command == "shot":
            where, size = tb.shot(text, out)
            print(f"{out}: {size[0]}×{size[1]}, {where}")
        elif command == "tour":
            folder, steps = tour(tb, out, items=items, file_dialogs=file_dialogs, restart=restart,
                                 capture=lambda wid, path: screencapture(wid, path))
            shots = sum(bool(x[k]) for s in steps for x in [s, *s["items"]] for k in ("file", "next_file"))
            print(f"{folder}: {len(steps)} steps, {shots} screenshots")
        else:
            os.makedirs(out, exist_ok=True)
            session(tb, out)
    except (LookupError, RuntimeError, ValueError) as e:
        sys.exit(str(e))
    finally:
        current[0].quit()


if __name__ == "__main__":
    main()
