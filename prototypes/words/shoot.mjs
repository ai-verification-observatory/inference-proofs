// Screenshots and checks: node shoot.mjs   (writes shots/*.png and shots/checks.txt)
// Env: BASE (default http://127.0.0.1:4421/), PLAYWRIGHT_MODULE (default "playwright"),
//      AXE_MODULE (default "@axe-core/playwright"; the axe checks are skipped, and say so, if it cannot be loaded).
import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
let AxeBuilder = null;
try { AxeBuilder = (await import(process.env.AXE_MODULE || '@axe-core/playwright')).default; } catch (_) { /* reported below */ }
const BASE = process.env.BASE || 'http://127.0.0.1:4421/';
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
const order = (p) => p.evaluate(() => [...document.querySelectorAll('#panel-benchmarked .row')].map((r) => r.id));
// the expected order, computed here from data-k, independently of words.js
const expected = (p, col, dir, view) => p.evaluate(([col, dir, view]) => {
  const rows = [...document.querySelectorAll('#panel-benchmarked .row')].map((r) => ({ id: r.id, name: r.dataset.name, k: JSON.parse(r.dataset.k)[view][col] }));
  const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  if (col === 'system') return rows.sort((a, b) => (dir === 'asc' ? 1 : -1) * byName(a, b)).map((r) => r.id);
  const have = rows.filter((r) => r.k != null).sort((a, b) => (dir === 'asc' ? a.k - b.k : b.k - a.k) || byName(a, b));
  const none = rows.filter((r) => r.k == null).sort(byName);
  return [...have, ...none].map((r) => r.id);
}, [col, dir, view]);
const sortState = (p) => p.evaluate(() => ({
  sel: document.querySelector('#sort').value,
  aria: [...document.querySelectorAll('.hc[aria-sort]')].map((h) => `${h.dataset.col}:${h.getAttribute('aria-sort')}`),
  glyphs: [...document.querySelectorAll('.hc .g')].map((g) => g.textContent).join(''),
  hash: location.hash,
  run: document.body.classList.contains('view-run'),
}));

// ---------------------------------------------------------------- home 1440: header, rows, hover
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await p.screenshot({ path: OUT + 'home-1440.png' });
  const mast = await p.evaluate(() => Math.round(document.querySelector('.mast').getBoundingClientRect().height));
  log('home-1440 header height', mast, 'px');
  ok(await cls(p) === 0, 'home-1440 CLS on load is 0');
  ok((await p.locator('.mast button, .mast [tabindex], .mast [aria-pressed]').count()) === 0, 'header has no buttons or pressable elements');
  ok((await p.locator('.mast a').count()) === 1, 'header holds one link (the draft-criteria link)');
  const snap = () => p.evaluate(() => [...document.querySelectorAll('.mast *')].map((n) => { const s = getComputedStyle(n); return s.color + s.backgroundColor + s.transform + s.fill + s.textDecorationThickness; }).join('|'));
  const s0 = await snap();
  for (const q of await p.locator('.mast .q').all()) { await q.hover(); await p.waitForTimeout(80); }
  ok(s0 === await snap(), 'pointing at header properties changes nothing');
  ok((await p.locator('.rd, .lay').count()) === 0, 'no per-row readout block');
  // row slice hover: lift and a positioned label; no row moves; the other slices keep their ink
  const h0 = await p.evaluate(() => [...document.querySelectorAll('.row')].filter((r) => r.offsetParent).map((r) => r.getBoundingClientRect().height));
  const pie = await p.locator('#sash .pie').boundingBox();
  await p.mouse.move(pie.x + pie.width * 0.8, pie.y + pie.height * 0.5); await p.waitForTimeout(400);
  const tip = await p.evaluate(() => { const t = document.querySelector('#sash .tip'); return { shown: getComputedStyle(t).display !== 'none', text: t.textContent, pos: getComputedStyle(t).position }; });
  ok(tip.shown && tip.pos === 'absolute' && tip.text.length > 3, 'row slice hover shows its name and state', tip.text);
  await p.screenshot({ path: OUT + 'home-1440-hover.png' });
  const h1 = await p.evaluate(() => [...document.querySelectorAll('.row')].filter((r) => r.offsetParent).map((r) => r.getBoundingClientRect().height));
  ok(JSON.stringify(h0) === JSON.stringify(h1), 'row heights unchanged on slice hover');
  ok(await p.evaluate(() => [...document.querySelectorAll('.row .pie .sl')].filter((s) => s.closest('.row').offsetParent).every((s) => getComputedStyle(s).opacity === '1' && getComputedStyle(s).filter === 'none')), 'other slices keep opacity 1, no filter');
  await ctx.close();
}

// ---------------------------------------------------------------- sorting: every column, both directions, both views
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'system', 'asc', 'published')), 'default order is System A to Z', await order(p));
  const st0 = await sortState(p);
  ok(st0.sel === 'system-asc' && st0.aria.join() === 'system:ascending' && st0.hash === '', 'default state: select, aria-sort, empty hash', st0);
  const cols = ['system', 'covers', 'proof_size', 'check_time', 'overhead'];
  for (const view of ['published', 'run']) {
    await p.click(`.vk[data-view="${view}"]`); await p.waitForTimeout(150);
    for (const col of cols) {
      for (const dir of ['asc', 'desc']) {
        await p.selectOption('#sort', `${col}-${dir}`); await p.waitForTimeout(260);
        const got = await order(p);
        const want = await expected(p, col, dir, view);
        const st = await sortState(p);
        const lastMissing = await p.evaluate(([col, view]) => {
          if (col === 'system') return true;
          const ks = [...document.querySelectorAll('#panel-benchmarked .row')].map((r) => JSON.parse(r.dataset.k)[view][col]);
          const firstNull = ks.findIndex((k) => k == null);
          return firstNull === -1 || ks.slice(firstNull).every((k) => k == null);
        }, [col, view]);
        ok(JSON.stringify(got) === JSON.stringify(want) && lastMissing && st.aria.join() === `${col}:${dir === 'asc' ? 'ascending' : 'descending'}`,
          `sort ${view} ${col} ${dir}`, { got, missing_last: lastMissing, hash: st.hash, glyphs: st.glyphs });
      }
    }
  }
  // switching the view re-sorts with that view's values
  await p.click('.vk[data-view="published"]'); await p.waitForTimeout(150);
  await p.selectOption('#sort', 'check_time-desc'); await p.waitForTimeout(260);
  const pubOrder = await order(p);
  await p.click('.vk[data-view="run"]'); await p.waitForTimeout(300);
  ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'check_time', 'desc', 'run')), 'view switch re-sorts with run-here values', { published: pubOrder, run: await order(p) });
  // every visible run figure with a stored spread shows n and its range on the row
  const spreads = await p.evaluate(() => [...document.querySelectorAll('.val.v-run')].filter((a) => a.offsetParent && /spread: n = /.test(a.title))
    .map((a) => /n = \d+ runs/.test(a.querySelector('.sub').textContent) && / to /.test(a.querySelector('.sub').textContent)));
  ok(spreads.length === 4 && spreads.every(Boolean), 'run figures show sample size and range', spreads);
  // the table does not move when the view changes
  await p.click('.vk[data-view="published"]'); await p.waitForTimeout(300);
  const t0 = await p.evaluate(() => Math.round(document.querySelector('.tbl').getBoundingClientRect().top + scrollY));
  await p.click('.vk[data-view="run"]'); await p.waitForTimeout(300);
  const t1 = await p.evaluate(() => Math.round(document.querySelector('.tbl').getBoundingClientRect().top + scrollY));
  ok(t0 === t1, 'table top unchanged by the view switch', [t0, t1]);
  await ctx.close();
}

// ---------------------------------------------------------------- shots of sorted states, hash round-trip, CLS
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await p.selectOption('#sort', 'proof_size-desc'); await p.waitForTimeout(400);
  await p.evaluate(() => scrollTo(0, 300)); await p.waitForTimeout(200);
  await p.screenshot({ path: OUT + 'home-1440-sorted.png' });
  const st = await sortState(p);
  ok(st.hash === '#sort=proof_size-desc', 'hash written', st.hash);
  ok(await cls(p) === 0, 'CLS after a sort (shifts without input) is 0');
  await ctx.close();
  // round-trip: a fresh page on that hash shows the same order and state
  const r = await pg(1440, 900);
  await r.p.goto(BASE + 'index.html' + st.hash, { waitUntil: 'networkidle' }); await r.p.waitForTimeout(settle);
  const st2 = await sortState(r.p);
  ok(st2.sel === 'proof_size-desc' && st2.aria.join() === 'proof_size:descending' && JSON.stringify(await order(r.p)) === JSON.stringify(await expected(r.p, 'proof_size', 'desc', 'published')), 'hash round-trip (proof size)', st2);
  ok(await cls(r.p) === 0, 'CLS on load with a sort hash is 0');
  await r.ctx.close();
  const q = await pg(1440, 900);
  await q.p.goto(BASE + '#sort=check_time-desc&view=run', { waitUntil: 'networkidle' }); await q.p.waitForTimeout(settle);
  const st3 = await sortState(q.p);
  ok(st3.run && st3.sel === 'check_time-desc' && JSON.stringify(await order(q.p)) === JSON.stringify(await expected(q.p, 'check_time', 'desc', 'run')), 'hash round-trip (run here, check time)', st3);
  await q.p.evaluate(() => scrollTo(0, 300)); await q.p.waitForTimeout(200);
  await q.p.screenshot({ path: OUT + 'home-1440-sorted-run.png' });
  ok(await cls(q.p) === 0, 'CLS on load with a run-view sort hash is 0');
  // hashchange and the draft-criteria link (#criteria) keep the order
  await q.p.evaluate(() => { location.hash = 'sort=overhead-desc'; }); await q.p.waitForTimeout(400);
  ok((await sortState(q.p)).sel === 'overhead-desc', 'hashchange applies a new order');
  await q.p.click('.mast .draft'); await q.p.waitForTimeout(900);
  const stc = await sortState(q.p);
  ok(stc.sel === 'overhead-desc' && /sort=overhead-desc/.test(stc.hash), 'the #criteria link keeps the order and its hash', stc.hash);
  await q.ctx.close();
  // an unknown order in the link: the page shows the default and the hash says so
  const z = await pg(1440, 900);
  await z.p.goto(BASE + 'index.html#sort=bogus-asc', { waitUntil: 'networkidle' }); await z.p.waitForTimeout(600);
  const stz = await sortState(z.p);
  ok(stz.sel === 'system-asc' && stz.hash === '', 'unknown sort in the hash falls back and clears it', stz.hash);
  await z.ctx.close();
}

// ---------------------------------------------------------------- keyboard
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await p.focus('#sort');
  await p.keyboard.press('Tab');
  const f1 = await p.evaluate(() => document.activeElement.matches('.sb') && document.activeElement.dataset.col);
  ok(f1 === 'system', 'Tab from the sort control reaches the System head button', f1);
  await p.keyboard.press('Tab'); await p.keyboard.press('Tab');
  const f2 = await p.evaluate(() => document.activeElement.dataset.col);
  await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  let st = await sortState(p);
  ok(f2 === 'proof_size' && st.sel === 'proof_size-asc' && st.aria.join() === 'proof_size:ascending', 'Enter on Proof size sorts ascending', st);
  await p.keyboard.press('Space'); await p.waitForTimeout(300);
  st = await sortState(p);
  ok(st.sel === 'proof_size-desc', 'Space on it again sorts descending', st);
  const fv = await p.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  ok(fv !== 'none', 'keyboard focus is visible on a head button', fv);
  await p.screenshot({ path: OUT + 'home-1440-keyboard.png' });
  await ctx.close();
}

// ---------------------------------------------------------------- narrow widths
for (const w of [1100, 1024, 900, 768]) {
  const { ctx, p } = await pg(w, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const o = await overflow(p);
  ok(o.over <= 0 && !o.clipped.length, `home-${w} no overflow, no clipped figure`, o);
  await ctx.close();
}
for (const w of [390, 360]) {
  for (const name of PAGES) {
    const { ctx, p } = await pg(w, 844, { touch: true });
    await p.goto(BASE + name, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
    const tag = name.replace('.html', '').replace('index', 'home');
    if (tag === 'home' && w === 390) {
      await p.screenshot({ path: OUT + 'home-390-landing.png' });
      const top = await p.evaluate(() => Math.round(document.querySelector('#panel-benchmarked .row .name').getBoundingClientRect().bottom));
      log(`home-${w} first system name bottom`, top, 'px');
      ok(top < 844, `home-${w} first system name shows on landing`, top);
    }
    if ((tag === 'home') || (tag === 'flashprove' && w === 390)) await full(p, OUT + `${tag}-${w}.png`);
    const o = await overflow(p);
    ok(o.over <= 0 && !o.clipped.length, `${tag}-${w} no horizontal overflow`, o);
    ok(await cls(p) === 0, `${tag}-${w} CLS 0`);
    if (tag === 'home') {
      for (const t of ['reference', 'not_benchmarked']) {
        await p.click(`#tab-${t}`); await p.waitForTimeout(400);
        const o2 = await overflow(p);
        ok(o2.over <= 0, `home-${w} ${t} tab no overflow`, o2);
      }
      await p.click('#tab-benchmarked'); await p.waitForTimeout(200);
      await p.selectOption('#sort', 'check_time-desc'); await p.waitForTimeout(300);
      const o3 = await overflow(p);
      ok(o3.over <= 0, `home-${w} sorted no overflow`, o3);
      ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'check_time', 'desc', 'published')), `home-${w} sort works from the control`);
      const lbl = await p.evaluate(() => { const l = document.querySelector('.vc[data-col="check_time"] .val:not([style*="none"]) .lbl'); return getComputedStyle(l, '::after').content; });
      ok(/↓/.test(lbl), `home-${w} sorted column label carries its glyph`, lbl);
    }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- system pages and the reference page
for (const name of ['flashprove', 'sash', 'reference']) {
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + name + '.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await full(p, OUT + `${name}-1440.png`);
  ok(await cls(p) === 0, `${name}-1440 CLS 0`);
  const o = await overflow(p);
  ok(o.over <= 0 && !o.clipped.length, `${name}-1440 no overflow`, o);
  const v = await p.evaluate(() => ({
    wordpie: document.querySelectorAll('.wpie, .net, .bigpie, .lab').length,
    pies: [...document.querySelectorAll('.ppie .pie-svg')].map((s) => Math.round(s.getBoundingClientRect().width)),
    lines: document.querySelectorAll('.pview .prop').length,
    quotesVisible: [...document.querySelectorAll('.pview .prop')].every((l) => l.querySelector('.pb > blockquote, .pb > .silent').offsetHeight > 0),
  }));
  ok(v.wordpie === 0 && v.pies.every((x) => x >= 120 && x <= 170) && v.lines === 6 * v.pies.length && v.quotesVisible, `${name}: no word pie; one small pie beside six lines, decisive quote visible`, v);
  await ctx.close();
}
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + 'sash.html#figures-run', { waitUntil: 'networkidle' }); await p.waitForTimeout(1200);
  ok(await p.evaluate(() => document.body.classList.contains('view-run')), 'sash.html#figures-run opens in the run view');
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
      const chrome = [...document.querySelectorAll('.top, .mast, .controls, .nbar, .heads, #sort, .jump, .crumbs')].map((n) => n.textContent).join(' ');
      return { all, chrome };
    });
    ok(!/These tests show only what happened|Printed as text/.test(t.all), `${name}: cut sentences absent`);
    ok(!/\b(best|top|fastest|leader|leaderboard|winner|rank(ed|ing)?)\b|#\s?1\b|🥇/i.test(t.chrome), `${name}: no ranking words in the site's own controls`);
    ok(!/\d\s*(Weights hidden|Model bound|Whole output proved|Formally verified|Security level|No trusted party)/.test(t.all), `${name}: no numbered property names`);
    ok(!/step \d of \d/i.test(t.all), `${name}: no "step N of M"`);
    const local = await p.evaluate(() => [...new Set([...document.querySelectorAll('a[href]')].map((a) => a.href).filter((h) => h.startsWith(location.origin)).map((h) => h.split('#')[0]))]);
    for (const u of local) { const r = await p.request.get(u); if (r.status() >= 400) bad.push(`${name} -> ${u} ${r.status()}`); }
  }
  ok(!bad.length, 'no dead local links', bad);
  await ctx.close();
}

// ---------------------------------------------------------------- axe: every page, plus home tabs, sorted and run states, at 1440 and 390
if (AxeBuilder) {
  const runs = [];
  for (const w of [1440, 390]) {
    for (const name of PAGES) runs.push([w, name, null]);
    runs.push([w, 'index.html#sort=overhead-desc&view=run', null], [w, 'index.html', 'reference'], [w, 'index.html', 'not_benchmarked']);
  }
  for (const [w, url, tab] of runs) {
    const { ctx, p } = await pg(w, 900, { reduce: true });
    await p.goto(BASE + url, { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
    if (tab) { await p.click(`#tab-${tab}`); await p.waitForTimeout(200); }
    const res = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    ok(res.violations.length === 0, `axe ${w} ${url}${tab ? ' tab ' + tab : ''}`, res.violations.map((v) => `${v.id} x${v.nodes.length} ${v.nodes[0]?.target}`));
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
