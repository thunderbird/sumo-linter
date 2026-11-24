# Search and replace in SUMO articles

`tools/scrape/replace.mjs` changes the same strings in many SUMO knowledge base articles. SUMO has no API for edits, so the script works through the edit page in a browser. You check each edit and you click Submit yourself. The script never submits a form. Issue #62 is the design record.

## What you need

- The scraper set up once: `cd tools/scrape && npm install && npx playwright install chromium`.
- `gh`, signed in to GitHub.
- Rust, because the script builds `sumo-lint` to lint each edit.
- A Mozilla account that can edit the KB, on staging, on production, or on both.

## 1. Make the issue

Make a GitHub issue with two checklists. Write each string item exactly as `"old" → "new"`, and write each article item as the article's slug.

```markdown
### Strings

- [ ] "Config Editor…" → "Advanced settings"
- [ ] "Message Store Type for new accounts:" → "Storage format for new accounts:"

### Articles

- [ ] advanced-panel-settings-in-thunderbird
- [ ] config-editor
```

Every string item applies, checked or not. The script works only on the article items that are not checked. Other sections of the issue are ignored.

The script replaces exact text only. It does not replace text inside HTML comments, `<nowiki>` or `<pre>`. If one old text is part of another, the longer one wins, and a replacement never applies to the output of another one.

## 2. Do a dry run

Run the script in your own terminal (Ghostty), not with `!` in Claude Code, because the script asks you questions.

```sh
cd ~/Documents/GIT/sumo-linter/tools/scrape
node replace.mjs https://github.com/thunderbird/sumo-linter/issues/N --base https://support.mozilla.org --dry-run
```

The dry run reads each article, shows each change with its line number, and lints the result. It does not fill an edit page, and it does not change the issue. Read the list of changes. Look for each `(check: …)` mark: a match inside a `[[link]]` can change a link target, and a match inside a `{for}` branch can be text for an older version that must stay.

If a string matches text that must not change, for example a sentence that names the old setting on purpose, edit that article by hand and leave it out of the list.

## 3. Do the edits

Run the same command without `--dry-run`. Leave out `--base` to edit staging (`support.allizom.org`), which is the default.

```sh
node replace.mjs https://github.com/thunderbird/sumo-linter/issues/N --base https://support.mozilla.org
```

For each article:

1. If your session expired, the browser window opens the sign-in page. Click Continue, then sign in. The script never reads your password, and it waits up to 15 minutes.
2. The script shows the changes. Type `y` to fill the edit page, `n` and a reason to skip the article, or `q` to stop.
3. After `y`, check the edit in the browser. Preview shows the result. The revision comment is already filled with `String changes from <issue URL>`.
4. Click Submit for Review, then Submit. To not save, type `s` and Enter in the terminal instead.
5. The script finds the new revision in the article's history. It checks the article item in the issue and adds a note, for example `- Note: revision 381300, 3 replacements: <URL>`.

The script saves the issue after each article, so you can stop at any time and run the same command again later. It then continues with the articles that are not checked.

## What the notes mean

| Note | Item | What happened |
|---|---|---|
| `revision N, K replacements: URL` | checked | You saved the edit as revision N. |
| `no match: no edit` | checked | The article has none of the strings. |
| `skipped: REASON` | not checked | You typed `n REASON`, or `s` after the fill. |
| `not edited: the edit adds …` | not checked | The edit would add a linter diagnostic, so the script did not offer it. |
| `not edited: the article changed on SUMO during the check` | not checked | Someone saved the article while you read the changes. Run again. |

A run that finds every article item checked says `nothing to do`. That is different from a run that did nothing.

## If something goes wrong

- If SUMO rate-limits the script (429), it waits quietly and prints when it tries again. Do not reload the page during the wait, because each request restarts it.
- If staging says `no match` but production has the text, the staging copy is probably older. Staging is not a copy of production from today.
- If the script stops with `FAILED`, nothing was saved for the current article unless you clicked Submit. Run the same command again.

## Rules that the script keeps

- You click Submit for every edit. The script only fills the form, and a test in CI makes sure that `replace.mjs` never clicks, submits or posts.
- The script changes only the listed strings. It does no style fixes and no whitespace changes, because volunteer localizers review every changed line.
- The script never adds a linter diagnostic to an article.
