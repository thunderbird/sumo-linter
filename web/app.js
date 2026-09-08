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

let wasm = null;

async function boot() {
  const status = document.getElementById('status');
  try {
    const res = await fetch(WASM_URL);
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

function run() {
  if (!wasm) return;
  const text = document.getElementById('src').value;
  const diags = call(wasm.lint, text);
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
    if (d.fix) {
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
    clearTimeout(t);
    t = setTimeout(run, 120);
  });
  document.getElementById('fixbtn').addEventListener('click', applyFixes);
  document.getElementById('stylebtn').addEventListener('click', applyStyle);
  document.getElementById('sample').addEventListener('click', () => {
    ta.value = [
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
    ].join('\n');
    run();
  });
  boot();
});
