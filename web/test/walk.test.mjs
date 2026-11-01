/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the walk-mode logic (#31): which range the page selects for the
// line walk.py sends, counted as the gutter and the linter count lines.
//
//   node web/test/walk.test.mjs

import assert from 'node:assert/strict';
import walk from '../walk.js';

const { isWalkMode, lineRange } = walk;

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

check('walk mode: ?walk=1', isWalkMode('?walk=1'), true);
check('walk mode: among other parameters', isWalkMode('?a=b&walk=1'), true);
check('walk mode: not without it', isWalkMode(''), false);
check('walk mode: not for another value', isWalkMode('?walk=0'), false);

const text = 'one\ntwo “Sent” two\n\nfour';
check('the whole first line', lineRange(text, 1), [0, 3]);
check('the whole second line, without its newline', lineRange(text, 2), [4, 18]);
check('an empty line selects nothing, at its start', lineRange(text, 3), [19, 19]);
check('the last line, which has no newline', lineRange(text, 4), [20, 24]);
check('the quoted text on the line', lineRange(text, 2, '“Sent”'), [8, 14]);
check('the first occurrence on the line', lineRange(text, 2, 'two'), [4, 7]);
check('text that is not on the line selects the line', lineRange(text, 2, 'four'), [4, 18]);
check('text on another line only does not count', lineRange(text, 1, 'two'), [0, 3]);
check('curly quotes find straight ones', lineRange('a\nmy "Sent" box', 2, 'my “Sent”'), [2, 11]);
check('straight quotes find curly ones', lineRange("it’s", 1, "it's"), [0, 4]);
check('no such line', lineRange(text, 5), null);
check('line 0 is not a line', lineRange(text, 0), null);
check('a line that is not a number', lineRange(text, '2'), null);
check('\\r\\n: the \\r stays on its line, as in the linter', lineRange('a\r\nb', 1), [0, 2]);
{
  // UTF-16 offsets, because the textarea uses them: 🐦 is two units.
  const birds = '🐦🐦\nx🐦y';
  check('offsets are UTF-16 units', lineRange(birds, 2, 'y'), [8, 9]);
}

const expected = 19;
if (checks < expected) {
  console.error(`\nonly ${checks} walk assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} walk assertions failed`);
  process.exit(1);
}
console.log(`walk: ${checks} assertions passed`);
