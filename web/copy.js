/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure logic for the Copy button, kept out of app.js so it can be tested under
 * plain Node, the same split as fixes.js and gutter.js.
 *
 * The button copies the textarea exactly as it is: no trim, no newline changes,
 * and no pending fixes applied. Fixing and house style are their own buttons, so
 * the text on the clipboard is always the text the last lint looked at.
 */

/** How long "Copied" or "Copy failed" shows before the label goes back. */
const COPY_RESET_MS = 2000;

/**
 * Write `text` to `clipboard` unchanged; resolves to 'copied' or 'failed'.
 *
 * Never rejects. A failure must reach the label, because an author who thinks
 * the copy worked pastes whatever was on the clipboard before into SUMO.
 * `clipboard` is missing outside a secure context, which counts as a failure.
 */
async function copyText(text, clipboard) {
  try {
    if (!clipboard || typeof clipboard.writeText !== 'function') return 'failed';
    await clipboard.writeText(text);
    return 'copied';
  } catch {
    return 'failed';
  }
}

/** The button label for a state: 'idle', 'copied' or 'failed'. */
function copyLabel(state) {
  if (state === 'copied') return 'Copied';
  if (state === 'failed') return 'Copy failed';
  return 'Copy';
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = { COPY_RESET_MS, copyText, copyLabel };
}
