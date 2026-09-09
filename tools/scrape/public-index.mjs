/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

/**
 * Write corpus/index.public.json — the committed index, drafts removed.
 *
 * "Public" is not a field the API gives you. It is decided the only way it can
 * be: by asking what an anonymous visitor sees. The signed-in listing returns
 * every article an admin may read, including unpublished drafts; the anonymous
 * listing returns what SUMO has actually published. The difference is exactly
 * what must never be committed to a public repository.
 *
 *   node scrape.mjs --list-only --profile /tmp/anon-profile > /tmp/anon.txt
 *   node public-index.mjs /tmp/anon.txt
 *
 * The first command must use a throwaway profile: the saved session in `.auth/`
 * would show the admin view and quietly mark the drafts public.
 */

import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CORPUS = resolve(HERE, '../../corpus');

const anonFile = process.argv[2];
if (!anonFile) {
  console.error('usage: node public-index.mjs <anonymous-listing.txt>');
  process.exit(2);
}

// The listing is `slug<TAB>products<TAB>title`, with progress lines mixed in.
const anon = new Set(
  (await readFile(anonFile, 'utf8'))
    .split('\n')
    .filter((l) => l.includes('\t'))
    .map((l) => l.split('\t')[0].trim())
    .filter(Boolean)
);
if (anon.size === 0) {
  console.error(`${anonFile} contained no slugs — was it produced by --list-only?`);
  process.exit(1);
}

const index = JSON.parse(await readFile(resolve(CORPUS, 'index.json'), 'utf8'));
const articles = index.articles.filter((a) => anon.has(a.slug));
const withheld = index.articles.filter((a) => !anon.has(a.slug)).map((a) => a.slug);

await writeFile(
  resolve(CORPUS, 'index.public.json'),
  JSON.stringify(
    {
      base: index.base,
      locale: index.locale,
      products: index.products,
      note: 'Public articles only; non-public drafts excluded by design.',
      count: articles.length,
      articles,
    },
    null,
    2
  ) + '\n',
  'utf8'
);

console.log(`index.public.json: ${articles.length} public of ${index.articles.length}`);
console.log(`withheld (${withheld.length}):`);
for (const s of withheld) console.log(`  ${s}`);
