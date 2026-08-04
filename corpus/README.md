# Thunderbird KB corpus snapshot

Raw wiki markup for the **public** en-US Thunderbird Knowledge Base articles, used as the
test corpus for `sumo-linter` and as a backup.

- **Source:** https://support.mozilla.org (production)
- **Products:** `thunderbird`, `thunderbird-android`
- **Locale:** en-US
- **Snapshot taken:** 2026-08-04
- **Articles:** 193 public (of 203 fetched)

## Provenance and licensing

This is Mozilla Support (SUMO) Knowledge Base content, written by Mozilla and MZLA
contributors. It is **not** covered by this repository's MPL-2.0 license. SUMO article
content is published under a Creative Commons license — see
<https://www.mozilla.org/foundation/licensing/website-content/>. Each article's authorship
and revision history live on SUMO; per-article URLs are in `index.public.json`.

These files are a **snapshot, not source of truth**. SUMO is authoritative; edit articles
there, never here.

## What is deliberately excluded

10 of the 203 fetched articles are **not committed**. Each returns HTTP 404 to anonymous
requests — they are unpublished drafts (and two are confirmed spam). Committing them to a
public repository would publish content SUMO has not published. They are listed explicitly
in the repository `.gitignore`, so a stray `git add -A` cannot include them.

`index.json` and `report.md` are also excluded, because both name those non-public articles.
`index.public.json` is the committed, public-only equivalent.

The excluded files still exist locally after a scrape, under `corpus/en-US/`, for review.

## Regenerating

```sh
cd tools/scrape
npm install && npx playwright install chromium
npm run login -- --base https://support.mozilla.org   # sign in yourself, once
node scrape.mjs --base https://support.mozilla.org    # resumable
npm run report                                        # writes report.md (gitignored)
```

Raw markup is only available to signed-in users, so a login is unavoidable. The scraper
issues GETs only and never submits a form. See `CLAUDE.md` for the API traps and rate-limit
behaviour discovered while building it.
