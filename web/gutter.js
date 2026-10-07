/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure logic for the line-number gutter, kept out of app.js so it can be tested
 * under plain Node, the same split as fixes.js.
 *
 * Diagnostics are reported as `line:column`, so the gutter has to count lines
 * exactly as the Rust core does: `line_col` in sumo-wiki-core counts `\n` and
 * nothing else. A textarea normalises CRLF to LF, so `\r` never reaches here.
 */

/** Number of lines the linter sees in `text`. An empty text is one line. */
function lineCount(text) {
  let n = 1;
  for (let i = text.indexOf('\n'); i !== -1; i = text.indexOf('\n', i + 1)) n++;
  return n;
}

/**
 * The worst severity reported on each line, as an array indexed from 0.
 *
 * A diagnostic marks the line it starts on, which is the line its `line:column`
 * names. An error outranks a warning. A diagnostic outside the text marks
 * nothing: it can only come from a lint of older text that a debounced re-lint
 * has not replaced yet.
 */
function lineSeverities(text, diags) {
  const marks = new Array(lineCount(text)).fill('');
  for (const d of diags) {
    const i = d.line - 1;
    if (!Number.isInteger(i) || i < 0 || i >= marks.length) continue;
    if (d.severity === 'error') marks[i] = 'error';
    else if (marks[i] === '') marks[i] = 'warning';
  }
  return marks;
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = { lineCount, lineSeverities };
}
