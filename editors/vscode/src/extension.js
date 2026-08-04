/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Thin LSP client. All the linting logic lives in sumo-lint-lsp, so this file
// stays trivial and never needs to change when rules are added.

const { workspace, window } = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');

let client;

function activate(context) {
  const command = workspace.getConfiguration('sumoLint').get('serverPath', 'sumo-lint-lsp');

  client = new LanguageClient(
    'sumoLint',
    'SUMO wiki markup linter',
    { command, transport: 1 /* stdio */ },
    { documentSelector: [{ scheme: 'file', language: 'sumo-wiki' }] },
  );

  client.start().catch((err) => {
    window.showErrorMessage(
      `sumo-lint: could not start "${command}". Build it with ` +
      `\`cargo build --release\` and point sumoLint.serverPath at ` +
      `target/release/sumo-lint-lsp. (${err.message})`,
    );
  });
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
