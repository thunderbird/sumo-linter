# Editor integration

One language server, `sumo-lint-lsp`, backs every editor. There is no per-editor
linting logic, so rules only ever have to be written once.

Build it first:

```sh
cargo build --release          # produces target/release/sumo-lint-lsp
```

Optionally put it on your `PATH`:

```sh
cp target/release/sumo-lint-lsp ~/.local/bin/
```

Treat `*.sumo` and `*.wiki` as SUMO markup. Remember that SUMO itself is the
source of truth — these are local drafts you paste back into the article editor.

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

## VS Code

The extension in `vscode/` is a thin `vscode-languageclient` wrapper.

```sh
cd editors/vscode
npm install
npx vsce package          # produces sumo-lint-0.1.0.vsix
code --install-extension sumo-lint-0.1.0.vsix
```

If `sumo-lint-lsp` is not on your `PATH`, set `sumoLint.serverPath` to an
absolute path in settings.

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
