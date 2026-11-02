# CLAUDE.md

## What this is

`sumo-linter` — a linter and opinionated formatter for SUMO (support.mozilla.org)
Knowledge Base wiki markup, scoped to **MZLA Thunderbird** content.

- **Phase 1:** detect and fix genuine formatting errors.
- **Phase 2:** apply opinionated house style (Black/Ruff-style), as a *named preset*.
- **Phase 3+:** non-English locales.

Firefox and other non-MZLA products are deliberately out of scope for style — they keep
their own conventions. This is why the style layer must be a configurable preset
(`style = "thunderbird"`) on top of a product-neutral correctness core, never hardcoded.

Scope: products `thunderbird` + `thunderbird-android` on **production**
(`support.mozilla.org`). Locale-aware architecture from day one, but **only en-US is
implemented**. The signed-in listing has 202 articles. The 196 public ones are committed under `corpus/`,
refreshed 2026-10-31 (#17). `corpus/README.md` records how the public/non-public split is decided
and why it cannot be inferred from the API.

## Current state

Phases 1 and 2 are implemented and tested. `cargo test` runs 42 tests, including property
tests over every corpus article.

The corpus is no longer Thunderbird-only: `corpus-other/` holds 475 public Firefox
articles, 207 other-product templates and the 5 markup-documentation articles — 897
documents of en-US source in total, all round-tripped in CI. It exists for lexer coverage
*and* for the markup-aware search in issue #6. Thunderbird **style** still applies only to
`corpus/`.

Linting the committed corpus reports **5 errors, all verified by hand** and all filed:
#223 and #225 (unbalanced `'''`) and #228 (two `{for}` bugs in
`keyboard-shortcuts-thunderbird` that the earlier regex audit could not detect, because the
file's 294/294 tag totals balance). The fifth is new in the 2026-10-31 refresh and filed as
#248: SW007 in `filelink-large-attachments` line 26, an image link closed with `]]]]`, which
SUMO renders as a literal `]]`. It was 5 until the 2026-09-09 refresh as well: the SW004 in
`thunderbird-desktop-and-thundermail` (#224) has since been fixed upstream — so **re-lint after a
rescrape and treat a change in that count as a real signal**, about either the articles or
the linter.

The WASM build and web app are **verified working in a real browser**: all six exports load,
diagnostics render with correct line/column, both buttons behave, and a 124 KB input with
Arabic, Japanese and em-dashes lints in 4 ms and styles in 11 ms while still round-tripping.

Toolchain: **rustup-managed rustc/cargo 1.97.1** plus the `wasm32-unknown-unknown` target,
Node 22, Playwright + Chromium 1234. Homebrew's `rust` formula was removed — having both
meant a stray `/opt/homebrew/bin/cargo` would silently lack the WASM target.

Build and serve the web app:

```sh
tools/build-web.sh                        # writes web/sumo_lint_wasm.wasm (~116 KB)
python3 -m http.server -d web 8412        # pick a free port; 8099 is often taken
```

## Where to pick up

Phases 1 and 2 are done, pushed, and CI is green. The web app is live at
<https://thunderbird.github.io/sumo-linter/>.

**Open, on Roland's side (no deadline):**
- **Staging test of the Thunderbird 159 string edits (#28).** Paste
  `tools/ui-strings/proposals/advanced-panel-settings-in-thunderbird.wiki` and
  `privacy-panel-settings-in-thunderbird.wiki` into support.allizom.org, work through the
  checklist comment on #28 (walk it with `uv run tools/checklist/walk.py
  https://github.com/thunderbird/sumo-linter/issues/28#issuecomment-6549440976 --web
  tools/ui-strings/proposals`, which also opens the web app at each item's line, #31), and report
  there. Next session: read that comment's ticks and `Note:` lines first. Then adjust `propose_edits.py` and do the other
  knowledgebase-issues #247 articles. The 160 section of #249 waits for the 160 release.
- Post the heading-convention consultation: `docs/heading-convention-discussion.md` plus
  the data gist <https://gist.github.com/rtanglao/2708f762f5a4ec71c699827d8bc4071f>.
  **This blocks nothing** — the per-article default needs no decision.
- Fix the four filed markup bugs: knowledgebase-issues **#223, #224, #225, #228**.
- Triage the 8 non-public drafts: knowledgebase-issues **#227** (has a checklist). Two of
  the eight are not drafts at all — `invalid-certificates` is a misfiled support question,
  and `troubleshoot-pdf-and-email-issues-thunderbird` reads like machine-generated filler.

**Open, for a future session:**
- **Shipped 2026-10-14:** the web app preview with the `{for}` System/version selector (#14)
  and SW012, `{for fxN}` in a Thunderbird article (#15). Unverified against live SUMO: how
  SUMO treats `fxN` in a Thunderbird article (the preview ignores it), and the heading-id
  slug for duplicate headings. Settle both with a `--rendered` scrape if a mismatch is
  reported.
- sumo-linter **#1 is answered** (2026-09-09), and the answers are in
  `corpus-other/README.md`: `{{{n}}}` does not exist but `{{{name}}}` does (31 uses, all
  named); `REDIRECT` is real but appears once, bare, with no leading `#`; and
  `[[Include:]]` occurs **nowhere** in 895 documents, so that path has no production markup
  to test against — a finding, not a gap. The same sweep found 21 real unbalanced-`{for}`
  errors in Firefox articles (correctness rules are product-neutral, now with evidence) and
  the SW007 false positive fixed in #7.
- Phase 3: non-English locales. Locale is already threaded through; no en-US assumptions
  live in rule logic.
- A **markup-aware search engine** over the KB — Roland's stated goal, 2026-09-09. SUMO's
  search indexes *rendered* text, so it cannot answer "which articles reference
  `[[Template:X]]`" or "which use this construct". Nothing is built; the point for now is
  that it makes corpus scrapes **complete sets, not samples** — `corpus-other/` exists for
  round-trip coverage *and* for this — and that the lossless token stream is already the
  right substrate: queries over token kinds rather than regexes over text.

**Do not redo:** the corpus is already scraped and committed (rescraping is cheap to *ask*
for and expensive to *run* — a full pass is ~200 signed-in page fetches and reliably earns
a 429 for the rest of the hour); the heading data is already measured; the four bugs are
already filed with rendered-output evidence. **Every test now runs in CI** — `rust`,
`vscode` (31 grammar + 51 link + 26 bold assertions, plus all 907 articles against SUMO's
highlighting rules), `emacs` (99 mode assertions, against the real CLI, plus the 907),
`vim` (109 plugin assertions, run under both Vim and Neovim, plus the 907), `ui-strings` (33 tests, plus 32 for the checklist walker and 24 for its Thunderbird screenshots, including that the committed comparison tables
are up to date) and `web` (31 assertions on the fix arithmetic, 16 on the line-number gutter, 21 on the Copy
button, 72 on autosave, save-to-file and the file name, 99 on the preview, 30 on walk mode, 35 on highlighting) — so there is no
by-hand test suite left.
LSP quick fixes (`textDocument/codeAction`) are implemented, tested, pushed and
CI-green as of 2026-08-17;
the VS Code `SUMO: Insert Link` command (`Cmd+K Cmd+L`) was added 2026-08-19, and
paste-a-URL-over-a-selection (sumo-linter #2) on 2026-08-28, and insert-link in Emacs and
Vim the same day, which brought the three editors to parity; toggle-bold landed in all
three at once on 2026-10-05 (sumo-linter #10), bound to `Cmd+B` in VS Code at Roland's
request and confirmed working in his editor the same day; the web app gained a
line-number gutter on 2026-10-07 (sumo-linter #9), verified in Chromium and live on Pages; a Copy button (sumo-linter #12) on 2026-10-14, which
copies the textarea exactly as it is, never with pending fixes applied, and says *Copy failed*
rather than failing silently; and autosave to `localStorage`, a Clear button and Save to
file (sumo-linter #13) the same day, saving `article.wiki` (all three editor modes open
`.wiki`), verified in Chromium and in Playwright's Firefox; and on 2026-10-30 a
file-name box (sumo-linter #16): a typed name, else the first h1, else the first h2, else
`article.wiki`, with the fallback shown as the box's placeholder because the first h1 is a
section heading and can be as generic as `Background`;
the editor-side setup they need is in `editors/README.md`, including the GhostText
`fileExtension` setting without which the extension never activates on a SUMO textarea.

## Hard-won facts about SUMO (verified live — do not re-derive)

**The markup is not Markdown.** It's Kitsune's own wiki dialect. A Markdown parser is the
wrong tool. Authoritative sources:
- `kitsune/wiki/parser.py` and `kitsune/sumo/parser.py` in mozilla/kitsune
- KB articles `markup-chart`, `markup-cheat-sheet`, `how-to-use-for`, `using-templates`

**Both prod and staging sit behind a Fastly client challenge.** Every plain HTTP request —
including `/api/1/kb/` — gets a 3038-byte JS interstitial titled `Client Challenge`. `curl`
cannot be used. A real browser is mandatory.

**`--disable-blink-features=AutomationControlled` is load-bearing.** The challenge gates on
`navigator.webdriver`. Measured, and counterintuitive: bundled Chromium *with* the flag
clears the challenge; `channel:'chrome'` *without* it stays blocked forever. Do not "clean
up" that launch arg.

**The public API never exposes raw wiki source.** `/api/1/kb/<slug>` returns
`id, title, slug, url, locale, products, topics, summary, html` — `html` is rendered.
`/kb/<slug>/history` and `/revision/<id>` are public but also rendered. Raw source lives
only in `<textarea name="content">` on `/<locale>/kb/<slug>/edit`, which **requires login**
on prod and staging alike.

**`?product=` is singular.** `?products=thunderbird` is silently ignored and returns the
entire 1493-article KB. A silent, easy-to-miss trap.

**SUMO rate-limits aggressively (429), including top-level navigation.** A 429 on a
navigation surfaces as `net::ERR_HTTP_RESPONSE_CODE_FAILURE`, not a status code. Backoff is
required in both the in-page fetches and `page.goto`. Bans persist for minutes; retrying
early may prolong them. Keep `--delay` high and prefer cached corpus files.

**Articles cannot be deleted on SUMO.** The available action is marking an article
**obsolete** (previously called "Archive"). Never recommend or describe deletion of a KB
article — the platform does not support it. Spam and misfiled content get marked obsolete.

**A template's slug cannot be derived from its title, and the API does not list templates
at all.** A `# COMPLETE` anonymous enumeration of `/api/1/kb/` returns 1325 public en-US
articles and zero templates. The KB contains `templatesharearticle` (colon dropped,
lowercased), `templateopenProfileFolderTB` (case kept) and `Template:optionspreferences`
(colon kept) — three conventions, so 44 guessed candidates all 404ed. Kitsune resolves
`[[Template:X]]` by *title*, so fetching one needs a title→slug map, and `/en-US/kb/all`
(`--all-docs`, 5299 documents, 221 templates) is the only index with both.

**A 404 to anonymous requests does not mean "unpublished draft."** Obsolete/archived, no
approved revision, and otherwise restricted all look identical from outside. Distinguishing
them requires the authenticated edit page or the SUMO admin UI.

**Free oracle:** the API's rendered `html` plus scraped source gives ~156
`(source → Kitsune's own HTML)` pairs. Useful for validating grammar assumptions without
running Kitsune in Docker. Opt in with `--rendered` (doubles request count).

## Scraper runbook

```sh
cd tools/scrape
npm install                 # once
npx playwright install chromium
npm run login               # you sign in by hand; session persists to .auth/
npm run scrape              # resumable; skips cached files
npm run scrape -- --limit 3 # trial
npm run report              # writes corpus/report.md
```

Read-only by construction: GETs only, never submits a form, defaults to staging
(`--base https://support.mozilla.org` to switch). `.auth/` is gitignored; **public** en-US
source is committed (see `corpus/README.md` and `corpus-other/README.md` for the rule and
the exclusions) — never commit an authenticated session or a non-public article.

Other modes, each added because nothing else could answer the question: `--force`
(re-fetch cached), `--list-only` (enumerate without a login), `--profile <dir>` (a throwaway
profile, i.e. what an *anonymous* visitor sees), `--only <listing>` (fetch nothing outside
an allow-list), `--slugs <file>` (`slug<TAB>name`, for documents no listing exposes),
`--all-docs` (page `/en-US/kb/all`, the only index containing templates), `--probe <file>`
(which slugs exist, by status code, no login, never fetches a body), `--path <p>` (one
arbitrary path through the same challenge/429/5xx handling), `--out <dir>`.
`batch.sh <product|--slugs FILE> <outdir> [batch] [allow-list]` paces a long scrape.

**Two tooling lessons, each of which cost a run on 2026-09-09:**

- **"Nothing left to do" and "nothing was done" are opposite outcomes that look identical
  from inside a loop.** This bit three times in one session: a two-file `awk` whose empty
  first file made every slug read as already-done (and reported success having probed
  nothing); `batch.sh` stopping because a pass *fetched* nothing when on a resume its whole
  batch was merely cached — it announced "firefox is complete" at 180 of 475 and deleted the
  state file that would have shown otherwise; and a truncated listing that would have filed
  every unreached article as an unpublished draft. Every such loop now compares what it
  recorded against what it asked for, and says which case it hit — hence the `# COMPLETE` /
  `# INCOMPLETE` marker that `public-index.mjs` refuses to run without.
- **Review the recovery path as carefully as the main one.** The resume line `batch.sh`
  wrote on failure omitted the allow-list, so following its own instructions would have
  dropped `--only` and started fetching drafts — the recovery path reintroducing exactly the
  hazard the flag exists to prevent.

## Architecture

Cargo workspace with **zero dependencies**. The core does no I/O so it compiles to WASM.

| Crate | Role |
|---|---|
| `crates/sumo-wiki-core` | lossless lexer → rules → formatter. No fs, no network, no deps. |
| `crates/sumo-lint-cli` | `sumo-lint` binary: hand-rolled args, `--fix`, `--style`, `--diff`, JSON |
| `crates/sumo-lint-lsp` | LSP over stdio: diagnostics, `textDocument/formatting`, `codeAction` quick fixes |
| `crates/sumo-lint-wasm` | four C-ABI exports (`lint`, `fix`, `style`, `is_lossless`) — no wasm-bindgen |
| `editors/` | VS Code extension (LSP client + TextMate grammar + `SUMO: Insert Link` + `SUMO: Toggle Bold` + URL-paste handler); Emacs mode; `editors/vim/` Vim-script plugin (Vim 8+ and Neovim); LSP wiring for Neovim and ALE |
| `tools/scrape/` | dev-only Node corpus fetcher (not a runtime dependency) |
| `tools/checklist/` | `walk.py URL`: walks the unchecked `- [ ]` items of a GitHub issue or comment through `gh`, checking each or adding a `  - Note:` line, and saves after every answer (#30). Made for the #28 test checklist. `--web DIR` (#31) serves `web/` on `127.0.0.1` with `?walk=1` and sends the page each item's file (`DIR/<heading>.wiki`) and `Line N:` over Server-Sent Events, so the cursor follows the checklist in one tab. Walk mode never touches `localStorage`, and Save to file suggests `<file>-edited.wiki` so the proposal is never replaced. To continue from his edits, never touch `proposals/`: make a new folder, copy each edited file into it under the article's plain name (the newest download, since Firefox and Safari add `(1)`, `(2)`…), copy the unedited articles from `proposals/`, and pass that folder to `--web`; documented in walk.py's docstring. The answer `g` (#34) uses an item's `(possible 159 text: …)` in the page: it replaces the old text and its `<!-- CHECK 159 … -->` comment, and walk.py checks the item only after the page reports success (`g some text` adds a comment to the note), because no answer must never look like done. All 29 guesses in the #28 checklist match their comment. Run it with `uv run` (#32): a PEP 723 block with no dependencies. It must stay one file, because `python3 -I` also works and drops the script's folder from `sys.path`. `--shots DIR --thunderbird APP [--expect 159]` (#39) screenshots each item's setting with `tb_shot.py`, a separate stdlib script that walk.py runs as a child (`session`, JSON lines on stdin/stdout), so walk.py stays one file. It starts a **second** Thunderbird with a temp profile, `-no-remote -new-instance --marionette` and `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` (chrome access is refused without it), plus a dummy IMAP account at `imap.invalid`, offline, for Account Settings. The setting is found by its 159 text (after `→`, else the possible 159 text, else `(shot: "…")`, which wins) in every Settings pane, then the Settings dialogs (Connection, Offline, …), then the Account Settings pages, which use DTD strings, not Fluent IDs. Captured in SUMO's style (`how-to-make-screenshots` in `corpus-other/markup-docs/`): a square `#f71701` outline drawn as an overlay over the whole page (a CSS outline on a radio is cut off by its dialog), the setting centered, at most 620 px each way, at scale 1 with `drawSnapshot`, because element screenshots and frame switching do not reach the Settings page. Measured traps: `offline.startup_state` 1 means "ask" (a prompt on every start; 3 is always offline), `gotoPref` shows a pane asynchronously, `SubDialog` in 159 has no `abortAll`, and Marionette's sandbox has no `ownerGlobal`. All 47 #28 items with a 159 text get a screenshot. Each new screenshot opens in the image viewer (`open -g`, so the terminal keeps the focus), and with `--web`, `c` on an item without a guess deletes that line's `<!-- CHECK the 159 string is correct -->` through the same page-edit round trip as `g`, checking only after the page reports (#41). `--real-account` / `tb_shot.py --account real` (#40) runs a temp **copy** of `.auth/thunderbird-profile` (gitignored), online, and deletes it after, because it holds OAuth tokens; `tb_shot.py login` opens that profile for Roland to add the **test** account by hand (its OAuth opens in Firefox; the script never types a password). Measured 2026-11-01: the copy checks mail over OAuth2 (status 0) and screenshots Account Settings with no prompt. Untested: whether a token refresh in a copy, after the access token expires, invalidates the original's refresh token; if `--account real` starts asking to sign in, run `login` again |
| `tools/ui-strings/` | dev-only Python (stdlib) tools for UI string changes, plus the 158 string sheet. `README.md` says how to add a version. `search.py` finds KB articles that quote changed strings (knowledgebase-issues #247, #249), and its docstring lists the matching lessons that the markup-aware search (#6) must keep. `extract.py` reads the en-US Settings and Account Settings strings out of an installed app's `omni.ja` into `strings/<version>.tsv` (committed). `compare.py` writes `string-versions.md`/`.mediawiki`: one column per version, mapped to CSV records (#18). `l10n_tables.py` writes the simpler visible-text tables for SUMO localizers, one for Settings and one for Account Settings per version set, `strings-<versions>-settings.*` and `strings-<versions>-account-settings.*` (#19, #20). The string file decides the window, because the same text can be in both. `shipped_search.py` finds the articles that quote a string that really changed, split into "changed in 159: edit now" and "changed in 160: edit when 160 is released"; its `affected-*.md` output is the body of knowledgebase-issues #247 and #249 (#27). The two 3-column wikitext tables are copied by hand to wiki.mozilla.org (`User:Rolandtb/strings-153.6.0-159.0-160.0-settings` and `-account-settings`), so update them after regenerating; the README has the check. A reworded string usually gets a new ID, so the CSV record is what links old and new |
| `web/` | static Pages app — **paste-in only** (can't fetch source: needs auth + CORS); byte↔UTF-16 arithmetic isolated in `fixes.js`, gutter line counting in `gutter.js`, Copy-button outcome in `copy.js`, autosave and the file-write queue in `save.js`, the preview renderer and `{for}` rules in `preview.js`, the walk-mode line range in `walk.js`, SUMO's markup highlighting in `highlight.js`, all tested under Node — plus a pink dot beside **Wiki markup** (#33) when the text differs from the last loaded or file-saved text; autosave to `localStorage` does not count as saved |

**Losslessness is non-negotiable.** Tokens tile the input exactly, so reprinting an
unmodified parse is byte-identical. This is asserted in the lexer, property-tested over
every corpus article, and re-checked before `--fix` writes a file — a lexer bug would
otherwise corrupt articles silently.

It is a **token stream**, not a full CST. That is enough for phase-1 rules and phase-2
formatting; do not describe it as a tree.

**Product-specific rules sit behind `Product`, never in the neutral core.** A construct can be
right in one product and wrong in another: `{for fx152}` is correct in a Firefox article and
probably a copy-paste error in a Thunderbird one (SW012, #15). So `rules::check` stays
product-neutral, `rules::check_product` holds the rest, and `Document::diagnostics()` means
`diagnostics_for(Product::Any)`. The CLI, LSP and web app lint as `Thunderbird`, because they are
scoped to it; `sumo-lint --product any` turns the product rules off. Measured: the 475 Firefox
articles give 1804 SW012 warnings by default and none with `--product any`. The one `fx152` in
`corpus/` (`what-mozilla-maintenance-service`) is inside an HTML comment, so the Thunderbird
corpus reports none — correctly.

Diagnostics carry a stable code (`SW001`), severity, byte span, message, and an optional
fix marked `Safe` or `Unsafe`; only `Safe` fixes apply without `--unsafe-fixes`. **`Safe`
means the author's intent is unambiguous, not that rendering is unchanged** — SW009 and
SW010 turn inert Markdown into a real link and real bold, and `=h1` → `=h1=` turns a
literal line into a heading. What makes a fix `Unsafe` is a real choice between plausible
repairs: `==H ===` could have meant either level, and picking one silently changes what the
article says. Apply that test to every new rule. In the LSP
both kinds are offered as quick fixes (`Unsafe` titled *(needs review)*), because accepting
a code action is a deliberate, undoable choice, unlike a CLI writing files unattended. The
web app follows the same rule with a **Fix** button on each diagnostic, and earns the
"undoable" half of that claim: it edits the textarea through `execCommand('insertText')`,
deprecated but still the only way to keep a textarea's native undo stack — assigning
`.value` throws the history away. It also refuses to splice if the text changed since the
lint that produced the offsets, because linting is debounced and a click can arrive first.

**The web app's line numbers keep the textarea wrapping.** A SUMO paragraph is one long
source line, so `wrap="off"` would mean constant horizontal scrolling. Instead `gutter.js`
counts lines exactly as `line_col` does (only `\n`), and `app.js` gives each number the
height its line takes in a hidden mirror at the textarea's content width. Gutter and
textarea must share one font and line height, or the numbers drift. Measured: alignment
is exact to the last line after a resize, and a 126 KB text lints and redraws in 39 ms.
Line marks clear while an edit changes the line count, until the debounced re-lint, so
they never sit on the wrong line.

**The preview is a JavaScript renderer, not a WASM export** (#14). It needs no module, so it
works before the linter loads, and it cannot hit the stale-module trap below. It approximates
Kitsune: templates, images and videos are placeholders, article links have no target (a title
does not give a URL). Its output goes into `innerHTML`, so raw HTML keeps only allow-listed tags
with no attributes, and links only http/https/ftp/mailto; the test asserts that every corpus
article renders with no tag outside that list. `{for}` follows `how-to-use-for`: hidden
branches stay in the DOM with `hidden`, as on SUMO, and leave the table of contents; `fxN`/`mN`
are ignored, and SW012 reports them. The version defaults to the latest monthly Thunderbird
release, as SUMO's sidebar does (#29): the page reads it from product-details.mozilla.org, with a
built-in fallback (`FALLBACK_LATEST_RELEASE` in `preview.js`, update it now and then), and the
version box also takes a number or `all`. A comment leaves a marker until the end, because
`{<!-- -->key}` is the documented way to show a macro literally. Measured: 131 KB renders in
29 ms under Node; checked in Chromium and Playwright's Firefox (columns, hide controls, `{for}`
selector, persistence across reload).

**The editor highlights markup with SUMO's own rules and colors, not the lexer** (#35). SUMO's
editor is CodeMirror 5 with a simple mode (regexes per state) in Kitsune's
`codemirror.sumo-mode.js`; `highlight.js` copies those rules unchanged (BSD-3 notice kept, Kitsune
commit pinned) and runs them as CodeMirror's `simple.js` does, so SUMO's gaps are kept on purpose:
`{/key}` is plain, `==H ===` is bold because the heading regex backtracks. The colors are Kitsune's
`--codemirror-*` values, light and dark. A highlighted `<pre>` sits behind the textarea, whose text
is transparent, so undo, Fix, Copy and walk mode are unchanged. It redraws on every input, not
debounced, or the old text would show: `highlightLines` redoes only the changed lines, and each line
is its own block, because as one paragraph Chromium laid out all 127 KB again per keystroke (13 ms;
1.3 ms as blocks). Measured in Chromium and Playwright's Firefox: drawing both layers in one color
and diffing screenshots gives no offset beyond antialiasing. A **Highlighting** switch turns it off
(`sumo-lint:highlight`). Vim, VS Code and Emacs got the same rules in #36 and #37.

**Autosave never writes the example or a cleared box over the author's file.** In Chrome
and Edge, Save to file keeps a File System Access handle and writes every change to it,
one write at a time with the latest text winning (`fileWriter`). Clear and *Load an
example* both drop that handle first and replace the text undoably, so Cmd+Z brings the
old text back and autosaves it again, while the file on disk keeps the last real version.
Firefox and Safari have no such API, so there each click downloads a new copy.

**Pages caches `app.js` and the `.wasm` independently** (`max-age=600`), so for ten minutes
after a deploy a returning visitor can run new JS against the previous module. Measured on
the live site, where it presented as a Fix button that threw. Two guards, both needed: the
module is fetched with `cache: 'no-cache'` so it revalidates, and a fix without a span is
rendered as description-only rather than as a button. Test a change to the JSON shape by
building the previous module and serving it under the new page — the failure is invisible
otherwise, because a local build always ships both halves at once.

**Paste-a-URL-over-a-selection hooks paste, never rebinds it.** In all three editors the
gesture is "select words, paste a URL, get `[url words]`", and in all three the paste key
must keep pasting: VS Code uses a `DocumentPasteEditProvider` (not a `Cmd+V` binding, which
would replace paste in `.sumo` files with input boxes), Emacs remaps `yank` (so it follows
`C-y` *and* `s-v`), Vim maps visual-mode `p`/`P` buffer-locally. Each falls through to the
ordinary paste unless the gesture is unambiguous — single non-empty single-line selection,
register/clipboard is one whitespace-free URL, selection isn't itself a URL or bracketed —
because a paste handler that guesses silently mangles the clipboard. External form only:
internal links go by article *title*, which a `/kb/<slug>` URL does not carry.

Per-editor traps, all measured: VS Code needs **1.97+** (`engines.vscode` was bumped),
guarded so an older host loses the handler rather than failing to activate. Emacs
`delete-selection-mode` deletes the region in `pre-command-hook`, so the command needs a
function-valued `delete-selection` property to keep its link text — and `transient-mark-mode`
is **nil under `--batch`**, so a region test must bind it or pass vacuously. Vim must not
read the selection by yanking it: under `clipboard=unnamed` that overwrites the very URL
being pasted, so the plugin slices the line with `setline` instead; `:echo` prints nothing
under `-es`, so the test writes to `/dev/stdout`.

**A quick-fix provider is not optional.** Without one, `Cmd+.` on a SUMO diagnostic falls
through to whatever else the editor has installed, and an AI assistant asked to fix SW009
rewrites the markup into a *Markdown* link — the very syntax the rule flags. Measured in
Roland's VS Code, Aug 2026.

## Editor parity is a requirement, not a nice-to-have

Roland's instruction, 2026-08-28: keep the VS Code, Emacs and Vim SUMO markup modes
**synchronised — the same features in all three, as far as each editor allows.** They are
peers, not a primary plus two ports. He uses more than one himself, and these features are
about muscle memory, which does not survive being available in one editor only.

| Feature | VS Code | Emacs | Vim / Neovim |
|---|---|---|---|
| Diagnostics | LSP client | Eglot / lsp-mode / Flymake | native LSP / ALE |
| Quick fixes | `Cmd+.` | `M-x eglot-code-actions` | `vim.lsp.buf.code_action()` |
| Fix / style whole buffer | code action, `codeActionsOnSave` | `C-c C-f` / `C-c C-s` | CLI |
| Syntax highlighting, SUMO's rules (#36, #37) | TextMate grammar | font-lock matcher | `syntax/sumo-wiki.vim` |
| Insert link (prompts) | `Cmd+K Cmd+L` | `C-c C-l` | `<LocalLeader>l` |
| Toggle bold `'''…'''` | `Cmd+B` | `C-c C-b` | `<LocalLeader>b` |
| Paste URL over selection | `Cmd+V` | `C-y` | visual `p`/`P` |

Idiom per editor, gesture in common: a VS Code paste provider, an Emacs `yank` remap and a
Vim visual mapping are the *same* feature even though the keystrokes differ. Do not chase
identical keybindings.

Keep each editor's decision logic a **pure function** — `link.js` and `bold.js`,
`sumo-wiki--build-link` / `--link-from-paste` / `--toggle-bold`, `sumo_wiki#build_link` /
`#link_from_paste` / `#toggle_bold` — so it is testable headlessly and lands in CI.
Linting itself lives once in `sumo-lint-lsp` and is never duplicated; only editing
gestures are. Highlighting is the one rule set that exists four times (web app, TextMate
grammar, Emacs matcher, Vim syntax file), because each engine needs its own form; what
keeps them equal is `editors/highlight-check.mjs`, which every editor's CI job uses to
compare all 907 committed articles, character by character, with `web/highlight.js`. Each
port runs Kitsune's rules as CodeMirror's simple mode does: a TextMate grammar's
earliest-match-then-first-pattern rule is the same thing, Emacs needs one font-lock matcher
(plain keywords color inside earlier matches) with the state cached on each newline, and
Vim gives priority to the item defined **last**, so its file lists the rules in reverse.
**Vim 9.2 and Neovim 0.11 call `*.wiki` `mediawiki`** before `ftdetect` runs, so
`sumo_wiki#claim_wiki()` overrides that guess, and uses `:setfiletype` otherwise, which
yields to a file type another plugin set but not to a FALLBACK one: Neovim 0.9 (Ubuntu's,
so CI's) has no `.wiki` rule and falls back to `conf` for any file with a `#` line, an
ordered list in SUMO markup, which made 85 corpus articles fail in CI before this was
handled. `g:sumo_wiki_claim_wiki = 0` opts out (#38). Vim's own
`ftplugin/mediawiki.vim` builds `b:undo_ftplugin` with `+=`, which makes it the Number 0, so
leaving mediawiki ran `:0` ("E749: Empty buffer" on a new file) and left its settings;
`claim_wiki` puts back the intended undo first. Measured in both, 2026-11-01.

Headless-test traps, all measured, one per editor:
- **Emacs** — `transient-mark-mode` is nil under `--batch` but t interactively, so a region
  test must bind it or pass vacuously. Stub prompts by `cl-letf`-ing `read-string`.
- **Vim** — `:echo` prints nothing under `-es`, so write to `/dev/stdout`. `feedkeys(...,
  'x')` is the only way to answer `input()`, which is why `insert_link` must **not** call
  `inputsave()`/`inputrestore()`: they clear the typeahead buffer the answers live in and
  the prompt blocks forever. `plugin/` is not sourced when the runtimepath is set after
  startup — `runtime!` it by hand. `maparg()` never finds a `<Plug>` lhs; ask `:nmap`
  through `execute()`.
- **VS Code** — grammar and link logic are tested under plain Node; nothing needs a VS Code
  harness, and it should stay that way.

## Conventions

- Scaffold with `cargo init`; keep `cargo fmt` and `cargo clippy --all-targets` clean.
- MPL-2.0 header on every new source file (see `tools/scrape/*.mjs`).
- Write tests alongside code — `cargo mutants` is planned and needs real assertions.
- Required properties: **round-trip** (parse→print of unmodified input is byte-identical)
  and **idempotence** (`format(format(x)) == format(x)`).
- `tests/fixtures/selftest-known-bad.wiki` holds deliberately broken markup with 15 planted
  errors; keep it passing as a regression fixture.

## Phase 2: implemented, with churn as the governing constraint

`sumo-wiki-core::style` implements phase-2 formatting. The default is the least
invasive setting that still removes real inconsistency, because **every source change is
reviewed by volunteer localizers** — a diff with no rendered difference costs their time
for nothing.

Measured on the 203-article corpus:

| Setting | Articles changed |
|---|---|
| Default (per-article heading normalisation) | **30 / 203 (15%)** |
| `--strip-trailing-whitespace` | 129 / 203 (64%) |

- **`HeadingSpacing::PreserveDominant` is the default.** Each article is normalised to
  whichever style *it* already uses most; already-consistent articles come back
  byte-identical, and ties are left alone. This means the `= H =` vs `=H=` question
  **does not block phase 2** — when the community decides, set `Style::heading_spacing`
  to `Spaced` or `Tight` and the same code enforces it.
- **`trailing_whitespace` defaults to false.** It quadruples churn for zero rendered
  benefit. Opt in per invocation with `--strip-trailing-whitespace`.
- Asymmetric headings are **skipped** by the formatter: which level the author meant is a
  guess, so it stays a phase-1 error (SW005) with an *Unsafe* fix for a human to resolve.
  A heading with **no** closing run (`=h1`) is a different case — the opening run is the
  only evidence, so that fix is *Safe* and closes with a run mirroring the opening
  spacing (`=h1` → `=h1=`, `= h1` → `= h1 =`), taking no side in the spacing question.
- Properties enforced over the whole corpus: formatting is **idempotent**, output still
  **round-trips**, and the **line count never changes** (localizers diff by line).

## Phase-2 candidate rules (not yet implemented)

- **Heading spacing as a global convention** — still awaiting community consultation, but
  no longer blocking; see the table above.
- **Make leading-space preformatting explicit.** A line beginning with a space is
  rendered preformatted by wiki markup, which is invisible in source and easy to
  create by accident. `switching-thunderbird` relies on it for a `.reg` sample.
  Proposed: rewrite such blocks as an explicit `<pre>` so the intent is obvious,
  and flag lone space-indented lines that were probably accidental. Needs care —
  the rewrite must not change rendering, so verify against the `--rendered` oracle.
- **Whitespace hygiene** — trailing whitespace (382 occurrences) and tab characters
  (98). Uncontroversial, safe to autofix.
- **Within-article heading consistency** — 20 articles mix both heading styles;
  normalising each to its own dominant style needs no community decision.

## Style rollout: opportunistic, never a bulk sweep

Decided 2026-08-04: once a house style is settled, apply it **going forward, as articles are
edited for other reasons**. Do not mass-reformat the KB.

Why this constrains the design: a bulk sweep would rewrite ~500+ headings with *zero*
rendered difference, bury substantive edits in revision history, and hand localisers a pile
of source changes with no user-visible payoff. So the formatter must be useful on a single
article at a time, and there is no migration script to write. The same applies to the 20
internally-inconsistent articles — fix them when touched.

Heading style is genuinely undecided and awaiting community consultation: the corpus splits
53.9% `= H =` vs 44.7% `=H=` across 1149 headings, and `=H=` is the *newer* trend. Neither
form may be treated as correct in the meantime. See `docs/heading-convention-discussion.md`.

## Rule-selection principle

Phase-1 rules are ranked by **measured frequency in the real corpus** (`corpus/report.md`),
not by guesswork. Every regex hit in that report is a *candidate* for human review, not a
verdict — the audit's heuristics are deliberately crude and do produce false positives.

Cautionary example: `# Text` looks like a stray Markdown heading but `#` is SUMO's
ordered-list marker, so the two are indistinguishable and no such rule can exist. Likewise
`*` is a list marker, not emphasis.

## Commands

```sh
cargo build && cargo test        # once Cargo.toml exists
cargo fmt && cargo clippy --all-targets
```
