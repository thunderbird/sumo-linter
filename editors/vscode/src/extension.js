/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Thin LSP client, plus one editing command. All the linting logic lives in
// sumo-lint-lsp, so this file stays trivial and never needs to change when
// rules are added.

const vscode = require('vscode');
const { workspace, window, commands, languages } = vscode;
const { LanguageClient } = require('vscode-languageclient/node');
const { toggleBold } = require('./bold');
const {
  buildLink,
  isUrl,
  linkFromPaste,
  seedFromSelection,
  validateLabel,
  validateTarget,
} = require('./link');

let client;

// Undefined on hosts older than VS Code 1.97; registerPasteProvider checks.
const PASTE_LINK_KIND = vscode.DocumentDropOrPasteEditKind
  ? vscode.DocumentDropOrPasteEditKind.Text.append('link', 'sumo')
  : undefined;

// `SUMO: Insert Link` — writes the wiki form of a link so nobody has to
// remember which of the two forms takes a pipe and which takes a space.
async function insertLink() {
  const editor = window.activeTextEditor;
  if (!editor) {
    return;
  }

  const seed = seedFromSelection(editor.document.getText(editor.selection));

  const target = await window.showInputBox({
    title: 'SUMO: insert link',
    prompt: 'URL, article title, or #w_anchor on this page',
    placeHolder: 'https://example.org — or — Install Thunderbird on Linux',
    value: seed.target,
    validateInput: validateTarget,
  });
  if (target === undefined) {
    return; // Escape, not an empty answer: leave the buffer alone.
  }

  const label = await window.showInputBox({
    title: 'SUMO: insert link',
    prompt: isUrl(target)
      ? 'Link text (leave empty to show the URL itself)'
      : 'Link text (leave empty to show the article title)',
    value: seed.label,
    validateInput: (value) => validateLabel(value, target),
  });
  if (label === undefined) {
    return;
  }

  // A plain edit, not insertSnippet: a URL containing `$` or `}` is snippet
  // syntax, and escaping it correctly is a bug waiting to happen.
  const selection = editor.selection;
  await editor.edit((builder) => builder.replace(selection, buildLink(target, label)));
}

// `SUMO: Toggle Bold` — SUMO bold is `'''three quotes'''`, which is six
// characters to type and easy to leave unbalanced (SW003). The decision logic
// is in ./bold.js; this half is a range replace plus the new selection.
async function toggleBoldCommand() {
  const editor = window.activeTextEditor;
  if (!editor) {
    return;
  }
  const selection = editor.selection;
  const line = selection.start.line;
  const text = editor.document.lineAt(line).text;
  const edit = selection.isSingleLine
    ? toggleBold(
      text.slice(0, selection.start.character),
      text.slice(selection.start.character, selection.end.character),
      text.slice(selection.end.character),
    )
    : undefined;

  if (edit === undefined) {
    // Saying so beats doing nothing: the alternative is a key that looks broken.
    window.showWarningMessage(
      "SUMO: cannot toggle bold here — select text on one line, clear of any stray '''.",
    );
    return;
  }

  const from = selection.start.character - edit.cutBefore;
  const to = selection.end.character + edit.cutAfter;
  const applied = await editor.edit((builder) =>
    builder.replace(new vscode.Range(line, from, line, to), edit.text));
  if (!applied) {
    return;
  }
  // Re-selecting the inner text is what makes a second press undo the first.
  editor.selection = new vscode.Selection(
    line, from + edit.selStart, line, from + edit.selEnd,
  );
}

// Paste a URL over selected text and get a link, the way Markdown mode does.
// Registered as a paste provider rather than a Cmd+V keybinding on purpose:
// Cmd+V has to keep pasting. This only fires on the one unambiguous gesture,
// and VS Code's paste widget still offers plain text afterwards.
const pasteProvider = {
  async provideDocumentPasteEdits(document, ranges, dataTransfer, _context, token) {
    if (!workspace.getConfiguration('sumoLint').get('pasteUrlAsLink', true)) {
      return undefined;
    }
    // One edit carries one string, so multiple cursors would paste the first
    // selection's label into all of them. Leave that to the normal paste.
    if (ranges.length !== 1) {
      return undefined;
    }
    const item = dataTransfer.get('text/plain');
    if (!item) {
      return undefined;
    }
    const pasted = await item.asString();
    if (token.isCancellationRequested) {
      return undefined;
    }
    const markup = linkFromPaste(pasted, document.getText(ranges[0]));
    if (markup === undefined) {
      return undefined;
    }
    return [new vscode.DocumentPasteEdit(markup, 'Insert SUMO link', PASTE_LINK_KIND)];
  },
};

function registerPasteProvider(context) {
  // Stable since VS Code 1.97. Guarded anyway so an older host loses the paste
  // handler instead of failing to activate the whole extension.
  if (!vscode.DocumentDropOrPasteEditKind || !languages.registerDocumentPasteEditProvider) {
    return;
  }
  context.subscriptions.push(
    languages.registerDocumentPasteEditProvider(
      // No `scheme`: GhostText buffers are untitled, and that is where most
      // SUMO editing actually happens.
      { language: 'sumo-wiki' },
      pasteProvider,
      { providedPasteEditKinds: [PASTE_LINK_KIND], pasteMimeTypes: ['text/plain'] },
    ),
  );
}

function activate(context) {
  const command = workspace.getConfiguration('sumoLint').get('serverPath', 'sumo-lint-lsp');

  client = new LanguageClient(
    'sumoLint',
    'SUMO wiki markup linter',
    // No `transport`: an Executable server speaks stdio by default. Naming a
    // TransportKind here is a trap — ipc only works for a forked Node module.
    { command },
    { documentSelector: [{ scheme: 'file', language: 'sumo-wiki' }] },
  );

  client.start().catch((err) => {
    window.showErrorMessage(
      `sumo-lint: could not start "${command}". Build it with ` +
      `\`cargo build --release\` and point sumoLint.serverPath at ` +
      `target/release/sumo-lint-lsp. (${err.message})`,
    );
  });
  context.subscriptions.push(
    { dispose: () => client && client.stop() },
    // Registered outside the client's lifetime on purpose: inserting a link is
    // pure text editing, and still works if the server failed to start.
    commands.registerCommand('sumoLint.insertLink', insertLink),
    commands.registerCommand('sumoLint.toggleBold', toggleBoldCommand),
  );
  registerPasteProvider(context);
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
