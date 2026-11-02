/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// The reference for markup highlighting in every editor (#35, #36, #37).
//
// web/highlight.js runs SUMO's own CodeMirror rules. Each editor port must
// give every character the same class, so its test writes one class letter per
// character, and this script compares that with web/highlight.js:
//
//   node editors/highlight-check.mjs DUMPDIR [MIN_FILES]
//
// Each file in DUMPDIR is a dump of one article: its first line is the
// article's path from the repository root, and each further line holds the
// letters for one line of the article. The letters are:
//
//   .  plain            S  syntax (delimiters, tag names, list markers)
//   L  link             B  bold (bold text and headings)
//   I  italic           C  comment (and <nowiki>, <code>, <pre> content)
//   Q  preformatted     U  underline           X  strikethrough
//
// Also importable: `classLines(text)` gives the expected letters.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import highlight from '../web/highlight.js';

const root = fileURLToPath(new URL('..', import.meta.url));

/** The letter for a CodeMirror class list, as web/highlight.js gives it. */
function letterOf(cls) {
  if (!cls) return '.';
  const c = cls.split(' ');
  if (c.includes('cm-quote')) return 'Q';
  if (c.includes('cm-comment')) return 'C';
  if (c.includes('cm-link')) return 'L';
  if (c.includes('cm-variable') || c.includes('cm-tag')) return 'S';
  if (c.includes('cm-bold')) return 'B';
  if (c.includes('cm-italic')) return 'I';
  if (c.includes('cm-underline')) return 'U';
  if (c.includes('cm-strikethrough')) return 'X';
  throw new Error(`no letter for ${cls}`);
}

/**
 * One string of letters per line of `text`, one letter per UTF-16 code unit,
 * which is how VS Code counts columns. The editor tests that count characters
 * instead give a character outside the BMP one letter; compare with `perChar`.
 */
export function classLines(text, { perChar = false } = {}) {
  return highlight.tokenize(text).map((pieces) => pieces
    .map(({ text: t, cls }) => letterOf(cls).repeat(perChar ? [...t].length : t.length))
    .join(''));
}

/** The committed articles: every `.wiki` file in corpus/ and corpus-other/. */
export function corpusFiles() {
  const out = [];
  const walk = (dir) => {
    for (const e of readdirSync(join(root, dir), { withFileTypes: true })) {
      const p = `${dir}/${e.name}`;
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.wiki')) out.push(p);
    }
  };
  walk('corpus');
  walk('corpus-other');
  return out.sort();
}

/** The article as an editor holds it: CRLF and lone CR become LF. */
export function readArticle(path) {
  return readFileSync(join(root, path), 'utf8').replace(/\r\n?/g, '\n');
}

/**
 * Compare `got` (letters per line) with the reference for `path`. Returns null
 * or a description of the first difference.
 */
export function firstDifference(path, got, options) {
  const text = readArticle(path);
  const want = classLines(text, options);
  const lines = text.split('\n');
  // A file ending in a newline has an empty last line that an editor may not
  // report. It holds no characters, so it cannot differ.
  while (got.length < want.length && want[got.length] === '') got = [...got, ''];
  for (let i = 0; i < Math.max(want.length, got.length); i++) {
    if (want[i] === got[i]) continue;
    const w = want[i] ?? '(no line)';
    const g = got[i] ?? '(no line)';
    let col = 0;
    while (col < w.length && w[col] === g[col]) col++;
    const from = Math.max(0, col - 30);
    const chars = options?.perChar ? [...(lines[i] ?? '')] : (lines[i] ?? '').split('');
    return `${path} line ${i + 1} column ${col + 1}\n`
      + `  text ${JSON.stringify(chars.slice(from, col + 30).join(''))}\n`
      + `  want ${w.slice(from, col + 30)}\n`
      + `  got  ${g.slice(from, col + 30)}`;
  }
  return null;
}

// Run as a script: check a directory of dumps.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [dir, min = '1'] = process.argv.slice(2);
  if (!dir) {
    console.error('usage: node editors/highlight-check.mjs DUMPDIR [MIN_FILES]');
    process.exit(2);
  }
  const dumps = readdirSync(dir).sort();
  const problems = [];
  for (const name of dumps) {
    const [path, ...got] = readFileSync(join(dir, name), 'utf8').replace(/\n$/, '').split('\n');
    const diff = firstDifference(path, got, { perChar: true });
    if (diff) problems.push(diff);
  }
  for (const p of problems.slice(0, 10)) console.error(`FAIL ${p}`);
  if (problems.length > 10) console.error(`… and ${problems.length - 10} more`);
  if (dumps.length < Number(min)) {
    console.error(`only ${dumps.length} articles were dumped, expected at least ${min}`);
    process.exit(1);
  }
  if (problems.length) {
    console.error(`${problems.length} of ${dumps.length} articles highlight differently from SUMO's rules`);
    process.exit(1);
  }
  console.log(`highlight: ${dumps.length} articles match SUMO's rules`);
}
