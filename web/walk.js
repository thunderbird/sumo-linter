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

/**
 * The edit that uses a guess (#34): on `line`, find the comment
 * `<!-- CHECK 159…"old" → "guess"? -->`, replace the old text just before it
 * with the guess, and delete the comment. Returns {start, end, replacement}
 * as UTF-16 offsets into `text`, or {error} saying why nothing can be done.
 *
 * The old text matches without regard to quote style, case or a trailing
 * colon. If it matched without its colon, the guess loses its colon too. A
 * closing `}` between the old text and the comment stays, so
 * `{button Clear Now}` becomes `{button Clear temporary files}`. Other
 * comments directly before this one are looked past and kept. If the old
 * text is not directly before the comment, its last occurrence in the same
 * `{for}` part or heading is used, and the text between stays.
 */
function guessEdit(text, line, old, guess) {
  const range = lineRange(text, line);
  if (!range) return { error: `there is no line ${line}` };
  const [ls, le] = range;
  const src = text.slice(ls, le);
  const flat = plainQuotes(src);
  const key = `"${plainQuotes(old)}" → "${plainQuotes(guess)}"?`;
  const comments = /<!--[\s\S]*?-->/g;
  let at = -1;
  let end = -1;
  for (let m; (m = comments.exec(flat));) {
    if (m[0].startsWith('<!-- CHECK 159') && m[0].includes(key)) {
      at = m.index;
      end = at + m[0].length;
      break;
    }
  }
  if (at === -1) return { error: `line ${line} has no CHECK comment for "${old}" → "${guess}"` };
  let before = at;
  for (let prev; (prev = /<!--(?:(?!-->)[\s\S])*-->$/.exec(flat.slice(0, before)));) {
    before -= prev[0].length;
  }
  const close = flat[before - 1] === '}' ? 1 : 0;
  const tail = flat.slice(0, before - close).toLowerCase();
  const plainOld = plainQuotes(old);
  const candidates = [[plainOld, guess]];
  if (plainOld.endsWith(':')) candidates.push([plainOld.slice(0, -1), guess.replace(/:$/, '')]);
  for (const [o, g] of candidates) {
    if (o && tail.endsWith(o.toLowerCase())) {
      const start = before - close - o.length;
      // Keep what sits between the old text and the comment: a `}` and any
      // other comment. Only the old text and this comment go.
      const kept = src.slice(before - close, at);
      return { start: ls + start, end: ls + end, replacement: g + kept };
    }
  }
  // Else the old text can sit a little earlier, as in the heading
  // `Network & Disk Space tab<!-- … "Disk Space" … -->`: its last occurrence
  // after the start of the `{for}` part or the line, and after any earlier
  // comment. Then two edits: the old text, and the comment.
  const forTag = flat.lastIndexOf('{for ', before);
  const comment = flat.lastIndexOf('-->', before - 1);
  const from = Math.max(forTag === -1 ? 0 : forTag, comment === -1 ? 0 : comment + 3);
  const region = flat.slice(from, before).toLowerCase();
  for (const [o, g] of candidates) {
    const i = o ? region.lastIndexOf(o.toLowerCase()) : -1;
    if (i !== -1) {
      const start = from + i;
      const replacement = g + src.slice(start + o.length, at);
      return { start: ls + start, end: ls + end, replacement };
    }
  }
  return { error: `on line ${line}, the text before the comment is not "${old}"` };
}

/** `s` with curly quotes made straight, keeping its length. */
function plainQuotes(s) {
  return s.replace(/[“”„]/g, '"').replace(/[‘’‚]/g, "'");
}

if (typeof module !== 'undefined') {
  module.exports = { isWalkMode, lineRange, guessEdit };
}
