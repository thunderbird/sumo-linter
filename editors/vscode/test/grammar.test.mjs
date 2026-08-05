/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Tokenises a fixture with the real vscode-textmate engine VS Code itself uses,
// and asserts the scope on a specific character of each line. A grammar that
// silently stops matching looks fine until someone opens a file, so this is the
// counterpart to editors/emacs/test-sumo-wiki-mode.el.
//
//   cd editors/vscode && npm install && npm test

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import assert from 'node:assert/strict';
// Default imports, not named: both packages are CommonJS and Node's ESM
// interop does not detect their exports statically.
import oniguruma from 'vscode-oniguruma';
import textmate from 'vscode-textmate';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

const wasm = await readFile(
  join(root, 'node_modules/vscode-oniguruma/release/onig.wasm'),
);
await oniguruma.loadWASM(wasm.buffer);

const registry = new textmate.Registry({
  onigLib: Promise.resolve({
    createOnigScanner: (s) => new oniguruma.OnigScanner(s),
    createOnigString: (s) => new oniguruma.OnigString(s),
  }),
  loadGrammar: async () =>
    textmate.parseRawGrammar(
      await readFile(join(root, 'syntaxes/sumo-wiki.tmLanguage.json'), 'utf8'),
      'sumo-wiki.tmLanguage.json',
    ),
});

const grammar = await registry.loadGrammar('text.sumo-wiki');
assert.ok(grammar, 'grammar failed to load');

// Line, the column to probe, and a scope that must be present there. Prefix the
// scope with '!' to assert it is absent instead — asserting the root scope
// `text.sumo-wiki` would pass vacuously, since every token carries it.
const CASES = [
  ['* first bullet', 0, 'keyword.other.list.sumo-wiki'],
  ['** nested bullet', 1, 'keyword.other.list.sumo-wiki'],
  ['# ordered item', 0, 'keyword.other.list.sumo-wiki'],
  ['## nested ordered', 1, 'keyword.other.list.sumo-wiki'],
  ['; definition term', 0, 'keyword.other.list.sumo-wiki'],
  // The bullet is a marker, so the text after it must not be a list scope.
  ['* first bullet', 5, '!keyword.other.list.sumo-wiki'],

  ['= Heading one =', 2, 'markup.heading.1.sumo-wiki'],
  ['=Heading one=', 1, 'markup.heading.1.sumo-wiki'],
  ['== Heading two ==', 3, 'markup.heading.2.sumo-wiki'],
  ['====== Heading six ======', 7, 'markup.heading.6.sumo-wiki'],
  ['= Heading one =', 0, 'punctuation.definition.heading.sumo-wiki'],

  [' preformatted line with * and = in it', 1, 'markup.raw.block.sumo-wiki'],
  // Markup inside a preformatted line stays inert.
  [' preformatted line with * and = in it', 24, 'markup.raw.block.sumo-wiki'],

  ['{for win,mac}', 0, 'keyword.control.conditional.sumo-wiki'],
  ['{for not mac}', 0, 'keyword.control.conditional.sumo-wiki'],
  ['{/for}', 0, 'keyword.control.conditional.sumo-wiki'],
  ['{note}', 0, 'entity.name.tag.callout.sumo-wiki'],
  ['{/warning}', 0, 'entity.name.tag.callout.sumo-wiki'],

  ['Press {key Ctrl+T} now', 6, 'support.function.macro.sumo-wiki'],
  ['Choose {menu Settings} there', 7, 'support.function.macro.sumo-wiki'],

  ['[[Template:tbmigration]]', 3, 'keyword.control.import.sumo-wiki'],
  ['[[Image:screenshot.png]]', 3, 'constant.other.media.sumo-wiki'],
  ['See [[Another Article|here]].', 6, 'markup.underline.link.sumo-wiki'],
  ['See [https://example.com label].', 6, 'markup.underline.link.sumo-wiki'],

  ["This is '''bold''' text", 10, 'markup.bold.sumo-wiki'],
  ["This is ''italic'' text", 10, 'markup.italic.sumo-wiki'],
  ["This is '''''both''''' text", 12, 'markup.bold.italic.sumo-wiki'],
  // An apostrophe in prose must not start emphasis.
  ["Thunderbird's account settings", 12, '!markup.italic.sumo-wiki'],
  ["Thunderbird's account settings", 12, '!markup.bold.sumo-wiki'],

  ['----', 0, 'keyword.other.separator.sumo-wiki'],
  ['__TOC__', 0, 'keyword.control.toc.sumo-wiki'],
  ['{|', 0, 'keyword.other.table.sumo-wiki'],
  ['|-', 0, 'keyword.other.table.sumo-wiki'],
  ['<!-- a comment -->', 5, 'comment.block.sumo-wiki'],
];

let failed = 0;
for (const [line, column, expected] of CASES) {
  const negated = expected.startsWith('!');
  const scope = negated ? expected.slice(1) : expected;
  const { tokens } = grammar.tokenizeLine(line, textmate.INITIAL);
  const token = tokens.find((t) => column >= t.startIndex && column < t.endIndex);
  const scopes = token ? token.scopes : [];
  if (scopes.includes(scope) === negated) {
    failed += 1;
    console.error(
      `FAIL ${JSON.stringify(line)} col ${column}\n` +
      `  want ${negated ? 'no ' : ''}${scope}\n` +
      `  got  ${scopes.join(', ') || '(no token)'}`,
    );
  }
}

if (failed) {
  console.error(`\n${failed} of ${CASES.length} grammar assertions failed`);
  process.exit(1);
}
console.log(`grammar: ${CASES.length} assertions passed`);
