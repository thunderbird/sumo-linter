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

## Neovim — configuration only, no plugin

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
vim.diagnostic.open_float()` shows the message under the cursor.

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

Both report *"nothing to fix"* / *"already consistent"* rather than appearing to do nothing,
and both preserve point's line and column.

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

That checks mode activation, every font-lock rule, Eglot registration, both commands
against the real binary, and the Flymake JSON path — 20 assertions.

## VS Code

The extension in `vscode/` is a thin `vscode-languageclient` wrapper plus a TextMate
grammar. It highlights the same constructs as the Emacs mode, including the
leading-space preformatted lines described above.

```sh
cd editors/vscode
npm install
npm test                  # tokenises a fixture with vscode-textmate: 34 assertions
npx vsce package          # produces sumo-lint-0.1.0.vsix
code --install-extension sumo-lint-0.1.0.vsix
```

If `sumo-lint-lsp` is not on your `PATH`, set `sumoLint.serverPath` to an
absolute path in settings.

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
