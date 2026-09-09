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

**How "public" is decided:** by asking what an anonymous visitor sees, because the API has
no such field. Signed in, the listing returns 203 articles; anonymously it returns 196, and
the difference is the drafts. `tools/scrape/public-index.mjs` does that subtraction and
writes `index.public.json`. Running the listing with the saved session by mistake would
silently mark every draft public, which is why that script takes an anonymous listing as an
explicit argument rather than fetching one itself.

Three more articles that were fetched in August — `age-calculation`,
`chitlink-smart-url-shortener-link-management-platf` (spam) and `invalid-certificates` (a
misfiled support question) — are no longer listed at all, even to an admin, so they have
been marked obsolete on SUMO since. Their August files are still on disk locally and remain
gitignored; they are simply no longer refreshed.

`index.json` and `report.md` are also excluded, because both name those non-public articles.
`index.public.json` is the committed, public-only equivalent.

The excluded files still exist locally after a scrape, under `corpus/en-US/`, for review.

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
