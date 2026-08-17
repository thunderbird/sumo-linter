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
implemented**. The corpus is 203 articles; 193 public ones are committed under `corpus/`.

## Current state

Phases 1 and 2 are implemented and tested. `cargo test` runs 31 tests, including property
tests over every corpus article.

Linting the committed corpus reports **5 errors, all verified by hand** and all filed:
issues #223, #224, #225 (unbalanced `'''`) and #228 (two `{for}` bugs in
`keyboard-shortcuts-thunderbird` that the earlier regex audit could not detect, because the
file's 294/294 tag totals balance).

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
- Post the heading-convention consultation: `docs/heading-convention-discussion.md` plus
  the data gist <https://gist.github.com/rtanglao/2708f762f5a4ec71c699827d8bc4071f>.
  **This blocks nothing** — the per-article default needs no decision.
- Fix the four filed markup bugs: knowledgebase-issues **#223, #224, #225, #228**.
- Triage the 8 non-public drafts: knowledgebase-issues **#227** (has a checklist). Two of
  the eight are not drafts at all — `invalid-certificates` is a misfiled support question,
  and `troubleshoot-pdf-and-email-issues-thunderbird` reads like machine-generated filler.

**Open, for a future session:**
- sumo-linter **#1** — `[[Include:]]`, `{{{n}}}` and `REDIRECT` occur **0** times in the
  Thunderbird corpus, so those lexer paths are untested. Scrape a sample of other products
  and find out. Not urgent; nothing Thunderbird-facing depends on it.
- Phase 3: non-English locales. Locale is already threaded through; no en-US assumptions
  live in rule logic.

**Do not redo:** the corpus is already scraped and committed; the heading data is already
measured; the four bugs are already filed with rendered-output evidence. **Every test now
runs in CI** — `rust`, `vscode` (34 grammar assertions) and `emacs` (20 mode assertions,
against the real CLI) — so there is no by-hand test suite left to remember. LSP quick fixes
(`textDocument/codeAction`) are implemented, tested, pushed and CI-green as of 2026-08-17;
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
(`--base https://support.mozilla.org` to switch). `corpus/` and `.auth/` are gitignored —
never commit scraped SUMO content or an authenticated session.

## Architecture

Cargo workspace with **zero dependencies**. The core does no I/O so it compiles to WASM.

| Crate | Role |
|---|---|
| `crates/sumo-wiki-core` | lossless lexer → rules → formatter. No fs, no network, no deps. |
| `crates/sumo-lint-cli` | `sumo-lint` binary: hand-rolled args, `--fix`, `--style`, `--diff`, JSON |
| `crates/sumo-lint-lsp` | LSP over stdio: diagnostics, `textDocument/formatting`, `codeAction` quick fixes |
| `crates/sumo-lint-wasm` | four C-ABI exports (`lint`, `fix`, `style`, `is_lossless`) — no wasm-bindgen |
| `editors/` | VS Code extension (LSP client + TextMate grammar); Emacs mode; Neovim and Vim 8 configuration |
| `tools/scrape/` | dev-only Node corpus fetcher (not a runtime dependency) |
| `web/` | static Pages app — **paste-in only** (can't fetch source: needs auth + CORS) |

**Losslessness is non-negotiable.** Tokens tile the input exactly, so reprinting an
unmodified parse is byte-identical. This is asserted in the lexer, property-tested over
every corpus article, and re-checked before `--fix` writes a file — a lexer bug would
otherwise corrupt articles silently.

It is a **token stream**, not a full CST. That is enough for phase-1 rules and phase-2
formatting; do not describe it as a tree.

Diagnostics carry a stable code (`SW001`), severity, byte span, message, and an optional
fix marked `Safe` or `Unsafe`; only `Safe` fixes apply without `--unsafe-fixes`. In the LSP
both kinds are offered as quick fixes (`Unsafe` titled *(needs review)*), because accepting
a code action is a deliberate, undoable choice, unlike a CLI writing files unattended.

**A quick-fix provider is not optional.** Without one, `Cmd+.` on a SUMO diagnostic falls
through to whatever else the editor has installed, and an AI assistant asked to fix SW009
rewrites the markup into a *Markdown* link — the very syntax the rule flags. Measured in
Roland's VS Code, Aug 2026.

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
  guess, so it stays a phase-1 error (SW005) for a human to resolve.
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
