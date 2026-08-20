/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Thin LSP client, plus one editing command. All the linting logic lives in
// sumo-lint-lsp, so this file stays trivial and never needs to change when
// rules are added.

const { workspace, window, commands } = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');
const {
  buildLink,
  isUrl,
  seedFromSelection,
  validateLabel,
  validateTarget,
} = require('./link');

let client;

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
  );
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
