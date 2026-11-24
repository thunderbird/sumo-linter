/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Tests for replace-lib.mjs (sumo-linter #62). Run: node --test tools/scrape/test/

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  parseIssue,
  protectedRanges,
  applyReplacements,
  describeChanges,
  newDiagnostics,
  newestRevision,
  markArticle,
  apiPath,
} from '../replace-lib.mjs';

const ISSUE = `Intro text.

### Strings

- [ ] "Config Editor…" → "Advanced settings"
- [x] "Move it to my “Sent” folder" → "Move to Sent folder"

### Articles

- [ ] config-editor
- [x] [advanced-panel-settings-in-thunderbird](https://example.org/x) already done
  - Note: revision 1
- [ ] \`tb-oauth\`

### Evaluation

- [ ] not an article
`;

test('reads both checklists, every string item and each article item', () => {
  const { strings, articles } = parseIssue(ISSUE);
  assert.deepEqual(strings, [
    { from: 'Config Editor…', to: 'Advanced settings' },
    { from: 'Move it to my “Sent” folder', to: 'Move to Sent folder' },
  ]);
  assert.deepEqual(
    articles.map((a) => [a.slug, a.checked]),
    [
      ['config-editor', false],
      ['advanced-panel-settings-in-thunderbird', true],
      ['tb-oauth', false],
    ]
  );
});

test('refuses a list that it cannot read in full', () => {
  assert.throws(() => parseIssue('### Articles\n- [ ] a\n'), /no "### Strings"/);
  assert.throws(() => parseIssue('### Strings\n- [ ] "a" → "b"\n'), /no "### Articles"/);
  assert.throws(() => parseIssue('### Strings\n- [ ] a → b\n### Articles\n- [ ] x\n'), /must be "old" → "new"/);
  assert.throws(() => parseIssue('### Strings\n- [ ] "a" → "a"\n### Articles\n- [ ] x\n'), /the same/);
  assert.throws(() => parseIssue('### Strings\n- [ ] "" → "a"\n### Articles\n- [ ] x\n'), /empty/);
  assert.throws(
    () => parseIssue('### Strings\n- [ ] "a" → "b"\n- [ ] "a" → "c"\n### Articles\n- [ ] x\n'),
    /listed twice/
  );
  assert.throws(() => parseIssue('### Strings\n- [ ] "a" → "b"\n### Articles\n- [ ] <x>\n'), /not a slug/);
});

test('replaces outside comments, nowiki and pre only', () => {
  const src = 'A old.\n<!-- old -->\n<nowiki>old</nowiki> <pre>old</pre> old\n<!-- old';
  assert.deepEqual(protectedRanges(src).length, 4);
  const r = applyReplacements(src, [{ from: 'old', to: 'new' }]);
  assert.equal(r.text, 'A new.\n<!-- old -->\n<nowiki>old</nowiki> <pre>old</pre> new\n<!-- old');
  assert.deepEqual(r.counts, [2]);
  assert.deepEqual(r.changes.map((c) => c.line), [1, 3]);
});

test('one pass, longest first: no chains and no partial matches', () => {
  const strings = [
    { from: 'Settings', to: 'Preferences' },
    { from: 'Account Settings', to: 'Account setup' },
    { from: 'Preferences', to: 'Options' },
  ];
  const r = applyReplacements('Settings, Account Settings, Preferences', strings);
  assert.equal(r.text, 'Preferences, Account setup, Options');
  assert.deepEqual(r.counts, [1, 1, 1]);
});

test('a match that runs into a comment is not replaced', () => {
  const r = applyReplacements('ab<!-- c -->', [{ from: 'ab<!--', to: 'x' }]);
  assert.equal(r.text, 'ab<!-- c -->');
  assert.deepEqual(r.counts, [0]);
});

test('keeps the line count, and flags links and {for} branches', () => {
  const src = '[[Old title|old]] old\n{for tb158}old{/for} old\n<!-- {for} -->old';
  const r = applyReplacements(src, [{ from: 'old', to: 'new' }]);
  assert.equal(r.text.split('\n').length, src.split('\n').length);
  assert.deepEqual(
    r.changes.map((c) => [c.line, c.why]),
    [
      [1, ['in a [[link]]']],
      [1, []],
      [2, ['in a {for} branch']],
      [2, []],
      [3, []],
    ]
  );
});

test('describes each change with text around it', () => {
  const src = `${'x'.repeat(50)} Config Editor… ${'y'.repeat(50)}`;
  const { changes } = applyReplacements(src, [{ from: 'Config Editor…', to: 'Advanced settings' }]);
  const [d] = describeChanges(src, changes, 10);
  assert.equal(d, `Line 1: …${'x'.repeat(9)} [- Config Editor… -][+ Advanced settings +] ${'y'.repeat(9)}…`);
  const short = applyReplacements('[[a b]]', [{ from: 'a', to: 'c' }]);
  assert.equal(describeChanges('[[a b]]', short.changes)[0], 'Line 1: [[[- a -][+ c +] b]]   (check: in a [[link]])');
});

test('finds only the diagnostics that the edit adds', () => {
  const d = (line, code) => ({ line, code, message: 'm' });
  assert.deepEqual(newDiagnostics([d(1, 'SW004'), d(2, 'SW004')], [d(1, 'SW004'), d(2, 'SW004')]), []);
  assert.deepEqual(newDiagnostics([d(1, 'SW004')], [d(1, 'SW004'), d(1, 'SW004'), d(3, 'SW007')]), [
    d(1, 'SW004'),
    d(3, 'SW007'),
  ]);
});

test('reads the newest revision from a history page', () => {
  const html =
    '<a href="/en-US/kb/a-b/revision/355475">x</a><a href="/en-US/kb/a-b/revision/355499">y</a>' +
    '<a href="/en-US/kb/a-b-c/revision/999999">other article</a>';
  assert.equal(newestRevision(html, 'a-b'), 355499);
  assert.equal(newestRevision('<p>none</p>', 'a-b'), null);
});

test('checks the article item and adds notes after its existing notes', () => {
  let body = markArticle(ISSUE, 'advanced-panel-settings-in-thunderbird', { check: true, notes: ['second'] });
  assert.match(body, /already done\n {2}- Note: revision 1\n {2}- Note: second\n- \[ \] `tb-oauth`/);
  body = markArticle(body, 'config-editor', { check: true, notes: ['revision 2, 1 replacement: url'] });
  assert.match(body, /- \[x\] config-editor\n {2}- Note: revision 2, 1 replacement: url\n/);
  body = markArticle(body, 'tb-oauth', { check: false, notes: ['skipped: wrong'] });
  assert.match(body, /- \[ \] `tb-oauth`\n {2}- Note: skipped: wrong\n/);
  assert.throws(() => markArticle(ISSUE, 'not-there', { check: true, notes: [] }), /no article item/);
  // The Evaluation section is not an article list.
  assert.throws(() => markArticle(ISSUE, 'not', { check: true, notes: [] }), /no article item/);
});

test('turns an issue or comment reference into a gh api path', () => {
  assert.equal(apiPath('https://github.com/thunderbird/sumo-linter/issues/62'), 'repos/thunderbird/sumo-linter/issues/62');
  assert.equal(
    apiPath('https://github.com/thunderbird/sumo-linter/issues/62#issuecomment-123'),
    'repos/thunderbird/sumo-linter/issues/comments/123'
  );
  assert.equal(apiPath('thunderbird/sumo-linter#62'), 'repos/thunderbird/sumo-linter/issues/62');
  assert.throws(() => apiPath('62'), /not an issue/);
});

// Roland decided on 2026-11-23 (#62) that he clicks Submit himself. The
// driver fills the form and never submits it, clicks or presses keys.
test('replace.mjs never submits a form or clicks', () => {
  const src = readFileSync(new URL('../replace.mjs', import.meta.url), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '');
  for (const banned of ['.click(', '.submit(', 'requestSubmit', '.press(', '.tap(', 'dispatchEvent', "method: 'POST'", 'method: "POST"']) {
    assert.ok(!src.includes(banned), `replace.mjs uses ${banned}`);
  }
});
