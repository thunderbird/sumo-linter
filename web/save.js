/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Pure logic for keeping the markup: autosave to localStorage, and saving to a
 * .wiki file. Kept out of app.js so it can be tested under plain Node, the same
 * split as fixes.js, gutter.js and copy.js.
 *
 * Both paths store the text exactly as it is, like the Copy button. Neither ever
 * fails silently: a save the author believes happened and did not loses work.
 */

/** The localStorage key. One draft per browser, not one per article. */
const DRAFT_KEY = 'sumo-lint:draft';

/**
 * `.wiki` opens in the SUMO mode of VS Code, Emacs and Vim, which all register
 * it. Emacs and Vim yield `.wiki` to another wiki mode that claims it first.
 */
const FILE_NAME = 'article.wiki';

/**
 * Save `text` as the draft; returns 'saved' or 'failed'. Never throws.
 *
 * An empty text removes the draft rather than storing '', so Clear leaves
 * nothing behind. `storage` is null where the browser blocks localStorage, and
 * `setItem` throws when the quota is full; both count as a failure.
 */
function saveDraft(storage, text) {
  try {
    if (!storage) return 'failed';
    if (text === '') storage.removeItem(DRAFT_KEY);
    else storage.setItem(DRAFT_KEY, text);
    return 'saved';
  } catch {
    return 'failed';
  }
}

/** The saved draft, or '' if there is none or storage is unreadable. */
function loadDraft(storage) {
  try {
    const text = storage ? storage.getItem(DRAFT_KEY) : null;
    return typeof text === 'string' ? text : '';
  } catch {
    return '';
  }
}

/**
 * Serialise writes to one file: at most one write runs at a time, and a text
 * that arrives during a write replaces any older one still waiting, so the file
 * ends with the latest text and no write is wasted on a version already gone.
 *
 * Without this, two overlapping writes to the same file handle can finish in
 * either order and leave the older text on disk.
 *
 * `write(text)` returns a promise. `onResult(state, error)` gets 'saved' or
 * 'failed' after each write. `push(text)` returns a promise that resolves once
 * the queue is empty.
 */
function fileWriter(write, onResult) {
  let busy = false;
  let waiting = false;
  let latest = '';
  let idle = Promise.resolve();

  async function drain() {
    busy = true;
    while (waiting) {
      const text = latest;
      waiting = false;
      try {
        await write(text);
        onResult('saved');
      } catch (e) {
        onResult('failed', e);
      }
    }
    busy = false;
  }

  return function push(text) {
    latest = text;
    waiting = true;
    if (!busy) idle = drain();
    return idle;
  };
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = { DRAFT_KEY, FILE_NAME, saveDraft, loadDraft, fileWriter };
}
