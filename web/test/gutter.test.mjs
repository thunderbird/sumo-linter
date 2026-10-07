/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the line counting behind the web app's line-number gutter. The
// diagnostics say `line:column`, so a gutter that counts lines differently from
// the Rust core points the reader at the wrong line.
//
//   node web/test/gutter.test.mjs

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import gutter from '../gutter.js';

const { lineCount, lineSeverities } = gutter;

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

// --- lineCount --------------------------------------------------------------
check('empty text is one line', lineCount(''), 1);
check('no newline is one line', lineCount('= H ='), 1);
check('a trailing newline opens a line', lineCount('a\n'), 2);
check('three lines', lineCount('a\nb\nc'), 3);
check('blank lines count', lineCount('\n\n\n'), 4);
// Only `\n` ends a line in `line_col`, so a lone `\r` must not.
check('a lone CR is not a line break', lineCount('a\rb'), 1);
check('multi-byte text does not shift lines', lineCount('عربي\n日本語\n🐦'), 3);

// --- lineSeverities ---------------------------------------------------------
const text = 'one\ntwo\nthree\nfour';
check('no diagnostics, no marks', lineSeverities(text, []), ['', '', '', '']);
check(
  'a warning marks its line',
  lineSeverities(text, [{ line: 2, severity: 'warning' }]),
  ['', 'warning', '', ''],
);
check(
  'an error marks its line',
  lineSeverities(text, [{ line: 4, severity: 'error' }]),
  ['', '', '', 'error'],
);
check(
  'an error outranks an earlier warning',
  lineSeverities(text, [
    { line: 1, severity: 'warning' },
    { line: 1, severity: 'error' },
  ]),
  ['error', '', '', ''],
);
check(
  'a later warning does not downgrade an error',
  lineSeverities(text, [
    { line: 1, severity: 'error' },
    { line: 1, severity: 'warning' },
  ]),
  ['error', '', '', ''],
);
check(
  'lines past the end mark nothing',
  lineSeverities(text, [{ line: 9, severity: 'error' }]),
  ['', '', '', ''],
);
check(
  'line 0 marks nothing',
  lineSeverities(text, [{ line: 0, severity: 'error' }]),
  ['', '', '', ''],
);
check(
  'a missing line marks nothing',
  lineSeverities(text, [{ severity: 'error' }]),
  ['', '', '', ''],
);
check('one mark per line of empty text', lineSeverities('', []), ['']);

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 16;
if (checks < expected) {
  console.error(`\nonly ${checks} gutter assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} gutter assertions failed`);
  process.exit(1);
}
console.log(`gutter: ${checks} assertions passed`);
