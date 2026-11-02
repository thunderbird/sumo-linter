/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the column-width arithmetic behind the drag handles (#46).
//
//   node web/test/columns.test.mjs

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import columns from '../columns.js';

const { equalWeights, parseColumns, shares, template, drag, boundaryPercent } = columns;

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

const round = (xs) => xs.map((x) => Math.round(x * 1000) / 1000);
const all = ['markup', 'preview', 'problems'];

// --- saved weights ------------------------------------------------------------
check('nothing saved: equal', parseColumns(null), equalWeights());
check('not JSON: equal', parseColumns('{'), equalWeights());
check('saved weights come back', parseColumns('{"markup":2,"preview":1,"problems":0.5}'),
  { markup: 2, preview: 1, problems: 0.5 });
check('invalid weights are equal again',
  parseColumns('{"markup":-1,"preview":"x","problems":0,"other":9}'), equalWeights());

// --- shares and the CSS -------------------------------------------------------
check('equal thirds', round(shares(equalWeights(), all)), [0.333, 0.333, 0.333]);
check('a hidden column does not count', shares({ markup: 3, preview: 1, problems: 1 }, ['markup', 'problems']),
  [0.75, 0.25]);
check('the template', template({ markup: 2, preview: 1, problems: 1 }, all),
  'minmax(0, 0.5fr) minmax(0, 0.25fr) minmax(0, 0.25fr)');

// --- dragging -------------------------------------------------------------------
// Three columns sharing 900 px, 300 each.
const dragged = drag(equalWeights(), all, 0, 150, 900, 100);
check('dragging right widens the left column', round(shares(dragged, all)), [0.5, 0.167, 0.333]);
check('the third column keeps its width', round(shares(dragged, all))[2], 0.333);
check('dragging left narrows it', round(shares(drag(equalWeights(), all, 1, -100, 900, 50), all)),
  [0.333, 0.222, 0.444]);
check('no column gets narrower than the minimum',
  Math.round(shares(drag(equalWeights(), all, 0, 1000, 900, 200), all)[1] * 900), 200);
check('nor on the other side',
  Math.round(shares(drag(equalWeights(), all, 0, -1000, 900, 200), all)[0] * 900), 200);
check('a minimum too big for the pair splits it evenly',
  round(shares(drag(equalWeights(), all, 0, 100, 900, 400), all)), [0.333, 0.333, 0.333]);
check('no boundary there: nothing changes', drag(equalWeights(), all, 2, 50, 900, 50), equalWeights());
// A hidden column keeps its weight, so showing it again restores the layout.
const two = drag({ markup: 1, preview: 1, problems: 1 }, ['markup', 'problems'], 0, 200, 800, 100);
check('dragging with Preview hidden leaves its weight', two.preview, 1);
check('two columns: 0.75 and 0.25', round(shares(two, ['markup', 'problems'])), [0.75, 0.25]);

// --- the boundary, for the handle's aria-valuenow -----------------------------
check('boundaries of equal thirds', [0, 1].map((i) => boundaryPercent(equalWeights(), all, i)), [33, 67]);

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 17;
if (checks < expected) {
  console.error(`\nonly ${checks} columns assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} columns assertions failed`);
  process.exit(1);
}
console.log(`columns: ${checks} assertions passed`);
