/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Audits the scraped corpus and writes corpus/report.md.
 *
 * Two jobs:
 *  1. Which markup constructs do Thunderbird articles actually use? Rules for
 *     constructs nobody uses are wasted effort.
 *  2. Which suspicious patterns actually occur, and how often? This ranking —
 *     not guesswork — decides which phase-1 rules get built first.
 *
 * Every "suspicious" count here is a *candidate*, produced by a deliberately
 * crude regex. Some will be false positives; that is what the checkpoint review
 * is for. Nothing in this file is the linter.
 *
 * Known limits, measured on the real corpus — do NOT file bugs from this output
 * without reading the source lines first:
 *   - Blanking <code>/<pre> keeps "===" inside a .reg example from looking like
 *     a heading, but it also deletes {/note} closers and list content that live
 *     inside code spans, manufacturing fake "unclosed {note}" and "empty list
 *     item" hits.
 *   - Of 6 candidates this script first reported as errors, only 3 were real.
 * Regexes cannot both respect and ignore a region at once. That is precisely
 * what the real linter's parser is for; this file is triage, not truth.
 */

import { readFile, writeFile, readdir } from 'node:fs/promises';
import { resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CORPUS = resolve(HERE, '../../corpus');

// Verified against kitsune/sumo/parser.py (IMAGE_PARAMS).
const IMAGE_PARAMS = ['alt', 'align', 'caption', 'valign', 'frame', 'page', 'link', 'width', 'height'];

const countOf = (text, re) => (text.match(re) || []).length;

/** Strip regions where wiki markup is not interpreted, to cut false positives. */
function stripUninterpreted(text) {
  // <code>/<pre> matter too: a real article had a Windows .reg example whose
  // literal "===" was reported as a malformed heading. Verify before believing.
  return text
    .replace(/<nowiki>[\s\S]*?<\/nowiki>/gi, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/<code>[\s\S]*?<\/code>/gi, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/<pre>[\s\S]*?<\/pre>/gi, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, ' '));
}

function constructs(text) {
  const t = stripUninterpreted(text);
  const c = {};
  c['heading ='] = countOf(t, /^\s*=+[^=\n]+=+\s*$/gm);
  c['{for}'] = countOf(t, /\{for\b[^}]*\}/g);
  c['{/for}'] = countOf(t, /\{\/for\}/g);
  c['{note}'] = countOf(t, /\{note\}/g);
  c['{warning}'] = countOf(t, /\{warning\}/g);
  c['{key}'] = countOf(t, /\{key\s[^}]*\}/g);
  c['{button}'] = countOf(t, /\{button\s[^}]*\}/g);
  c['{menu}'] = countOf(t, /\{menu\s[^}]*\}/g);
  c['{filepath}'] = countOf(t, /\{filepath\s[^}]*\}/g);
  c['{pref}'] = countOf(t, /\{pref\s[^}]*\}/g);
  c['[[Template:]] / [[T:]]'] = countOf(t, /\[\[(?:Template|T):[^\]]*\]\]/gi);
  c['[[Include:]] / [[I:]]'] = countOf(t, /\[\[(?:Include|I):[^\]]*\]\]/gi);
  c['[[Image:]]'] = countOf(t, /\[\[Image:[^\]]*\]\]/gi);
  c['[[Video:]] / [[V:]]'] = countOf(t, /\[\[(?:Video|V):[^\]]*\]\]/gi);
  c['[[UI:]]'] = countOf(t, /\[\[UI:[^\]]*\]\]/gi);
  c['internal link [[...]]'] = countOf(t, /\[\[(?!(?:Template|T|Include|I|Image|Video|V|UI):)[^\]]*\]\]/gi);
  c['external link [http]'] = countOf(t, /\[https?:\/\/[^\]]*\]/g);
  c["bold '''"] = countOf(t, /'''/g);
  c["italic ''"] = countOf(t, /(?<!')''(?!')/g);
  c['table {|'] = countOf(t, /^\s*\{\|/gm);
  c['list item'] = countOf(t, /^\s*[*#]+/gm);
  c['definition ;'] = countOf(t, /^\s*;/gm);
  c['__TOC__'] = countOf(t, /__TOC__/g);
  c['<nowiki>'] = countOf(text, /<nowiki>/gi);
  c['<!-- comment -->'] = countOf(text, /<!--/g);
  c['template arg {{{n}}}'] = countOf(t, /\{\{\{[^{}]+\}\}\}/g);
  c['raw HTML tag'] = countOf(t, /<(?:br|u|sup|sub|s|del|code|blockquote|pre|li|ul|ol|b|i|span|div)\b[^>]*>/gi);
  c['REDIRECT'] = countOf(t, /^\s*REDIRECT\b/gim);
  c['---- hr'] = countOf(t, /^-{4,}\s*$/gm);
  return c;
}

function suspicious(text) {
  const t = stripUninterpreted(text);
  const lines = t.split('\n');
  const s = {};
  const add = (k, n) => { if (n) s[k] = (s[k] || 0) + n; };

  // Block delimiter balance.
  add('unclosed/extra {for}', Math.abs(countOf(t, /\{for\b[^}]*\}/g) - countOf(t, /\{\/for\}/g)));
  add('unclosed/extra {note}', Math.abs(countOf(t, /\{note\}/g) - countOf(t, /\{\/note\}/g)));
  add('unclosed/extra {warning}', Math.abs(countOf(t, /\{warning\}/g) - countOf(t, /\{\/warning\}/g)));

  // Headings.
  let asym = 0, padded = 0;
  for (const line of lines) {
    const m = line.match(/^\s*(=+)([^=\n]*)(=+)\s*$/);
    if (!m) continue;
    if (m[1].length !== m[3].length) asym++;
    // Do NOT call either form "correct": the corpus splits 53.5% `= H =` vs
    // 45.0% `=H=`, so there is no established convention to deviate from.
    // This counts inconsistency for phase 2 to settle, not errors.
    if (m[2] !== ` ${m[2].trim()} `) padded++;
  }
  add('asymmetric heading = count', asym);
  add('heading spacing differs from `= H =` (no corpus-wide norm exists)', padded);

  // Emphasis balance per PARAGRAPH, not per line. Bold-italic legitimately
  // spans several lines ('''''intro ... list items ...'''''), so per-line
  // counting reported both ends of a correctly balanced span as errors.
  add(
    "odd number of ''' in a paragraph",
    t.split(/\n\s*\n/).filter((para) => countOf(para, /'''/g) % 2 === 1).length
  );

  // Image params outside the verified allowlist.
  let badParam = 0;
  for (const m of t.matchAll(/\[\[Image:([^\]]*)\]\]/gi)) {
    const parts = m[1].split('|').slice(1);
    for (const p of parts) {
      const key = p.split('=')[0].trim().toLowerCase();
      if (key && !IMAGE_PARAMS.includes(key)) badParam++;
    }
  }
  add('unknown [[Image:]] param', badParam);

  // Whitespace hygiene (mostly phase-2 material, but worth measuring now).
  // Whitespace hygiene is about literal bytes, so measure the ORIGINAL text.
  // Measuring the stripped copy inflated this: blanking a block turned code
  // content at end-of-line into fabricated trailing spaces.
  add('trailing whitespace', text.split('\n').filter((l) => /[ \t]+$/.test(l)).length);
  add('3+ consecutive blank lines', countOf(text, /\n[ \t]*\n[ \t]*\n[ \t]*\n/g));
  add('tab character', countOf(text, /\t/g));
  add('CRLF line ending', countOf(text, /\r\n/g));

  // Likely-malformed constructs.
  add('{key} with lowercase modifier', countOf(t, /\{key\s+(?:ctrl|alt|shift|cmd)\b[^}]*\}/g));
  add('space inside {tag } open', countOf(t, /\{\s+(?:for|note|warning|key|button|menu)\b/g));
  add('Markdown link (wrong syntax)', countOf(t, /\[[^\]]+\]\([^)]+\)/g));
  add('Markdown bold ** (wrong syntax)', countOf(t, /\*\*[^*\n]+\*\*/g));
  // No "Markdown heading" check: in SUMO markup `#` is the ordered-list marker,
  // so `# Text` is valid wiki and indistinguishable from a Markdown heading.
  // Likewise `*` is an unordered-list marker, not emphasis.
  add('unclosed [[', Math.abs(countOf(t, /\[\[/g) - countOf(t, /\]\]/g)));
  add('empty list item', lines.filter((l) => /^\s*[*#]+\s*$/.test(l)).length);

  return s;
}

async function main() {
  const idxRaw = await readFile(resolve(CORPUS, 'index.json'), 'utf8').catch(() => null);
  if (!idxRaw) {
    console.error('No corpus/index.json — run `npm run scrape` first.');
    process.exit(1);
  }
  const idx = JSON.parse(idxRaw);
  const srcDir = resolve(CORPUS, idx.locale);
  const files = (await readdir(srcDir)).filter((f) => f.endsWith('.wiki'));
  if (!files.length) {
    console.error(`No .wiki files in ${srcDir}.`);
    process.exit(1);
  }

  const totalConstructs = {}, totalSusp = {};
  const articlesWith = {}, perArticle = [];
  let bytes = 0;

  for (const f of files) {
    const text = await readFile(resolve(srcDir, f), 'utf8');
    bytes += text.length;
    const c = constructs(text), s = suspicious(text);
    for (const [k, v] of Object.entries(c)) {
      totalConstructs[k] = (totalConstructs[k] || 0) + v;
      if (v) articlesWith[k] = (articlesWith[k] || 0) + 1;
    }
    for (const [k, v] of Object.entries(s)) totalSusp[k] = (totalSusp[k] || 0) + v;
    const flagged = Object.values(s).reduce((a, b) => a + b, 0);
    perArticle.push({ slug: basename(f, '.wiki'), bytes: text.length, flagged, detail: s });
  }

  const desc = (o) => Object.entries(o).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const L = [];
  L.push('# Thunderbird KB corpus audit\n');
  L.push(`Source: \`${idx.base}\` · locale \`${idx.locale}\` · products ${idx.products.map((p) => `\`${p}\``).join(', ')}`);
  L.push(`\n**${files.length} articles**, ${(bytes / 1024).toFixed(1)} KiB of raw wiki markup.\n`);

  L.push('## Constructs in use\n');
  L.push('Rules only matter for constructs that appear here.\n');
  L.push('| Construct | Occurrences | Articles |');
  L.push('|---|---:|---:|');
  for (const [k, v] of desc(totalConstructs)) L.push(`| \`${k}\` | ${v} | ${articlesWith[k] || 0} |`);

  const unused = Object.entries(totalConstructs).filter(([, v]) => v === 0).map(([k]) => k);
  if (unused.length) L.push(`\n**Unused:** ${unused.map((u) => `\`${u}\``).join(', ')} — deprioritize.\n`);

  L.push('\n## Candidate rules, ranked by real frequency\n');
  L.push('Regex-derived candidates, not verdicts. Review before promoting any to a rule.\n');
  L.push('| Candidate | Hits |');
  L.push('|---|---:|');
  for (const [k, v] of desc(totalSusp)) L.push(`| ${k} | ${v} |`);

  L.push('\n## Articles with the most flags\n');
  L.push('Good first review targets — and the harshest test cases.\n');
  L.push('| Article | Bytes | Flags | Top reasons |');
  L.push('|---|---:|---:|---|');
  for (const a of perArticle.sort((x, y) => y.flagged - x.flagged).slice(0, 20)) {
    const top = desc(a.detail).slice(0, 3).map(([k, v]) => `${k} (${v})`).join('; ');
    L.push(`| \`${a.slug}\` | ${a.bytes} | ${a.flagged} | ${top || '—'} |`);
  }

  const failures = (idx.articles || []).filter((a) => String(a.status).startsWith('failed'));
  if (failures.length) {
    L.push('\n## Fetch failures\n');
    for (const f of failures) L.push(`- \`${f.slug}\` — ${f.status}`);
  }

  const out = resolve(CORPUS, 'report.md');
  await writeFile(out, L.join('\n') + '\n', 'utf8');
  console.log(`Wrote ${out}`);
  console.log(`${files.length} articles · ${Object.keys(totalSusp).length} candidate rule types`);
}

main().catch((e) => { console.error(e); process.exit(1); });
