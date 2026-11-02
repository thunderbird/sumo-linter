# UI strings tools

Tools that track the Settings and Account Settings strings of Thunderbird, and the KB articles
that quote them. They use the Python standard library only.

| File | What it does |
|---|---|
| `tb-desktop-settings-account-settings-changes-158-and-newer.csv` | The UX sheet of planned string changes. |
| `search.py` | Finds KB articles in `corpus/` that quote strings the sheet changes (knowledgebase-issues #247, #249). |
| `table.py` | Writes an old-string/new-string table from the sheet (`settings-strings-158.*`). |
| `extract.py` | Reads the strings out of an installed Thunderbird app into `strings/<version>.tsv`. |
| `compare.py` | Compares all versions in `strings/` and maps them to the sheet (`string-versions.*`). |
| `l10n_tables.py` | Writes simple old-text/new-text tables for SUMO localizers, one for Settings and one for Account Settings (`strings-<versions>-<window>.*`). |
| `shipped_search.py` | Finds KB articles that quote a string that really changed in 159 or 160, from the shipped strings (`affected-*.md`, the bodies of knowledgebase-issues #247 and #249). |
| `propose_edits.py` | Proposes a `{for not tb159}…{/for}{for tb159}…{/for}` edit for named articles, with `CHECK 159` comments where a person must decide (`proposals/`, sumo-linter #28). A string that 159 reworded under a new ID is paired with its successor in the same file, helped by the spreadsheet's plan, rather than called "removed" (#47). `--out DIR` writes elsewhere, so `proposals/` stays as a running checklist expects. |
| `test_ui_strings.py` | Tests for `extract.py`, `compare.py`, `l10n_tables.py` and `shipped_search.py`. CI runs it. |

## Copies on wiki.mozilla.org

Roland copied the two 3-column wikitext tables by hand to these pages on 2026-10-31:

- [User:Rolandtb/strings-153.6.0-159.0-160.0-settings](https://wiki.mozilla.org/User:Rolandtb/strings-153.6.0-159.0-160.0-settings),
  from `strings-153.6.0-159.0-160.0-settings.mediawiki`
- [User:Rolandtb/strings-153.6.0-159.0-160.0-account-settings](https://wiki.mozilla.org/User:Rolandtb/strings-153.6.0-159.0-160.0-account-settings),
  from `strings-153.6.0-159.0-160.0-account-settings.mediawiki`

Each page starts with one extra line that names the file it was copied from. Apart from that
line, both pages matched the files in this folder on 2026-10-31.

The pages do not update by themselves. After you change these files, paste the new content into
the pages and keep the first line. To see whether a page is out of date, compare its raw text
with the file:

```sh
p=strings-153.6.0-159.0-160.0-settings
curl -s "https://wiki.mozilla.org/index.php?title=User:Rolandtb/$p&action=raw" | sed 1d \
  | diff - tools/ui-strings/$p.mediawiki
```

A difference only at the last line ("No newline at end of file") does not matter.

## Add a version

You need the macOS app of the new version, for example a new beta. The app can be in any
folder. The tools only read the app. They do not start it or change it.

1. Extract the strings. If the path of the app contains a space, put it in quotes:

   ```sh
   python3 -I tools/ui-strings/extract.py "/Applications/THUNDERBIRD_BETA/Thunderbird Beta.app"
   ```

   The script reads the version from the app's `Info.plist` and writes
   `tools/ui-strings/strings/<version>.tsv`, for example `161.0.tsv`. It prints the number of
   strings and files. You can give several apps in one command.

2. Compare the strings and write the tables:

   ```sh
   python3 -I tools/ui-strings/compare.py \
       tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv
   ```

   This rewrites `string-versions.md` and `string-versions.mediawiki`. They get one column for
   each file in `strings/`, in version order. The script prints a summary line with the counts
   for the three tables.

3. Write the localizer tables. First, edit two settings at the top of `l10n_tables.py`.
   `TABLES` lists the version sets, one table each, for example `("159.0", "160.0", "161.0")`.
   `LABELS` gives the column headings, for example `"161.0": "Beta 161.0"`. Then run:

   ```sh
   python3 -I tools/ui-strings/l10n_tables.py \
       tools/ui-strings/tb-desktop-settings-account-settings-changes-158-and-newer.csv
   ```

   Each version set gets a Settings table and an Account Settings table, each as Markdown and
   wikitext, for example `strings-153.6.0-159.0-settings.md` and
   `strings-153.6.0-159.0-account-settings.mediawiki`. The string file decides the window:
   `ACCOUNT_FILES` in `l10n_tables.py` lists the Account Settings files. If you remove a version
   set from `TABLES`, delete its four files.

   The tables mark changes so that a reader can scan them. Bold marks the words that changed
   from the previous version. A table with three or more versions also has a "Changed in"
   column, and writes "same as 159" (for example) where a version did not change the text. The
   wikitext tables also give each changed cell a light background colour.

4. Find the affected articles again. First update `VERSIONS` and `SECTIONS` at the top of
   `shipped_search.py`. Then run it with the same CSV argument, and paste each `affected-*.md`
   file into its issue: Settings into knowledgebase-issues #247, Account Settings into #249.
   Keep the boxes that someone already ticked.

5. Run the tests:

   ```sh
   python3 tools/ui-strings/test_ui_strings.py
   ```

6. Commit the new `.tsv` file and all the tables together. If you commit the `.tsv` file
   without the tables, the CI test fails, because the tables are then out of date.

7. If the 3-column tables changed, update the copies on wiki.mozilla.org (see above).

## Check the result

- Compare the file count that `extract.py` prints with the count for the previous version. If
  the count is much lower, Thunderbird possibly moved strings to a file that `extract.py` does
  not read. For example, 160.0 has no `preferences.properties` files, because those strings
  moved to Fluent. To read a new file, add its path to `SCOPE` in `extract.py` and extract all
  versions again.
- Look at table 2 in `string-versions.md`. A record that moves into that table after a new
  version often means a missing file, not a paraphrase in the sheet.
- To see what changed in one version, use `git diff` on its `.tsv` file, or run
  `diff strings/160.0.tsv strings/161.0.tsv`.

## Replace or remove a version

- To refresh a version, extract the same version again. The script overwrites its `.tsv` file.
- A point release such as 160.0.1 gets its own file, `160.0.1.tsv`, and its own column. To
  show it instead of 160.0, delete `160.0.tsv` and run `compare.py` again.
- To remove a version from the tables, delete its `.tsv` file and run `compare.py` again.
- If you have two apps of the same version, only the last one you extract is kept.

## Use a new UX sheet

`compare.py` takes the sheet as its only argument. The sheet must have the columns `Setting`,
`Current content`, `New content`, `Pane` and `Section`. If the new sheet replaces the current
one, also change `CSV` in `test_ui_strings.py`, because the test regenerates the tables from
that sheet.
