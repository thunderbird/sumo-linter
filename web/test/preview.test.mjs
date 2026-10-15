/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the web app's preview renderer (#14): the markup it renders, the
// `{for}` platform rules, and that nothing pasted can put script in the page.
//
//   node web/test/preview.test.mjs

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
// CommonJS module: the default import is its `module.exports` object.
import preview from '../preview.js';

const { renderWiki, forMatches, slugify } = preview;

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

const has = (what, src, fragment, platform) => check(what, renderWiki(src, platform).includes(fragment), true);
const lacks = (what, src, fragment, platform) => check(what, renderWiki(src, platform).includes(fragment), false);

// --- headings and paragraphs ------------------------------------------------
check('spaced heading', renderWiki('= Install it ='), '<h1 id="w_install-it">Install it</h1>');
check('tight heading', renderWiki('===Sub==='), '<h3 id="w_sub">Sub</h3>');
check('asymmetric heading takes the shorter run', renderWiki('==H ==='), '<h2 id="w_h">H =</h2>');
check('a heading with no closing run is text', renderWiki('=h1'), '<p>=h1</p>');
check('Kitsune id form', slugify('Thunderbird Release Channel (default)'), 'w_thunderbird-release-channel-default');
check('duplicate headings get distinct ids',
  renderWiki('=A=\n=A=').match(/id="[^"]*"/g), ['id="w_a"', 'id="w_a-2"']);
check('lines of a paragraph join', renderWiki('one\ntwo\n\nthree'), '<p>one\ntwo</p><p>three</p>');
check('horizontal rule', renderWiki('----'), '<hr>');

// --- inline -----------------------------------------------------------------
check('bold and italic', renderWiki("'''b''' and ''i''"), '<p><b>b</b> and <i>i</i></p>');
check('bold italic', renderWiki("'''''both'''''"), '<p><b><i>both</i></b></p>');
check('unclosed bold ends with the line', renderWiki("'''open\nnext"), '<p><b>open</b>\nnext</p>');
has('menu', '{menu Tools > Settings}', '<span class="menu">Tools &gt; Settings</span>');
has('button', '{button Continue}', '<span class="button">Continue</span>');
has('key combination', '{key Ctrl+Shift+T}',
  '<span class="key">Ctrl</span>+<span class="key">Shift</span>+<span class="key">T</span>');
has('filepath', '{filepath C:\\x}', '<span class="filepath">C:\\x</span>');
has('{for} nested in a macro', '{menu {for win}Open{/for}}', '<span class="menu"><span class="for" data-for="win">Open</span></span>');
check('commented-out macro stays literal', renderWiki('{<!-- -->key Ctrl+T}'), '<p>{key Ctrl+T}</p>');
check('entities pass through', renderWiki('&#123;pref x&#125; a&nbsp;b'), '<p>&#123;pref x&#125; a&nbsp;b</p>');
check('bare & is escaped', renderWiki('A & B'), '<p>A &amp; B</p>');

// --- links and placeholders ------------------------------------------------
has('external link', '[https://example.com/a Example]',
  '<a href="https://example.com/a" target="_blank" rel="noopener noreferrer">Example</a>');
has('bare URL', 'see https://example.com/x.', '<a href="https://example.com/x" target="_blank" rel="noopener noreferrer">https://example.com/x</a>.');
has('article link has no target', '[[Profiles|your profile]]', '<a class="wikilink" title="Article: Profiles">your profile</a>');
has('anchor link', '[[#w_release|Release]]', '<a href="#w_release">Release</a>');
has('image placeholder', '[[Image:tb-141-oauth|width=450]]', '<span class="ph" title="Image:tb-141-oauth">Image: tb-141-oauth</span>');
has('template placeholder', '[[Template:optionspreferences]]', 'Template: optionspreferences</span>');
has('video placeholder', '[[V:abc]]', 'Video: abc</span>');

// --- lists --------------------------------------------------------------------
check('ordered list', renderWiki('# a\n# b'), '<ol><li>a</li><li>b</li></ol>');
check('nested list', renderWiki('* a\n** b\n* c'), '<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>');
check('#: continues the item', renderWiki('# a\n#: more\n# b'),
  '<ol><li>a<dl><dd>more</dd></dl></li><li>b</li></ol>');
check('definition on one line', renderWiki(';term : def'), '<dl><dt>term</dt><dd>def</dd></dl>');
check('a URL colon does not split a term', renderWiki('; see https://x.example'),
  '<dl><dt>see <a href="https://x.example" target="_blank" rel="noopener noreferrer">https://x.example</a></dt></dl>');
check('blank line ends a list', renderWiki('# a\n\n# b'), '<ol><li>a</li></ol><ol><li>b</li></ol>');
check('comment-only line does not end a list', renderWiki('# a\n<!-- x -->\n# b'), '<ol><li>a</li><li>b</li></ol>');

// --- blocks -------------------------------------------------------------------
check('inline note', renderWiki("{note}'''Note:''' x{/note}"), '<p><span class="note"><b>Note:</b> x</span></p>');
check('note over lines', renderWiki('{note}one\n\ntwo{/note}'), '<div class="note"><p>one</p><p>two</p></div>');
check('warning block', renderWiki('{warning}\nx\n{/warning}'), '<div class="warning"><p>x</p></div>');
check('block {for}', renderWiki('{for mac}\n* a\n{/for}'), '<div class="for" data-for="mac"><ul><li>a</li></ul></div>');
check('details with summary heading',
  renderWiki('[[UI:details_start]]\n===Profiles===\nText\n[[UI:details_end]]'),
  '<details><summary><h3 id="w_profiles">Profiles</h3></summary><p>Text</p></details>');
check('details without a heading', renderWiki('[[UI:details_start]]\nText\n[[UI:details_end]]'),
  '<details><summary>Details</summary><p>Text</p></details>');
check('table of contents', renderWiki('__TOC__\n=A=\n==B==\n=C='),
  '<nav class="toc"><ul><li><a href="#w_a">A</a><ul><li><a href="#w_b">B</a></li></ul></li><li><a href="#w_c">C</a></li></ul></nav>'
  + '<h1 id="w_a">A</h1><h2 id="w_b">B</h2><h1 id="w_c">C</h1>');

// --- regions that are not interpreted --------------------------------------
check('nowiki', renderWiki("<nowiki>'''[[x]]'''</nowiki>"), "<p>'''[[x]]'''</p>");
check('pre', renderWiki('<pre>\n= x =\n</pre>'), '<p><pre>\n= x =\n</pre></p>');
check('leading space is preformatted', renderWiki(' = x =\n a'), '<pre>= x =\na</pre>');
check('comment removed', renderWiki('a<!-- hidden -->b'), '<p>ab</p>');

// --- tables -------------------------------------------------------------------
check('table', renderWiki('{|\n|+ Cap\n!A!!B\n|-\n|1||2\n|}'),
  '<table><caption>Cap</caption><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>');
check('cell attributes keep only spans', renderWiki('{|\n|style="x" colspan="2"|wide\n|}'),
  '<table><tr><td colspan="2">wide</td></tr></table>');
check('link pipe is not a cell attribute', renderWiki('{|\n|[[#w_a|A]]||b\n|}'),
  '<table><tr><td><a href="#w_a">A</a></td><td>b</td></tr></table>');
check('nested table', renderWiki('{|\n|outer\n{|\n|inner\n|}\n|}'),
  '<table><tr><td><p>outer</p><table><tr><td>inner</td></tr></table></td></tr></table>');

// --- {for} platform rules ---------------------------------------------------
const any = { os: null, version: null };
const mac140 = { os: 'mac', version: 140 };
const win10 = { os: 'win10', version: null };
check('any platform shows everything', ['mac', 'win', 'not tb60', '=tb115'].map((c) => forMatches(c, any)), [true, true, true, true]);
check('os match', forMatches('mac', mac140), true);
check('os mismatch', forMatches('win,linux', mac140), false);
check('win matches every Windows', forMatches('win', win10), true);
check('a specific Windows', [forMatches('win10', win10), forMatches('winxp', win10)], [true, false]);
check('not os', [forMatches('not mac', mac140), forMatches('not mac', win10)], [false, true]);
check('tbN is N or newer', [forMatches('tb115', mac140), forMatches('tb150', mac140)], [true, false]);
check('=tbN is only N', [forMatches('=tb140', mac140), forMatches('=tb115', mac140)], [true, false]);
check('not tbN is older than N', [forMatches('not tb115', mac140), forMatches('not tb150', mac140)], [false, true]);
check('both groups must match', [forMatches('mac, tb150', mac140), forMatches('mac, tb115', mac140)], [false, true]);
check('version only, any os', forMatches('linux, tb115', { os: null, version: 140 }), true);
check('Firefox conditions are ignored', forMatches('not fx152', mac140), true);
check('empty condition', forMatches('', mac140), true);
has('mismatch is hidden', '{for win}x{/for}', '<span class="for" data-for="win" hidden>', mac140);
lacks('match is not hidden', '{for mac}x{/for}', 'hidden', mac140);
check('hidden headings leave the table of contents',
  renderWiki('__TOC__\n{for win}\n=Win=\n{/for}\n=All=', mac140).startsWith('<nav class="toc"><ul><li><a href="#w_all">'), true);

// --- safety -------------------------------------------------------------------
lacks('script tag is literal', '<script>alert(1)</script>', '<script');
lacks('attributes are dropped', '<span onclick="alert(1)">x</span>', 'onclick=');
lacks('img is literal', '<img src=x onerror=alert(1)>', '<img');
lacks('javascript URL is not a link', '[javascript:alert(1) x]', 'href');
lacks('quote in URL cannot leave the attribute', '[https://x.example/" onmouseover="alert(1) y]', '" onmouseover');
lacks('quote in a title cannot leave the attribute', '[[a" onmouseover="x]]', '" onmouseover');
lacks('quote in a condition cannot leave the attribute', '{for a" onmouseover="x}y{/for}', '" onmouseover');
lacks('forged stash marker', '\uE0000\uE001<nowiki>x</nowiki>', '\uE000');
has('unknown tag is text', '<account name>', '&lt;account name&gt;');

// --- saved view -------------------------------------------------------------
const { parseView } = preview;
const fresh = { preview: true, problems: true, os: null, version: null };
check('nothing saved', parseView(null), fresh);
check('not JSON', parseView('{oops'), fresh);
check('not an object', parseView('7'), fresh);
check('saved view', parseView('{"preview":false,"problems":true,"os":"mac","version":140}'),
  { preview: false, problems: true, os: 'mac', version: 140 });
check('invalid fields fall back', parseView('{"preview":"no","os":"beos","version":-3}'), fresh);
check('win is a condition, not a system', parseView('{"os":"win"}').os, null);
check('version must be a whole number', parseView('{"version":1.5}').version, null);

// --- the whole corpus renders ------------------------------------------------
// Every article renders without throwing, and the only tags in the output are
// ones the renderer writes itself.
const OWN = new Set(['a', 'caption', 'details', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'nav',
  'pre', 'summary', ...preview.ALLOWED_TAGS]);
const dir = new URL('../../corpus/en-US/', import.meta.url);
let articles = 0;
const strays = new Set();
for (const f of readdirSync(dir).filter((n) => n.endsWith('.wiki'))) {
  const html = renderWiki(readFileSync(new URL(f, dir), 'utf8'), mac140);
  articles += 1;
  for (const m of html.matchAll(/<\/?([a-zA-Z][a-zA-Z0-9]*)/g)) {
    if (!OWN.has(m[1].toLowerCase())) strays.add(`${f}: ${m[1]}`);
  }
  if (/[\uE000-\uE003]/.test(html)) strays.add(`${f}: private-use marker`);
}
check('corpus articles render', articles > 150, true);
check('corpus output has only known tags', [...strays], []);

if (failed) {
  console.error(`preview: ${failed} of ${checks} assertions failed`);
  process.exit(1);
}
console.log(`preview: ${checks} assertions passed`);
