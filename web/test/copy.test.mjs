/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the web app's Copy button logic. The clipboard must hold exactly the
// text the linter saw, and a failed copy must say so: an author who believes a
// copy worked pastes stale text into SUMO.
//
//   node web/test/copy.test.mjs

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import copy from '../copy.js';

const { COPY_RESET_MS, copyText, copyLabel } = copy;

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

/** A clipboard that records what it was given. */
function recorder() {
  const written = [];
  return { written, writeText: async (s) => { written.push(s); } };
}

// --- copyText: the text goes over unchanged ---------------------------------
const exact = [
  ['plain', '= H ='],
  ['trailing whitespace', '= H = \t\n'],
  ['leading space (preformatted line)', ' REGEDIT4\n'],
  ['blank lines', '\n\n\n'],
  ['multi-byte', 'عربي\n日本語 — 🐦'],
  ['empty', ''],
];
for (const [what, text] of exact) {
  const cb = recorder();
  check(`${what}: reports copied`, await copyText(text, cb), 'copied');
  check(`${what}: written byte for byte`, cb.written, [text]);
}

// --- copyText: every failure is reported, none rejects ----------------------
check('no clipboard API', await copyText('x', undefined), 'failed');
check('clipboard without writeText', await copyText('x', {}), 'failed');
check(
  'writeText rejects (permission denied)',
  await copyText('x', { writeText: async () => { throw new Error('NotAllowedError'); } }),
  'failed',
);
check(
  'writeText throws synchronously',
  await copyText('x', { writeText() { throw new Error('boom'); } }),
  'failed',
);

// --- copyLabel --------------------------------------------------------------
check('idle label', copyLabel('idle'), 'Copy');
check('copied label', copyLabel('copied'), 'Copied');
check('failed label', copyLabel('failed'), 'Copy failed');
check('unknown state falls back to idle', copyLabel(undefined), 'Copy');
check('the confirmation is visible for two seconds', COPY_RESET_MS, 2000);

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 21;
if (checks < expected) {
  console.error(`\nonly ${checks} copy assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} copy assertions failed`);
  process.exit(1);
}
console.log(`copy: ${checks} assertions passed`);
