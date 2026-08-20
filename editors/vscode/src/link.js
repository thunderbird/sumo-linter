/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Link text for the `sumoLint.insertLink` command. Kept free of `require
// ('vscode')` so it runs under plain node in test/link.test.mjs — the editor
// half is two input boxes, the part worth testing is the syntax.
//
// SUMO has two link forms and they are not interchangeable:
//   [https://example.org label]   external, scheme required, space-separated
//   [[Article title|label]]       internal, by *title* (not slug), pipe-separated
// Getting this backwards is exactly what SW009 exists to catch.

// External links need an explicit scheme; anything else is an article title
// or a `#w_` anchor on the current page.
function isUrl(target) {
  return /^(https?|ftp|mailto):/i.test(target.trim());
}

// Build the markup. `label` may be empty, which is meaningful for both forms:
// `[[Article title]]` renders the title, and a bare `[url]` renders the URL.
function buildLink(target, label) {
  const t = target.trim();
  const l = (label || '').trim();
  if (isUrl(t)) {
    return l ? `[${t} ${l}]` : `[${t}]`;
  }
  // A label identical to the title adds nothing but localiser diff noise.
  return l && l !== t ? `[[${t}|${l}]]` : `[[${t}]]`;
}

// VS Code's `validateInput` contract: a string is an error, undefined is OK.
function validateTarget(target) {
  const t = target.trim();
  if (!t) {
    return 'Enter a URL, an article title, or a #w_anchor on this page.';
  }
  if (/[[\]]/.test(t)) {
    return 'A link target cannot contain [ or ].';
  }
  if (t.includes('|')) {
    return 'A link target cannot contain | — that separates the target from the text.';
  }
  return undefined;
}

function validateLabel(label, target) {
  const l = label.trim();
  if (/[[\]]/.test(l)) {
    return 'Link text cannot contain [ or ].';
  }
  // In `[[Title|text]]` the pipe is the separator, so a second one would split
  // the label. External links have no pipe syntax, so there it is just a character.
  if (l.includes('|') && !isUrl(target)) {
    return 'Link text cannot contain | in an internal link.';
  }
  return undefined;
}

// Split what the user had selected into a starting target and label, so the
// common cases — select a URL, or select the words you want linked — need
// only one thing typed.
function seedFromSelection(selection) {
  const s = (selection || '').trim();
  if (!s || /[\n[\]|]/.test(s)) {
    return { target: '', label: '' };
  }
  return isUrl(s) ? { target: s, label: '' } : { target: '', label: s };
}

module.exports = { isUrl, buildLink, validateTarget, validateLabel, seedFromSelection };
