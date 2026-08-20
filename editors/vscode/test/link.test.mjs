/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Asserts the markup `SUMO: Insert Link` writes. The command exists so nobody
// hand-writes a link, so producing `[text](url)` here — the syntax SW009 flags
// — would be the worst possible bug, and these cases are what rule it out.
//
//   cd editors/vscode && npm test

import assert from 'node:assert/strict';
// CommonJS module: the default import is its `module.exports` object.
import link from '../src/link.js';

const { buildLink, isUrl, seedFromSelection, validateLabel, validateTarget } = link;

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

// --- buildLink: external ----------------------------------------------------
// SUMO separates an external URL from its text with a space, never a pipe.
check('external with label', buildLink('https://example.org', 'Example'), '[https://example.org Example]');
check('external without label', buildLink('https://example.org', ''), '[https://example.org]');
check('external, http', buildLink('http://example.org', 'x'), '[http://example.org x]');
check('external, mailto', buildLink('mailto:a@b.org', 'Mail us'), '[mailto:a@b.org Mail us]');
check('surrounding space is trimmed', buildLink('  https://example.org  ', '  Example  '), '[https://example.org Example]');
check('a URL with a space in the label keeps it', buildLink('https://e.org/a?b=1&c=2', 'A and C'), '[https://e.org/a?b=1&c=2 A and C]');

// --- buildLink: internal ----------------------------------------------------
// Internal links go by article *title*, and the separator is a pipe.
check('internal with label', buildLink('Install Thunderbird on Linux', 'Linux'), '[[Install Thunderbird on Linux|Linux]]');
check('internal without label', buildLink('Automatic Account Configuration', ''), '[[Automatic Account Configuration]]');
check('label equal to title is dropped', buildLink('Config Editor', 'Config Editor'), '[[Config Editor]]');
check('anchor on this page', buildLink('#w_whitelisting', 'Whitelisting'), '[[#w_whitelisting|Whitelisting]]');
check('title plus anchor', buildLink('Getting Started#w_7-message-list-pane', 'Message List Pane'), '[[Getting Started#w_7-message-list-pane|Message List Pane]]');
check('a slug-looking target is still treated as internal', buildLink('install-thunderbird', 'here'), '[[install-thunderbird|here]]');
check('undefined label behaves as empty', buildLink('Config Editor', undefined), '[[Config Editor]]');

// Never Markdown, whatever the input looks like.
for (const [target, label] of [['https://example.org', 'Example'], ['Config Editor', 'here']]) {
  const out = buildLink(target, label);
  check(`no markdown link for ${target}`, /\]\(/.test(out), false);
}

// --- isUrl ------------------------------------------------------------------
check('isUrl https', isUrl('https://example.org'), true);
check('isUrl is case-insensitive', isUrl('HTTPS://example.org'), true);
check('isUrl needs a scheme', isUrl('example.org'), false);
check('a title is not a URL', isUrl('Install Thunderbird on Linux'), false);
check('an anchor is not a URL', isUrl('#w_whitelisting'), false);

// --- validation -------------------------------------------------------------
// undefined means "accepted" in VS Code's validateInput contract.
check('empty target rejected', typeof validateTarget('   '), 'string');
check('bracket in target rejected', typeof validateTarget('a]b'), 'string');
check('pipe in target rejected', typeof validateTarget('Title|text'), 'string');
check('ordinary title accepted', validateTarget('Config Editor'), undefined);
check('ordinary URL accepted', validateTarget('https://example.org'), undefined);
check('empty label accepted', validateLabel('', 'Config Editor'), undefined);
check('bracket in label rejected', typeof validateLabel('a]b', 'Config Editor'), 'string');
check('pipe in internal label rejected', typeof validateLabel('a|b', 'Config Editor'), 'string');
check('pipe in external label accepted', validateLabel('a|b', 'https://example.org'), undefined);

// --- seedFromSelection ------------------------------------------------------
check('selected URL seeds the target', seedFromSelection('https://example.org'), { target: 'https://example.org', label: '' });
check('selected prose seeds the label', seedFromSelection('the release notes'), { target: '', label: 'the release notes' });
check('no selection seeds nothing', seedFromSelection(''), { target: '', label: '' });
check('undefined selection seeds nothing', seedFromSelection(undefined), { target: '', label: '' });
// Selecting an existing link would seed unusable values, so seed nothing and
// let the user type; SW009's quick fix is the tool for rewriting a bad link.
check('selected markup seeds nothing', seedFromSelection('[[Config Editor|here]]'), { target: '', label: '' });
check('multi-line selection seeds nothing', seedFromSelection('one\ntwo'), { target: '', label: '' });

// A floor on the count: a file that stops running its body would otherwise
// print no failures and pass.
const expected = 35;
if (checks < expected) {
  console.error(`\nonly ${checks} link assertions ran, expected at least ${expected}`);
  process.exit(1);
}
if (failed) {
  console.error(`\n${failed} of ${checks} link assertions failed`);
  process.exit(1);
}
console.log(`link: ${checks} assertions passed`);
