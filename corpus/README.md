# Thunderbird KB corpus snapshot

Raw wiki markup for the **public** en-US Thunderbird Knowledge Base articles, used as the
test corpus for `sumo-linter` and as a backup.

- **Source:** https://support.mozilla.org (production)
- **Products:** `thunderbird`, `thunderbird-android`
- **Locale:** en-US
- **Snapshot taken:** 2026-09-09 (first snapshot: 2026-08-04)
- **Articles:** 196 public (of 203 fetched)

## Provenance and licensing

This is Mozilla Support (SUMO) Knowledge Base content, written by Mozilla and MZLA
contributors. It is **not** covered by this repository's MPL-2.0 license. SUMO article
content is published under a Creative Commons license — see
<https://www.mozilla.org/foundation/licensing/website-content/>. Each article's authorship
and revision history live on SUMO; per-article URLs are in `index.public.json`.

These files are a **snapshot, not source of truth**. SUMO is authoritative; edit articles
there, never here.

## What is deliberately excluded

7 of the 203 fetched articles are **not committed**. Each is invisible to anonymous
requests — they are unpublished drafts. Committing them to a public repository would
publish content SUMO has not published. They are listed explicitly in the repository
`.gitignore`, so a stray `git add -A` cannot include them.

**How "public" is decided:** the test is *is this content published*, not *is this page
anonymously reachable*. For articles the two coincide, and the API has no "public" field, so
it is decided by asking what an anonymous visitor sees: signed in the listing returns 203
articles, anonymously 196, and the difference is the drafts.
`tools/scrape/public-index.mjs` does that subtraction and writes `index.public.json`. It
takes an anonymous listing as an explicit argument rather than fetching one itself, because
running the listing with the saved session by mistake would silently mark every draft
public.

For **templates** the two tests come apart — see below. A template page can 404 anonymously
while SUMO serves its text to the public inside every article that includes it. Page
visibility is not publication.

Three more articles that were fetched in August — `age-calculation`,
`chitlink-smart-url-shortener-link-management-platf` (spam) and `invalid-certificates` (a
misfiled support question) — are no longer listed at all, even to an admin, so they have
been marked obsolete on SUMO since. Their August files are still on disk locally and remain
gitignored; they are simply no longer refreshed.

`index.json` and `report.md` are also excluded, because both name those non-public articles.
`index.public.json` is the committed, public-only equivalent.

The excluded files still exist locally after a scrape, under `corpus/en-US/`, for review.

## Templates

`templates/en-US/` holds the templates the public articles include — the `[[Template:X]]`
and `[[T:X]]` constructs, 66 references across 44 of the 196 articles. They are here
because Thunderbird's *rendered* articles depend on them: a reader sees the template's text,
not the reference.

They are kept out of `en-US/` deliberately. That directory is the measured corpus — the Rust
property tests walk it and every "N of 203 articles" figure refers to it — so a template
dropped in there would silently join both.

Two things about templates, both measured on 2026-09-09 and neither guessable:

- **The API does not list them.** A `# COMPLETE` anonymous enumeration of `/api/1/kb/`
  returned 1325 public articles and zero template pages, so no listing names them. They are
  fetched by explicit slug (`scrape.mjs --slugs`).
- **A template's slug cannot be derived from its title.** The KB contains all three of
  `templatesharearticle` (colon dropped, lowercased), `templateopenProfileFolderTB` (case
  kept) and `Template:optionspreferences` (colon kept) — three conventions, so no rule
  finds them and 44 guessed candidates all 404ed. Kitsune resolves `[[Template:X]]` by
  *title*, so fetching one needs a title→slug map, and `/en-US/kb/all` is the only index
  that has both (`scrape.mjs --all-docs`, 5299 documents, 221 of them templates).
  Filenames come from the *title* — colon to `-`, spaces to `_` — so
  `Template:optionspreferences TB` is stored as `Template-optionspreferences_TB.wiki`
  regardless of the slug it was fetched from.

A template's content is published even where its own page looks absent, and the
rendered-HTML oracle is what shows it: `message-threading-thunderbird` includes
`[[Template:optionspreferences TB]]`, and the API's rendered `html` for that article —
served to anyone — expands it to "Click Thunderbird app menu ☰ > Settings" with no
broken-link markup. That is also how the slug map was verified: the fetched
`Template-optionspreferences_TB.wiki` contains exactly that sentence, which proves
`templateoptionspreferences` is the document `Template:optionspreferences TB` and not a
lookalike.

## Regenerating

```sh
cd tools/scrape
npm install && npx playwright install chromium
npm run login -- --base https://support.mozilla.org   # sign in yourself, once
node scrape.mjs --base https://support.mozilla.org --force   # re-fetch everything

# Decide what is public, from a throwaway profile so the saved admin session
# cannot make drafts look published, then write the committed index.
node scrape.mjs --base https://support.mozilla.org --list-only \
  --profile /tmp/anon-profile > /tmp/anon.txt
node public-index.mjs /tmp/anon.txt

npm run report                                        # writes report.md (gitignored)
```

Raw markup is only available to signed-in users, so a login is unavoidable. The scraper
issues GETs only and never submits a form. See `CLAUDE.md` for the API traps and rate-limit
behaviour discovered while building it.
