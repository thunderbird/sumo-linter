/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Link text for the `sumoLint.insertLink` command. Kept free of `require
// ('vscode')` so it runs under plain node in test/link.test.mjs — the editor
// half is two input boxes, the part worth testing is the syntax.
//
// Also the paste handler, which is the same markup reached a different way.
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

// Paste-over-selection, the way Markdown mode does it: select some words,
// paste a URL, get a link. Returns undefined for every case that is not
// unambiguously that gesture, and undefined means "let VS Code paste normally"
// — a paste handler that guesses is worse than no paste handler, because the
// thing it silently mangles is whatever was on the clipboard.
function linkFromPaste(pasted, selected) {
  const url = (pasted || '').trim();
  const text = (selected || '').trim();

  // A URL never contains whitespace, so anything that does is prose that merely
  // starts with a scheme, and pasting it over a selection is a plain replace.
  if (!isUrl(url) || /\s/.test(url)) {
    return undefined;
  }
  // No selection: there is no link text, so this is an ordinary paste. Markdown
  // mode draws the line in the same place ("smartWithSelection").
  if (!text) {
    return undefined;
  }
  // Replacing one URL with another is a correction, not a link.
  if (isUrl(text)) {
    return undefined;
  }
  // A multi-line selection has no sensible label, and brackets would close the
  // link early. `|` is safe here: it only separates in the [[internal]] form.
  if (/[\n[\]]/.test(text)) {
    return undefined;
  }
  return `[${url} ${text}]`;
}

module.exports = {
  isUrl,
  buildLink,
  validateTarget,
  validateLabel,
  seedFromSelection,
  linkFromPaste,
};
