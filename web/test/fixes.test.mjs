/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the byte↔UTF-16 arithmetic the web app applies fixes with. The linter
// speaks byte offsets; the textarea speaks UTF-16. Get that wrong on an Arabic
// or Japanese article — both of which are in the corpus — and clicking "Fix"
// splices bytes into the middle of a character.
//
//   node web/test/fixes.test.mjs

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import fixes from '../fixes.js';

const { applyFixToText, byteToCharIndex, utf8Len } = fixes;

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

// --- utf8Len ----------------------------------------------------------------
check('ascii is 1 byte', utf8Len('a'.codePointAt(0)), 1);
check('é is 2 bytes', utf8Len('é'.codePointAt(0)), 2);
check('Arabic is 2 bytes', utf8Len('ع'.codePointAt(0)), 2);
check('Japanese is 3 bytes', utf8Len('日'.codePointAt(0)), 3);
check('an em-dash is 3 bytes', utf8Len('—'.codePointAt(0)), 3);
check('an emoji is 4 bytes', utf8Len('🐦'.codePointAt(0)), 4);

// --- byteToCharIndex --------------------------------------------------------
check('zero maps to zero', byteToCharIndex('anything', 0), 0);
check('ascii offsets are identical', byteToCharIndex('=h1\n* fi\n', 4), 4);
check('past the end clamps', byteToCharIndex('abc', 99), 3);
check('empty text', byteToCharIndex('', 5), 0);
// 'ع' is 2 bytes, so the '=' after it is at byte 2 and index 1.
check('after a 2-byte character', byteToCharIndex('ع=', 2), 1);
check('after two 3-byte characters', byteToCharIndex('日本語', 6), 2);
// The regression: an emoji is one code point, 4 bytes, two UTF-16 units. Counting
// each surrogate half separately reads it as 6 bytes and skews everything after.
check('after an emoji', byteToCharIndex('🐦x', 4), 2);
check('the character after an emoji', byteToCharIndex('🐦x=', 5), 3);
check('an emoji then a heading', byteToCharIndex('=🐦\n', 5), 3);

// --- applyFixToText ---------------------------------------------------------
// SW005: an insertion at the end of the line, the shape of the unclosed-heading
// fix. Its span is empty, which must not eat the character it sits before.
check(
  'insert a closing run',
  applyFixToText('=h1\n* fi\n', { start: 3, end: 3, replacement: '=' }),
  { text: '=h1=\n* fi\n', start: 3, end: 4 },
);
// SW009: a replacement spanning several characters.
check(
  'rewrite a markdown link',
  applyFixToText('see [x](http://y) here', { start: 4, end: 17, replacement: '[http://y x]' }),
  { text: 'see [http://y x] here', start: 4, end: 16 },
);
// SW008: a deletion, so the replacement is empty.
check(
  'delete an empty list item',
  applyFixToText('* a\n*\n* b\n', { start: 4, end: 5, replacement: '' }),
  { text: '* a\n\n* b\n', start: 4, end: 4 },
);
// The case the byte arithmetic exists for: an edit *after* multi-byte text.
check(
  'a fix after Japanese text',
  applyFixToText('日本語 **b**\n', { start: 10, end: 15, replacement: "'''b'''" }),
  { text: "日本語 '''b'''\n", start: 4, end: 11 },
);
check(
  'a fix after an emoji',
  applyFixToText('🐦 **b**\n', { start: 5, end: 10, replacement: "'''b'''" }),
  { text: "🐦 '''b'''\n", start: 3, end: 10 },
);
// Whatever the input, the bytes outside the span are untouched.
for (const src of ['=h1\n', '日本語=h1\n', '🐦=h1\n']) {
  const at = new TextEncoder().encode(src).length - 1; // before the newline
  const out = applyFixToText(src, { start: at, end: at, replacement: '=' });
  check(`round trip outside the span for ${JSON.stringify(src)}`, out.text, `${src.slice(0, -1)}=\n`);
}

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 23;
if (checks < expected) {
  console.error(`\nonly ${checks} web assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} web assertions failed`);
  process.exit(1);
}
console.log(`web: ${checks} assertions passed`);
