/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts what `SUMO: Toggle Bold` writes. SUMO bold is `'''three quotes'''`,
// so producing `**bold**` here — the syntax SW010 flags — would be the worst
// possible bug, and these cases are what rule it out.
//
//   cd editors/vscode && npm test

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import bold from '../src/bold.js';

const { toggleBold } = bold;

let failed = 0;
let checks = 0;

function check(what, actual, expected) {
  checks += 1;
  try {
    assert.deepEqual(actual, expected);
  } catch {
    failed += 1;
    console.error(`FAIL ${what}\n  want ${JSON.stringify(expected)}\n  got  ${JSON.stringify(actual)}`);
  }
}

// Apply a result the way the command does, so the cases below read as text
// rather than as offsets. `|` marks the caret, `[...]` the new selection.
function apply(before, selected, after) {
  const r = toggleBold(before, selected, after);
  if (r === undefined) {
    return undefined;
  }
  const head = before.slice(0, before.length - r.cutBefore);
  const tail = after.slice(r.cutAfter);
  const marked = r.selStart === r.selEnd
    ? `${r.text.slice(0, r.selStart)}|${r.text.slice(r.selStart)}`
    : `${r.text.slice(0, r.selStart)}[${r.text.slice(r.selStart, r.selEnd)}]${r.text.slice(r.selEnd)}`;
  return head + marked + tail;
}

// --- wrapping ---------------------------------------------------------------
check('a selection becomes bold', apply('See ', 'release notes', ' today'),
  "See '''[release notes]''' today");
check('the whole line', apply('', 'all of it', ''), "'''[all of it]'''");
check('outer whitespace stays outside the markers', apply('See', '  release notes  ', '.'),
  "See  '''[release notes]'''  .");
check('an italic span nests, giving bold+italic', apply('', "''both''", ''),
  "'''[''both'']'''");
check('a multibyte selection survives', apply('le ', 'café', ' noir'),
  "le '''[café]''' noir");

// --- unwrapping -------------------------------------------------------------
check('a selected bold span loses the markers', apply('See ', "'''release notes'''", '.'),
  'See [release notes].');
check('a word selected inside a bold span loses them too',
  apply("See '''", 'release notes', "''' today"), 'See [release notes] today');
check('part of a bold span is refused, since splitting it is a guess',
  toggleBold("See '''release ", 'notes', "''' today"), undefined);
check('bold+italic loses only the bold layer', apply('', "'''''both'''''", ''),
  "[''both'']");
check('an empty bold span is removed', apply('a', "''''''", 'b'), 'a|b');
check('a selection inside an unclosed bold span is refused',
  toggleBold("'''open ", 'words', ' and on'), undefined);

// Toggling twice is the identity: the first result re-selects exactly the text
// the second call needs, which is the whole point of returning a selection.
for (const word of ['release notes', 'café', "''italic''"]) {
  const first = toggleBold('See ', word, ' today');
  const second = toggleBold(`See ${first.text.slice(0, first.selStart)}`,
    first.text.slice(first.selStart, first.selEnd),
    `${first.text.slice(first.selEnd)} today`);
  check(`toggling ${word} twice restores it`, second.text, word);
}

// --- nothing selected -------------------------------------------------------
check('an empty selection inserts markers and a caret', apply('See ', '', ' today'),
  "See '''|''' today");
check('whitespace only is treated as empty', apply('See', '  ', 'today'),
  "See  '''|'''today");

// --- refusals ---------------------------------------------------------------
// undefined means "do nothing and say so". Bold does not span lines, and a
// stray marker inside the selection has no single right reading.
check('a multi-line selection is refused', toggleBold('', 'one\ntwo', ''), undefined);
check('a stray marker inside the selection is refused',
  toggleBold('', "x '''b'''", ''), undefined);
check('a stray marker inside a selected span is refused',
  toggleBold('', "'''a''' and '''b'''", ''), undefined);
check('a stray marker before the text is refused', toggleBold('', "'''b''' x", ''), undefined);

// --- never Markdown ---------------------------------------------------------
for (const [b, s, a] of [['', 'words', ''], ['x ', 'words', ' y'], ['', '', '']]) {
  const r = toggleBold(b, s, a);
  check(`no ** for ${JSON.stringify(s)}`, /\*/.test(r.text), false);
  check(`three quotes either side for ${JSON.stringify(s)}`,
    (r.text.match(/'''/g) || []).length, 2);
}

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 26;
if (checks < expected) {
  console.error(`\nonly ${checks} bold assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} bold assertions failed`);
  process.exit(1);
}
console.log(`bold: ${checks} assertions passed`);
