# Other-product KB templates

Wiki source for the **templates of other Mozilla products** — overwhelmingly Firefox. This
directory exists for one reason: `sumo-linter` had three lexer paths with no production
markup behind them, and templates are where two of them live.

- **Source:** https://support.mozilla.org (production)
- **Locale:** en-US
- **Snapshot taken:** 2026-09-09
- **Templates:** 207 public (of 209 fetched)

Thunderbird's own 12 templates are **not** here — they are in `../corpus/templates/en-US/`,
and this set deliberately excludes them so there is no second copy to drift.

## Not the measured corpus

`../corpus/en-US/` is the corpus every "N of 203 articles" figure refers to, and the
Thunderbird house style applies only there. Firefox and other non-MZLA products keep their
own conventions and are **out of scope for style** — see the repository `CLAUDE.md`.

These files are here as *lexer input*, nothing more: the property tests round-trip them, so
markup no Thunderbird contributor would write still has to survive the lexer byte-for-byte.

## What it found

Fetching these answered the open questions in sumo-linter #1:

| Construct | In 196 TB articles | In 221 templates |
|---|---:|---:|
| `{{{name}}}` (template parameter) | 0 | 31, in 6 templates |
| `[[Include:]]` / `[[I:]]` | 0 | 0 |
| `REDIRECT` | 0 | 1 |

Every parameter found is **named** — `{{{ver}}}`, `{{{type}}}`, `{{{slug}}}`,
`{{{channel}}}`, `{{{service}}}`, `{{{serviceURL}}}` — and not one is numbered, so the
`{{{n}}}` the issue asked about does not occur at all.

Linting all 209 found exactly one real markup error: `{for fx56}` is never closed in
`Template:adddevices`. Correctness rules are product-neutral by design; this is the first
evidence of that outside Thunderbird content.

## Provenance and licensing

SUMO Knowledge Base content, written by Mozilla contributors, **not** covered by this
repository's MPL-2.0 licence — see
<https://www.mozilla.org/foundation/licensing/website-content/>. A snapshot, never the
source of truth: edit articles on SUMO.

## What is deliberately excluded

Two of the 209 are not committed, because they return 404 to anonymous requests:
`Template:Fx56OptionsPrefs` and `Template: shaping the next decade` (whose one line is a
link to an off-site flipbook). They are named in the repository `.gitignore`, so a stray
`git add -A` cannot include them.

Templates are a case where page visibility and publication genuinely differ — see
`../corpus/README.md`. These two are excluded for the ordinary reason: nothing establishes
their content is published, and unreachable-plus-unused is the profile of a draft.

## Regenerating

Templates appear in **no** product listing and none of `/api/1/kb/`, and a template's slug
cannot be derived from its title. So the index comes from `/en-US/kb/all`:

```sh
cd tools/scrape
node scrape.mjs --base https://support.mozilla.org --all-docs > /tmp/alldocs.txt
# Build `slug<TAB>title` rows for the Template: entries you want, then:
./batch.sh --slugs /tmp/templates.txt corpus-other/templates 60

# Publication check: probe anonymously, in batches, and commit only what exists.
node scrape.mjs --base https://support.mozilla.org \
  --probe /tmp/chunk.txt --profile /tmp/anon-profile
```

`--probe` needs no login: it reports status codes and never fetches a body.
