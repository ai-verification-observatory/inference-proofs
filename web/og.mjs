// Preview cards: PLAYWRIGHT_MODULE=<path to playwright/index.mjs> node og.mjs, then rebuild the site
// (OG_CHANNEL=chrome runs an installed Chrome instead of Playwright's own browser)
// (README §Build and check). Renders each og/<card>.html that the build wrote to og/<card>.png and
// records the sha256 of both in og/cards.json; the build then names each picture in the pages. A card is 1200 x 630 CSS px at 2x
// unless its <html> sets data-w, data-h and data-scale (the 180 px touch icon). A page whose card
// is not in the record, or was rendered from another source, names the home card. Fonts load from
// ../fonts/, so it needs no network.
import crypto from 'node:crypto';
import fs from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const DIR = fileURLToPath(new URL('./og/', import.meta.url));
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const cards = fs.readdirSync(DIR).filter((f) => f.endsWith('.html')).map((f) => f.slice(0, -5)).sort();
if (!cards.length) throw new Error('no card sources in og/: build the site first (README §Build and check)');

const b = await chromium.launch(process.env.OG_CHANNEL ? { channel: process.env.OG_CHANNEL } : {});
const record = {};
for (const card of cards) {
  const src = `${DIR}${card}.html`;
  const size = /<html[^>]*data-w="(\d+)" data-h="(\d+)" data-scale="(\d+)"/.exec(fs.readFileSync(src, 'utf8'));
  const [W, H, SCALE] = size ? size.slice(1).map(Number) : [1200, 630, 2];
  const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(String(e)));
  p.on('requestfailed', (r) => errs.push(`failed to load ${r.url()}`));
  await p.goto(pathToFileURL(src).href, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  if (!size) {
    const fonts = await p.evaluate(() => [...new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/"/g, '')))]);
    // every family the card sets text in must have loaded (the lockup is drawn in outline)
    const used = await p.evaluate(() => [...new Set([...document.querySelectorAll('body *')]
      .filter((n) => [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim()))
      .map((n) => getComputedStyle(n).fontFamily.split(',')[0].replace(/"/g, '').trim()))]);
    for (const want of used) {
      if (!fonts.includes(want)) throw new Error(`${card}: font ${want} did not load (loaded: ${fonts.join(', ') || 'none'})`);
    }
  }
  // nothing may spill past the card's edges, a box marked fit (a name, a figure) is as wide as its words, the
  // card's blocks overlap nothing, and what stands on the band starts inside it
  const bad = await p.evaluate(([W, H]) => {
    const out = [];
    const cls = (n) => n.className.baseVal ?? n.className;
    for (const n of document.querySelectorAll('body *')) {
      const r = n.getBoundingClientRect();
      if (!r.width) continue;
      if (r.left < -0.5 || r.right > W + 0.5 || r.top < -0.5 || r.bottom > H + 0.5) out.push(`past the edge: ${cls(n)}`);
    }
    for (const n of document.querySelectorAll('.fit')) {
      if (n.scrollWidth > n.clientWidth + 1) out.push(`runs past its box: ${cls(n)}`);
    }
    const blocks = [...document.body.children].map((n) => [n, n.getBoundingClientRect()]);
    blocks.forEach(([a, r], i) => blocks.slice(i + 1).forEach(([b, s]) => {
      if (r.left < s.right && s.left < r.right && r.top < s.bottom && s.top < r.bottom) out.push(`${cls(a)} overlaps ${cls(b)}`);
    }));
    const band = document.querySelector('.band');
    if (band) {
      const top = band.getBoundingClientRect().top + 16;
      for (const n of band.children) if (n.getBoundingClientRect().top < top) out.push(`too tall for the band: ${cls(n)}`);
    }
    return out;
  }, [W, H]);
  if (bad.length) throw new Error(`${card}: ${bad.slice(0, 5).join('; ')}`);
  if (errs.length) throw new Error(`${card}: ${errs.join('; ')}`);
  const png = `${DIR}${card}.png`;
  await p.screenshot({ path: png });
  record[card] = { png: sha(fs.readFileSync(png)), source: sha(fs.readFileSync(src)) };
  console.log(`og/${card}.png`, `${W * SCALE}x${H * SCALE}`, `${Math.round(fs.statSync(png).size / 1024)} kB`);
  await ctx.close();
}
await b.close();
// canonical JSON (iproofs fmt): sorted keys, two-space indent, a final newline
fs.writeFileSync(`${DIR}cards.json`, `${JSON.stringify(record, null, 2)}\n`);
