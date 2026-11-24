# KB fixes

This folder holds fixed wiki markup for SUMO articles, for you to paste into the article's edit page. A file here is not the article as it is on SUMO. The scraped source stays in `corpus/`.

## new-thunderbird-desktop.wiki

Issue #60. It starts from revision 381287, read from the edit page on 2026-11-23. The fix adds a `[[UI:details_end]]` `[[UI:details_start]]` pair before each `=Thunderbird N=` heading from 158 to 140. Nothing else changes: the diff is 38 added lines.

Without the pairs, all versions from 159 to 140 are in one collapsible block. Each version h1 is then hidden inside the last collapsed h2 of the version above it, so `Thunderbird 158` shows only when you expand `Settings string changes`. In the web app preview, the revision hides 19 h1s and the fixed file hides none.

If someone edits the article before you paste, start again from the new revision.
