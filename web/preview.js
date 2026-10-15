/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Renders SUMO wiki markup to HTML for the web app's preview (#14).
 *
 * Pure, so it is tested under plain Node, the same split as fixes.js. It needs
 * no WASM: the preview works before the linter module loads.
 *
 * This approximates Kitsune's output, it is not a copy of it. Templates,
 * images and videos become labelled placeholders, because the page cannot
 * fetch from SUMO (login and CORS) and a template resolves by title.
 *
 * The output goes into innerHTML, and people paste drafts and markup from
 * other people, so nothing the author typed reaches the output unescaped:
 * raw HTML tags are kept only from ALLOWED_TAGS and lose every attribute, and
 * a link keeps only an http, https, ftp or mailto target.
 */

/** Raw HTML tags kept in the preview. Any other tag shows as literal text, as
 *  Kitsune does with the corpus's `<account name>` placeholders. */
const ALLOWED_TAGS = new Set([
  'abbr', 'b', 'big', 'blockquote', 'br', 'cite', 'code', 'dd', 'del', 'div', 'dl', 'dt',
  'em', 'hr', 'i', 'ins', 'kbd', 'li', 'mark', 'ol', 'p', 's', 'samp', 'small', 'span',
  'strike', 'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'tt',
  'u', 'ul', 'var',
]);
const VOID_TAGS = new Set(['br', 'hr']);

/** `{for}` operating systems, as in the `how-to-use-for` article. `win`
 *  matches every Windows version. */
const OS_NAMES = ['win', 'winxp', 'win7', 'win8', 'win10', 'win11', 'mac', 'linux'];

// Private-use characters mark the regions taken out before parsing. Any in
// the input are removed first, so the author cannot forge one.
const STASH_OPEN = '';
const STASH_CLOSE = '';
const COMMENT = '';
const TOC = '';

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Escape for an attribute value, dropping any stashed region. */
function attr(s) {
  return esc(s.replace(/\d+/g, '').replace(/[-]/g, ''));
}

/**
 * Whether `{for cond}` content is visible on `platform`.
 *
 * `platform` is `{ os, version }`; a null field means "any", which matches
 * every condition of its kind. From `how-to-use-for`: content is shown if it
 * has no OS condition or one true OS condition, and no version condition or
 * one true version condition. `tbN` is version N or newer, `=tbN` only N, and
 * `not` negates. Firefox conditions (`fxN`, `mN`) mean nothing in a
 * Thunderbird article, so they are ignored; SW012 reports them.
 */
function forMatches(cond, platform) {
  let osSeen = false;
  let osTrue = false;
  let verSeen = false;
  let verTrue = false;
  for (const raw of cond.split(',')) {
    let c = raw.trim().toLowerCase();
    if (!c) continue;
    let negate = false;
    const not = /^not\s+/.exec(c);
    if (not) {
      negate = true;
      c = c.slice(not[0].length);
    }
    if (OS_NAMES.includes(c)) {
      osSeen = true;
      const os = platform.os;
      const truth = os == null || (c === 'win' ? os.startsWith('win') : os === c);
      if (os == null || truth !== negate) osTrue = true;
      continue;
    }
    const m = /^(=?)tb(\d+)$/.exec(c);
    if (m) {
      verSeen = true;
      const v = platform.version;
      const n = Number(m[2]);
      const truth = m[1] ? v === n : v >= n;
      if (v == null || truth !== negate) verTrue = true;
    }
  }
  return (!osSeen || osTrue) && (!verSeen || verTrue);
}

/** Kitsune's heading id: `w_` and the heading text as a slug. */
function slugify(text) {
  return 'w_' + text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .trim()
    .replace(/[\s_]+/g, '-');
}

/** The text of rendered inline HTML, for heading ids and the table of contents. */
function plainText(html) {
  return html
    .replace(/<[^>]*>/g, '')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&');
}

/**
 * Render `source` to HTML.
 *
 * `platform` chooses which `{for}` content is visible; see forMatches. With
 * both fields null every branch is visible, and app.js labels each one.
 */
function renderWiki(source, platform = { os: null, version: null }) {
  const stash = [];
  const put = (html) => `${STASH_OPEN}${stash.push(html) - 1}${STASH_CLOSE}`;

  // Regions that are not interpreted, in one left-to-right pass so that a
  // comment inside <nowiki> stays literal and the other way round. A comment
  // leaves a marker until the end, because `{<!-- -->key}` is the documented
  // way to show a macro without running it.
  let text = source
    .replace(/\r\n?/g, '\n')
    .replace(/[-]/g, '')
    .replace(
      /<!--[\s\S]*?(?:-->|$)|<nowiki>([\s\S]*?)<\/nowiki>|<pre>([\s\S]*?)<\/pre>/gi,
      (whole, nowiki, pre) => {
        if (nowiki !== undefined) return put(esc(nowiki));
        if (pre !== undefined) return put(`<pre>${esc(pre.replace(/<\/?nowiki>/gi, ''))}</pre>`);
        return COMMENT;
      },
    );

  const state = { platform, headings: [], ids: new Set(), forStack: [], put };
  // A line that held only a comment is not there at all, so it neither ends a
  // list nor starts a paragraph.
  const lines = text.split('\n').filter((l) => !(l.includes(COMMENT) && l.replace(/[\s]/g, '') === ''));
  let html = renderBlocks(lines, state);

  if (html.includes(TOC)) html = html.split(TOC).join(tocHtml(state.headings));
  return html.replace(/(\d+)/g, (_, n) => stash[Number(n)]).replace(//g, '');
}

/** A nested list of the visible headings, for `__TOC__`. */
function tocHtml(headings) {
  if (!headings.length) return '';
  let out = '<nav class="toc">';
  const stack = [];
  for (const h of headings) {
    while (stack.length && stack[stack.length - 1] > h.level) {
      out += '</li></ul>';
      stack.pop();
    }
    if (stack.length && stack[stack.length - 1] === h.level) out += '</li>';
    else {
      out += '<ul>';
      stack.push(h.level);
    }
    out += `<li><a href="#${attr(h.id)}">${h.html}</a>`;
  }
  out += '</li></ul>'.repeat(stack.length);
  return out + '</nav>';
}

const LIST_OPEN = { '*': '<ul><li>', '#': '<ol><li>', ';': '<dl><dt>', ':': '<dl><dd>' };
const LIST_CLOSE = { '*': '</li></ul>', '#': '</li></ol>', ';': '</dt></dl>', ':': '</dd></dl>' };
const ITEM_OPEN = { '*': '<li>', '#': '<li>', ';': '<dt>', ':': '<dd>' };
const ITEM_CLOSE = { '*': '</li>', '#': '</li>', ';': '</dt>', ':': '</dd>' };
const sameList = (a, b) => a === b || (/[;:]/.test(a) && /[;:]/.test(b));

const BLOCK_OPENER = /^\s*\{(note|warning|for)((?:\s[^}]*)?)\}/;
const BLOCK_CLOSER = /\{\/(note|warning|for)\}\s*$/;

/** Render lines to block HTML. Table cells call this again for their content. */
function renderBlocks(lines, state) {
  const out = [];
  let para = [];
  let pre = [];
  let listPrefix = '';
  let pendingSummary = false;

  const flushPara = () => {
    if (para.length) out.push(`<p>${para.map((l) => inline(l, state)).join('\n')}</p>`);
    para = [];
  };
  const flushPre = () => {
    if (pre.length) out.push(`<pre>${pre.map(esc).join('\n')}</pre>`);
    pre = [];
  };
  const closeLists = () => {
    for (let k = listPrefix.length - 1; k >= 0; k--) out.push(LIST_CLOSE[listPrefix[k]]);
    listPrefix = '';
  };
  const flush = () => {
    flushPara();
    flushPre();
    closeLists();
  };
  // SUMO uses the heading that follows `[[UI:details_start]]` as the summary.
  const summary = (inner) => {
    out.push(`<summary>${inner}</summary>`);
    pendingSummary = false;
  };

  const openBlock = (kind, cond) => {
    flush();
    if (kind === 'for') out.push(forOpen('div', cond, state));
    else out.push(`<div class="${kind}">`);
  };
  const closeBlock = (kind) => {
    flush();
    if (kind === 'for') state.forStack.pop();
    out.push('</div>');
  };

  for (let n = 0; n < lines.length; n++) {
    let line = lines[n];

    if (/^\s*\{\|/.test(line)) {
      flush();
      if (pendingSummary) summary('Details');
      let depth = 0;
      const table = [];
      for (; n < lines.length; n++) {
        const t = lines[n].trimStart();
        if (t.startsWith('{|')) depth++;
        else if (t.startsWith('|}')) depth--;
        table.push(lines[n]);
        if (depth === 0) break;
      }
      out.push(renderTable(table, state));
      continue;
    }

    // `{note}` or `{for}` that opens here and closes on a later line wraps
    // whole blocks, so it becomes a <div>. One that closes on the same line
    // stays inline and is handled by `inline`.
    for (let m; (m = BLOCK_OPENER.exec(line)) && !line.includes(`{/${m[1]}}`, m[0].length); ) {
      openBlock(m[1], m[2].trim());
      line = line.slice(m[0].length);
    }
    const closers = [];
    for (let m; (m = BLOCK_CLOSER.exec(line)) && !line.slice(0, m.index).match(new RegExp(`\\{${m[1]}[\\s}]`)); ) {
      closers.unshift(m[1]);
      line = line.slice(0, m.index);
    }

    const trimmed = line.trim();
    let heading;
    if (trimmed === '') {
      // A blank line ends a paragraph and a list. A line left empty by peeling
      // a block marker ends them too, which openBlock and closeBlock did.
      if (!closers.length) flush();
    } else if (pendingSummary && (heading = headingHtml(line, state))) {
      flush();
      summary(heading);
    } else if (/^\[\[ui:details_start\]\]$/i.test(trimmed)) {
      flush();
      out.push('<details>');
      pendingSummary = true;
    } else if (/^\[\[ui:details_end\]\]$/i.test(trimmed)) {
      flush();
      if (pendingSummary) summary('Details');
      out.push('</details>');
    } else {
      if (pendingSummary) {
        flush();
        summary('Details');
      }
      if (line.startsWith(' ')) {
        flushPara();
        closeLists();
        pre.push(line.slice(1));
      } else if ((heading = headingHtml(line, state))) {
        flush();
        out.push(heading);
      } else if (/^-{4,}\s*$/.test(line)) {
        flush();
        out.push('<hr>');
      } else if (trimmed === '__TOC__') {
        flush();
        out.push(TOC);
      } else if (/^[*#:;]/.test(line)) {
        flushPara();
        flushPre();
        const prefix = /^[*#:;]+/.exec(line)[0];
        let content = line.slice(prefix.length).trim();
        let common = 0;
        while (common < Math.min(prefix.length, listPrefix.length)
          && sameList(prefix[common], listPrefix[common])) common++;
        for (let k = listPrefix.length - 1; k >= common; k--) out.push(LIST_CLOSE[listPrefix[k]]);
        if (common === prefix.length && common > 0) {
          out.push(ITEM_CLOSE[listPrefix[common - 1]] + ITEM_OPEN[prefix[common - 1]]);
        }
        for (let k = common; k < prefix.length; k++) out.push(LIST_OPEN[prefix[k]]);
        let current = prefix;
        // `;term : definition` on one line.
        const colon = prefix.endsWith(';') ? definitionColon(content) : -1;
        if (colon >= 0) {
          out.push(inline(content.slice(0, colon).trim(), state) + '</dt><dd>');
          content = content.slice(colon + 1).trim();
          current = prefix.slice(0, -1) + ':';
        }
        out.push(inline(content, state));
        listPrefix = current;
      } else {
        flushPre();
        closeLists();
        para.push(line);
      }
    }
    for (const kind of closers) closeBlock(kind);
  }
  flush();
  if (pendingSummary) summary('Details');
  return out.join('');
}

/** The first `:` in a `;` item that is not in a link, a macro or a URL. */
function definitionColon(s) {
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '[' || c === '{' || c === '<') depth++;
    else if ((c === ']' || c === '}' || c === '>') && depth > 0) depth--;
    else if (c === ':' && depth === 0 && !s.startsWith('//', i + 1)) return i;
  }
  return -1;
}

/**
 * A heading line as HTML, or null. As in MediaWiki, the level is the shorter
 * of the two `=` runs, and the extra `=` of the longer run is heading text.
 * A line with no closing run (`=h1`) is not a heading; SW005 reports it.
 */
function headingHtml(line, state) {
  const m = /^(={1,6})(.+?)(={1,6})\s*$/.exec(line);
  if (!m) return null;
  const level = Math.min(m[1].length, m[3].length);
  const body = '='.repeat(m[1].length - level) + m[2] + '='.repeat(m[3].length - level);
  if (!body.trim()) return null;
  const inner = inline(body.trim(), state);
  let id = slugify(plainText(inner));
  for (let k = 2; state.ids.has(id); k++) id = `${slugify(plainText(inner))}-${k}`;
  state.ids.add(id);
  // Hidden by `{for}`, so not in the table of contents, as on SUMO.
  if (state.forStack.every(Boolean)) state.headings.push({ level, id, html: inner });
  return `<h${level} id="${attr(id)}">${inner}</h${level}>`;
}

/** Open a `{for}` element. It stays in the page but hidden, as on SUMO. */
function forOpen(tag, cond, state) {
  const visible = forMatches(cond, state.platform);
  state.forStack.push(visible);
  return `<${tag} class="for" data-for="${attr(cond)}"${visible ? '' : ' hidden'}>`;
}

/** Split a table cell into its optional attributes and its content. */
function cellParts(cell) {
  const m = /^([^|[\]{}]*=[^|[\]{}]*)\|(?!\|)([\s\S]*)$/.exec(cell);
  if (!m) return { attrs: '', content: cell };
  let attrs = '';
  for (const a of m[1].matchAll(/\b(colspan|rowspan)\s*=\s*"?(\d+)"?/gi)) {
    attrs += ` ${a[1].toLowerCase()}="${a[2]}"`;
  }
  return { attrs, content: m[2] };
}

/** Render a `{| … |}` table. Cell content is block markup, so tables nest. */
function renderTable(lines, state) {
  const rows = [];
  let caption = '';
  let row = null;
  let cell = null;
  let depth = 0;
  const newRow = () => {
    row = [];
    rows.push(row);
    cell = null;
  };
  const addCells = (tag, parts) => {
    if (!row) newRow();
    for (const p of parts) {
      cell = { tag, ...cellParts(p), more: [] };
      row.push(cell);
    }
  };

  for (const line of lines.slice(1)) {
    const t = line.trimStart();
    if (depth > 0) {
      if (t.startsWith('{|')) depth++;
      else if (t.startsWith('|}')) depth--;
      if (cell) cell.more.push(line);
      continue;
    }
    if (t.startsWith('{|')) {
      depth++;
      if (!cell) addCells('td', ['']);
      cell.more.push(line);
    } else if (t.startsWith('|}')) {
      break;
    } else if (t.startsWith('|+')) {
      caption = t.slice(2).trim();
    } else if (t.startsWith('|-')) {
      newRow();
    } else if (t.startsWith('!')) {
      addCells('th', t.slice(1).split(/!!|\|\|/));
    } else if (t.startsWith('|')) {
      addCells('td', t.slice(1).split('||'));
    } else if (cell) {
      cell.more.push(line);
    }
  }

  let out = '<table>';
  if (caption) out += `<caption>${inline(caption, state)}</caption>`;
  for (const r of rows) {
    if (!r.length) continue;
    out += '<tr>';
    for (const c of r) {
      let inner = renderBlocks([c.content.trim(), ...c.more], state);
      // A cell of one paragraph renders as plain inline content.
      const single = /^<p>([\s\S]*)<\/p>$/.exec(inner);
      if (single && !single[1].includes('<p>')) inner = single[1];
      out += `<${c.tag}${c.attrs}>${inner}</${c.tag}>`;
    }
    out += '</tr>';
  }
  return out + '</table>';
}

const RE = {
  wikiLink: /\[\[([^\]]*?)\]\]/y,
  extLink: /\[((?:https?|ftp):\/\/[^\s\]]+|mailto:[^\s\]]+)(?:\s+([^\]]*))?\]/y,
  forTag: /\{(\/?)(for|note|warning)((?:\s[^}]*)?)\}/y,
  macro: /\{(key|button|menu|filepath|pref) /y,
  quotes: /'{2,}/y,
  tag: /<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*>/y,
  entity: /&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/y,
  url: /(?:https?|ftp):\/\/[^\s<>[\]"{}|-]+/y,
};

function at(re, s, i) {
  re.lastIndex = i;
  return re.exec(s);
}

/** Render one line of inline markup. Bold and italic end at the line's end. */
function inline(s, state) {
  let out = '';
  const open = []; // 'b' and 'i', innermost last
  const toggle = (tag) => {
    const k = open.lastIndexOf(tag);
    if (k < 0) {
      out += `<${tag}>`;
      open.push(tag);
      return;
    }
    const above = open.splice(k);
    for (let j = above.length - 1; j >= 0; j--) out += `</${above[j]}>`;
    for (const t of above.slice(1)) {
      out += `<${t}>`;
      open.push(t);
    }
  };

  for (let i = 0; i < s.length; ) {
    const c = s[i];
    let m;
    if (c === '[' && (m = at(RE.wikiLink, s, i))) {
      out += wikiLink(m[1], state);
      i += m[0].length;
    } else if (c === '[' && (m = at(RE.extLink, s, i))) {
      const label = m[2] ? inline(m[2], state) : esc(m[1]);
      out += `<a href="${attr(m[1])}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      i += m[0].length;
    } else if (c === '{' && (m = at(RE.forTag, s, i))) {
      const [, close, kind, cond] = m;
      if (kind === 'for' && !close) out += forOpen('span', cond.trim(), state);
      else if (kind === 'for') {
        state.forStack.pop();
        out += '</span>';
      } else out += close ? '</span>' : `<span class="${kind}">`;
      i += m[0].length;
    } else if (c === '{' && (m = at(RE.macro, s, i)) && macroEnd(s, i) > 0) {
      const end = macroEnd(s, i);
      const arg = s.slice(i + m[0].length, end).trim();
      if (m[1] === 'key') {
        out += arg.split('+').map((k) => `<span class="key">${inline(k.trim(), state)}</span>`).join('+');
      } else {
        out += `<span class="${m[1]}">${inline(arg, state)}</span>`;
      }
      i = end + 1;
    } else if (c === "'" && (m = at(RE.quotes, s, i))) {
      let n = m[0].length;
      if (n === 4 || n > 5) {
        // Extra apostrophes are text, as in MediaWiki.
        const extra = n === 4 ? 1 : n - 5;
        out += "'".repeat(extra);
        n -= extra;
      }
      if (n === 2) toggle('i');
      else if (n === 3) toggle('b');
      else if (open.includes('b') && open.includes('i')) {
        // Close both, innermost first, so neither is reopened.
        toggle(open[open.length - 1]);
        toggle(open[open.length - 1]);
      } else if (open.includes('i')) {
        toggle('i');
        toggle('b');
      } else {
        toggle('b');
        toggle('i');
      }
      i += m[0].length;
    } else if (c === '<' && (m = at(RE.tag, s, i)) && ALLOWED_TAGS.has(m[2].toLowerCase())) {
      const name = m[2].toLowerCase();
      out += m[1] ? (VOID_TAGS.has(name) ? '' : `</${name}>`) : `<${name}>`;
      i += m[0].length;
    } else if (c === '&' && (m = at(RE.entity, s, i))) {
      out += m[0];
      i += m[0].length;
    } else if ((c === 'h' || c === 'f') && !/[\p{L}\p{N}]/u.test(s[i - 1] || '') && (m = at(RE.url, s, i))) {
      const url = m[0].replace(/[.,;:!?)]+$/, '');
      out += `<a href="${attr(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>`;
      i += url.length;
    } else if (c === '_' && s.startsWith('__TOC__', i)) {
      out += TOC;
      i += 7;
    } else {
      out += esc(c);
      i += 1;
    }
  }
  for (let j = open.length - 1; j >= 0; j--) out += `</${open[j]}>`;
  return out;
}

/** Index of the `}` closing the macro that opens at `i`, or -1. Braces nest,
 *  because real articles put `{for}` inside `{menu}`. */
function macroEnd(s, i) {
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === '{') depth++;
    else if (s[j] === '}' && --depth === 0) return j;
  }
  return -1;
}

/** `[[…]]`: an article link, an anchor, or a placeholder for media and templates. */
function wikiLink(body, state) {
  const bar = body.indexOf('|');
  const target = (bar < 0 ? body : body.slice(0, bar)).trim();
  const label = bar < 0 ? '' : body.slice(bar + 1);
  const colon = target.indexOf(':');
  const prefix = colon < 0 ? '' : target.slice(0, colon).trim().toLowerCase();
  const name = target.slice(colon + 1).trim();
  const kinds = {
    image: 'Image', video: 'Video', v: 'Video', template: 'Template', t: 'Template',
    include: 'Include', i: 'Include', ui: 'UI',
  };
  if (kinds[prefix]) {
    return `<span class="ph" title="${attr(target)}">${esc(kinds[prefix])}: ${inline(name, state)}</span>`;
  }
  const text = label ? inline(label, state) : inline(target, state);
  if (target.startsWith('#')) return `<a href="#${attr(target.slice(1))}">${text}</a>`;
  // A title does not give the article's URL, so the link has no target.
  return `<a class="wikilink" title="${attr(`Article: ${target}`)}">${text}</a>`;
}

/** The localStorage key for the view: visible columns and the platform. */
const VIEW_KEY = 'sumo-lint:view';

/**
 * The view saved in `json`, with a default for anything missing or invalid.
 * Never throws: a bad saved value must not stop the page loading.
 */
function parseView(json) {
  const view = { preview: true, problems: true, os: null, version: null };
  let saved;
  try {
    saved = JSON.parse(json);
  } catch {
    return view;
  }
  if (!saved || typeof saved !== 'object') return view;
  if (typeof saved.preview === 'boolean') view.preview = saved.preview;
  if (typeof saved.problems === 'boolean') view.problems = saved.problems;
  if (OS_NAMES.includes(saved.os) && saved.os !== 'win') view.os = saved.os;
  if (Number.isInteger(saved.version) && saved.version > 0) view.version = saved.version;
  return view;
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = { renderWiki, forMatches, slugify, parseView, VIEW_KEY, OS_NAMES, ALLOWED_TAGS };
}
