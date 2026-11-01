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

/** The localStorage key for the file name the author typed (#16). */
const NAME_KEY = 'sumo-lint:filename';

/** The longest name, in code points, before `.wiki` is added. */
const NAME_LIMIT = 80;

/**
 * The name to save `text` under (#16): the name the author typed, else the
 * first h1, else the first h2, else `article.wiki`.
 *
 * The heading is only a fallback because it is a section heading, not the
 * article title: SUMO keeps the title outside the markup, so an article can
 * give `Background.wiki`. The text box shows this name as its placeholder, so
 * the author sees it before saving and types a better one when needed.
 */
function fileName(typed, text) {
  const own = safeName(String(typed ?? '').replace(/\.wiki\s*$/i, ''));
  if (own) return `${own}.wiki`;
  const heading = firstHeading(text, 1) || firstHeading(text, 2);
  return heading ? `${heading}.wiki` : FILE_NAME;
}

/**
 * The name Save to file suggests in walk mode (#31): the loaded file's name
 * with `-edited` before `.wiki`. A different name means that the saved copy
 * can never replace the proposal that walk.py serves, even in its folder.
 */
function editedName(file) {
  const base = safeName(String(file ?? '').replace(/\.wiki\s*$/i, ''));
  return base ? `${base}-edited.wiki` : FILE_NAME;
}

/**
 * The visible text of the first heading of `level`, made safe as a file name,
 * or '' if there is none. As in preview.js, the level is the shorter of the two
 * `=` runs, and a line with no closing run is not a heading. A heading whose
 * text is all markup (an image, say) gives nothing, and the next one is tried.
 * Comments are removed first, because a commented-out heading is not shown.
 */
function firstHeading(text, level) {
  const source = String(text ?? '').replace(/<!--[\s\S]*?(?:-->|$)/g, '');
  for (const line of source.split('\n')) {
    const m = /^(=+)(.*?)(=+)[ \t\r]*$/.exec(line);
    if (!m || m[2].trim() === '') continue;
    const n = Math.min(m[1].length, m[3].length);
    if (n !== level) continue;
    // The extra `=` of the longer run is heading text, as on SUMO.
    const inner = m[1].slice(n) + m[2] + m[3].slice(n);
    const name = safeName(visibleText(inner));
    if (name) return name;
  }
  return '';
}

/**
 * The text a reader sees in a heading. Of several `{for}` branches only the
 * first is kept (decided in #16), so `{for not tb31}A{/for}{for tb31}B{/for}`
 * gives `A`, not `AB`.
 */
function visibleText(s) {
  let branches = 0;
  return s
    .replace(/\{for [^}]*\}([\s\S]*?)\{\/for\}/g, (_, body) => (branches++ ? '' : body))
    .replace(/\{\/?for\b[^}]*\}/g, '') // an unclosed or stray tag
    .replace(/\[\[(?:Image|Video|Template|Include|UI):[^\]]*\]\]/gi, '')
    .replace(/\[\[[^\]|]*\|([^\]]*)\]\]/g, '$1')
    .replace(/\[\[([^\]]*)\]\]/g, '$1')
    .replace(/\[[a-z]+:\S+\s+([^\]]*)\]/gi, '$1')
    .replace(/\[[a-z]+:\S+\]/gi, '')
    .replace(/\{[a-z]+ ([^}]*)\}/gi, '$1') // `{menu Tools}`, `{key Ctrl}`
    .replace(/\{\/?[a-z]+\}/gi, '')
    .replace(/'{2,}/g, '')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)));
}

/**
 * `s` as a file name: no character any of Windows, macOS or Linux rejects,
 * space runs collapsed, at most NAME_LIMIT code points, never cutting a
 * surrogate pair. Leading and trailing dots go too: a leading one hides the
 * file on macOS and Linux, and Windows drops a trailing one.
 */
function safeName(s) {
  const clean = (t) => t.replace(/\s+/g, ' ').replace(/^[ .]+|[ .]+$/g, '');
  // eslint-disable-next-line no-control-regex
  const legal = clean(s.replace(/[\/\\:*?"<>|\u0000-\u001f\u007f]/g, ' '));
  return clean(Array.from(legal).slice(0, NAME_LIMIT).join(''));
}

/**
 * Save `text` as the draft; returns 'saved' or 'failed'. Never throws.
 *
 * An empty text removes the draft rather than storing '', so Clear leaves
 * nothing behind. `storage` is null where the browser blocks localStorage, and
 * `setItem` throws when the quota is full; both count as a failure.
 */
function saveDraft(storage, text, key = DRAFT_KEY) {
  try {
    if (!storage) return 'failed';
    if (text === '') storage.removeItem(key);
    else storage.setItem(key, text);
    return 'saved';
  } catch {
    return 'failed';
  }
}

/**
 * The saved draft, or '' if there is none or storage is unreadable. With
 * NAME_KEY, both functions keep the typed file name instead.
 */
function loadDraft(storage, key = DRAFT_KEY) {
  try {
    const text = storage ? storage.getItem(key) : null;
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
  module.exports = {
    DRAFT_KEY, FILE_NAME, NAME_KEY, NAME_LIMIT,
    fileName, editedName, saveDraft, loadDraft, fileWriter,
  };
}
