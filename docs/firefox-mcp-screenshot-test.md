# Can firefox-mcp take SUMO screenshots of Firefox Settings?

Test date: 2026-11-25. Tested with `@mozilla/firefox-mcp` 0.11.0 from npm, Firefox 161.0 on
macOS, headless, a 1280x900 viewport and an empty temporary profile.

## Result

Yes, with one condition. If Firefox runs without `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1`, it
refuses to open `about:preferences` at all. If the variable is set, the public package opens
Settings and runs scripts with chrome privileges in the Settings page. It also screenshots
the page and its in-page subdialogs. It cannot reach the browser's own window (toolbar, menus, panels)
or a dialog in a separate window, because the public package does not include the privileged
tools.

## What was tested

The test used a small MCP client over stdio (JSON-RPC lines to `dist/index.js`), not an
agent. It called the tools in a fixed order, so every result below is a direct tool result.

1. Started the server with `--toolPreset all`. The server logged this line:
   `Tool modules are not available in this build and were skipped: launch, prefs, privileged, bidi`.
   The public package drops the privileged tools even when you ask for them.
2. Called `navigate_page` to `about:preferences#privacy` with no environment variable. The
   result was `BiDi error: "unsupported operation": Navigation to "about:preferences#privacy"
   is not allowed in this context`. `new_page` gave the same error.
3. Passed `--startUrl about:preferences`. Every later tool call failed with the same error,
   including `list_pages` and `screenshot_page`, so the session was unusable.
4. Set `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` for the server and passed
   `--env MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` for Firefox. Then `navigate_page` to
   `about:preferences#privacy` worked in 1.7 s, and `list_pages` showed the tab as `Settings`.
5. `screenshot_page` returned the viewport in 71 ms. With `fullPage: true`, it returned the
   whole scrollable pane in 327 ms.
6. `take_snapshot` returned the Settings page as an accessibility tree with UIDs, for example
   `tab "Privacy and security"`. These UIDs work with `click_by_uid` and `screenshot_by_uid`.
7. `evaluate_script` ran in the Settings page with chrome privileges: `typeof Services` was
   `"object"` and `Services.appinfo.version` was `"161.0"`. The script scrolled `#historyMode`
   to the center and drew a fixed overlay with a 3 px `#f71701` outline around it. The next
   screenshot showed the History radio group with the outline, in SUMO's style.
8. A script clicked `#connectionSettings`. The next screenshot showed the Connection Settings
   subdialog over the dimmed pane. The subdialog is an in-page frame (`.dialogFrame`), so the
   page screenshot includes it.

One mistake in the test: the overlay from step 7 stayed in step 8, because a change of the
`#` part of the address does not reload the page. A real script must remove its overlay
before it outlines the next setting.

## What it cannot do

- Screenshot the browser window: the toolbar, the menus, the panels or the address bar. The
  public package has no tool for chrome windows.
- Screenshot a dialog in a separate window. Only in-page subdialogs are part of the page.
- Run safely with your normal Firefox profile. `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` gives the
  remote client chrome privileges. Use it only with a temporary profile.
- Work with Thunderbird. This was not tested, and the package documents Firefox only.

## Comparison with tb_shot.py

`tools/checklist/tb_shot.py` uses Marionette directly with the same environment variable. It
reaches chrome windows, separate prompt windows and file dialogs, and it has no dependencies.
For Firefox Settings panes and their in-page subdialogs, firefox-mcp is enough. It is useful
for exploring a pane by hand from Claude Code, because `take_snapshot` lists every control
with a UID. For a repeatable screenshot tour like #55, a Firefox version of `tb_shot.py` is
the better start. A tour needs the browser window and separate dialogs too. An MCP server
also adds Node, Selenium and an agent to a process that must give the same result every
time.

## How to repeat the test

```sh
mkdir -p /tmp/fxmcp-pkg && cd /tmp/fxmcp-pkg
npm init -y && npm install @mozilla/firefox-mcp@0.11.0
MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1 node node_modules/@mozilla/firefox-mcp/dist/index.js \
  --headless --viewport 1280x900 --profilePath /tmp/fxmcp-test/prof \
  --env MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1
```

Then send MCP `initialize` and `tools/call` requests on stdin, one JSON object per line.
To use it from Claude Code, add the same command with `claude mcp add`.
