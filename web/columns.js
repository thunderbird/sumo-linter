/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure logic for column widths (#46): the drag handles between Wiki markup,
 * Preview and Problems. Kept out of app.js so it can be tested under plain
 * Node, like gutter.js.
 *
 * Each column has a weight, kept in this browser. The visible columns share
 * the width in proportion to their weights, so hiding a column and showing
 * it again leaves the others as they were.
 */

const COLUMNS = ['markup', 'preview', 'problems'];

/** Where the weights are kept, beside the Show settings (`sumo-lint:view`). */
const COLUMNS_KEY = 'sumo-lint:columns';

/** Equal weights. */
function equalWeights() {
  return { markup: 1, preview: 1, problems: 1 };
}

/** The saved weights, or equal ones for anything missing or invalid. */
function parseColumns(json) {
  const weights = equalWeights();
  let saved;
  try {
    saved = JSON.parse(json);
  } catch {
    return weights;
  }
  if (!saved || typeof saved !== 'object') return weights;
  for (const name of COLUMNS) {
    const w = saved[name];
    if (typeof w === 'number' && Number.isFinite(w) && w > 0) weights[name] = w;
  }
  return weights;
}

/** The share of the width of each visible column, summing to 1. */
function shares(weights, visible) {
  const total = visible.reduce((sum, name) => sum + weights[name], 0);
  return visible.map((name) => weights[name] / total);
}

/** The CSS grid-template-columns for the visible columns. */
function template(weights, visible) {
  return shares(weights, visible)
    .map((s) => `minmax(0, ${Number(s.toFixed(4))}fr)`)
    .join(' ');
}

/**
 * New weights after moving the boundary between visible[i] and visible[i+1]
 * by `deltaPx`, where the columns share `totalPx`. Neither column gets
 * narrower than `minPx`. Only those two columns change, and their sum stays
 * the same, so the other column keeps its width.
 */
function drag(weights, visible, i, deltaPx, totalPx, minPx) {
  if (i < 0 || i + 1 >= visible.length || !(totalPx > 0)) return { ...weights };
  const s = shares(weights, visible);
  const pair = s[i] + s[i + 1];
  const min = Math.min(minPx / totalPx, pair / 2);
  const left = Math.min(Math.max(s[i] + deltaPx / totalPx, min), pair - min);
  const sum = visible.reduce((acc, name) => acc + weights[name], 0);
  return {
    ...weights,
    [visible[i]]: left * sum,
    [visible[i + 1]]: (pair - left) * sum,
  };
}

/** Where the boundary after visible[i] sits, in percent of the width. */
function boundaryPercent(weights, visible, i) {
  const s = shares(weights, visible);
  return Math.round(100 * s.slice(0, i + 1).reduce((a, b) => a + b, 0));
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = {
    COLUMNS, COLUMNS_KEY, equalWeights, parseColumns, shares, template, drag, boundaryPercent,
  };
}
