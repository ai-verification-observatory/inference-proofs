// Preview cards: PLAYWRIGHT_MODULE=<path to playwright/index.mjs> node og.mjs, then rebuild the site
// (OG_CHANNEL=chrome runs an installed Chrome instead of Playwright's own browser)
// (README §Build and check). Renders each og/<card>.html that the build wrote to og/<card>.png and
// records the sha256 of both in og/cards.json; the build then names each picture in the pages. A card is 1200 x 630 CSS px at 2x
// unless its <html> sets data-w, data-h and data-scale (the 180 px touch icon). A page whose card
// is not in the record names the home card. Fonts load from ../fonts/, so it needs no network.
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
  // nothing may spill past the card's edges (the system name is cut at the band's bottom on purpose,
  // so inside the band only its left and right count), and the name must clear the band's corner text
  const bad = await p.evaluate(([W, H]) => {
    const out = [];
    for (const n of document.querySelectorAll('body *')) {
      const r = n.getBoundingClientRect();
      if (!r.width) continue;
      const inBand = !!n.closest('.band');
      if (r.left < -0.5 || r.right > W + 0.5 || (!inBand && (r.top < -0.5 || r.bottom > H + 0.5))) out.push(`past the edge: ${n.className.baseVal ?? n.className}`);
    }
    const name = document.querySelector('.band .name');
    const meta = document.querySelector('.band .meta');
    if (name && meta) {
      const a = name.getBoundingClientRect();
      const m = meta.getBoundingClientRect();
      if (a.right > m.left - 24) out.push(`the name runs into the corner text (${Math.round(a.right)} > ${Math.round(m.left - 24)})`);
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
