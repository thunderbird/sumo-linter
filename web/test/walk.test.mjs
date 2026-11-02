/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the walk-mode logic (#31): which range the page selects for the
// line walk.py sends, counted as the gutter and the linter count lines.
//
//   node web/test/walk.test.mjs

import assert from 'node:assert/strict';
import walk from '../walk.js';

const { isWalkMode, lineRange, guessEdit, confirmEdit, CONFIRM_COMMENT } = walk;

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

check('walk mode: ?walk=1', isWalkMode('?walk=1'), true);
check('walk mode: among other parameters', isWalkMode('?a=b&walk=1'), true);
check('walk mode: not without it', isWalkMode(''), false);
check('walk mode: not for another value', isWalkMode('?walk=0'), false);

const text = 'one\ntwo “Sent” two\n\nfour';
check('the whole first line', lineRange(text, 1), [0, 3]);
check('the whole second line, without its newline', lineRange(text, 2), [4, 18]);
check('an empty line selects nothing, at its start', lineRange(text, 3), [19, 19]);
check('the last line, which has no newline', lineRange(text, 4), [20, 24]);
check('the quoted text on the line', lineRange(text, 2, '“Sent”'), [8, 14]);
check('the first occurrence on the line', lineRange(text, 2, 'two'), [4, 7]);
check('text that is not on the line selects the line', lineRange(text, 2, 'four'), [4, 18]);
check('text on another line only does not count', lineRange(text, 1, 'two'), [0, 3]);
check('curly quotes find straight ones', lineRange('a\nmy "Sent" box', 2, 'my “Sent”'), [2, 11]);
check('straight quotes find curly ones', lineRange("it’s", 1, "it's"), [0, 4]);
check('no such line', lineRange(text, 5), null);
check('line 0 is not a line', lineRange(text, 0), null);
check('a line that is not a number', lineRange(text, '2'), null);
check('\\r\\n: the \\r stays on its line, as in the linter', lineRange('a\r\nb', 1), [0, 2]);
{
  // UTF-16 offsets, because the textarea uses them: 🐦 is two units.
  const birds = '🐦🐦\nx🐦y';
  check('offsets are UTF-16 units', lineRange(birds, 2, 'y'), [8, 9]);
}

// Using a guess (#34). Each case is a real comment from the #28 proposals.
function applied(text, line, old, guess, own = false) {
  const e = guessEdit(text, line, old, guess, own);
  return e.error ? e : text.slice(0, e.start) + e.replacement + text.slice(e.end);
}
check('a guess replaces the old text and the comment',
  applied("x\n{for tb159}'''Enable Global Search and Indexer<!-- CHECK 159: \"Enable Global Search and Indexer\" → \"Search & performance\"? -->''': text{/for}",
    2, 'Enable Global Search and Indexer', 'Search & performance'),
  "x\n{for tb159}'''Search & performance''': text{/for}");
check('case and a trailing colon, which the guess then loses',
  applied("'''No Proxy For<!-- CHECK 159: \"No proxy for:\" → \"Manual proxy setup:\"? -->'''", 1, 'No proxy for:', 'Manual proxy setup:'),
  "'''Manual proxy setup'''");
check('a colon in the text keeps the colon of the guess',
  applied('When a server requests my personal certificate:<!-- CHECK 159: "When a server requests my personal certificate:" → "When a server asks for a certificate:"? -->', 1,
    'When a server requests my personal certificate:', 'When a server asks for a certificate:'),
  'When a server asks for a certificate:');
check('the closing brace of a macro stays',
  applied('{for tb159}{button Clear Now}<!-- CHECK 159: "Clear Now" → "Clear temporary files"? -->{/for}', 1, 'Clear Now', 'Clear temporary files'),
  '{for tb159}{button Clear temporary files}{/for}');
check('curly quotes in the checklist, straight ones in the article',
  applied("'''Tell me if the message I'm reading is a suspected email scam<!-- CHECK 159: \"Tell me if the message I’m reading is a suspected email scam\" → \"Check messages\"? -->'''",
    1, 'Tell me if the message I’m reading is a suspected email scam', 'Check messages'),
  "'''Check messages'''");
{
  const heading = '= Network & Disk Space tab<!-- CHECK 159, heading: "Network & Disk Space" → "Network and storage"? --><!-- CHECK 159, heading: "Disk Space" → "Temporary storage"? --> =';
  const second = applied(heading, 1, 'Disk Space', 'Temporary storage');
  check('looks past the other comment of a heading, and keeps it', second,
    '= Network & Temporary storage tab<!-- CHECK 159, heading: "Network & Disk Space" → "Network and storage"? --> =');
  check('then the other guess no longer matches', applied(second, 1, 'Network & Disk Space', 'Network and storage'),
    { error: 'on line 1, the text before the comment is not "Network & Disk Space"' });
}
check('only the comment for this guess counts',
  applied('a<!-- CHECK 159: "a" → "b"? -->', 1, 'a', 'c'), { error: 'line 1 has no CHECK comment for "a" → "c"' });
check('no such line', guessEdit('a', 3, 'a', 'b'), { error: 'there is no line 3' });
check('the old text a little earlier in the heading, the rest stays',
  applied('= Network & Disk Space tab<!-- CHECK 159, heading: "Network & Disk Space" → "Network and storage"? --> =', 1, 'Network & Disk Space', 'Network and storage'),
  '= Network and storage tab =');
check('never from the other {for} part',
  applied('{for not tb159}Old{/for}{for tb159}New text<!-- CHECK 159: "Old" → "X"? -->{/for}', 1, 'Old', 'X'),
  { error: 'on line 1, the text before the comment is not "Old"' });

// --- confirmEdit: `c` deletes the line's CHECK comment ------------------------
{
  const line2 = `{for tb159}'''Move to Sent folder'''{/for}${CONFIRM_COMMENT}`;
  const text = `first\n${line2}\nlast`;
  const e = confirmEdit(text, 2);
  const after = text.slice(0, e.start) + e.replacement + text.slice(e.end);
  check('confirm: the comment goes', after, "first\n{for tb159}'''Move to Sent folder'''{/for}\nlast");
  check('confirm: only that line', confirmEdit(text, 1), { none: true });
  check('confirm: a second c on the line finds none', confirmEdit(after, 2), { none: true });
  check('confirm: no such line', confirmEdit(text, 9), { error: 'there is no line 9' });
  // A guess comment is not this comment, so it stays.
  check('confirm: a guess comment stays', confirmEdit('<!-- CHECK 159: "A" → "B"? -->', 1), { none: true });
}

// --- g with the author's own text (shot: "…"), against a "removed" comment ----
{
  const src = `{for tb159}'''Leave it in my Inbox<!-- CHECK 159: "Leave it in my Inbox" → "removed"? -->''': Return receipts.{/for}`;
  check('shot text replaces the old text and the removed comment',
    applied(src, 1, 'Leave it in my Inbox', 'Leave in Inbox', true),
    "{for tb159}'''Leave in Inbox''': Return receipts.{/for}");
  check('without shot text, a comment with another guess is refused',
    applied(src, 1, 'Leave it in my Inbox', 'Leave in Inbox'),
    { error: 'line 1 has no CHECK comment for "Leave it in my Inbox" → "Leave in Inbox"' });
  check('the exact comment still wins over another for the same text',
    applied('A<!-- CHECK 159: "A" → "X"? --> A<!-- CHECK 159: "A" → "B"? -->', 1, 'A', 'B', true),
    'A<!-- CHECK 159: "A" → "X"? --> B');
}

const expected = 38;
if (checks < expected) {
  console.error(`\nonly ${checks} walk assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} walk assertions failed`);
  process.exit(1);
}
console.log(`walk: ${checks} assertions passed`);
