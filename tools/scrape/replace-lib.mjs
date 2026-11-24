/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * The logic of replace.mjs (sumo-linter #62), with no browser and no I/O, so
 * that `node --test` covers it in CI.
 *
 * The issue holds two checklists:
 *
 *   ### Strings
 *
 *   - [ ] "Config Editor…" → "Advanced settings"
 *
 *   ### Articles
 *
 *   - [ ] config-editor
 *
 * Every string item applies, checked or not. An article item is done when it
 * is checked.
 */

const ITEM = /^(\s*)- \[( |x|X)\] (.*)$/;
const HEADING = /^#{1,6}\s+(.*?)\s*#*\s*$/;
const STRING = /^"(.*)" → "(.*)"\s*$/;
const NOTE = /^\s+- /;

/** The lines of the section under `### <name>`, as [index, line] pairs. */
function section(lines, name) {
  const out = [];
  let inside = false;
  lines.forEach((line, i) => {
    const h = line.match(HEADING);
    if (h) {
      inside = h[1].toLowerCase() === name.toLowerCase();
      return;
    }
    if (inside) out.push([i, line]);
  });
  return out;
}

/** The slug of an article item: the first word, or the text of a Markdown link. */
function slugOf(text) {
  const link = text.match(/^\[([^\]]+)\]\([^)]*\)/);
  const word = link ? link[1] : text.split(/\s+/)[0];
  return word.replace(/^`|`$/g, '');
}

/**
 * Read both checklists. Throws if either is missing or empty, or if a string
 * item cannot be read, because a half-read list would edit articles with only
 * some of the replacements.
 */
export function parseIssue(body) {
  const lines = body.split(/\r?\n/);
  const strings = [];
  for (const [i, line] of section(lines, 'Strings')) {
    const m = line.match(ITEM);
    if (!m || m[1]) continue;
    const s = m[3].trim().match(STRING);
    if (!s) throw new Error(`line ${i + 1}: a string item must be "old" → "new": ${line}`);
    const [, from, to] = s;
    if (!from) throw new Error(`line ${i + 1}: the old text is empty`);
    if (from.includes('\n') || to.includes('\n')) throw new Error(`line ${i + 1}: a string must be one line`);
    if (from === to) throw new Error(`line ${i + 1}: the old and the new text are the same`);
    if (strings.some((x) => x.from === from)) throw new Error(`line ${i + 1}: "${from}" is listed twice`);
    strings.push({ from, to });
  }
  const articles = [];
  for (const [i, line] of section(lines, 'Articles')) {
    const m = line.match(ITEM);
    if (!m || m[1]) continue;
    const slug = slugOf(m[3].trim());
    if (!/^[A-Za-z0-9._:%-]+$/.test(slug)) throw new Error(`line ${i + 1}: not a slug: ${slug}`);
    articles.push({ slug, checked: m[2] !== ' ', line: i });
  }
  if (strings.length === 0) throw new Error('the issue has no "### Strings" checklist');
  if (articles.length === 0) throw new Error('the issue has no "### Articles" checklist');
  return { strings, articles };
}

/**
 * Byte ranges that Kitsune does not parse as markup: HTML comments,
 * `<nowiki>` and `<pre>`. A replacement there would change text that a reader
 * never sees, or text that the author kept literal on purpose. An unclosed
 * opener runs to the end, as in the lexer.
 */
export function protectedRanges(src) {
  const out = [];
  const pairs = [
    ['<!--', '-->'],
    ['<nowiki>', '</nowiki>'],
    ['<pre>', '</pre>'],
  ];
  let i = 0;
  while (i < src.length) {
    let best = null;
    for (const [open, close] of pairs) {
      const at = src.indexOf(open, i);
      if (at !== -1 && (best === null || at < best.at)) best = { at, open, close };
    }
    if (!best) break;
    const end = src.indexOf(best.close, best.at + best.open.length);
    const to = end === -1 ? src.length : end + best.close.length;
    out.push([best.at, to]);
    i = to;
  }
  return out;
}

/** 1-based line of offset `at`. */
function lineAt(src, at) {
  let n = 1;
  for (let i = src.indexOf('\n'); i !== -1 && i < at; i = src.indexOf('\n', i + 1)) n++;
  return n;
}

/**
 * Where a match sits, if that can need a different edit: in a `[[…]]` link,
 * whose target is an article title, or in a `{for}` branch, which may hold
 * the text for another version on purpose.
 */
function contextAt(src, at, guarded) {
  const why = [];
  const lineStart = src.lastIndexOf('\n', at - 1) + 1;
  const before = src.slice(lineStart, at);
  const open = before.lastIndexOf('[[');
  if (open !== -1 && before.indexOf(']]', open) === -1) why.push('in a [[link]]');
  let depth = 0;
  const re = /\{for\b[^}]*\}|\{\/for\}/g;
  for (let m = re.exec(src); m && m.index < at; m = re.exec(src)) {
    if (guarded(m.index)) continue;
    depth += m[0] === '{/for}' ? -1 : 1;
    if (depth < 0) depth = 0;
  }
  if (depth > 0) why.push('in a {for} branch');
  return why;
}

/**
 * Apply every replacement in one pass, longest old text first at each
 * position, so a replacement never applies to the output of another and a
 * string never matches inside a longer listed one.
 *
 * Returns the new text, the count per string (in list order), and one change
 * per match with its line and any context to check.
 */
export function applyReplacements(src, strings) {
  const ranges = protectedRanges(src);
  const guarded = (at) => ranges.some(([a, b]) => at >= a && at < b);
  const order = [...strings].sort((a, b) => b.from.length - a.from.length);
  const counts = strings.map(() => 0);
  const changes = [];
  let out = '';
  let i = 0;
  let r = 0; // index of the next protected range
  while (i < src.length) {
    while (r < ranges.length && ranges[r][1] <= i) r++;
    if (r < ranges.length && ranges[r][0] <= i) {
      out += src.slice(i, ranges[r][1]);
      i = ranges[r][1];
      continue;
    }
    const limit = r < ranges.length ? ranges[r][0] : src.length;
    const hit = order.find((s) => i + s.from.length <= limit && src.startsWith(s.from, i));
    if (!hit) {
      out += src[i];
      i++;
      continue;
    }
    counts[strings.indexOf(hit)]++;
    changes.push({ line: lineAt(src, i), from: hit.from, to: hit.to, at: i, why: contextAt(src, i, guarded) });
    out += hit.to;
    i += hit.from.length;
  }
  return { text: out, counts, changes };
}

/**
 * One line per change, with some text around it, for the terminal. SUMO
 * paragraphs are one long line each, so whole lines would hide the change.
 */
export function describeChanges(src, changes, width = 40) {
  return changes.map((c) => {
    const lineStart = src.lastIndexOf('\n', c.at - 1) + 1;
    let lineEnd = src.indexOf('\n', c.at);
    if (lineEnd === -1) lineEnd = src.length;
    const left = src.slice(Math.max(lineStart, c.at - width), c.at);
    const right = src.slice(c.at + c.from.length, Math.min(lineEnd, c.at + c.from.length + width));
    const pre = c.at - width > lineStart ? '…' : '';
    const post = c.at + c.from.length + width < lineEnd ? '…' : '';
    const why = c.why.length ? `   (check: ${c.why.join(', ')})` : '';
    return `Line ${c.line}: ${pre}${left}[- ${c.from} -][+ ${c.to} +]${right}${post}${why}`;
  });
}

/**
 * Diagnostics in `after` that are not in `before`. The replacements keep
 * every line in place, so a diagnostic is the same if its line, code and
 * message are.
 */
export function newDiagnostics(before, after) {
  const key = (d) => `${d.line}\t${d.code}\t${d.message}`;
  const seen = new Map();
  for (const d of before) seen.set(key(d), (seen.get(key(d)) ?? 0) + 1);
  const out = [];
  for (const d of after) {
    const n = seen.get(key(d)) ?? 0;
    if (n > 0) seen.set(key(d), n - 1);
    else out.push(d);
  }
  return out;
}

/** The highest revision ID that a `/kb/<slug>/history` page links to. */
export function newestRevision(html, slug) {
  const esc = slug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`/kb/${esc}/revision/(\\d+)`, 'g');
  let best = 0;
  for (const m of html.matchAll(re)) best = Math.max(best, Number(m[1]));
  return best || null;
}

/**
 * Mark the article item for `slug` in `body`: check it if `check`, and add
 * `notes` as `  - Note:` lines after the item and its existing notes. Throws
 * if the item is not there, so a note is never lost silently.
 */
export function markArticle(body, slug, { check, notes }) {
  const lines = body.split('\n');
  const item = section(lines.map((l) => l.replace(/\r$/, '')), 'Articles').find(([, line]) => {
    const m = line.match(ITEM);
    return m && !m[1] && slugOf(m[3].trim()) === slug;
  });
  if (!item) throw new Error(`the issue has no article item for ${slug}`);
  let [i] = item;
  if (check) lines[i] = lines[i].replace(/- \[ \]/, '- [x]');
  let at = i + 1;
  while (at < lines.length && NOTE.test(lines[at])) at++;
  const cr = lines[i].endsWith('\r') ? '\r' : '';
  lines.splice(at, 0, ...notes.map((n) => `  - Note: ${n}${cr}`));
  return lines.join('\n');
}

/** `owner/repo#n`, an issue URL or an issue-comment URL → the `gh api` path. */
export function apiPath(ref) {
  let m = ref.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/issues\/\d+#issuecomment-(\d+)$/);
  if (m) return `repos/${m[1]}/${m[2]}/issues/comments/${m[3]}`;
  m = ref.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/issues\/(\d+)\/?$/);
  if (m) return `repos/${m[1]}/${m[2]}/issues/${m[3]}`;
  m = ref.match(/^([^/\s]+)\/([^#\s]+)#(\d+)$/);
  if (m) return `repos/${m[1]}/${m[2]}/issues/${m[3]}`;
  throw new Error(`not an issue or comment: ${ref}`);
}
