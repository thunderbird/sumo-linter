/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Markup highlighting for the web app's editor (sumo-linter #35), the same as
 * on SUMO's edit page.
 *
 * SUMO does not highlight with its wiki parser. Its editor is CodeMirror 5
 * with a "simple mode": for each state, a list of regular expressions that are
 * tried in order at the current position. To look like SUMO, quirks included,
 * this file copies those rules unchanged and runs them the way CodeMirror's
 * simple mode does. For example, `{/key}` stays plain, because SUMO's rules
 * know only `{/for}`, `{/note}` and `{/warning}`. The lexer in sumo-wiki-core
 * gives its own view of the text through the diagnostics.
 *
 * The rules come from Kitsune commit 908a9601bb628d69aed824bfed68928f2f8983ac,
 * kitsune/sumo/static/sumo/js/codemirror.sumo-mode.js, under this license:
 *
 *   Copyright (c) 2011, 2012, 2013 Mozilla Foundation
 *   All rights reserved.
 *
 *   Redistribution and use in source and binary forms, with or without
 *   modification, are permitted provided that the following conditions are
 *   met:
 *
 *   * Redistributions of source code must retain the above copyright notice,
 *     this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright
 *     notice, this list of conditions and the following disclaimer in the
 *     documentation and/or other materials provided with the distribution.
 *   * Neither the name of the copyright holder nor the names of its
 *     contributors may be used to endorse or promote products derived from
 *     this software without specific prior written permission.
 *
 *   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
 *   IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 *   THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 *   PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 *   CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 *   EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 *   PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 *   PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
 *   LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 *   NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 *   SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * The matching follows CodeMirror 5.65's addon/mode/simple.js (MIT, copyright
 * Marijn Haverbeke and others). No CodeMirror code is loaded.
 */

/** SUMO's rules, copied unchanged. Update them together with the commit above. */
const SUMO_MODE = {
  start: [
    { token: 'variable.language', regex: '__TOC__' },
    { token: ['variable.language', 'meta.tag.name'], regex: /(\{)(for)/, next: 'fx_version_os_version' },
    { token: ['variable.language', 'meta.tag.name'], regex: /(\{)(note|warning)/, next: 'close_tag' },
    { token: 'variable.language', regex: /\{\/(for|note|warning)\}/ },
    { token: 'meta.tag', regex: /<\/?br>/ },
    {
      token: ['variable.language', 'meta.tag', 'markup.italic', 'variable.language'],
      regex: /(\{)(filepath|key|menu|button|pref)(.*?)(\})/,
    },
    {
      token: ['markup.other.link', 'markup.other.link', 'markup.other.link', 'markup.other.link'],
      regex: /(\[{2})([^\]]*?)(\|.*?)(\]{2})/,
    },
    {
      token: ['markup.other.link', 'markup.other.link', 'markup.other.link', 'markup.other.link'],
      regex: /(\[{2})(\S*:)(.*?)(\]{2})/,
    },
    { token: ['markup.other.link', 'markup.other.link', 'markup.other.link'], regex: /(\[{2})(.*?)(\]{2})/ },
    {
      token: ['markup.other.link', 'markup.other.link', 'markup.other.link', 'markup.other.link'],
      regex: /(\[)(\S*)(.*?)(\])/,
    },
    { token: ['variable.language', 'markup.bold', 'variable.language'], regex: /(''')(.*?)(''')/ },
    { token: ['variable.language', 'markup.italic', 'variable.language'], regex: /('')(.*?)('')/ },
    { token: ['variable.language', 'markup.underline', 'variable.language'], regex: /(<u>)(.*?)(<\/u>)/ },
    { token: ['variable.language', 'markup.strikethrough', 'variable.language'], regex: /(<s>)(.*?)(<\/s>)/ },
    { token: ['variable.language', 'markup.strikethrough', 'variable.language'], regex: /(<del>)(.*?)(<\/del>)/ },
    { token: 'variable.language', regex: /<nowiki>/, next: 'nowiki' },
    { token: 'variable.language', regex: /<code>/, next: 'code' },
    { token: 'variable.language', regex: /<pre>/, next: 'pre' },
    { token: 'markup.quote', regex: /^\s+.*/, sol: true },
    { token: ['markup.bold', 'markup.bold', 'markup.bold'], regex: /^(={1,6})(.*?)(\1)$/, sol: true },
    { token: 'variable.language', regex: /^[\-]{4}/, sol: true },
    { token: 'variable.language', regex: /^[;:#\*]+/, sol: true },
    { token: 'variable.language', regex: /^\{?[\|!][+\-]?\}?/, sol: true },
    { token: 'comment', merge: true, regex: '<\\!--', next: 'comment' },
  ],
  comment: [
    { token: 'comment', regex: '.*?-->', next: 'start' },
    { token: 'comment', merge: true, regex: '.+' },
  ],
  nowiki: [
    { token: 'variable.language', regex: /<\/nowiki>/, next: 'start' },
    { token: 'comment', regex: /./ },
  ],
  code: [
    { token: 'variable.language', regex: /<\/code>/, next: 'start' },
    { token: 'comment', regex: /./ },
  ],
  pre: [
    { token: 'variable.language', regex: /<\/pre>/, next: 'start' },
    { token: 'comment', regex: /./ },
  ],
  space: [{ token: 'text', regex: '\\s+' }],
  fx_version_os_version: [
    {
      token: ['markup.italic'],
      regex: /((?:,\s?)?(?:not\s)?(?:(?:win(?:xp|7|8|10|11)?|mac|linux|android|maemo)|=?(?:fx|tb|m|ios)\d*))+/,
      next: 'close_tag',
    },
    { token: 'variable.language', regex: /\{\/for\}/ },
  ],
  close_tag: [{ token: 'variable.language', regex: /\}/, next: 'start' }],
};

/** CodeMirror's default `maxHighlightLength`: the rest of a longer line is plain. */
const MAX_HIGHLIGHT_LENGTH = 10000;

/** `a.b` → `cm-a cm-b`, the classes CodeMirror gives a token. */
function classesOf(token) {
  return token ? token.split('.').map((t) => `cm-${t}`).join(' ') : null;
}

/**
 * CodeMirror anchors each rule with `^(?:…)` on the rest of the line. A sticky
 * regex on the whole line is the same, because every rule that uses `^` or `$`
 * itself is a `sol` rule, tried only at position 0. It saves copying the line.
 */
function compile(mode) {
  const out = {};
  for (const [name, rules] of Object.entries(mode)) {
    out[name] = rules.map((r) => {
      const source = r.regex instanceof RegExp ? r.regex.source : String(r.regex);
      const flags = r.regex instanceof RegExp && r.regex.ignoreCase ? 'iy' : 'y';
      return {
        regex: new RegExp(`(?:${source})`, flags),
        classes: Array.isArray(r.token) ? r.token.map(classesOf) : classesOf(r.token),
        sol: !!r.sol,
        next: r.next || null,
      };
    });
  }
  return out;
}

const RULES = compile(SUMO_MODE);

/**
 * Highlight one line, starting in `state`. Returns the pieces, which tile the
 * line, and the state for the next line: CodeMirror keeps the state across
 * lines, so an unclosed `<!--` or `{for` carries on.
 */
function tokenizeLine(line, state) {
  const pieces = [];
  const push = (text, cls) => {
    if (text === '') return;
    const last = pieces[pieces.length - 1];
    if (last && last.cls === cls) last.text += text;
    else pieces.push({ text, cls });
  };
  let pos = 0;
  while (pos < line.length) {
    if (pos > MAX_HIGHLIGHT_LENGTH) {
      push(line.slice(pos), null);
      break;
    }
    let matched = false;
    for (const rule of RULES[state]) {
      if (rule.sol && pos !== 0) continue;
      rule.regex.lastIndex = pos;
      const m = rule.regex.exec(line);
      // A rule that matches nothing would not advance; CodeMirror rejects it.
      if (!m || m[0] === '') continue;
      if (rule.next) state = rule.next;
      if (Array.isArray(rule.classes) && m.length > 2) {
        // One token per group. The groups of every SUMO rule tile its match.
        for (let g = 1; g < m.length; g++) if (m[g]) push(m[g], rule.classes[g - 1]);
      } else {
        push(m[0], Array.isArray(rule.classes) ? rule.classes[0] : rule.classes);
      }
      pos += m[0].length;
      matched = true;
      break;
    }
    if (!matched) {
      // No rule matches: CodeMirror moves one character on, unstyled. A
      // surrogate pair stays whole, so no half character reaches the page.
      const code = line.charCodeAt(pos);
      const width = code >= 0xd800 && code <= 0xdbff && pos + 1 < line.length ? 2 : 1;
      push(line.slice(pos, pos + width), null);
      pos += width;
    }
  }
  return { pieces, state };
}

/** Every line of `text`, as pieces. Only `\n` ends a line, as in gutter.js. */
function tokenize(text) {
  let state = 'start';
  return text.split('\n').map((line) => {
    const r = tokenizeLine(line, state);
    state = r.state;
    return r.pieces;
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => (c === '&' ? '&amp;' : c === '<' ? '&lt;' : '&gt;'));
}

function piecesHtml(pieces) {
  return pieces
    .map(({ text, cls }) => (cls ? `<span class="${cls}">${escapeHtml(text)}</span>` : escapeHtml(text)))
    .join('');
}

/**
 * The HTML of each line of `text`, without its newline.
 *
 * Pass the previous result as `prev` to redo only what an edit changed: the
 * lines before the first changed line are kept, and so are the lines after the
 * last one, as soon as a line there starts in the same state as before. A full
 * pass over 126 KB takes tens of milliseconds, too slow for every keystroke.
 */
function highlightLines(text, prev) {
  const lines = text.split('\n');
  const n = lines.length;
  const html = new Array(n);
  const starts = new Array(n);
  const ends = new Array(n);
  const old = prev || { lines: [], html: [], starts: [], ends: [] };
  const m = old.lines.length;

  let p = 0; // lines before the edit
  while (p < n && p < m && lines[p] === old.lines[p]) {
    html[p] = old.html[p];
    starts[p] = old.starts[p];
    ends[p] = old.ends[p];
    p++;
  }
  let s = 0; // lines after the edit
  while (s < n - p && s < m - p && lines[n - 1 - s] === old.lines[m - 1 - s]) s++;

  let state = p > 0 ? ends[p - 1] : 'start';
  for (let i = p; i < n; i++) {
    const k = i - n + m; // the same line in `old`
    if (i >= n - s && old.starts[k] === state) {
      // The rest is unchanged and starts in the same state, so it highlights the same.
      for (let j = k; i < n; i++, j++) {
        html[i] = old.html[j];
        starts[i] = old.starts[j];
        ends[i] = old.ends[j];
      }
      break;
    }
    const r = tokenizeLine(lines[i], state);
    starts[i] = state;
    html[i] = piecesHtml(r.pieces);
    ends[i] = state = r.state;
  }
  return { lines, html, starts, ends };
}

/**
 * The HTML for the highlighted copy behind the textarea. It has exactly the
 * text of `text`, plus one newline, because a `<pre>` shows no empty last line
 * where a textarea does.
 */
function highlightHtml(text) {
  return highlightLines(text).html.map((h) => `${h}\n`).join('');
}

/** Where the highlighting switch is kept in this browser. */
const HIGHLIGHT_KEY = 'sumo-lint:highlight';

/** The saved switch: on unless it was turned off. */
function parseHighlight(saved) {
  return saved !== 'off';
}

// Loaded as a plain <script> in the browser, where these are globals; required
// as CommonJS by the test.
if (typeof module !== 'undefined') {
  module.exports = {
    SUMO_MODE, tokenize, tokenizeLine, highlightLines, highlightHtml, parseHighlight, HIGHLIGHT_KEY,
  };
}
