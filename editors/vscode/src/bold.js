/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Toggle bold for the `sumoLint.toggleBold` command. Kept free of
// `require('vscode')` so it runs under plain node in test/bold.test.mjs — the
// editor half is a range replace, the part worth testing is the arithmetic.
//
// SUMO bold is three apostrophes, not `**`: `'''bold'''`. Writing `**bold**`
// here would be the same bug SW010 exists to catch.
//
// The same decision logic lives in `sumo-wiki--toggle-bold` (Emacs) and
// `sumo_wiki#toggle_bold` (Vim). Three implementations, one set of rules.

const MARK = "'''";

// Non-overlapping, so `'''''` — bold plus italic — counts as the one bold
// marker it is.
function countMarks(text) {
  return text.split(MARK).length - 1;
}

// Everything is one line: `'''` does not span lines in this dialect, so the
// caller passes the rest of the line on either side of the selection.
//
// Returns undefined for anything ambiguous, and undefined means "do nothing
// and tell the user" — a toggle that guesses turns markup into a run of
// quotes that renders as something else entirely.
//
// On success: replace [start - cutBefore, end + cutAfter) with `text`, then
// select [selStart, selEnd) counted from the start of `text`. Selecting the
// new inner text is what makes the command its own inverse.
function toggleBold(before, selected, after) {
  const sel = selected || '';
  const head = before || '';
  const tail = after || '';
  if (sel.includes('\n')) {
    return undefined;
  }

  // Outer whitespace stays outside the markers: `''' x '''` renders the spaces
  // inside the bold run, which is never what selecting a word and a trailing
  // space meant.
  const core = sel.trim();
  const lead = core ? sel.slice(0, sel.indexOf(core)) : sel;
  const trail = core ? sel.slice(lead.length + core.length) : '';

  // The selection is exactly a bold span: take the markers off. Five quotes is
  // bold+italic, so stripping three from each end leaves the italic behind,
  // which is the right answer for a *bold* toggle.
  if (core.length >= 2 * MARK.length && core.startsWith(MARK) && core.endsWith(MARK)) {
    const inner = core.slice(MARK.length, -MARK.length);
    if (inner.includes(MARK)) {
      return undefined;
    }
    return {
      text: lead + inner + trail,
      cutBefore: 0,
      cutAfter: 0,
      selStart: lead.length,
      selEnd: lead.length + inner.length,
    };
  }

  // The selection sits inside a bold span — double-click a word in
  // `'''release notes'''` and you get this, not the case above.
  if (head.endsWith(MARK) && tail.startsWith(MARK) && !core.includes(MARK)) {
    return {
      text: sel,
      cutBefore: MARK.length,
      cutAfter: MARK.length,
      selStart: 0,
      selEnd: sel.length,
    };
  }

  // An odd number of markers before the selection means it sits inside a bold
  // span that opened earlier on the line. Wrapping would nest, and nesting
  // renders as a run of quotes rather than as bold; un-bolding part of a span
  // means splitting it, which is a guess about where the author wanted it to
  // end. Refuse both.
  if (countMarks(head) % 2 === 1) {
    return undefined;
  }

  // A stray `'''` inside the selection has no single right reading: the user
  // may have meant to extend that span or to nest a new one, and wrapping
  // produces a quote run that renders as neither.
  if (core.includes(MARK)) {
    return undefined;
  }

  const text = lead + MARK + core + MARK + trail;
  return {
    text,
    cutBefore: 0,
    cutAfter: 0,
    // Nothing selected: leave the caret between the two runs, ready to type.
    selStart: lead.length + MARK.length,
    selEnd: lead.length + MARK.length + core.length,
  };
}

module.exports = { MARK, toggleBold };
