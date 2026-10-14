/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the web app's autosave and save-to-file logic. A save must keep the
// text byte for byte, must say when it failed, and overlapping file writes must
// leave the latest text on disk.
//
//   node web/test/save.test.mjs

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import save from '../save.js';

const { DRAFT_KEY, FILE_NAME, saveDraft, loadDraft, fileWriter } = save;

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

/** An in-memory stand-in for localStorage. */
function memoryStorage() {
  const map = new Map();
  return {
    map,
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)); },
    removeItem: (k) => { map.delete(k); },
  };
}

// --- saveDraft / loadDraft --------------------------------------------------
const exact = [
  ['plain', '= H ='],
  ['trailing whitespace', '= H = \t\n'],
  ['leading space (preformatted line)', ' REGEDIT4\n'],
  ['multi-byte', 'عربي\n日本語 — 🐦'],
];
for (const [what, text] of exact) {
  const s = memoryStorage();
  check(`${what}: reports saved`, saveDraft(s, text), 'saved');
  check(`${what}: round-trips byte for byte`, loadDraft(s), text);
}

{
  const s = memoryStorage();
  saveDraft(s, 'old');
  check('empty text reports saved', saveDraft(s, ''), 'saved');
  check('empty text removes the draft', s.map.has(DRAFT_KEY), false);
  check('a removed draft loads as empty', loadDraft(s), '');
}
check('no draft yet loads as empty', loadDraft(memoryStorage()), '');
check('storage blocked: save fails', saveDraft(null, 'x'), 'failed');
check('storage blocked: load is empty', loadDraft(null), '');
check(
  'quota full: save fails, not throws',
  saveDraft({ setItem() { throw new Error('QuotaExceededError'); } }, 'x'),
  'failed',
);
check(
  'unreadable storage: load is empty, not throws',
  loadDraft({ getItem() { throw new Error('SecurityError'); } }),
  '',
);
check('the key is namespaced', DRAFT_KEY, 'sumo-lint:draft');
check('the file opens in the editors\' SUMO modes', FILE_NAME, 'article.wiki');

// --- fileWriter -------------------------------------------------------------
/** A write that only finishes when the test says so. */
function controlledWrite() {
  const started = [];
  const finish = [];
  let running = 0;
  let maxRunning = 0;
  const write = (text) => new Promise((resolve, reject) => {
    running += 1;
    maxRunning = Math.max(maxRunning, running);
    started.push(text);
    finish.push((err) => {
      running -= 1;
      if (err) reject(err);
      else resolve();
    });
  });
  return { write, started, finish, maxRunning: () => maxRunning };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

{
  const w = controlledWrite();
  const results = [];
  const push = fileWriter(w.write, (state) => results.push(state));
  const done = push('a');
  push('b');
  push('c');
  await tick();
  check('first write starts at once', w.started, ['a']);
  w.finish[0]();
  await tick();
  check('only the latest waiting text is written next', w.started, ['a', 'c']);
  w.finish[1]();
  await done;
  check('the queue ends after the latest text', w.started, ['a', 'c']);
  check('never two writes at once', w.maxRunning(), 1);
  check('each write reports saved', results, ['saved', 'saved']);
}

{
  const w = controlledWrite();
  const results = [];
  const push = fileWriter(w.write, (state) => results.push(state));
  const first = push('a');
  await tick();
  w.finish[0](new Error('NotAllowedError'));
  await first;
  check('a failed write reports failed', results, ['failed']);
  const second = push('b');
  await tick();
  w.finish[1]();
  await second;
  check('the writer keeps working after a failure', w.started, ['a', 'b']);
  check('and reports the later success', results, ['failed', 'saved']);
}

{
  const w = controlledWrite();
  const push = fileWriter(w.write, () => {});
  push('');
  await tick();
  check('an empty text is still written (the file must match)', w.started, ['']);
  w.finish[0]();
}

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 27;
if (checks < expected) {
  console.error(`\nonly ${checks} save assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} save assertions failed`);
  process.exit(1);
}
console.log(`save: ${checks} assertions passed`);
