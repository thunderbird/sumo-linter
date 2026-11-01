/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure logic for walk mode (#31): `walk.py --web` serves this page with
 * `?walk=1` and sends it the line of each checklist item. Kept out of app.js
 * so it can be tested under plain Node, like fixes.js and gutter.js.
 */

/** True if the page was opened by walk.py. */
function isWalkMode(search) {
  return new URLSearchParams(String(search ?? '')).get('walk') === '1';
}

/**
 * The UTF-16 range to select for `line` (1-based) of `text`: the first
 * occurrence of `find` on that line, else the whole line without its `\n`.
 * Lines are counted as the linter and the gutter count them, by `\n` only.
 * Curly and straight quotes count as the same. Returns null if the text has
 * no such line.
 */
function lineRange(text, line, find) {
  const s = String(text ?? '');
  if (!Number.isInteger(line) || line < 1) return null;
  let start = 0;
  for (let n = 1; n < line; n++) {
    const nl = s.indexOf('\n', start);
    if (nl === -1) return null;
    start = nl + 1;
  }
  let end = s.indexOf('\n', start);
  if (end === -1) end = s.length;
  if (find) {
    // The checklist quotes the app's strings, with curly quotes, and articles
    // often use straight ones: `“Sent”` must find `"Sent"`. Each quote is one
    // UTF-16 unit either way, so offsets do not move.
    const at = plainQuotes(s.slice(start, end)).indexOf(plainQuotes(find));
    if (at !== -1) return [start + at, start + at + find.length];
  }
  return [start, end];
}

/** `s` with curly quotes made straight, keeping its length. */
function plainQuotes(s) {
  return s.replace(/[“”„]/g, '"').replace(/[‘’‚]/g, "'");
}

if (typeof module !== 'undefined') {
  module.exports = { isWalkMode, lineRange };
}
