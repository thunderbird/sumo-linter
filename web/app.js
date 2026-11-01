/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Browser front-end for sumo-lint.
 *
 * Talks to the raw wasm32-unknown-unknown module directly — no wasm-bindgen, no
 * npm, no build step beyond `cargo build --target wasm32-unknown-unknown`. The
 * ABI is four exported functions; see crates/sumo-lint-wasm/src/lib.rs.
 *
 * The byte-offset arithmetic lives in fixes.js so it can be tested under plain
 * Node; everything here touches the DOM.
 *
 * Everything runs client-side. Nothing is uploaded, which matters because people
 * will paste unpublished draft articles in here.
 */

const WASM_URL = './sumo_lint_wasm.wasm';

/**
 * Walk mode (#31): walk.py serves this page with `?walk=1` and sends it each
 * checklist item's file and line. The text then comes from walk.py, so the
 * page keeps nothing in localStorage: the author's own draft stays as it was.
 */
const walkMode = typeof isWalkMode === 'function' && isWalkMode(location.search);
const walking = {
  file: null, // the .wiki file now in the text box
  line: null, // the line of the current item, marked in the gutter
  state: 'waiting', // 'waiting', 'on', 'stopped' or 'lost'
  edits: new Set(), // ids of the guesses already used, so none is made twice
};

let wasm = null;

async function boot() {
  const status = document.getElementById('status');
  try {
    // `no-cache` revalidates rather than trusting the cached copy. Pages serves
    // `max-age=600`, and app.js and the module are cached independently: without
    // this, a returning visitor within ten minutes of a deploy runs new JS against
    // an older module. Measured live — it presented as a Fix button that threw.
    const res = await fetch(WASM_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { instance } = await WebAssembly.instantiate(await res.arrayBuffer(), {});
    wasm = instance.exports;
    status.textContent = 'ready — linting runs entirely in your browser';
    status.className = 'ok';
    run();
  } catch (e) {
    status.textContent =
      `could not load the linter (${e.message}). ` +
      `Build it with: cargo build -p sumo-lint-wasm --release --target wasm32-unknown-unknown`;
    status.className = 'err';
  }
}

/** Copy a JS string into wasm memory as UTF-8; returns [ptr, len]. */
function writeString(s) {
  const bytes = new TextEncoder().encode(s);
  const ptr = wasm.alloc(bytes.length);
  new Uint8Array(wasm.memory.buffer, ptr, bytes.length).set(bytes);
  return [ptr, bytes.length];
}

/** Read a NUL-terminated UTF-8 string out of wasm memory. */
function readCString(ptr) {
  const mem = new Uint8Array(wasm.memory.buffer);
  let end = ptr;
  while (mem[end] !== 0) end++;
  return new TextDecoder().decode(mem.subarray(ptr, end));
}

function call(fn, text, ...extra) {
  const [ptr, len] = writeString(text);
  try {
    return JSON.parse(readCString(fn(ptr, len, ...extra)));
  } finally {
    wasm.dealloc(ptr, len);
  }
}

/**
 * Replace a UTF-16 range of the textarea, keeping its native undo stack.
 *
 * `execCommand` is deprecated but it is still the only way to edit a textarea
 * undoably: assigning `.value` discards the history, which matters most for the
 * needs-review fixes — accepting one is meant to be a decision you can take back
 * with Cmd+Z, exactly as in an editor. Falls back to assignment where it fails.
 */
function replaceRange(ta, start, end, text) {
  ta.focus();
  ta.setSelectionRange(start, end);
  let undoable = false;
  try {
    undoable =
      text === ''
        ? document.execCommand('delete')
        : document.execCommand('insertText', false, text);
  } catch {
    undoable = false;
  }
  if (!undoable) {
    ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
  }
  ta.setSelectionRange(start, start + text.length);
}

/**
 * Apply one diagnostic's fix, safe or not.
 *
 * `snapshot` is the text the offsets were measured against. Linting is debounced,
 * so a click can land after an edit and before the re-lint; splicing stale byte
 * offsets into edited text would corrupt it, so re-lint instead.
 */
function applyOne(fix, snapshot) {
  const ta = document.getElementById('src');
  if (ta.value !== snapshot) {
    run();
    return;
  }
  replaceRange(
    ta,
    byteToCharIndex(snapshot, fix.start),
    byteToCharIndex(snapshot, fix.end),
    fix.replacement,
  );
  run();
}

/**
 * Worst severity per line, from the most recent lint. Between an edit and the
 * debounced re-lint it can be stale; see drawGutter.
 */
let gutterMarks = [''];
let gutterFrame = 0;

/** Redraw the gutter once, on the next frame, however often this is called. */
function scheduleGutter() {
  if (!gutterFrame) gutterFrame = requestAnimationFrame(drawGutter);
}

/**
 * Number every line the linter counts, including lines the textarea wraps.
 *
 * Wrapping is why the numbers cannot simply be one per row: a SUMO paragraph is
 * one long source line, and a wrapped one would push every later number off its
 * line. So each line is laid out in a hidden mirror at the textarea's own content
 * width, and its number is given the height that line takes.
 */
function drawGutter() {
  gutterFrame = 0;
  const ta = document.getElementById('src');
  const gutter = document.getElementById('gutter');
  const mirror = document.getElementById('mirror');
  const text = ta.value;

  // If an edit added or removed lines since the last lint, the marks would sit
  // on the wrong lines until the re-lint, so show none. An edit within a line
  // keeps them, which stops them flickering on every keystroke.
  if (gutterMarks.length !== lineCount(text)) gutterMarks = lineSeverities(text, []);

  // Set the width first: it changes the textarea's width, and so the wrapping.
  const digits = Math.max(2, String(gutterMarks.length).length);
  ta.parentElement.style.setProperty('--gutter', `${digits}ch`);

  const heights = lineHeights(ta, mirror, text);

  gutter.replaceChildren(
    ...gutterMarks.map((mark, i) => {
      const n = document.createElement('div');
      n.textContent = String(i + 1);
      if (mark) n.className = mark;
      if (i + 1 === walking.line) n.classList.add('walk');
      n.style.height = `${heights[i]}px`;
      return n;
    }),
  );
  gutter.scrollTop = ta.scrollTop;
}

/** The height each line of `text` takes in the textarea, wrapping included. */
function lineHeights(ta, mirror, text) {
  const cs = getComputedStyle(ta);
  const width = ta.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  mirror.style.width = `${width}px`;
  mirror.replaceChildren(
    ...text.split('\n').map((line) => {
      const row = document.createElement('div');
      // An empty line still takes one row.
      row.textContent = line || ' ';
      return row;
    }),
  );
  const heights = Array.from(mirror.children, (row) => row.getBoundingClientRect().height);
  mirror.replaceChildren();
  return heights;
}

let copyTimer = 0;

/** Copy the textarea as it is, and say on the button whether that worked. */
async function copyMarkup() {
  const btn = document.getElementById('copybtn');
  const state = await copyText(document.getElementById('src').value, navigator.clipboard);
  btn.textContent = copyLabel(state);
  btn.className = state === 'failed' ? 'err' : '';
  clearTimeout(copyTimer);
  copyTimer = setTimeout(() => {
    btn.textContent = copyLabel('idle');
    btn.className = '';
  }, COPY_RESET_MS);
}

/** Nothing to copy, save or clear in an empty textarea. Works before the module loads. */
function updateButtons() {
  const empty = document.getElementById('src').value === '';
  for (const id of ['copybtn', 'savebtn', 'clearbtn']) document.getElementById(id).disabled = empty;
}

/** localStorage, or null where the browser blocks it: even reading it can throw. */
function draftStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Where the markup is kept, for the note beside the buttons. Every failure is
 * shown, because a save the author believes happened and did not loses work.
 */
const kept = {
  draft: 'saved', // 'saved' or 'failed', from the last autosave
  fileName: null, // Chrome and Edge: the file every change is written to
  file: 'saved', // 'saved' or 'failed', from the last write to that file
  writeFile: null, // fileWriter for that file, or null once a write fails
  downloaded: null, // Firefox and Safari: the name of a copy downloaded since the last change
};

function renderSaveNote() {
  const parts = [];
  const empty = document.getElementById('src').value === '';
  if (walkMode) parts.push(walkNote());
  else if (kept.draft === 'failed') parts.push('could not save in this browser');
  else if (!empty) parts.push('saved in this browser');
  if (kept.fileName) {
    parts.push(kept.file === 'failed'
      ? `could not write ${kept.fileName}: press Save to file again`
      : `saving to ${kept.fileName}`);
  }
  if (kept.downloaded) parts.push(`downloaded ${kept.downloaded}`);
  const note = document.getElementById('savenote');
  note.textContent = parts.join(' · ');
  note.className = kept.draft === 'failed' || kept.file === 'failed' ? 'err' : '';
}

/**
 * The last text the author knows is kept (#33): what walk.py loaded, what was
 * last saved to a file, or what Clear and the example put there. Autosave to
 * this browser does not count, because that copy is not the one pasted into
 * SUMO. Null until the page has read its first text.
 */
let knownText = null;

/** Show the pink dot when the text differs from the known text. */
function renderChanged() {
  const dot = document.getElementById('changed');
  if (!dot) return;
  const text = document.getElementById('src').value;
  dot.hidden = knownText === null || text === knownText;
}

/** Mark `text` as kept, for the dot. */
function markKnown(text) {
  knownText = text;
  renderChanged();
}

/** Autosave the text, and write it to the chosen file if there is one. */
function keep() {
  const text = document.getElementById('src').value;
  if (!walkMode) kept.draft = saveDraft(draftStorage(), text);
  kept.downloaded = null;
  showFileName();
  if (kept.writeFile) kept.writeFile(text);
  renderSaveNote();
}

/**
 * Stop writing to the chosen file. Clear and the example call this first:
 * otherwise autosave would overwrite the author's saved article with an empty
 * text box or with the example.
 */
/**
 * The name Save to file will use (#16): the typed one, else the first heading,
 * else `article.wiki`.
 */
function currentFileName() {
  const box = document.getElementById('filename');
  const typed = box ? box.value : '';
  if (walkMode && walking.file && typed.trim() === '') return editedName(walking.file);
  return fileName(typed, document.getElementById('src').value);
}

/**
 * Show the fallback name in the empty box, so the author sees a generic name
 * such as `Background.wiki` before saving and can type a better one.
 */
function showFileName() {
  const box = document.getElementById('filename');
  if (!box) return;
  box.placeholder = walkMode && walking.file
    ? editedName(walking.file)
    : fileName('', document.getElementById('src').value);
}

function forgetFile() {
  kept.writeFile = null;
  kept.fileName = null;
  kept.file = 'saved';
}

/**
 * Save to a .wiki file. Chrome and Edge choose a file once and then write every
 * change to it; elsewhere each click downloads a new copy.
 */
async function saveToFile() {
  if (typeof window.showSaveFilePicker !== 'function') {
    download(document.getElementById('src').value);
    return;
  }
  let handle;
  try {
    handle = await window.showSaveFilePicker({
      // Only names a new file: one already chosen keeps its name (#16).
      suggestedName: currentFileName(),
      types: [{ description: 'SUMO wiki markup', accept: { 'text/plain': ['.wiki'] } }],
    });
  } catch (e) {
    // Cancelling the dialog is a choice, not a failure. Anything else (for
    // example, a page in a cross-origin frame) falls back to a download.
    if (e.name !== 'AbortError') download(document.getElementById('src').value);
    return;
  }
  const writeFile = fileWriter(
    async (text) => {
      // A writable stream goes to a temporary file that replaces the real one
      // on close, so a failed write never leaves the article half-written.
      const stream = await handle.createWritable();
      await stream.write(text);
      await stream.close();
      if (kept.writeFile === writeFile) markKnown(text);
    },
    (state) => {
      if (kept.writeFile !== writeFile) return; // a file since forgotten
      kept.file = state;
      // A failed write usually means the permission is gone; retrying on every
      // keystroke would only fail again. Save to file asks again.
      if (state === 'failed') kept.writeFile = null;
      renderSaveNote();
    },
  );
  kept.writeFile = writeFile;
  kept.fileName = handle.name;
  kept.file = 'saved';
  kept.downloaded = null;
  // The current text, which may have changed while the dialog was open.
  writeFile(document.getElementById('src').value);
  renderSaveNote();
}

/** Download `text` as a .wiki file. Each call is a new file. */
function download(text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  const name = currentFileName();
  a.download = name;
  // Firefox ignores a click on a link that is not in the document.
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  markKnown(text);
  kept.downloaded = name;
  renderSaveNote();
}

/**
 * Replace the whole text, undoably, without writing it to the chosen file.
 * Undo brings the old text back and autosaves it again.
 */
function startOver(text) {
  forgetFile();
  // A different article, so the typed name no longer applies. Undo restores
  // the text but not the name, which falls back to the heading.
  const box = document.getElementById('filename');
  if (box) {
    box.value = '';
    if (!walkMode) saveDraft(draftStorage(), '', NAME_KEY);
  }
  const ta = document.getElementById('src');
  replaceRange(ta, 0, ta.value.length, text);
  markKnown(text);
  run();
}

/** Visible columns and the `{for}` platform, kept in this browser. */
let view = { preview: true, problems: true, os: null, version: null };

/** The latest monthly Thunderbird release: SUMO's default version (#29). */
let latest = typeof FALLBACK_LATEST_RELEASE === 'number' ? FALLBACK_LATEST_RELEASE : null;

/** Ask product-details for the latest release. On any failure, keep the fallback. */
async function loadLatestRelease() {
  if (typeof latestRelease !== 'function') return;
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 5000);
  try {
    const res = await fetch(RELEASES_URL, { signal: abort.signal });
    const n = res.ok ? latestRelease(await res.text()) : null;
    if (n) {
      latest = n;
      showVersionHint();
      renderPreview();
    }
  } catch {
    // Offline or blocked: the fallback release stays.
  } finally {
    clearTimeout(timer);
  }
}

/** The version box's placeholder names the release an empty box stands for. */
function showVersionHint() {
  const box = document.getElementById('forversion');
  if (box) box.placeholder = latest ? `latest (${latest})` : 'latest';
}

function saveView() {
  try {
    draftStorage()?.setItem(VIEW_KEY, JSON.stringify(view));
  } catch {
    // Storage full or blocked: the view still applies until the page closes.
  }
}

/** Show or hide the columns, and give the visible ones the width. */
function applyView() {
  const previewCol = document.getElementById('previewcol');
  const problemsCol = document.getElementById('problemscol');
  previewCol.hidden = !view.preview;
  problemsCol.hidden = !view.problems;
  const cols = 1 + view.preview + view.problems;
  document.querySelector('.grid').style.setProperty('--cols', String(cols));
  document.body.classList.toggle('wide', cols === 3);
  document.getElementById('showpreview').checked = view.preview;
  document.getElementById('showproblems').checked = view.problems;
  document.getElementById('foros').value = view.os ?? '';
  document.getElementById('forversion').value = view.version ?? '';
  showVersionHint();
  // The column widths changed, so the textarea wraps differently.
  scheduleGutter();
}

/** Render the preview, unless its column is hidden. */
function renderPreview() {
  const el = document.getElementById('preview');
  // An older cached page has no preview column, or no preview.js.
  if (!el || !view.preview || typeof renderWiki !== 'function') return;
  const platform = typeof platformFor === 'function'
    ? platformFor(view, latest)
    : { os: view.os, version: view.version };
  el.classList.toggle('show-all', platform.os == null && platform.version == null);
  el.innerHTML = renderWiki(document.getElementById('src').value, platform);
}

function run() {
  updateButtons();
  renderChanged();
  keep();
  renderPreview();
  if (!wasm) return;
  const text = document.getElementById('src').value;
  const diags = call(wasm.lint, text);
  gutterMarks = lineSeverities(text, diags);
  scheduleGutter();
  const list = document.getElementById('diags');
  const summary = document.getElementById('summary');

  // Everything rendered below refers to byte offsets in *this* text.
  const snapshot = text;
  const errors = diags.filter((d) => d.severity === 'error').length;
  const warnings = diags.length - errors;
  const fixable = diags.filter((d) => d.fix && d.fix.safe).length;

  summary.textContent = text.trim()
    ? `${errors} error${errors === 1 ? '' : 's'}, ${warnings} warning${warnings === 1 ? '' : 's'}`
    : 'paste some wiki markup to begin';
  summary.className = errors ? 'err' : diags.length ? 'warn' : 'ok';

  document.getElementById('fixbtn').disabled = fixable === 0;
  document.getElementById('fixbtn').textContent =
    fixable > 0 ? `Apply ${fixable} safe fix${fixable === 1 ? '' : 'es'}` : 'No safe fixes';

  list.innerHTML = '';
  if (!diags.length) {
    if (text.trim()) {
      const li = document.createElement('li');
      li.className = 'clean';
      li.textContent = 'No problems found.';
      list.append(li);
    }
    return;
  }

  for (const d of diags) {
    const li = document.createElement('li');
    li.className = d.severity;

    const loc = document.createElement('button');
    loc.className = 'loc';
    loc.textContent = `${d.line}:${d.column}`;
    loc.title = 'jump to this position';
    loc.addEventListener('click', () => {
      const ta = document.getElementById('src');
      ta.focus();
      ta.setSelectionRange(
        byteToCharIndex(ta.value, d.start),
        byteToCharIndex(ta.value, d.end),
      );
    });

    const code = document.createElement('code');
    code.textContent = d.code;

    const msg = document.createElement('span');
    msg.textContent = d.message;

    li.append(loc, code, msg);
    if (d.fix && !isApplicable(d.fix)) {
      // An older module than this page: describe the repair, offer no button.
      const tag = document.createElement('em');
      tag.className = 'wide';
      tag.textContent = d.fix.safe
        ? `fix: ${d.fix.description}`
        : `fix needs review: ${d.fix.description}`;
      li.append(tag);
    } else if (d.fix) {
      // Both kinds get a button, on the same reasoning as the LSP quick fixes:
      // clicking one is a deliberate, undoable choice, unlike `--fix` rewriting
      // files unattended. The unsafe ones say so rather than being hidden.
      const row = document.createElement('div');
      row.className = 'fixrow';

      const apply = document.createElement('button');
      apply.type = 'button';
      apply.className = d.fix.safe ? 'fix' : 'fix review';
      apply.textContent = d.fix.safe ? 'Fix' : 'Fix (needs review)';
      apply.title = d.fix.safe
        ? `Apply: ${d.fix.description}`
        : `Apply, then check it: ${d.fix.description}. The intended markup is a `
          + `guess here, so this may not be the repair you want.`;
      apply.addEventListener('click', () => applyOne(d.fix, snapshot));

      const tag = document.createElement('em');
      tag.textContent = d.fix.description;

      row.append(apply, tag);
      li.append(row);
    }
    list.append(li);
  }
}

/** The walk's part of the note beside the buttons. */
function walkNote() {
  if (walking.state === 'stopped') return 'walk.py stopped: nothing here is saved unless you use Save to file';
  if (walking.state === 'lost') return 'walk.py is not running';
  if (!walking.file) return 'waiting for walk.py';
  return walking.line ? `walk.py: ${walking.file}, line ${walking.line}` : `walk.py: ${walking.file}`;
}

/**
 * Go to one item: load its file if it is a different one, then select its
 * line and scroll it into view.
 */
async function walkTo(t) {
  const ta = document.getElementById('src');
  if (t.file && t.file !== walking.file) {
    let text;
    try {
      const res = await fetch(`/walk/file/${encodeURIComponent(t.file)}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      text = await res.text();
    } catch {
      walking.state = 'lost';
      renderSaveNote();
      return;
    }
    // Set first, so the name box shows `…-edited.wiki` at once. startOver
    // stops writing to a file saved from the previous article.
    walking.file = t.file;
    startOver(text);
  }
  walking.line = t.line;
  scheduleGutter();
  renderSaveNote();
  let range = t.line ? lineRange(ta.value, t.line, t.find) : null;
  if (t.edit && t.line) range = useGuess(t) || range;
  if (!range) return;
  ta.focus({ preventScroll: true });
  ta.setSelectionRange(range[0], range[1]);
  // A selection alone does not scroll a textarea in every browser, so put the
  // line a third of the way down, measured as the gutter measures it.
  const heights = lineHeights(ta, document.getElementById('mirror'), ta.value);
  const top = heights.slice(0, t.line - 1).reduce((a, b) => a + b, 0);
  ta.scrollTop = Math.max(0, top + parseFloat(getComputedStyle(ta).paddingTop) - ta.clientHeight / 3);
  document.getElementById('gutter').scrollTop = ta.scrollTop;
  ta.closest('.editor').scrollIntoView({ block: 'nearest' });
}

/**
 * Use the guess that walk.py sent (#34), undoably, and tell walk.py whether
 * that worked: it checks the item only after a success. Returns the range of
 * the new text, or null.
 */
function useGuess(t) {
  const { id, old, guess } = t.edit;
  if (walking.edits.has(id)) return null;
  walking.edits.add(id);
  const ta = document.getElementById('src');
  const edit = guessEdit(ta.value, t.line, old, guess);
  let range = null;
  if (!edit.error) {
    replaceRange(ta, edit.start, edit.end, edit.replacement);
    range = [edit.start, edit.start + edit.replacement.length];
    run();
  }
  const answer = { id, ok: !edit.error, message: edit.error ? `${edit.error}.` : '' };
  fetch('/walk/result', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(answer),
  }).catch(() => {
    // walk.py stopped. It saves nothing without this answer.
  });
  return range;
}

/** Listen to walk.py. Items are handled one at a time, in order. */
function startWalk() {
  let queue = Promise.resolve();
  const events = new EventSource('/walk/events');
  events.onmessage = (e) => {
    const t = JSON.parse(e.data);
    walking.state = 'on';
    queue = queue.then(() => walkTo(t));
  };
  events.addEventListener('stop', () => {
    events.close();
    walking.state = 'stopped';
    walking.line = null;
    scheduleGutter();
    renderSaveNote();
  });
  // EventSource tries again by itself, so a lost connection can come back.
  events.onerror = () => {
    if (walking.state === 'stopped') return;
    walking.state = 'lost';
    renderSaveNote();
  };
  events.onopen = () => {
    if (walking.state === 'lost') walking.state = walking.file ? 'on' : 'waiting';
    renderSaveNote();
  };
}

/**
 * Apply phase-2 house style.
 *
 * Passing 0 selects per-article heading normalisation, so an article that is
 * already internally consistent comes back unchanged and the button reports as
 * much rather than silently doing nothing.
 */
function applyStyle() {
  const ta = document.getElementById('src');
  const result = call(wasm.style, ta.value, 0);
  const note = document.getElementById('stylenote');
  if (result.changed) {
    replaceRange(ta, 0, ta.value.length, result.text);
    note.textContent = 'house style applied';
    run();
  } else {
    note.textContent = 'already consistent — nothing to change';
  }
}

function applyFixes() {
  const ta = document.getElementById('src');
  const result = call(wasm.fix, ta.value, 0);
  if (result.applied > 0) {
    replaceRange(ta, 0, ta.value.length, result.text);
    run();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const ta = document.getElementById('src');
  // Debounced so typing in a 15 KB article stays responsive.
  let t = null;
  ta.addEventListener('input', () => {
    updateButtons();
    renderChanged();
    scheduleGutter();
    clearTimeout(t);
    t = setTimeout(run, 120);
  });
  ta.addEventListener('scroll', () => {
    document.getElementById('gutter').scrollTop = ta.scrollTop;
  });
  // Resizing the window or dragging the textarea's handle changes the wrapping.
  new ResizeObserver(scheduleGutter).observe(ta);
  document.getElementById('fixbtn').addEventListener('click', applyFixes);
  document.getElementById('stylebtn').addEventListener('click', applyStyle);
  document.getElementById('copybtn').addEventListener('click', copyMarkup);
  document.getElementById('savebtn').addEventListener('click', saveToFile);
  document.getElementById('clearbtn').addEventListener('click', () => {
    walking.file = null; // the next item loads its file again
    startOver('');
  });
  // Typing is debounced, so a tab closed within that window has not autosaved.
  // In walk mode the text comes from walk.py, and the stored draft and name
  // are the author's own work, so they are neither read nor replaced.
  if (!walkMode) {
    window.addEventListener('pagehide', () => saveDraft(draftStorage(), ta.value));
    // The browser may have restored the text itself on reload; keep that if so.
    if (ta.value === '') ta.value = loadDraft(draftStorage());
  }
  const nameBox = document.getElementById('filename');
  if (nameBox && !walkMode) {
    if (nameBox.value === '') nameBox.value = loadDraft(draftStorage(), NAME_KEY);
    nameBox.addEventListener('input', () => {
      saveDraft(draftStorage(), nameBox.value, NAME_KEY);
    });
  }
  // In walk mode the first file from walk.py sets the known text instead.
  if (!walkMode) markKnown(ta.value);
  showFileName();
  updateButtons();
  renderSaveNote();
  if (typeof parseView === 'function' && document.getElementById('previewcol')) {
    let saved = null;
    try {
      saved = draftStorage()?.getItem(VIEW_KEY) ?? null;
    } catch {
      saved = null;
    }
    view = parseView(saved);
    applyView();
    const changeView = (update) => {
      update();
      saveView();
      applyView();
      renderPreview();
    };
    document.getElementById('showpreview').addEventListener('change', (e) => {
      changeView(() => { view.preview = e.target.checked; });
    });
    document.getElementById('showproblems').addEventListener('change', (e) => {
      changeView(() => { view.problems = e.target.checked; });
    });
    document.getElementById('foros').addEventListener('change', (e) => {
      changeView(() => { view.os = e.target.value || null; });
    });
    document.getElementById('forversion').addEventListener('input', (e) => {
      // Not applyView: rewriting the field while the author types in it
      // would fight the cursor.
      // Guarded: Pages caches app.js and preview.js separately, so for a
      // while after a deploy this can run beside the previous preview.js.
      if (typeof parseVersionInput === 'function') {
        view.version = parseVersionInput(e.target.value);
      } else {
        const n = Number(e.target.value);
        view.version = e.target.value !== '' && Number.isInteger(n) && n > 0 ? n : null;
      }
      saveView();
      renderPreview();
    });
  }
  renderPreview();
  loadLatestRelease();
  document.getElementById('sample').addEventListener('click', () => {
    // Undoable, because the example replaces whatever was there.
    walking.file = null;
    startOver([
      '= Example article =',
      '',
      '==Asymmetric heading ===',
      '',
      "{for win}This has an unclosed platform block.",
      '',
      "* '''Authentication method: '''OAuth2'''",
      '* [[Image:screenshot.png|width=300|bogus=7]]',
      '* see [label](http://example.com) and **bold**',
      '',
      '{note}A note that never closes.',
    ].join('\n'));
  });
  if (walkMode) startWalk();
  boot();
});
