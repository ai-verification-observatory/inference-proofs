// Screenshots and checks: node shoot.mjs   (writes shots/*.png and shots/checks.txt)
// Env: BASE (default http://127.0.0.1:4421/), PLAYWRIGHT_MODULE (default "playwright"),
//      AXE_MODULE (default "@axe-core/playwright"; the axe checks are skipped, and say so, if it cannot be loaded).
import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
let AxeBuilder = null;
try { AxeBuilder = (await import(process.env.AXE_MODULE || '@axe-core/playwright')).default; } catch (_) { /* reported below */ }
const BASE = process.env.BASE || 'http://127.0.0.1:4440/';
const OUT = new URL('./shots/', import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });
const PAGES = ['index.html', 'flashprove.html', 'sash.html', 'reference.html'];
const b = await chromium.launch();
const errs = [];
const report = [];
let fails = 0;
const log = (...a) => { const s = a.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(' '); console.log(s); report.push(s); };
const ok = (cond, what, detail = '') => { if (!cond) fails++; log(`${cond ? 'ok  ' : 'FAIL'} ${what}${detail !== '' ? ' ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)) : ''}`); };

async function pg(w, h, o = {}) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, hasTouch: !!o.touch, isMobile: !!o.touch, reducedMotion: o.reduce ? 'reduce' : 'no-preference' });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push(`${w} ${p.url()}: ${e}`));
  p.on('console', (m) => { if (m.type() === 'error') errs.push(`${w} ${p.url()}: ${m.text()}`); });
  return { ctx, p };
}
const settle = 2200;
const overflow = (p) => p.evaluate(() => {
  const cw = document.documentElement.clientWidth;
  const wide = [...document.querySelectorAll('body *')].filter((n) => { const r = n.getBoundingClientRect(); return r.width && r.right > cw + 0.5 && getComputedStyle(n).visibility !== 'hidden'; })
    .map((n) => `${n.tagName}.${n.className.baseVal ?? n.className}`).slice(0, 6);
  const clipped = [...document.querySelectorAll('.val .vm, .plate .pv')].filter((n) => n.offsetParent && n.scrollWidth > n.clientWidth + 1).map((n) => n.textContent.trim().slice(0, 24));
  return { over: document.documentElement.scrollWidth - cw, wide, clipped };
});
// layout shifts not caused by input (what CLS counts)
const cls = (p) => p.evaluate(() => new Promise((res) => { let v = 0; new PerformanceObserver((l) => l.getEntries().forEach((e) => { if (!e.hadRecentInput) v += e.value; })).observe({ type: 'layout-shift', buffered: true }); setTimeout(() => res(+v.toFixed(4)), 400); }));
async function full(p, path) {
  const vp = p.viewportSize();
  const h = await p.evaluate(() => document.documentElement.scrollHeight);
  await p.setViewportSize({ width: vp.width, height: h }); await p.waitForTimeout(300);
  await p.screenshot({ path });
  await p.setViewportSize(vp);
}
// one order for every model's table: the rows of each table, table after table
const order = (p) => p.evaluate(() => [...document.querySelectorAll('.tbl')].map((t) => [...t.querySelectorAll('.rows > .row')].map((r) => r.id)));
// the expected order, computed here from data-k, independently of words.js
const expected = (p, col, dir) => p.evaluate(([col, dir]) => [...document.querySelectorAll('.tbl')].map((t) => {
  const rows = [...t.querySelectorAll('.rows > .row')].map((r) => ({ id: r.id, name: r.dataset.name, k: JSON.parse(r.dataset.k)[col] }));
  const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  if (col === 'system') return rows.sort((a, b) => (dir === 'asc' ? 1 : -1) * byName(a, b)).map((r) => r.id);
  const have = rows.filter((r) => r.k != null).sort((a, b) => (dir === 'asc' ? a.k - b.k : b.k - a.k) || byName(a, b));
  const none = rows.filter((r) => r.k == null).sort(byName);
  return [...have, ...none].map((r) => r.id);
}), [col, dir]);
const sortState = (p) => p.evaluate(() => ({
  aria: [...new Set([...document.querySelectorAll('.hc[aria-sort]')].map((h) => `${h.dataset.col}:${h.getAttribute('aria-sort')}`))],
  heads: document.querySelectorAll('.hc[aria-sort]').length,
  glyphs: [...document.querySelectorAll('.hc .g')].map((g) => g.textContent).join(''),
  hash: location.hash,
}));
// click a head until it sorts the wanted way
const sortBy = async (p, col, dir) => {
  for (let i = 0; i < 2; i++) {
    const s = await sortState(p);
    if (s.aria.join() === `${col}:${dir === 'asc' ? 'ascending' : 'descending'}`) return;
    await p.locator(`.tbl .sb[data-col="${col}"]`).last().click(); await p.waitForTimeout(260);
  }
};

// ---------------------------------------------------------------- home 1440: header, sections, hover
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await p.screenshot({ path: OUT + 'home-1440.png' });
  await full(p, OUT + 'home-1440-full.png');
  const mast = await p.evaluate(() => Math.round(document.querySelector('.mast').getBoundingClientRect().height));
  log('home-1440 header height', mast, 'px');
  ok(await cls(p) === 0, 'home-1440 CLS on load is 0');
  ok((await p.locator('.mast button, .mast [tabindex], .mast [aria-pressed]').count()) === 0, 'header has no buttons or pressable elements');
  const snap = () => p.evaluate(() => [...document.querySelectorAll('.mast *')].map((n) => { const s = getComputedStyle(n); return s.color + s.backgroundColor + s.transform + s.fill + s.textDecorationThickness; }).join('|'));
  const s0 = await snap();
  for (const q of await p.locator('.mast .q').all()) { await q.hover(); await p.waitForTimeout(80); }
  ok(s0 === await snap(), 'pointing at header properties changes nothing');
  const shape = await p.evaluate(() => ({
    select: document.querySelectorAll('select, #sort, .sortc').length,
    toggles: document.querySelectorAll('[aria-pressed], [role=tab], .vk').length,
    quotes: document.querySelectorAll('blockquote').length,
    tables: [...document.querySelectorAll('.bench')].map((s) => `${s.querySelector('h2').textContent}:${[...s.querySelectorAll('.tbl .row')].map((r) => r.id).join('+')}`),
    refs: [...document.querySelectorAll('.refs .row')].map((r) => r.id),
    wip: document.querySelectorAll('#wip, .wip, .mwip').length + (/work in progress/i.test(document.body.innerText) ? 1 : 0),
    sameAsAbove: /same as above/i.test(document.body.innerText),
    nb: document.querySelectorAll('#not-yet .nb').length,
    sections: [...document.querySelectorAll('main .sec')].map((s) => s.id),
  }));
  ok(shape.select === 0 && shape.toggles === 0, 'no sort control, no view toggle, no tabs', shape);
  ok(shape.quotes === 0, 'no quotes on the home');
  ok(shape.tables.join() === 'Llama 4 Maverick:flashprove,Llama 3.1 8B:sash' && shape.wip === 0, 'one table per model, biggest model first; no work-in-progress label', shape.tables);
  ok(shape.refs.join() === 'ref-serve,ref-recompute' && !shape.sameAsAbove, 'two reference rows after the models, no "same as above"', shape.refs);
  ok(shape.sections.join() === 'llama-4-maverick,llama-3-1-8b,references,not-yet' && shape.nb === 19, 'sections in order, 19 not benchmarked yet', shape.sections);
  // row slice hover: lift and a positioned label; no row moves; the other slices keep their ink
  const h0 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  const pie = await p.locator('#flashprove .pie').boundingBox();
  await p.mouse.move(pie.x + pie.width * 0.8, pie.y + pie.height * 0.5); await p.waitForTimeout(400);
  const tip = await p.evaluate(() => { const t = document.querySelector('#flashprove .tip'); return { shown: getComputedStyle(t).display !== 'none', text: t.textContent, pos: getComputedStyle(t).position }; });
  ok(tip.shown && tip.pos === 'absolute' && tip.text.length > 3, 'row slice hover shows its name and state', tip.text);
  const h1 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  ok(JSON.stringify(h0) === JSON.stringify(h1), 'row heights unchanged on slice hover');
  ok(await p.evaluate(() => [...document.querySelectorAll('.row .pie .sl')].every((s) => getComputedStyle(s).opacity === '1' && getComputedStyle(s).filter === 'none')), 'other slices keep opacity 1, no filter');
  const spreads = await p.evaluate(() => [...document.querySelectorAll('.tbl .val')].filter((a) => /spread: n = /.test(a.title))
    .map((a) => /n = \d+ runs/.test(a.querySelector('.sub').textContent) && / to /.test(a.querySelector('.sub').textContent)));
  ok(spreads.length === 4 && spreads.every(Boolean), 'figures with a spread show sample size and range', spreads);
  await ctx.close();
}

// ---------------------------------------------------------------- sorting by the column heads: every column, both directions
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const st0 = await sortState(p);
  ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'system', 'asc')) && st0.aria.join() === 'system:ascending' && st0.heads === 2 && st0.hash === '', 'default: System A to Z in both tables, empty hash', st0);
  for (const col of ['system', 'covers', 'proof_size', 'check_time', 'overhead']) {
    for (const dir of ['asc', 'desc']) {
      await sortBy(p, col, dir);
      const got = await order(p);
      const st = await sortState(p);
      ok(JSON.stringify(got) === JSON.stringify(await expected(p, col, dir)) && st.heads === 2 && st.aria.join() === `${col}:${dir === 'asc' ? 'ascending' : 'descending'}`
        && (col === 'system' && dir === 'asc' ? st.hash === '' : st.hash === `#sort=${col}-${dir}`), `sort ${col} ${dir}`, { got, hash: st.hash, glyphs: st.glyphs });
    }
  }
  await sortBy(p, 'proof_size', 'desc');
  ok(await cls(p) === 0, 'CLS after a sort (shifts without input) is 0');
  const said = await p.evaluate(() => document.querySelector('#sort-now').textContent);
  ok(said === 'Proof size, large to small', 'the order is named for screen readers', said);
  await ctx.close();
  const r = await pg(1440, 900);
  await r.p.goto(BASE + 'index.html#sort=check_time-desc', { waitUntil: 'networkidle' }); await r.p.waitForTimeout(settle);
  const st2 = await sortState(r.p);
  ok(st2.aria.join() === 'check_time:descending' && JSON.stringify(await order(r.p)) === JSON.stringify(await expected(r.p, 'check_time', 'desc')), 'hash round-trip', st2);
  ok(await cls(r.p) === 0, 'CLS on load with a sort hash is 0');
  await r.p.evaluate(() => { location.hash = 'sort=overhead-desc'; }); await r.p.waitForTimeout(400);
  ok((await sortState(r.p)).aria.join() === 'overhead:descending', 'hashchange applies a new order');
  await r.p.click('.mast .draft'); await r.p.waitForTimeout(900);
  ok(/sort=overhead-desc/.test((await sortState(r.p)).hash), 'the #criteria link keeps the order and its hash');
  await r.ctx.close();
  const z = await pg(1440, 900);
  await z.p.goto(BASE + 'index.html#sort=bogus-asc', { waitUntil: 'networkidle' }); await z.p.waitForTimeout(600);
  const stz = await sortState(z.p);
  ok(stz.aria.join() === 'system:ascending' && stz.hash === '', 'unknown sort in the hash falls back and clears it', stz.hash);
  await z.ctx.close();
}

// ---------------------------------------------------------------- keyboard
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await p.locator('.sb[data-col="proof_size"]').first().focus();
  await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  let st = await sortState(p);
  ok(st.aria.join() === 'proof_size:ascending', 'Enter on Proof size sorts ascending', st);
  await p.keyboard.press('Space'); await p.waitForTimeout(300);
  st = await sortState(p);
  ok(st.aria.join() === 'proof_size:descending', 'Space on it again sorts descending', st);
  const fv = await p.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  ok(fv !== 'none', 'keyboard focus is visible on a head button', fv);
  await ctx.close();
}

// ---------------------------------------------------------------- narrow widths
for (const w of [1100, 1024, 900, 768]) {
  for (const name of PAGES) {
    const { ctx, p } = await pg(w, 900);
    await p.goto(BASE + name, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
    const o = await overflow(p);
    ok(o.over <= 0 && !o.clipped.length, `${name}-${w} no overflow, no clipped figure`, o);
    await ctx.close();
  }
}
for (const w of [390, 360]) {
  for (const name of PAGES) {
    const { ctx, p } = await pg(w, 844, { touch: true });
    await p.goto(BASE + name, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
    const tag = name.replace('.html', '').replace('index', 'home');
    if (tag === 'home' && w === 390) {
      await p.screenshot({ path: OUT + 'home-390-landing.png' });
      const top = await p.evaluate(() => Math.round(document.querySelector('.tbl .row .name').getBoundingClientRect().bottom));
      log(`home-${w} first system name bottom`, top, 'px');
      ok(top < 844, `home-${w} first system name shows on landing`, top);
    }
    if (w === 390) await full(p, OUT + `${tag}-${w}.png`);
    const o = await overflow(p);
    ok(o.over <= 0 && !o.clipped.length, `${tag}-${w} no horizontal overflow`, o);
    ok(await cls(p) === 0, `${tag}-${w} CLS 0`);
    if (tag === 'home') {
      ok(await p.locator('.sb[data-col="check_time"]').first().isVisible(), `home-${w} the column heads stay as sort buttons`);
      await sortBy(p, 'check_time', 'desc');
      ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'check_time', 'desc')), `home-${w} sorts from the heads`);
    }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- system pages and the reference page: the pie with its properties around it
for (const name of ['flashprove', 'sash', 'reference']) {
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + name + '.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await full(p, OUT + `${name}-1440.png`);
  ok(await cls(p) === 0, `${name}-1440 CLS 0`);
  const o = await overflow(p);
  ok(o.over <= 0 && !o.clipped.length, `${name}-1440 no overflow`, o);
  const v = await p.evaluate(() => [...document.querySelectorAll('.rose')].map((r) => {
    const pie = r.querySelector('.rpie .pie-svg').getBoundingClientRect();
    const cx = pie.left + pie.width / 2;
    const items = [...r.querySelectorAll('.rp')].map((li) => { const b = li.getBoundingClientRect(); return { n: +li.dataset.n, side: b.left > cx ? 'r' : b.right < cx ? 'l' : 'x', top: b.top }; });
    const byN = Object.fromEntries(items.map((i) => [i.n, i]));
    return {
      pie: Math.round(pie.width), n: items.length,
      sides: items.every((i) => i.side === (i.n <= 3 ? 'r' : 'l')),
      downward: byN[1].top < byN[2].top && byN[2].top < byN[3].top && byN[6].top < byN[5].top && byN[5].top < byN[4].top,
      facts: !!r.parentElement.querySelector('.facts'),
    };
  }));
  ok(v.length >= 1 && v.every((x) => x.pie <= 220 && x.n === 6 && x.sides && x.downward && x.facts), `${name}: small pie, slices 1-3 described on its right and 4-6 on its left, facts beside`, v);
  const firstScreen = await p.evaluate(() => Math.round(document.querySelector('.rose').getBoundingClientRect().bottom));
  ok(firstScreen <= 900, `${name}: the six properties fit the first screen`, firstScreen);
  ok(await p.evaluate(() => document.querySelectorAll('blockquote, details').length === 0), `${name}: no quotes, nothing folded`);
  // pointing at a property lifts its slice
  await p.hover('.rp[data-n="2"]'); await p.waitForTimeout(300);
  const lift = await p.evaluate(() => getComputedStyle(document.querySelector('.rpie .s2')).transform);
  ok(lift !== 'none', `${name}: pointing at a property lifts its slice`, lift);
  await ctx.close();
}
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + 'sash.html', { waitUntil: 'networkidle' });
  ok(!/work in progress/i.test(await p.locator('body').innerText()) && /Llama 3\.1 8B/.test(await p.locator('#figures .sec-l').innerText()), 'sash.html: no work-in-progress label; its figures name their model');
  await p.goto(BASE + 'system.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(600);
  ok(p.url().endsWith('flashprove.html'), 'system.html redirects', p.url());
  await ctx.close();
}

// ---------------------------------------------------------------- words: cut sentences, neutrality, numbered names, links
{
  const { ctx, p } = await pg(1440, 900);
  const bad = [];
  for (const name of PAGES) {
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const t = await p.evaluate(() => {
      const all = document.body.innerText + ' ' + [...document.querySelectorAll('[aria-label],[title]')].map((n) => (n.getAttribute('aria-label') || '') + ' ' + (n.title || '')).join(' ');
      const chrome = [...document.querySelectorAll('.top, .mast, .heads, .sec-h, .subh')].map((n) => n.textContent).join(' ');
      return { all, chrome };
    });
    ok(!/These tests show only what happened|Printed as text/.test(t.all), `${name}: cut sentences absent`);
    ok(!/\bmock\b/i.test(t.all), `${name}: no placeholder marking on the page`);
    ok(!/\b(best|top|fastest|leader|leaderboard|winner|rank(ed|ing)?)\b|#\s?1\b|🥇/i.test(t.chrome), `${name}: no ranking words in the site's own controls`);
    ok(!/\d\s*(Weights hidden|Model bound|Whole output proved|Formally verified|Security level|No trusted party)/.test(t.all), `${name}: no numbered property names`);
    ok(!/step \d of \d/i.test(t.all), `${name}: no "step N of M"`);
    const local = await p.evaluate(() => [...new Set([...document.querySelectorAll('a[href]')].map((a) => a.href).filter((h) => h.startsWith(location.origin)).map((h) => h.split('#')[0]))]);
    for (const u of local) { const r = await p.request.get(u); if (r.status() >= 400) bad.push(`${name} -> ${u} ${r.status()}`); }
  }
  ok(!bad.length, 'no dead local links', bad);
  await ctx.close();
}

// ---------------------------------------------------------------- axe: every page and a sorted home, at 1440 and 390
if (AxeBuilder) {
  const runs = [];
  for (const w of [1440, 390]) {
    for (const name of PAGES) runs.push([w, name, null]);
    runs.push([w, 'index.html#sort=overhead-desc', null]);
  }
  for (const [w, url] of runs) {
    const { ctx, p } = await pg(w, 900, { reduce: true });
    await p.goto(BASE + url, { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
    const res = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    ok(res.violations.length === 0, `axe ${w} ${url}`, res.violations.map((v) => `${v.id} x${v.nodes.length} ${v.nodes[0]?.target}`));
    await ctx.close();
  }
} else {
  log('SKIP axe: @axe-core/playwright not found (set AXE_MODULE)');
}

ok(!errs.length, 'no console or page errors', errs);
log(`${fails} failed check(s)`);
fs.writeFileSync(OUT + 'checks.txt', report.join('\n') + '\n');
await b.close();
process.exitCode = fails ? 1 : 0;
