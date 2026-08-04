/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Corpus fetcher for sumo-linter (dev-only; not part of the shipped linter).
 *
 * Three hard-won constraints shape this file:
 *
 * 1. Both prod and staging sit behind a Fastly client challenge that answers
 *    every plain request — including /api/1/kb/ — with a JS interstitial titled
 *    "Client Challenge". Only a real browser clears it, and only with
 *    automation fingerprinting disabled (see the launch args). The pass cookie
 *    is short-lived (hours), so the challenge can reappear mid-run.
 *
 * 2. Raw wiki source is not public anywhere. The API returns rendered `html`;
 *    source lives only in <textarea name="content"> on /<locale>/kb/<slug>/edit,
 *    which redirects anonymous users to /users/auth. Login is unavoidable.
 *
 * 3. SUMO rate-limits hard: 429 with Retry-After: 600, and requests made during
 *    a ban appear to restart the window. Waiting quietly is the only cure.
 *
 * All network I/O goes through fetchPath(), which uses the browser *context's*
 * request API rather than in-page fetch(). That matters: an earlier version ran
 * relative fetch() inside the page, so when the page navigated to Mozilla
 * Accounts during login, those requests hit the wrong origin and crashed.
 * Context requests share the cookie jar but are independent of page navigation.
 *
 *   node scrape.mjs --login    # opens a window; you sign in by hand, once
 *   node scrape.mjs            # fetches the corpus, resumable
 *   node scrape.mjs --limit 3  # trial run
 */

import { chromium } from 'playwright';
import { mkdir, writeFile, readFile, access } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../..');

const argv = process.argv.slice(2);
const flag = (name, dflt = null) => {
  const i = argv.indexOf(`--${name}`);
  if (i === -1) return dflt;
  const next = argv[i + 1];
  return next && !next.startsWith('--') ? next : true;
};

const CONFIG = {
  base: String(flag('base', 'https://support.allizom.org')).replace(/\/$/, ''),
  locale: flag('locale', 'en-US'),
  products: String(flag('products', 'thunderbird,thunderbird-android')).split(','),
  delayMs: Number(flag('delay', 3000)),
  limit: Number(flag('limit', 0)) || Infinity,
  rendered: argv.includes('--rendered'),
  // --channel chrome uses installed Google Chrome instead of bundled Chromium.
  // Does NOT help with rate limiting (that's IP-based) and picks up no login
  // from your personal profile. Bundled Chromium is the tested default.
  channel: flag('channel', null),
  profileDir: resolve(REPO, '.auth/chromium-profile'),
  outDir: resolve(REPO, 'corpus'),
  loginOnly: argv.includes('--login'),
  force: argv.includes('--force'),
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const exists = (p) => access(p).then(() => true, () => false);
const isChallenge = (body) => body.includes('Client Challenge') && body.includes('_fs-ch-');

/**
 * Wait out an edge ban BEFORE any page navigation.
 *
 * Critical ordering: solveChallenge() uses page.goto(), which cannot see a 429
 * as a status code (it surfaces as ERR_HTTP_RESPONSE_CODE_FAILURE) and cannot
 * read Retry-After. Navigating during a ban restarts the 600s window, so an
 * impatient retry loop there can never succeed. This probe uses a context
 * request — one call, then a full quiet wait.
 */
async function ensureNotRateLimited(ctx) {
  for (let cycle = 1; cycle <= 3; cycle++) {
    let res;
    try {
      res = await ctx.request.get(`${CONFIG.base}/${CONFIG.locale}/`, { maxRedirects: 0, timeout: 30_000 });
    } catch {
      return; // transient network problem — let the normal flow report it
    }
    if (res.status() !== 429) return;
    const ra = Number(res.headers()['retry-after'] || 600);
    const wait = Math.min(ra + 15, 900);
    console.log(`Edge is rate limiting (429, Retry-After: ${ra}s).`);
    console.log(`Waiting ${wait}s quietly — any request now would restart the window.`);
    await sleep(wait * 1000);
  }
  throw new Error(
    `Still rate limited on ${CONFIG.base}. Wait longer, or use --base https://support.mozilla.org (separate limit bucket).`
  );
}

/** Clear the Fastly challenge in a real page; the cookie then covers context requests too. */
async function solveChallenge(ctx, page) {
  const title = async () => {
    try { return await page.title(); } catch { return 'Client Challenge'; }
  };
  let backoff = 30_000;
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      const resp = await page.goto(`${CONFIG.base}/${CONFIG.locale}/`, { waitUntil: 'domcontentloaded' });
      if (resp && resp.status() === 429) throw new Error('HTTP 429');
      for (let i = 0; i < 20; i++) {
        const t = await title();
        if (t && t !== 'Client Challenge') return;
        await sleep(1000);
      }
    } catch (e) {
      // A blocked navigation is almost always a 429 in disguise. Re-probe via a
      // context request so we can read the real status and Retry-After, and wait
      // that long instead of guessing — guessing short restarts the ban.
      const why = String(e.message).split('\n')[0].slice(0, 60);
      console.log(`  navigation blocked (${why})`);
      await ensureNotRateLimited(ctx);
      await sleep(backoff);
      backoff = Math.min(backoff * 2, 120_000);
    }
  }
  throw new Error('Could not clear the Fastly challenge.');
}

/**
 * Single funnel for every request. Handles, in one place:
 *   - 429: waits the full Retry-After quietly (polling restarts the ban window)
 *   - challenge interstitial: re-solves in the page, then retries
 * Returns { status, url, body }. `url` is post-redirect, for auth detection.
 */
async function fetchPath(ctx, page, path) {
  const url = path.startsWith('http') ? path : `${CONFIG.base}${path}`;
  for (let attempt = 1; attempt <= 4; attempt++) {
    let res;
    try {
      res = await ctx.request.get(url, { timeout: 45_000 });
    } catch (e) {
      if (attempt === 4) throw e;
      await sleep(5000);
      continue;
    }
    if (res.status() === 429) {
      const ra = Number(res.headers()['retry-after'] || 600);
      const wait = Math.min(ra + 15, 900);
      console.log(`  rate limited (429, Retry-After: ${ra}s) — waiting ${wait}s quietly`);
      await sleep(wait * 1000);
      continue;
    }
    const body = await res.text();
    if (isChallenge(body)) {
      console.log('  challenge cookie expired — re-solving');
      await solveChallenge(ctx, page);
      continue;
    }
    return { status: res.status(), url: res.url(), body };
  }
  throw new Error(`Gave up on ${url} (rate limit or challenge kept recurring).`);
}

/**
 * true / false — is this session authenticated?
 *
 * Determined by whether the edit page redirects to /users/auth. Note the trap
 * that burned an earlier version: a 429 also fails to redirect, so it was read
 * as "signed in" while actually anonymous. fetchPath() now absorbs 429s before
 * we ever get here, so a non-redirect genuinely means authenticated.
 */
async function loginState(ctx, page) {
  const r = await fetchPath(ctx, page, `/${CONFIG.locale}/kb/markup-chart/edit`);
  return !r.url.includes('/users/auth');
}

/** Read back the actual username — never infer identity from a missing redirect. */
async function whoami(ctx, page) {
  const r = await fetchPath(ctx, page, `/${CONFIG.locale}/`);
  const m = r.body.match(/\/user\/([A-Za-z0-9._%-]+)/);
  return { hasLogout: /\/users\/logout/.test(r.body), username: m ? m[1] : null };
}

async function login(ctx, page) {
  console.log('\nOpening the SUMO login page.');
  console.log('Sign in in the browser window (including any 2FA), then come back here.');
  console.log('Your credentials stay in the browser — this script never reads them.\n');
  await page.goto(`${CONFIG.base}/${CONFIG.locale}/users/auth`, { waitUntil: 'domcontentloaded' });

  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    await sleep(4000);
    // Context requests are immune to the page being on the Mozilla Accounts
    // origin mid-login, which used to crash this poll with "Failed to fetch".
    let signedIn = false;
    try { signedIn = await loginState(ctx, page); } catch { /* keep waiting */ }
    if (signedIn) {
      const who = await whoami(ctx, page);
      console.log(`\nSigned in as: ${who.username ?? '(username not detected)'}`);
      console.log('Session saved to .auth/ (gitignored).');
      return true;
    }
  }
  throw new Error('Timed out waiting for sign-in (15 min).');
}

/**
 * Enumerate a product's articles.
 * The param is singular `product=`. `products=` is silently ignored and returns
 * the entire 1493-article KB — an invisible mistake.
 */
async function listArticles(ctx, page, product) {
  const out = [];
  let path = `/api/1/kb/?product=${encodeURIComponent(product)}`;
  while (path) {
    const r = await fetchPath(ctx, page, path);
    if (r.status !== 200) throw new Error(`list ${path} -> HTTP ${r.status}`);
    const j = JSON.parse(r.body);
    out.push(...(j.results || []));
    path = j.next;
    if (path) await sleep(CONFIG.delayMs);
  }
  return out;
}

/** Public API detail: metadata plus Kitsune's own rendered HTML (the free oracle). */
async function fetchRendered(ctx, page, slug) {
  const r = await fetchPath(ctx, page, `/api/1/kb/${encodeURIComponent(slug)}`);
  if (r.status !== 200) return { ok: false, status: r.status };
  return { ok: true, doc: JSON.parse(r.body) };
}

/**
 * Raw wiki source from the edit form's textarea.
 * The HTML is fetched via the context, then parsed in the page purely as a
 * string — DOMParser gives correct entity decoding without hand-rolling one.
 */
async function fetchSource(ctx, page, locale, slug) {
  const r = await fetchPath(ctx, page, `/${locale}/kb/${encodeURIComponent(slug)}/edit`);
  if (r.url.includes('/users/auth')) return { ok: false, reason: 'auth-required' };
  if (r.status !== 200) return { ok: false, reason: `http-${r.status}` };

  return page.evaluate((html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    let ta = doc.querySelector('textarea[name="content"]');
    let via = 'textarea[name=content]';
    if (!ta) {
      const all = [...doc.querySelectorAll('textarea')].sort(
        (a, b) => (b.value || b.textContent || '').length - (a.value || a.textContent || '').length
      );
      ta = all[0];
      via = ta ? `fallback:largest-textarea[name=${ta.getAttribute('name')}]` : 'none';
    }
    if (!ta) return { ok: false, reason: 'no-textarea' };
    return { ok: true, via, content: ta.value || ta.textContent || '' };
  }, r.body);
}

async function main() {
  await mkdir(CONFIG.profileDir, { recursive: true });
  const ctx = await chromium.launchPersistentContext(CONFIG.profileDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    // Required, and measured — not cargo-culted. The Fastly challenge gates on
    // `navigator.webdriver`; this flag makes it false. Verified empirically:
    // bundled Chromium + this flag clears the challenge, while channel:'chrome'
    // WITHOUT it stays blocked forever. Drop this and the scraper stops working.
    args: ['--disable-blink-features=AutomationControlled'],
    ...(CONFIG.channel ? { channel: String(CONFIG.channel) } : {}),
  });
  const page = ctx.pages()[0] ?? (await ctx.newPage());

  try {
    console.log(`Base: ${CONFIG.base}   locale: ${CONFIG.locale}   delay: ${CONFIG.delayMs}ms`);
    await ensureNotRateLimited(ctx);
    await solveChallenge(ctx, page);
    console.log('Past the Fastly challenge.');

    const signedIn = await loginState(ctx, page);
    if (CONFIG.loginOnly) {
      if (signedIn) {
        const who = await whoami(ctx, page);
        console.log(`Already signed in as: ${who.username ?? '(username not detected)'}`);
      } else {
        await login(ctx, page);
      }
      return;
    }
    if (!signedIn) {
      throw new Error('Not signed in. Run `npm run login` first (opens a window for you to sign in).');
    }
    const who = await whoami(ctx, page);
    console.log(`Signed in as: ${who.username ?? '(username not detected)'}`);

    // Enumerate. A slug can belong to both products, so dedupe.
    const bySlug = new Map();
    for (const product of CONFIG.products) {
      const items = await listArticles(ctx, page, product);
      console.log(`  ${product}: ${items.length} articles`);
      for (const it of items) {
        const prev = bySlug.get(it.slug);
        if (prev) prev.products.push(product);
        else bySlug.set(it.slug, { ...it, products: [product] });
      }
      await sleep(CONFIG.delayMs);
    }
    const articles = [...bySlug.values()].slice(0, CONFIG.limit);
    console.log(`${articles.length} unique articles to fetch.\n`);

    const srcDir = resolve(CONFIG.outDir, CONFIG.locale);
    const renderedDir = resolve(CONFIG.outDir, 'rendered', CONFIG.locale);
    await mkdir(srcDir, { recursive: true });
    await mkdir(renderedDir, { recursive: true });

    const index = [];
    let done = 0, skipped = 0, failed = 0;

    for (const art of articles) {
      const srcPath = resolve(srcDir, `${art.slug}.wiki`);
      const relSrc = `corpus/${CONFIG.locale}/${art.slug}.wiki`;

      if (!CONFIG.force && (await exists(srcPath))) {
        skipped++;
        index.push({ ...art, locale: CONFIG.locale, status: 'cached', source: relSrc });
        continue;
      }

      const src = await fetchSource(ctx, page, CONFIG.locale, art.slug);
      if (!src.ok) {
        failed++;
        console.log(`  ✗ ${art.slug} — ${src.reason}`);
        index.push({ ...art, locale: CONFIG.locale, status: `failed:${src.reason}` });
        if (src.reason === 'auth-required') {
          throw new Error('Session expired mid-run. Re-run with --login.');
        }
        await sleep(CONFIG.delayMs);
        continue;
      }
      await writeFile(srcPath, src.content, 'utf8');

      // The rendered-HTML oracle doubles the request count against a limiter we
      // have already tripped, and is not needed for the bucket-1 audit.
      let rend = { ok: false };
      let relRendered = null;
      if (CONFIG.rendered) {
        rend = await fetchRendered(ctx, page, art.slug);
        if (rend.ok) {
          relRendered = `corpus/rendered/${CONFIG.locale}/${art.slug}.html`;
          await writeFile(resolve(renderedDir, `${art.slug}.html`), rend.doc.html ?? '', 'utf8');
        }
        await sleep(CONFIG.delayMs);
      }

      done++;
      index.push({
        ...art,
        locale: CONFIG.locale,
        status: 'ok',
        via: src.via,
        bytes: src.content.length,
        source: relSrc,
        rendered: relRendered,
        title: rend.ok ? rend.doc.title : art.title,
        topics: rend.ok ? rend.doc.topics : undefined,
      });
      console.log(`  ✓ ${art.slug} (${src.content.length} B)`);
      await sleep(CONFIG.delayMs);
    }

    await writeFile(
      resolve(CONFIG.outDir, 'index.json'),
      JSON.stringify(
        { base: CONFIG.base, locale: CONFIG.locale, products: CONFIG.products, articles: index },
        null, 2
      ),
      'utf8'
    );

    console.log(`\nfetched ${done}   cached ${skipped}   failed ${failed}`);
    console.log('corpus/index.json written. Next: npm run report');
  } finally {
    await ctx.close();
  }
}

main().catch((err) => {
  console.error(`\nFAILED: ${err.message}`);
  process.exit(1);
});
