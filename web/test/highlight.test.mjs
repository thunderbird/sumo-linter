/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the editor's markup highlighting (#35): that it follows SUMO's own
// CodeMirror rules, quirks included, and that the highlighted copy has exactly
// the text of the textarea, or the colors drift away from the letters.
//
//   node web/test/highlight.test.mjs

import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
// CommonJS module: the default import is its `module.exports` object.
import highlight from '../highlight.js';

const { tokenize, highlightLines, highlightHtml, parseHighlight } = highlight;

let failed = 0;
let checks = 0;

function check(what, actual, expected) {
  checks += 1;
  try {
    assert.deepEqual(actual, expected);
  } catch {
    failed += 1;
    console.error(`FAIL ${what}\n  want ${JSON.stringify(expected)}\n  got  ${JSON.stringify(actual)}`);
  }
}

/** One line's pieces as [text, classes] pairs, for short expectations. */
const line = (src) => tokenize(src)[0].map((p) => [p.text, p.cls]);

const SYN = 'cm-variable cm-language';
const LINK = 'cm-markup cm-other cm-link';
const ITALIC = 'cm-markup cm-italic';
const BOLD = 'cm-markup cm-bold';
const COMMENT = 'cm-comment';

// --- the cases in Roland's two SUMO screenshots -----------------------------
check('template shorthand is a link', line('[[T:TBMore]]'), [['[[T:TBMore]]', LINK]]);
check('{for} with a condition and its close', line('{for tb123}dddd{/for}'), [
  ['{', SYN], ['for', 'cm-meta cm-tag cm-name'], [' ', null], ['tb123', ITALIC], ['}', SYN],
  ['dddd', null], ['{/for}', SYN],
]);
check('{/key} is plain, as on SUMO', line('{key}key{/key}'), [
  ['{', SYN], ['key', 'cm-meta cm-tag'], ['}', SYN], ['key{/key}', null],
]);
check('{button} has an italic argument', line('{button ok}'), [
  ['{', SYN], ['button', 'cm-meta cm-tag'], [' ok', ITALIC], ['}', SYN],
]);
check('<-- is not a comment', line('<--html comment-->'), [['<--html comment-->', null]]);
check('an external link', line('[https://example.com example]'), [['[https://example.com example]', LINK]]);
check('bold markers and bold text', line("the '''Appearance''' panel"), [
  ['the ', null], ["'''", SYN], ['Appearance', BOLD], ["'''", SYN], [' panel', null],
]);
check('italic markers and italic text', line("the ''kebab'' menu"), [
  ['the ', null], ["''", SYN], ['kebab', ITALIC], ["''", SYN], [' menu', null],
]);
check('__TOC__', line('__TOC__'), [['__TOC__', SYN]]);
check('an image link', line('[[Image:tb-140-appearances-panel]]'), [['[[Image:tb-140-appearances-panel]]', LINK]]);
check('a piped article link', line('([[Find what version|Thunderbird version]] 140'), [
  ['(', null], ['[[Find what version|Thunderbird version]]', LINK], [' 140', null],
]);
check('a heading line is bold', line('==Card view =='), [['==Card view ==', BOLD]]);
// SUMO's heading regex backtracks to `=…=`, so an asymmetric heading is bold too.
check('an asymmetric heading is bold too', line('==Card view ==='), [['==Card view ===', BOLD]]);
check('a heading with no closing run is not', line('=h1'), [['=h1', null]]);
check('list markers', line('** Click'), [['**', SYN], [' Click', null]]);
check('a list marker only at the start of a line', line('a * b'), [['a * b', null]]);
check('a leading space is a quote line', line(' preformatted'), [[' preformatted', 'cm-markup cm-quote']]);
check('{menu} text is italic', line('{menu Settings}'), [
  ['{', SYN], ['menu', 'cm-meta cm-tag'], [' Settings', ITALIC], ['}', SYN],
]);

// --- state that carries across lines ----------------------------------------
check('a comment spans lines', tokenize('a <!-- one\ntwo --> b').map((l) => l.map((p) => [p.text, p.cls])), [
  [['a ', null], ['<!-- one', COMMENT]],
  [['two -->', COMMENT], [' b', null]],
]);
check('<nowiki> content is comment-colored', line("<nowiki>'''x'''</nowiki>"), [
  ['<nowiki>', SYN], ["'''x'''", COMMENT], ['</nowiki>', SYN],
]);
check('<pre> spans lines', tokenize('<pre>\n[[x]]\n</pre>').map((l) => l.map((p) => p.cls)), [
  [SYN], [COMMENT], [SYN],
]);
check('{note} closes its tag', line('{note}Hi{/note}'), [
  ['{', SYN], ['note', 'cm-meta cm-tag cm-name'], ['}', SYN], ['Hi', null], ['{/note}', SYN],
]);

// --- the HTML -----------------------------------------------------------------
check('markup is escaped', highlightHtml('<b> & </b>'), '&lt;b&gt; &amp; &lt;/b&gt;\n');
check('one extra newline, for the empty last line', highlightHtml('a\n'), 'a\n\n');
check('spans carry the classes', highlightHtml('__TOC__'), `<span class="${SYN}">__TOC__</span>\n`);
check('a surrogate pair stays whole', tokenize('🐦')[0], [{ text: '🐦', cls: null }]);

// --- the switch ---------------------------------------------------------------
check('on by default', parseHighlight(null), true);
check('off when turned off', parseHighlight('off'), false);
check('on when turned on', parseHighlight('on'), true);

// --- every committed article: same text, and fast enough -------------------
function wikiFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...wikiFiles(p));
    else if (name.endsWith('.wiki')) out.push(p);
  }
  return out;
}
const root = new URL('../../', import.meta.url).pathname;
const files = [...wikiFiles(join(root, 'corpus')), ...wikiFiles(join(root, 'corpus-other'))];
check('the corpus is there', files.length > 800, true);

const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
let mismatched = [];
let biggest = '';
for (const f of files) {
  const src = readFileSync(f, 'utf8').replace(/\r\n?/g, '\n'); // as a textarea gives it
  if (src.length > biggest.length) biggest = src;
  const text = unescape(highlightHtml(src).replace(/<[^>]*>/g, ''));
  if (text !== `${src}\n`) mismatched.push(f);
}
check('every article keeps its exact text', mismatched, []);

// --- incremental highlighting equals a full pass ---------------------------
// Edits at random places in real articles, including ones that open or close
// a comment and so change the state of every later line.
let seed = 35;
const rand = (n) => {
  seed = (seed * 1103515245 + 12345) % 2147483648;
  return seed % n;
};
const INSERTS = ['x', '\n', '<!--', '-->', '{for tb140}', '}', "'''", '\n\n= H =\n', ''];
const wrong = [];
let edits = 0;
for (const f of files.filter((_, i) => i % 15 === 0)) {
  let text = readFileSync(f, 'utf8').replace(/\r\n?/g, '\n');
  let prev = highlightLines(text);
  for (let step = 0; step < 8; step++) {
    const at = rand(text.length + 1);
    const cut = rand(3) === 0 ? rand(40) : 0;
    text = text.slice(0, at) + INSERTS[rand(INSERTS.length)] + text.slice(at + cut);
    prev = highlightLines(text, prev);
    edits += 1;
    if (prev.html.join('\n') !== highlightLines(text).html.join('\n')) {
      wrong.push(`${f} step ${step}`);
      break;
    }
  }
}
check('incremental highlighting equals a full pass', wrong, []);
check('enough edits ran', edits > 400, true);

// The textarea is transparent while highlighting, so the copy is redrawn on
// every keystroke. Typing one letter in a 126 KB text must cost little.
const big = biggest.repeat(Math.max(1, Math.ceil(126000 / biggest.length)));
let t0 = performance.now();
const full = highlightLines(big);
const fullMs = performance.now() - t0;
const mid = big.indexOf('\n', big.length >> 1);
const typed = `${big.slice(0, mid)}x${big.slice(mid)}`;
t0 = performance.now();
const again = highlightLines(typed, full);
const typeMs = performance.now() - t0;
console.log(
  `highlight: ${big.length} characters, full pass ${fullMs.toFixed(1)} ms, `
  + `one keystroke ${typeMs.toFixed(2)} ms`,
);
check('one keystroke re-highlights one line', again.html.filter((h, i) => h !== full.html[i]).length, 1);
check('one keystroke in 126 KB takes under 5 ms', typeMs < 5, true);

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 35;
if (checks < expected) {
  console.error(`\nonly ${checks} highlight assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} highlight assertions failed`);
  process.exit(1);
}
console.log(`highlight: ${checks} assertions passed`);
