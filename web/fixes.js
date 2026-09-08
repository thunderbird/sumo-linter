/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure text arithmetic for the web app, kept out of app.js so it can be tested
 * under plain Node — the same split as `editors/vscode/src/link.js`.
 *
 * The linter speaks byte offsets, because that is what the Rust core spans are.
 * A JS string is UTF-16, so every edit has to be converted, and getting that
 * conversion wrong on a multi-byte character does not misplace a highlight by a
 * little — it splices bytes into the middle of a character and corrupts the
 * article.
 */

/** UTF-8 length of one code point. */
function utf8Len(cp) {
  if (cp < 0x80) return 1;
  if (cp < 0x800) return 2;
  if (cp < 0x10000) return 3;
  return 4;
}

/**
 * Map a UTF-8 byte offset to a UTF-16 index, so highlighting and edits line up.
 *
 * Walks code points, not code units: an earlier version indexed by code unit and
 * measured each surrogate half separately, which reads an emoji as 6 bytes
 * instead of 4 and puts everything after it in the wrong place.
 */
function byteToCharIndex(text, byteOffset) {
  let bytes = 0;
  let i = 0;
  while (i < text.length && bytes < byteOffset) {
    const cp = text.codePointAt(i);
    bytes += utf8Len(cp);
    i += cp > 0xffff ? 2 : 1;
  }
  return i;
}

/**
 * Whether a fix from the lint JSON carries enough to apply.
 *
 * GitHub Pages serves with `max-age=600`, so app.js and the `.wasm` are cached
 * independently and a returning visitor can get new JS against a ten-minute-old
 * module — measured on the live site, not hypothetical. That module describes its
 * fixes but reports no span, so the button must not be offered at all rather than
 * throwing when it is pressed.
 */
function isApplicable(fix) {
  return (
    !!fix &&
    typeof fix.replacement === 'string' &&
    Number.isInteger(fix.start) &&
    Number.isInteger(fix.end) &&
    fix.end >= fix.start
  );
}

/**
 * Apply one fix to `text`, returning the new text and the UTF-16 range the
 * replacement now occupies so the caller can show what changed.
 */
function applyFixToText(text, fix) {
  const start = byteToCharIndex(text, fix.start);
  const end = byteToCharIndex(text, fix.end);
  return {
    text: text.slice(0, start) + fix.replacement + text.slice(end),
    start,
    end: start + fix.replacement.length,
  };
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = { applyFixToText, byteToCharIndex, isApplicable, utf8Len };
}
