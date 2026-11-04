<!-- This Source Code Form is subject to the terms of the Mozilla Public
   - License, v. 2.0. If a copy of the MPL was not distributed with this
   - file, You can obtain one at https://mozilla.org/MPL/2.0/. -->

# sumo-lint rules reference

This page describes every rule that `sumo-lint` checks in SUMO Knowledge Base wiki markup. The web app, the VS Code, Emacs and Vim modes, and the `sumo-lint` command all use the same rules. `sumo-lint --list-rules` prints the one-line list.

Each rule has a stable code, for example `SW005`. The code does not change between versions, so you can use it in review comments.

## Severity

- An error is markup that renders wrongly or breaks the structure of the article.
- A warning is markup that is suspicious or unnecessary, but that can be deliberate.

## Fix kinds

Some rules offer a fix. Each fix has one of three kinds.

| Kind | Meaning | Who applies it |
|---|---|---|
| Safe | The intended markup is clear. | `sumo-lint --fix`, the editor's fix-all action on save, the web app's *Apply N safe fixes* button, or a click on the fix. |
| Needs review | The fix is a guess between two or more plausible repairs. | `sumo-lint --unsafe-fixes`, or a click on the fix. The editors and the web app label it *(needs review)*. |
| Click only | The fix is correct, but it changes nothing that a reader sees. | Only a click on the fix in an editor or the web app. No bulk action applies it, because each source change costs volunteer localizers review time. |

A safe fix can change the rendered page. For example, the SW009 fix turns literal Markdown text into a real link. "Safe" means that the author's intent is clear.

## Products

Most rules apply to every product. A rule that applies only to Thunderbird articles says so. The web app and the editors lint as Thunderbird. Use `sumo-lint --product any` to turn the Thunderbird-only rules off.

---

## SW001

Unclosed or unopened `{for}` block.

- Severity: error
- Products: all
- Fix: none

A `{for}` without a `{/for}`, or a `{/for}` without a `{for}`.

```
{for win}Click {button OK}.
```

Why: SUMO does not show the text after an unclosed `{for}` correctly. Find where the condition ends and add `{/for}` there. The linter cannot know where that is.

## SW002

Unclosed or unopened `{note}` block.

- Severity: error
- Products: all
- Fix: none

```
{note}Back up your profile first.
```

Why: the note box does not end where the author meant. Add `{/note}` where the note ends.

## SW003

Unclosed or unopened `{warning}` block.

- Severity: error
- Products: all
- Fix: none

```
{warning}This deletes all your messages.
```

Why: the warning box does not end where the author meant. Add `{/warning}` where the warning ends.

## SW004

Unbalanced `'''` bold markers in a paragraph.

- Severity: error
- Products: all
- Fix: none

A paragraph contains an odd number of `'''`, so one marker has no partner.

```
Click '''Settings and then {button OK}.
```

Why: the rest of the paragraph renders bold. The linter counts per paragraph, not per line, because bold text can correctly span several lines. It cannot know where the bold text was meant to end.

## SW005

The `=` runs of a heading differ in length, or the heading has no closing run.

- Severity: error
- Products: all
- Fix: safe for a heading with no closing run, needs review for runs of different lengths

```
==Settings ===
=Older releases
```

Why: the author of `==Settings ===` meant a level 2 heading or a level 3 heading, and the linter cannot know which. So the fix keeps the opening run and needs review. `=Older releases` has only the opening run, so the level is clear. The safe fix closes it with the same spacing as the opening. So `=Older releases` becomes `=Older releases=`, and `= Older releases` becomes `= Older releases =`.

## SW006

Unknown `[[Image:]]` parameter.

- Severity: error
- Products: all
- Fix: none

```
[[Image:gear icon|size=300]]
```

Why: Kitsune accepts only `alt`, `align`, `caption`, `valign`, `frame`, `page`, `link`, `width` and `height` (`IMAGE_PARAMS` in `kitsune/sumo/parser.py`). It ignores other parameters. In the example, you probably meant `width=300`.

## SW007

Unmatched `[[` or `]]`.

- Severity: error
- Products: all
- Fix: none

```
See [[Thunderbird release notes for more.
[[Image:filelink]]]]
```

Why: SUMO shows an unmatched bracket as literal text. The markup documentation shows a link as text with `<nowiki>[[</nowiki>Page]]`. So the rule ignores a `]]` that follows a `[[` inside `<nowiki>` on the same line.

## SW008

Empty list item.

- Severity: warning
- Products: all
- Fix: safe, deletes the empty item

```
* First item
*
* Second item
```

Why: SUMO shows an empty bullet or number.

An empty line ends a list. So if the next line is also a list item, the fix deletes the whole line, and the list stays one list. Otherwise, the fix deletes only the marker and keeps the line break, so that the paragraphs before and after the item do not join. See issue #51.

## SW009

Markdown link syntax instead of wiki syntax.

- Severity: error
- Products: all
- Fix: safe

```
[Thunderbird](https://www.thunderbird.net)
```

The fix writes `[https://www.thunderbird.net Thunderbird]`. For a target that is not a web address, it writes an internal link, `[[Page|text]]`.

Why: SUMO markup is not Markdown, so the Markdown link shows as literal text.

## SW010

Markdown bold syntax instead of wiki syntax.

- Severity: error
- Products: all
- Fix: safe

```
Click **Save**.
```

The fix writes `'''Save'''`.

Why: SUMO shows the asterisks as text. A `**` at the start of a line is not flagged, because it is a second-level list item.

## SW011

Empty macro argument.

- Severity: warning
- Products: all
- Fix: none

```
Press {key } to open the menu.
```

Why: `{key}`, `{button}`, `{menu}`, `{filepath}` and `{pref}` show their argument. With no argument, they show nothing.

## SW012

Firefox version condition `{for fxN}` in a Thunderbird article.

- Severity: warning
- Products: Thunderbird only
- Fix: needs review, changes `fx` to `tb` and keeps the number

```
{for fx152}New in this version.{/for}
```

Why: the KB article `how-to-use-for` says that Firefox articles use `fxN` and Thunderbird articles use `tbN`. So `fxN` in a Thunderbird article is probably copied from a Firefox article. The Thunderbird version number that matches is not known, so check the number after the fix.

## SW013

`[[UI:details_end]]` directly followed by `[[UI:details_start]]`.

- Severity: warning
- Products: all
- Fix: click only, deletes both tags and the blank lines between them

```
=Older releases=
[[UI:details_start]]
==Version 2==
Text
[[UI:details_end]]
[[UI:details_start]]
==Version 1==
Text
[[UI:details_end]]
```

After the fix:

```
=Older releases=
[[UI:details_start]]
==Version 2==
Text
==Version 1==
Text
[[UI:details_end]]
```

Why: `[[UI:details_start]]` opens a collapsible section and `[[UI:details_end]]` closes it. Every h2 to h6 heading inside one section collapses separately, so one pair around all the sections is enough. An h1 does not collapse, so put the start tag after the h1. A staging test on 2026-11-03 showed that both forms look the same. See issue #49.
