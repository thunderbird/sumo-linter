/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Semi-automatic search and replace over SUMO KB articles (sumo-linter #62).
 *
 *   node replace.mjs ISSUE [--base URL] [--locale en-US] [--comment TEXT]
 *   npm run replace -- https://github.com/thunderbird/sumo-linter/issues/N
 *
 * ISSUE is an issue URL, an issue-comment URL or `owner/repo#n`. Its text holds
 * a `### Strings` checklist (`- [ ] "old" → "new"`) and a `### Articles`
 * checklist (`- [ ] slug`). Every string item applies; the unchecked article
 * items are the work.
 *
 * For each article, in a headed Chromium with `.auth/chromium-profile`:
 *
 *   1. Open the edit page. If the session expired, ask you to sign in.
 *   2. Read the source, apply the replacements as exact text (never inside
 *      comments, <nowiki> or <pre>), and lint the old and the new source.
 *   3. Show each change with its line. `y` fills the editor and the revision
 *      comment, `n REASON` skips the article, `q` stops.
 *   4. You check the edit in the browser and click Submit for Review and
 *      Submit yourself. This script never submits a form (Roland's decision,
 *      2026-11-23), and a test checks that it never clicks.
 *   5. When the new revision is in the article's history, the script checks
 *      the article item and adds `  - Note: revision N, …` to the issue.
 *
 * The issue is saved after every article, so a stop loses nothing. An article
 * with no match is checked with the note `no match: no edit`; a skipped one
 * stays unchecked with your reason, so the next run offers it again.
 *
 * Defaults to staging, as the scraper does. Production needs
 * `--base https://support.mozilla.org`.
 *
 * `--dry-run` reads, replaces, lints and shows every change, but never fills
 * an edit page and never changes the checklist: it prints the note it would
 * add instead. It still signs you in, because the source is only on the edit
 * page. `--issue-file F` reads and writes the checklist in a local file
 * instead of GitHub, for tests.
 */

import { chromium } from 'playwright';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline/promises';
import {
  parseIssue,
  applyReplacements,
  describeChanges,
  newDiagnostics,
  newestRevision,
  markArticle,
  apiPath,
} from './replace-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../..');
const argv = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i === -1 ? dflt : argv[i + 1];
};
const VALUED = new Set(['--base', '--locale', '--profile', '--comment', '--issue-file']);
const ref =
  argv.find((a, i) => !a.startsWith('--') && !(i > 0 && VALUED.has(argv[i - 1]))) ??
  (argv.includes('--issue-file') ? 'local/file#0' : null);
if (!ref) {
  console.error('usage: node replace.mjs ISSUE [--base URL] [--locale en-US] [--comment TEXT] [--dry-run] [--issue-file F]');
  process.exit(2);
}
const CONFIG = {
  base: String(flag('base', 'https://support.allizom.org')).replace(/\/$/, ''),
  locale: String(flag('locale', 'en-US')),
  profileDir: resolve(REPO, String(flag('profile', '.auth/chromium-profile'))),
  comment: flag('comment', null),
  // For tests: read and write the checklist in a local file, not on GitHub.
  issueFile: flag('issue-file', null),
  // Stop before filling the edit page.
  dryRun: argv.includes('--dry-run'),
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isChallenge = (body) => body.includes('Client Challenge') && body.includes('_fs-ch-');

// ---------------------------------------------------------------------------
// GitHub, through gh
// ---------------------------------------------------------------------------

const API = apiPath(ref);
const issueUrl = (() => {
  const m = API.match(/^repos\/([^/]+)\/([^/]+)\/issues\/(\d+)$/);
  return m ? `https://github.com/${m[1]}/${m[2]}/issues/${m[3]}` : ref;
})();

function readBody() {
  if (CONFIG.issueFile) return readFileSync(CONFIG.issueFile, 'utf8');
  return JSON.parse(execFileSync('gh', ['api', API], { encoding: 'utf8' })).body ?? '';
}

/** Read the issue again, mark one article, and save, so no other edit is lost. */
function saveMark(slug, mark) {
  const body = markArticle(readBody(), slug, mark);
  if (CONFIG.dryRun) {
    console.log(`  Dry run, so the checklist is not changed. It would get: ${mark.check ? 'checked, ' : ''}${mark.notes.map((n) => `Note: ${n}`).join('; ')}`);
    return;
  }
  if (CONFIG.issueFile) {
    writeFileSync(CONFIG.issueFile, body);
    return;
  }
  const dir = mkdtempSync(join(tmpdir(), 'sumo-replace-'));
  try {
    const f = join(dir, 'body.md');
    writeFileSync(f, body);
    execFileSync('gh', ['api', '-X', 'PATCH', API, '-F', `body=@${f}`], { stdio: ['ignore', 'ignore', 'inherit'] });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------------------
// The linter
// ---------------------------------------------------------------------------

const LINT = join(REPO, 'target', 'debug', 'sumo-lint');
function lint(text) {
  const r = spawnSync(LINT, ['--format', 'json', '-'], { input: text, encoding: 'utf8' });
  try {
    return JSON.parse(r.stdout);
  } catch {
    throw new Error(`sumo-lint gave no JSON: ${r.stderr || r.stdout}`);
  }
}

// ---------------------------------------------------------------------------
// SUMO, through a real browser
// ---------------------------------------------------------------------------

let ctx;
let main; // the page you see and edit in
let req; // a second page on the SUMO origin that sends the requests (#61)

async function waitPastChallenge(page) {
  // Look for the challenge page's own marker, not at the title: robots.txt,
  // which the request page loads, has no title at all.
  for (let i = 0; i < 30; i++) {
    const html = await page.content().catch(() => '_fs-ch- Client Challenge');
    if (!isChallenge(html)) return;
    await sleep(1000);
  }
  throw new Error('Could not clear the Fastly challenge.');
}

/**
 * Navigate, with patience for a 429: on a navigation it shows only as
 * ERR_HTTP_RESPONSE_CODE_FAILURE, and an early retry prolongs the ban.
 */
async function go(page, url) {
  for (let attempt = 1; ; attempt++) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      await waitPastChallenge(page);
      return;
    } catch (e) {
      if (attempt >= 3) throw e;
      const wait = 120 * attempt;
      console.log(`  navigation failed (${String(e.message).split('\n')[0].slice(0, 60)}), waiting ${wait}s`);
      await sleep(wait * 1000);
    }
  }
}

/** GET a SUMO path with `fetch` in the request page. Returns { status, url, body }. */
async function get(path) {
  for (let attempt = 1; attempt <= 4; attempt++) {
    if (!req.url().startsWith(CONFIG.base)) await go(req, `${CONFIG.base}/robots.txt`);
    const r = await req.evaluate(async (u) => {
      const res = await fetch(u, { credentials: 'include' });
      return { status: res.status, url: res.url, retryAfter: res.headers.get('retry-after'), body: await res.text() };
    }, `${CONFIG.base}${path}`);
    if (r.status === 429) {
      const wait = Math.min((Number(r.retryAfter || 600) + 15) * attempt, 3600);
      console.log(`  rate limited (429), waiting ${wait}s quietly`);
      await sleep(wait * 1000);
      continue;
    }
    if (r.status >= 500) {
      await sleep(30_000 * attempt);
      continue;
    }
    if (isChallenge(r.body)) {
      await go(req, `${CONFIG.base}/robots.txt`);
      continue;
    }
    return r;
  }
  throw new Error(`Gave up on ${path} (rate limit or challenge kept recurring).`);
}

const editPath = (slug) => `/${CONFIG.locale}/kb/${encodeURIComponent(slug)}/edit`;
const historyPath = (slug) => `/${CONFIG.locale}/kb/${encodeURIComponent(slug)}/history`;

/**
 * Wait until the session can open an edit page, asking you to sign in if not.
 *
 * While you sign in, the script only watches the address of the window and
 * sends no request: polling the edit page every few seconds earned a 429 from
 * staging in the first trial (#62), in the middle of the sign-in. You are
 * signed in when the window is back on the edit page after the sign-in page.
 */
async function ensureSignedIn(slug) {
  const first = await get(editPath(slug));
  if (!first.url.includes('/users/auth')) return;
  const target = `${CONFIG.base}${editPath(slug)}`;
  console.log(`\nSign in to ${CONFIG.base} in the browser window: click Continue, then sign in.`);
  console.log('This script never reads your password, and it waits up to 15 minutes.');
  await go(main, `${CONFIG.base}/${CONFIG.locale}/users/auth?next=${encodeURIComponent(editPath(slug))}`);
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    await sleep(2000);
    if (main.url().split('?')[0] === target) {
      await waitPastChallenge(main);
      if ((await main.locator('textarea[name="content"]').count()) > 0) {
        console.log('Signed in.');
        return;
      }
    }
  }
  throw new Error('Timed out waiting for sign-in (15 min).');
}

/** The source and the based-on revision of an edit page, read in the request page. */
async function readEditForm(slug) {
  const r = await get(editPath(slug));
  if (r.url.includes('/users/auth')) throw new Error('signed out');
  if (r.status !== 200) throw new Error(`${editPath(slug)}: HTTP ${r.status}`);
  return req.evaluate((html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const ta = doc.querySelector('textarea[name="content"]');
    const based = doc.querySelector('input[name="based_on"]');
    // A textarea's value turns CRLF into LF, as CodeMirror does.
    return ta ? { source: ta.value.replace(/\r\n?/g, '\n'), basedOn: based ? based.value : null } : null;
  }, r.body);
}

// ---------------------------------------------------------------------------
// One article
// ---------------------------------------------------------------------------

const rl = createInterface({ input: process.stdin, output: process.stdout });

async function ask(q) {
  return (await rl.question(q)).trim();
}

/** Returns 'edited', 'nomatch', 'skipped', 'dry' (shown in a dry run) or 'quit'. */
async function doArticle(slug, strings, comment) {
  console.log(`\n=== ${slug}`);
  await ensureSignedIn(slug);
  const form = await readEditForm(slug);
  if (!form) {
    console.log('  The edit page has no source textarea. Skipping.');
    saveMark(slug, { check: false, notes: ['skipped: the edit page has no source textarea'] });
    return 'skipped';
  }
  const { text, counts, changes } = applyReplacements(form.source, strings);
  if (changes.length === 0) {
    console.log('  No match: no edit.');
    saveMark(slug, { check: true, notes: ['no match: no edit'] });
    return 'nomatch';
  }
  for (const line of describeChanges(form.source, changes)) console.log(`  ${line}`);
  console.log('');
  strings.forEach((s, i) => counts[i] && console.log(`  ${counts[i]} × "${s.from}" → "${s.to}"`));
  const added = newDiagnostics(lint(form.source), lint(text));
  if (added.length) {
    console.log('\n  The edit adds diagnostics, so it is not offered:');
    for (const d of added) console.log(`    line ${d.line}: ${d.code} ${d.message}`);
    saveMark(slug, {
      check: false,
      notes: [`not edited: the edit adds ${added.map((d) => `${d.code} on line ${d.line}`).join(', ')}`],
    });
    return 'skipped';
  }

  if (CONFIG.dryRun) {
    console.log(`\n  Dry run: ${changes.length} change(s) shown, the edit page is not filled.`);
    return 'dry';
  }

  for (;;) {
    const a = await ask(`\n  ${changes.length} change(s). y = fill the edit page, n REASON = skip, q = stop: `);
    if (a === 'q') return 'quit';
    if (a === 'n' || a.startsWith('n ')) {
      const reason = a.slice(1).trim() || 'no reason given';
      saveMark(slug, { check: false, notes: [`skipped: ${reason}`] });
      return 'skipped';
    }
    if (a === 'y') break;
  }

  // Someone may have edited the article while you read the changes.
  const now = await readEditForm(slug);
  if (!now || now.basedOn !== form.basedOn || now.source !== form.source) {
    console.log('  The article changed on SUMO while you checked. Not filled; run again.');
    saveMark(slug, { check: false, notes: ['not edited: the article changed on SUMO during the check; run again'] });
    return 'skipped';
  }
  const before = newestRevision((await get(historyPath(slug))).body, slug) ?? 0;

  await go(main, `${CONFIG.base}${editPath(slug)}`);
  await main.waitForSelector('.CodeMirror', { timeout: 60_000 });
  const filled = await main.evaluate(
    ({ text, comment, source }) => {
      const cm = document.querySelector('.CodeMirror').CodeMirror;
      if (cm.getValue() !== source) return 'the page shows other source than the script read';
      cm.setValue(text);
      cm.save();
      const c = document.querySelector('#id_comment');
      if (c) c.value = comment;
      return cm.getValue() === text && document.querySelector('#id_content').value === text ? 'ok' : 'the editor did not take the text';
    },
    { text, comment, source: form.source }
  );
  if (filled !== 'ok') {
    console.log(`  Not filled: ${filled}.`);
    saveMark(slug, { check: false, notes: [`not edited: ${filled}`] });
    return 'skipped';
  }
  console.log('\n  The edit page is filled, with the revision comment:');
  console.log(`    ${comment}`);
  console.log('  Check it in the browser (Preview shows the result), then click Submit for Review and Submit.');
  console.log('  The script waits for the new revision. Type s and Enter here to skip instead.');

  let skipped = false;
  const onLine = (line) => {
    if (line.trim() === 's') skipped = true;
  };
  rl.on('line', onLine);
  let revision = null;
  const deadline = Date.now() + 60 * 60_000;
  while (!revision && !skipped && Date.now() < deadline) {
    await sleep(5000);
    if (skipped) break;
    // Only look while the page has left the edit form, so a fetch never races the save.
    if (main.url().includes('/edit')) continue;
    const n = newestRevision((await get(historyPath(slug))).body, slug);
    if (n && n > before) revision = n;
  }
  rl.off('line', onLine);
  if (!revision) {
    console.log('  No new revision. Skipped.');
    saveMark(slug, { check: false, notes: ['skipped: filled, but no new revision was saved'] });
    return 'skipped';
  }
  const url = `${CONFIG.base}/${CONFIG.locale}/kb/${slug}/revision/${revision}`;
  const n = changes.length;
  console.log(`  Saved as revision ${revision}: ${url}`);
  saveMark(slug, { check: true, notes: [`revision ${revision}, ${n} replacement${n === 1 ? '' : 's'}: ${url}`] });
  return 'edited';
}

// ---------------------------------------------------------------------------

async function run() {
  const { strings, articles } = parseIssue(readBody());
  const todo = articles.filter((a) => !a.checked);
  console.log(`${strings.length} strings, ${articles.length} articles, ${todo.length} not checked yet.`);
  if (todo.length === 0) {
    console.log('Every article item is already checked: nothing to do.');
    return;
  }
  const n = issueUrl.match(/\/issues\/(\d+)$/)?.[1];
  const comment = CONFIG.comment ?? `String changes from ${issueUrl}`;
  console.log(`Base: ${CONFIG.base}   locale: ${CONFIG.locale}   issue: ${n ? `#${n}` : issueUrl}`);

  execFileSync('cargo', ['build', '-q', '-p', 'sumo-lint-cli'], { cwd: REPO, stdio: 'inherit' });

  ctx = await chromium.launchPersistentContext(CONFIG.profileDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    // Load-bearing: the Fastly challenge gates on navigator.webdriver.
    args: ['--disable-blink-features=AutomationControlled'],
  });
  main = ctx.pages()[0] ?? (await ctx.newPage());
  req = await ctx.newPage();
  await main.bringToFront();
  await go(main, `${CONFIG.base}/${CONFIG.locale}/`);

  const tally = { edited: 0, nomatch: 0, skipped: 0, dry: 0 };
  let stopped = false;
  for (const a of todo) {
    const r = await doArticle(a.slug, strings, comment);
    if (r === 'quit') {
      stopped = true;
      break;
    }
    tally[r]++;
  }
  const done = tally.edited + tally.nomatch + tally.skipped + tally.dry;
  console.log(
    `\n${CONFIG.dryRun ? `Dry run: ${tally.dry} with changes to make, ` : `${tally.edited} edited, `}` +
      `${tally.nomatch} with no match, ${tally.skipped} skipped, ` +
      `${todo.length - done} not reached${stopped ? ' (you stopped)' : ''}.`
  );
}

try {
  await run();
} catch (e) {
  console.error(`\nFAILED: ${e.message}`);
  process.exitCode = 1;
} finally {
  rl.close();
  await ctx?.close();
}
