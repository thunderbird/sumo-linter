<!-- Draft for community consultation. Not published anywhere — copy/adapt as needed.
     Data: public en-US Thunderbird KB articles, snapshot 2026-08-04.
     Per-article table: https://gist.github.com/rtanglao/2708f762f5a4ec71c699827d8bc4071f -->

# Heading style in the Thunderbird KB: `= Heading =` or `=Heading=`?

## Why I'm asking

I've been building a linter and formatter for SUMO wiki markup, aimed at Thunderbird KB
articles. Most of what it can check is uncontroversial — unbalanced `'''`, malformed
`{for}` blocks, that sort of thing. But one question can't be settled from the markup rules,
because **both forms are equally valid wiki** and render identically:

```
= Space on both sides =
=No spaces=
```

Before the formatter takes a position, I'd like to know what the community prefers.

## What our articles actually do today

I measured every public en-US Thunderbird and Thunderbird for Android article
(**166 articles containing headings, 1149 headings total**):

| Style | Headings | Share |
|---|---:|---:|
| `= Heading =` (space both sides) | 619 | 53.9% |
| `=Heading=` (no spaces) | 514 | 44.7% |
| asymmetric / multi-space | 16 | 1.4% |

It's very nearly a coin flip. **There is no established convention to enforce** — which is
exactly why this needs a decision rather than a bug report.

## Two findings that I think matter more than the headline split

**1. Articles are individually consistent; the KB as a whole isn't.**

| | Articles | Share |
|---|---:|---:|
| `= Heading =` throughout | 86 | 51.8% |
| `=Heading=` throughout | 59 | 35.5% |
| **Mixes both within one article** | **20** | **12.0%** |

So 87% of articles pick a style and stick to it. This is author preference, not carelessness.

**2. `=Heading=` is the newer trend, not the legacy form.**

Splitting the consistent articles by article ID (a rough proxy for age):

| | `= Heading =` | `=Heading=` |
|---|---:|---:|
| Older half | 68% | 32% |
| Newer half | 51% | 49% |

`= Heading =` dominated early and has been losing ground steadily. Worth naming explicitly,
because "stay consistent with our history" and "match where the KB is trending" point in
**opposite directions**. Which of those we care about is really the question.

## A change that needs no decision at all

Separately from the global question: those 20 mixed articles are internally inconsistent,
which is undesirable under *either* convention. Making each one self-consistent with its
**own** dominant style means changing just **43 headings** — and several are lone strays:

| Article | `= H =` | `=H=` |
|---|---:|---:|
| `new-thunderbird-desktop` | 2 | 54 |
| `switching-thunderbird` | 12 | 1 |
| `keyboard-shortcuts-thunderbird` | 10 | 1 |
| `thunderbird-and-yahoo` | 2 | 14 |

I'd like to do this regardless of the outcome below, since it's neutral on the global
question and fixes 20 articles by touching 43 lines.

## What I'd like to decide

1. **Which style is the Thunderbird house style?** (`= Heading =`, `=Heading=`, or
   "don't standardise — only fix within-article inconsistency")

**This is no longer blocking anything.** The formatter already ships with a default that
needs no decision: it normalises each article to **whichever style that article already
uses most**, and leaves articles that are already consistent **byte-identical**. Measured
across the corpus, that touches 30 of 203 articles — the 20 that contradict themselves plus
about 10 with one-sided spacing like `= Sharing your key with others=`. The other 173 are
untouched. When the community picks a convention, one setting switches the tool over.

**On rollout: apply going forward as articles are edited for other reasons — no mass
reformat.** A bulk sweep would touch ~500 headings for zero rendered difference, bury real
edits in revision histories, and create work for localisers reviewing changed source.

For the same reason, **trailing-whitespace cleanup is off by default**. It sounds harmless,
but it takes the proportion of articles modified from 15% to 64% — 129 of 203 — with no
rendered difference at all. Every one of those diffs would land in front of a volunteer
localiser who has to look at a changed line and find nothing actually changed.

To be clear about scope: this is a **Thunderbird/MZLA** convention. Firefox and other
products can keep their own; nothing here asks anything of them.

## Data

Full per-article table — slug, article ID, counts of each style, and which dominates:
<https://gist.github.com/rtanglao/2708f762f5a4ec71c699827d8bc4071f>

Method: raw wiki source for every public en-US article in the `thunderbird` and
`thunderbird-android` products, snapshotted 2026-08-04. Headings inside `<nowiki>`,
`<code>`, `<pre>`, and HTML comments are excluded, so literal `=` in code samples isn't
miscounted as a heading.
