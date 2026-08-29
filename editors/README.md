# Editor integration

One language server, `sumo-lint-lsp`, backs every editor. There is no per-editor
linting logic, so rules only ever have to be written once.

Build it first:

```sh
cargo build --release          # produces target/release/sumo-lint-lsp
```

Optionally put it on your `PATH`. Copy the CLI too — Emacs's commands and ALE's
non-LSP mode shell out to `sumo-lint`, and fail with "cannot find" without it:

```sh
cp target/release/sumo-lint-lsp target/release/sumo-lint ~/.local/bin/
```

Treat `*.sumo` and `*.wiki` as SUMO markup. Remember that SUMO itself is the
source of truth — these are local drafts you paste back into the article editor.

## Quick fixes

Every diagnostic that carries a fix is offered as an LSP code action, so the
squiggle is never a dead end:

| Editor | How |
|---|---|
| VS Code | `Cmd+.` with the caret **on** the error, or `Cmd+.` `Enter` for the preferred fix |
| Neovim | `:lua vim.lsp.buf.code_action()` |
| Emacs (Eglot) | `M-x eglot-code-actions`, or `C-c C-f` for the whole buffer |

Fixes are matched to the requested range, so put the cursor inside the error —
`F8` (VS Code) or `]d` (Neovim) jumps there. There is also a document-wide
`source.fixAll.sumo-lint` action, which applies every *safe* fix at once and can
run on save:

```json
"[sumo-wiki]": {
  "editor.codeActionsOnSave": { "source.fixAll.sumo-lint": "explicit" }
}
```

Unsafe fixes appear in the menu too, marked *(needs review)* — the CLI withholds
them behind `--unsafe-fixes` because it writes files unattended, whereas
accepting a code action is a deliberate, undoable choice.

This matters more than it looks: without a code-action provider of our own, `Cmd+.`
on a SUMO diagnostic falls through to whatever else is installed, and an AI
assistant asked to fix `SW009` will "correct" the markup to a Markdown link —
`[text](url)`, the exact syntax the rule flags. SUMO wants `[url text]`.

## Vim and Neovim

`vim/` is a plain Vim-script plugin directory, shared by Vim 8+ and Neovim. It carries the
editing helper only — diagnostics still come from `sumo-lint-lsp`, configured below.

Add it to your runtimepath, however your plugin manager spells that:

```vim
set runtimepath^=~/path/to/sumo-linter/editors/vim
filetype plugin on
```

```lua
-- lazy.nvim
{ dir = '~/path/to/sumo-linter/editors/vim' }
```

`.sumo` and `.wiki` then get the `sumo-wiki` filetype — `.wiki` via `:setfiletype`, so it
yields to any wiki plugin you already use.

### Paste a URL over a selection

Select some words, copy a URL, press `p` (or `P`): you get
`[https://example.org the words]` instead of the selection being replaced. Same gesture as
`Cmd+V` in VS Code and `C-y` in the Emacs mode.

The mappings are **buffer-local to `sumo-wiki`** and fall through to the ordinary paste on
anything ambiguous, because a paste mapping that guesses destroys what was in your register:

| Falls through when | Why |
|---|---|
| the register is not one whitespace-free URL | prose that starts with a scheme is a replace |
| the register is linewise or blockwise | that is text you meant to place, not a URL you copied |
| a count was given (`2p`) | one link is not "paste it twice" — the count is carried through |
| the selection spans lines, or is not charwise | no single sensible label |
| the selection is itself a URL | replacing one URL with another is a correction |
| the selection contains `[` or `]` | they would close the link early |

`let g:sumo_wiki_paste_url_as_link = 0` turns it off; `b:sumo_wiki_paste_url_as_link`
overrides per buffer; `let g:sumo_wiki_no_mappings = 1` skips the mappings entirely and
leaves `sumo_wiki#visual_paste()` for you to map yourself. Only the external form is
produced — an internal link goes by article **title**, which a `/kb/<slug>` URL does not
carry.

### Insert a link: `<LocalLeader>l`

The type-it-in half, for when there is nothing on the clipboard — and the only way to write
an internal `[[Title|text]]` link, since an article title cannot be derived from a URL. It
asks for the target, then the link text, re-asking on invalid input. An **empty target
cancels**: `input()` cannot tell Esc from an empty line, so emptiness is the abort. In
visual mode the selection seeds both prompts and is replaced.

`<LocalLeader>` is `\` unless you have changed it, so `\l` by default. Both modes go
through `<Plug>(sumo-wiki-insert-link)`, and `hasmapto` means your own mapping to that
target wins rather than being shadowed:

```vim
nmap <Leader>k <Plug>(sumo-wiki-insert-link)
xmap <Leader>k <Plug>(sumo-wiki-insert-link)
```

Verify the plugin after changing it:

```sh
vim  -es -Nu NONE -S editors/vim/test/test-sumo-wiki.vim
nvim -es -u NONE  -S editors/vim/test/test-sumo-wiki.vim
```

61 assertions, run against both editors in CI as the `vim` job: the pure link and paste
functions, the real `p` and insert-link mappings driven end to end, filetype detection,
`'selection'` both ways, a multibyte label, and that the register survives. Four things to
know if you add cases:

- `:echo` prints nothing under `-es`, so results go to stdout via `writefile`.
- `:edit` after a paste case aborts with **E37** unless you `enew!` first.
- `feedkeys(..., 'x')` is the only way to answer an `input()` prompt headlessly — which is
  why `sumo_wiki#insert_link` does **not** call `inputsave()`/`inputrestore()`. Those save
  *and clear* the typeahead buffer, which is where `feedkeys` put the answers, so the prompt
  blocks forever. The mappings have no trailing keys to protect, so nothing is lost.
- `plugin/` is sourced at startup, before the test sets the runtimepath, so the test does
  `runtime! plugin/sumo-wiki.vim` by hand. Without it the `<Plug>` mappings are absent and
  `<LocalLeader>l` is a mapping to nothing. `maparg()` will not find a `<Plug>` lhs in
  either notation; ask `:nmap`/`:xmap` through `execute()` instead.

## Neovim LSP — configuration only

```lua
vim.filetype.add({ extension = { sumo = 'sumo-wiki', wiki = 'sumo-wiki' } })

vim.api.nvim_create_autocmd('FileType', {
  pattern = 'sumo-wiki',
  callback = function(args)
    vim.lsp.start({
      name = 'sumo-lint',
      cmd = { 'sumo-lint-lsp' },          -- or an absolute path
      root_dir = vim.fn.getcwd(),
    }, { bufnr = args.buf })
  end,
})
```

Diagnostics then appear through Neovim's built-in LSP client. `:lua
vim.diagnostic.open_float()` shows the message under the cursor. The `vim.filetype.add`
line is redundant if you already have `editors/vim` on the runtimepath — its `ftdetect`
does the same thing.

## Vim 8 with ALE

ALE has no LSP autodetection for a custom server, so register it:

```vim
au BufRead,BufNewFile *.sumo,*.wiki set filetype=sumo-wiki

call ale#linter#Define('sumo-wiki', {
\   'name': 'sumo-lint',
\   'lsp': 'stdio',
\   'executable': 'sumo-lint-lsp',
\   'command': '%e',
\   'project_root': getcwd(),
\})
```

Alternatively, run the CLI as a plain linter, which needs no LSP at all:

```vim
call ale#linter#Define('sumo-wiki', {
\   'name': 'sumo-lint-cli',
\   'executable': 'sumo-lint',
\   'command': '%e --format json -',
\   'callback': 'ale#handlers#unix#HandleAsWarning',
\})
```

## Emacs

`emacs/sumo-wiki-mode.el` provides syntax highlighting plus linting. Add it to your
`load-path` and require it:

```elisp
(add-to-list 'load-path "~/path/to/sumo-linter/editors/emacs")
(require 'sumo-wiki-mode)
```

`.sumo` files then open in `sumo-wiki-mode`. `.wiki` is also registered, but appended
rather than prepended so it yields to any wiki mode you already use.

Three ways to get diagnostics, in decreasing order of integration:

- **Eglot** (built in to Emacs 29+) — registered automatically. Just `M-x eglot`.
- **lsp-mode** — also registered automatically when lsp-mode loads.
- **Flymake, no language server** — `M-x sumo-wiki-flymake-setup`, which pipes the buffer
  through the `sumo-lint` CLI. Same diagnostics, no long-running process.

Commands:

| Key | Command | Effect |
|---|---|---|
| `C-c C-f` | `sumo-wiki-fix-buffer` | apply safe fixes (phase 1) |
| `C-c C-s` | `sumo-wiki-apply-style` | apply house style (phase 2) |
| `C-c C-l` | `sumo-wiki-insert-link` | ask for a target and text, write the link |
| `C-y` | `sumo-wiki-yank` | yank a URL over the region → a link |

The first two report *"nothing to fix"* / *"already consistent"* rather than appearing to do
nothing, and both preserve point's line and column.

`sumo-wiki-insert-link` is the counterpart of `SUMO: Insert Link` in VS Code, and the only
way to write an internal `[[Title|text]]` link — an article title cannot be derived from a
URL. It asks twice, re-asking on invalid input; `C-g` aborts, and the region seeds both
prompts and is replaced.

`sumo-wiki-yank` is the same gesture as `Cmd+V` in VS Code: mark some words, copy a URL,
yank, and you get `[https://example.org the words]` instead of the region replaced. It
**remaps `yank`** rather than binding a key, so it follows whatever you have yank on — `C-y`,
and `s-v` on macOS. Everything else yanks exactly as before, including the prefix argument.

It only rewrites the yank when the gesture is unambiguous, and yanks normally otherwise:
the kill is a single scheme-bearing URL with no whitespace, the region is non-empty, on one
line, not itself a URL, and free of `[` and `]`. `sumo-wiki-paste-url-as-link` set to nil
turns it off. Only the external form is produced — an internal link goes by article
**title**, which a `/kb/<slug>` URL does not carry.

`delete-selection-mode` deletes the region in `pre-command-hook`, which would leave the
command with no link text, so the command carries a function-valued `delete-selection`
property that suppresses the deletion for exactly this case. If you turn
`transient-mark-mode` off, `use-region-p` is nil and you get a plain `C-y` — deliberately.

One highlighting choice worth knowing: **lines beginning with a space are shown in a
distinct face**, because the wiki renders them preformatted. A single stray leading space
silently turns a paragraph into a code block, and that is invisible in a plain editor.

Verify the mode after changing it:

```sh
cargo build --release
PATH="$PWD/target/release:$PATH" \
  /Applications/Emacs.app/Contents/MacOS/Emacs -Q --batch \
  -l editors/emacs/test-sumo-wiki-mode.el
```

That checks mode activation, every font-lock rule, Eglot registration, the CLI commands
against the real binary, the Flymake JSON path, and both link paths — 63 assertions. **CI runs it too**, as the `emacs` job, on `emacs-nox` from Ubuntu's archive.

Two wrinkles if you add cases: `transient-mark-mode` is nil under `--batch` but t in any
interactive Emacs, so a region test must bind it or it passes vacuously; and the prompts are
driven by stubbing `read-string` with `cl-letf`.

It exits non-zero on failure, which is not free in `--batch`: Emacs exits 0 however many
FAILs were printed, so the summary block at the end of the file is what makes the run a
gate rather than decoration. It also enforces a floor on the assertion count, because a
form that stops running its body would otherwise print fewer lines and still pass — raise
the `expected` value when you add assertions.

## VS Code

The extension in `vscode/` is a thin `vscode-languageclient` wrapper plus a TextMate
grammar. It highlights the same constructs as the Emacs mode, including the
leading-space preformatted lines described above.

```sh
cd editors/vscode
npm install
npm test                  # 34 grammar assertions + 51 link assertions
npx vsce package          # produces sumo-lint-0.3.0.vsix
code --install-extension sumo-lint-0.3.0.vsix
```

If `sumo-lint-lsp` is not on your `PATH`, set `sumoLint.serverPath` to an
absolute path in settings.

### Insert a link: `Cmd+K Cmd+L`

`SUMO: Insert Link` (Command Palette, right-click menu, or `Cmd+K Cmd+L` /
`Ctrl+K Ctrl+L`) asks for a target and the link text, then writes the correct
form — because SUMO has two, and they are not interchangeable:

| You type | You get |
|---|---|
| `https://example.org` + `Example` | `[https://example.org Example]` |
| `Install Thunderbird on Linux` + `Linux` | `[[Install Thunderbird on Linux\|Linux]]` |
| `#w_whitelisting` + `Whitelisting` | `[[#w_whitelisting\|Whitelisting]]` |

Anything with a scheme (`http:`, `https:`, `ftp:`, `mailto:`) is external and
takes a **space**; anything else is an internal link by article **title** — not
slug — and takes a **pipe**. Leave the text empty for `[[Article title]]`, and a
label identical to the title is dropped rather than duplicated.

Select first and it seeds the prompts: a selected URL becomes the target, selected
prose becomes the link text. The selection is replaced.

Two deliberate choices:

- The keybinding is scoped `editorLangId == sumo-wiki`, where it shadows **Toggle
  Fold**. That chord is the near-universal "insert link" shortcut and folding is
  of little use in an article; `Cmd+Alt+[` still folds.
- It does not rewrite an existing link. Select `[text](url)` and the prompts come
  up empty — the tool for that is SW009's quick fix, which knows the span.

### Paste a URL over selected text: `Cmd+V`

Select some words, copy a URL, press `Cmd+V` — you get
`[https://example.org the release notes]` instead of the selection being
replaced. This is the same gesture Markdown mode uses, and usually the faster of
the two: the clipboard already holds the URL, so there is nothing to type.

It is a **paste handler**, not a keybinding — `Cmd+V` is still paste. It only
rewrites the paste when *all* of these hold, and pastes normally otherwise:

- the clipboard holds a single URL with a scheme and no whitespace,
- exactly one selection, non-empty, on one line, and
- the selection is not itself a URL (that is a correction) and has no `[` or `]`.

VS Code's paste widget still offers **Paste as plain text** afterwards, and
`sumoLint.pasteUrlAsLink: false` turns the handler off for good.

Only the external form is produced. An internal link needs the article **title**,
and a `support.mozilla.org/kb/<slug>` URL on the clipboard does not carry one —
resolving it would take a network call, so use `Cmd+K Cmd+L` for those.

The provider needs VS Code **1.97** or newer (the paste API stabilised there). On
an older host the extension still loads; only the paste handler is skipped.

`npm test` covers the markup both paths produce (51 assertions, no VS Code
needed); the prompting itself is two input boxes and an edit, and is not worth a
harness.

Two things about the grammar that look like mistakes and are not:

- List markers are scoped `keyword.other.list` **and**
  `punctuation.definition.list.begin`. The latter is the semantically right name, but
  themes only colour it under a `.markdown` suffix, so on its own the bullets come out
  unstyled. `keyword.other` is what actually renders them blue.
- The server options object passes **no** `TransportKind`. An `Executable` server
  already speaks stdio; naming a kind there is how you get
  `Transport kind ipc is not support for command executable`, because `stdio` is `0`
  and `1` — the tempting value — is `ipc`, which needs a forked Node module.

Publishing to the marketplace is deliberately out of scope — sideloading a
`.vsix` is enough for a contributor tool, and avoids needing a publisher account.

### GhostText: set `ghostText.fileExtension` to `sumo`

[GhostText](https://ghosttext.fregante.com/) edits a browser textarea in your editor,
which is the natural way to work on a SUMO article: you stay in the wiki editor and get
real markup tooling. But the extension only claims `*.sumo` and `*.wiki`, and GhostText
names its scratch buffer from one global setting, so without this the buffer opens as
plain text (or whatever else you had set) and **none of sumo-lint runs** — no
highlighting, no diagnostics, no quick fixes:

```json
"ghostText.fileExtension": "sumo"
```

Two consequences of that setting being global, not per-site:

- Every other GhostText session opens as `.sumo` too, so editing Wikipedia will highlight
  as SUMO markup and MediaWiki-only constructs get flagged. The alternative is leaving it
  empty and setting the language per buffer with `Cmd+K M`.
- GhostText buffers are unsaved scratch files, so `editor.codeActionsOnSave` almost never
  fires there. `Cmd+.` is how you apply a fix.

Nothing is written back to SUMO by any of this — GhostText syncs your keystrokes into the
textarea, and *you* still press Save in the wiki editor.

## Just the CLI

No editor setup at all:

```sh
sumo-lint draft.wiki              # report problems
sumo-lint --diff draft.wiki       # show what --fix would change
sumo-lint --fix draft.wiki        # apply safe fixes in place
sumo-lint --format json corpus/   # machine-readable, for CI
```

Exit code is 1 if there are errors, 0 otherwise, so it drops straight into a
pre-commit hook or CI job.
