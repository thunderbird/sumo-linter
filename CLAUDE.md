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

Scope: products `thunderbird` (154 articles) + `thunderbird-android` (2). Locale-aware
architecture from day one, but **only en-US is implemented**.

## Current state

Empty of Rust code. Only the dev-only corpus scraper exists (`tools/scrape/`) plus
`tests/fixtures/`. No `Cargo.toml` yet. Check the filesystem before assuming any module
layout — the plan below describes the intended shape, not what exists.

Toolchain present: rustc/cargo 1.89.0 (Homebrew), Node 22, Playwright + Chromium 1234.

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

## Intended architecture

Cargo workspace. The core must stay I/O-free so it compiles to WASM.

| Crate | Role |
|---|---|
| `crates/sumo-wiki-core` | lexer → lossless CST → rules → formatter. No fs, no network. |
| `crates/sumo-lint-cli` | `sumo-lint` binary: clap, file walking, config, diffs, `--fix` |
| `crates/sumo-lint-wasm` | `wasm-bindgen` shim for the GitHub Pages app |
| `tools/scrape/` | dev-only Node corpus fetcher (not a runtime dependency) |
| `web/` | static Pages app — **paste-in only** (can't fetch source: needs auth + CORS) |

**Lossless CST is non-negotiable.** A formatter must reprint everything it didn't
deliberately change, so tokens carry byte spans and all trivia is preserved.

Diagnostics carry a stable code (`SW001`), severity, byte span, message, and an optional
fix marked `safe` or `unsafe`; only `safe` fixes apply without `--force`.

## Conventions

- Scaffold with `cargo init`; keep `cargo fmt` and `cargo clippy --all-targets` clean.
- MPL-2.0 header on every new source file (see `tools/scrape/*.mjs`).
- Write tests alongside code — `cargo mutants` is planned and needs real assertions.
- Required properties: **round-trip** (parse→print of unmodified input is byte-identical)
  and **idempotence** (`format(format(x)) == format(x)`).
- `tests/fixtures/selftest-known-bad.wiki` holds deliberately broken markup with 15 planted
  errors; keep it passing as a regression fixture.

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
