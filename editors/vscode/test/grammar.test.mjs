/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Tokenises with the real vscode-textmate engine VS Code itself uses, asserts
// the scope on a specific character of each line, and compares every committed
// article with SUMO's own rules in web/highlight.js (#37). A grammar that
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
import { corpusFiles, firstDifference, readArticle } from '../../highlight-check.mjs';

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
const S = 'variable.language.sumo-wiki';
const CASES = [
  // The cases in Roland's two screenshots of SUMO's editor (#35).
  ['[[T:TBMore]]', 3, 'markup.other.link.sumo-wiki'],
  ['{for tb123}dddd{/for}', 0, S],
  ['{for tb123}dddd{/for}', 1, 'meta.tag.name.sumo-wiki'],
  ['{for tb123}dddd{/for}', 5, 'markup.italic.sumo-wiki'],
  ['{for tb123}dddd{/for}', 10, S],
  ['{for tb123}dddd{/for}', 12, `!${S}`],
  ['{for tb123}dddd{/for}', 16, S],
  ['{key}key{/key}', 1, 'meta.tag.sumo-wiki'],
  // SUMO's rules know no {/key}, so it stays plain.
  ['{key}key{/key}', 9, `!${S}`],
  ['{button ok}', 9, 'markup.italic.sumo-wiki'],
  ['<--html comment-->', 5, '!comment.block.sumo-wiki'],
  ['[https://example.com example]', 5, 'markup.underline.link.sumo-wiki'],
  ["the '''Appearance''' panel", 4, S],
  ["the '''Appearance''' panel", 8, 'markup.bold.sumo-wiki'],
  ["the ''kebab'' menu", 7, 'markup.italic.sumo-wiki'],
  ['__TOC__', 0, S],
  ['==Card view ==', 0, 'markup.bold.sumo-wiki'],
  ['==Card view ==', 5, 'markup.heading.sumo-wiki'],
  ['** Click', 1, S],
  ['** Click', 4, `!${S}`],
  [' preformatted', 3, 'markup.quote.sumo-wiki'],
  ['a <!-- c --> b', 5, 'comment.block.sumo-wiki'],
  ['a <!-- c --> b', 13, '!comment.block.sumo-wiki'],
  ["<nowiki>'''x'''</nowiki>", 9, 'comment.block.sumo-wiki'],
  ['{note}Hi{/note}', 3, 'meta.tag.name.sumo-wiki'],
  // Before a condition, } is plain and the state goes on, as in CodeMirror.
  ['{for}x mac}', 4, `!${S}`],
  ['{for}x mac}', 7, 'markup.italic.sumo-wiki'],
  ['{for}x mac}', 10, S],
  // After the condition, everything up to } is plain, even another condition.
  ['{for mac and win}', 13, '!markup.italic.sumo-wiki'],
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

// Every committed article must highlight exactly as SUMO's rules do in
// web/highlight.js (#37), character by character.
function letter(scopes) {
  const has = (prefix) => scopes.some((s) => s.startsWith(prefix));
  if (has('markup.quote')) return 'Q';
  if (has('comment')) return 'C';
  if (has('markup.other.link')) return 'L';
  if (has('variable.language') || has('meta.tag')) return 'S';
  if (has('markup.bold')) return 'B';
  if (has('markup.italic')) return 'I';
  if (has('markup.underline.sumo-wiki')) return 'U';
  if (has('markup.strikethrough')) return 'X';
  return '.';
}
const files = corpusFiles();
const differences = [];
for (const path of files) {
  let stack = textmate.INITIAL;
  const got = readArticle(path).split('\n').map((line) => {
    const r = grammar.tokenizeLine(line, stack);
    stack = r.ruleStack;
    return r.tokens
      .map((t) => letter(t.scopes).repeat(Math.min(t.endIndex, line.length) - Math.min(t.startIndex, line.length)))
      .join('');
  });
  const diff = firstDifference(path, got);
  if (diff) differences.push(diff);
}
for (const d of differences.slice(0, 10)) console.error(`FAIL ${d}`);
if (files.length < 800) {
  failed += 1;
  console.error(`only ${files.length} corpus articles found`);
}
if (differences.length) {
  failed += 1;
  console.error(`${differences.length} of ${files.length} articles highlight differently from SUMO's rules`);
}

const total = CASES.length + 2;
if (failed) {
  console.error(`\n${failed} of ${total} grammar assertions failed`);
  process.exit(1);
}
console.log(`grammar: ${total} assertions passed, ${files.length} articles match SUMO's rules`);
