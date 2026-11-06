// Screenshots and checks: node shoot.mjs   (writes shots/*.png and shots/checks.txt)
// Env: BASE (default http://127.0.0.1:4440/, served by python3 -I serve.py), PLAYWRIGHT_MODULE (default "playwright"),
//      AXE_MODULE (default "@axe-core/playwright"; the axe checks are skipped, and say so, if it cannot be loaded).
import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
let AxeBuilder = null;
try { AxeBuilder = (await import(process.env.AXE_MODULE || '@axe-core/playwright')).default; } catch (_) { /* reported below */ }
const BASE = process.env.BASE || 'http://127.0.0.1:4440/';
const OUT = new URL('./shots/', import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });
const PAGES = ['', 'flashprove', 'sash', 'reference', 'criteria'];  // clean addresses, as on the site
const tagOf = (name) => name || 'home';
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
  ok(shape.tables.join() === 'Llama 4 Maverick:flashprove+sash' && shape.wip === 0, 'one table, Llama 4 Maverick, every benchmarked system in it; no work-in-progress label', shape.tables);
  ok(shape.refs.join() === 'ref-serve,ref-recompute' && !shape.sameAsAbove, 'two reference rows after the models, no "same as above"', shape.refs);
  ok(shape.sections.join() === 'llama-4-maverick,references,not-yet' && shape.nb === 19 && !/Llama 3\.1 8B/.test(await p.locator('.bench, .refs').allInnerTexts().then((x) => x.join(' '))), 'sections in order, 19 not benchmarked yet, no Llama 3.1 8B', shape.sections);
  // row slice hover: lift and a positioned label; no row moves; the other slices keep their ink
  const h0 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  const pie = await p.locator('#flashprove .pie').boundingBox();
  await p.mouse.move(pie.x + pie.width * 0.8, pie.y + pie.height * 0.5); await p.waitForTimeout(400);
  const tip = await p.evaluate(() => { const t = document.querySelector('#flashprove .tip'); return { shown: getComputedStyle(t).display !== 'none', text: t.textContent, pos: getComputedStyle(t).position }; });
  ok(tip.shown && tip.pos === 'absolute' && tip.text.length > 3, 'row slice hover shows its name and state', tip.text);
  const h1 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  ok(JSON.stringify(h0) === JSON.stringify(h1), 'row heights unchanged on slice hover');
  ok(await p.evaluate(() => [...document.querySelectorAll('.row .pie .sl')].every((s) => getComputedStyle(s).opacity === '1' && getComputedStyle(s).filter === 'none')), 'other slices keep opacity 1, no filter');
  // an empty (Not stated) slot is its side alone: pointing at it lifts that side in paper, with no outline
  const sb = await p.locator('#sash .pie .h1').boundingBox();
  await p.mouse.move(sb.x + sb.width * 0.6, sb.y + sb.height * 0.4); await p.waitForTimeout(400);
  const emp = await p.evaluate(() => {
    const pie = document.querySelector('#sash .pie'); const s = pie.querySelector('.s1'); const cs = getComputedStyle(s);
    return { hot: pie.dataset.hot, band: s.classList.contains('eb'), fill: cs.fill, stroke: cs.stroke, moved: cs.transform !== 'none', ticks: pie.querySelectorAll('.eo').length, paper: getComputedStyle(document.body).color };
  });
  ok(emp.hot === '1' && emp.band && emp.moved && emp.fill === emp.paper && emp.stroke === 'none', 'an empty slot lifts its side alone, in paper, with no outline', emp);
  await p.mouse.move(0, 0);
  const spreads = await p.evaluate(() => [...document.querySelectorAll('.tbl .val')].filter((a) => /spread: /.test(a.title))
    .map((a) => /\d+\s+completed, \d+\s+failed/.test(a.querySelector('.sub').textContent) && / to /.test(a.querySelector('.sub').textContent)));
  ok(spreads.length === 4 && spreads.every(Boolean), 'figures with a spread show sample size and range', spreads);
  await ctx.close();
}

// ---------------------------------------------------------------- sorting by the column heads: every column, both directions
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const st0 = await sortState(p);
  ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'system', 'asc')) && st0.aria.join() === 'system:ascending' && st0.heads === 1 && st0.hash === '', 'default: System A to Z in the table, empty hash', st0);
  for (const col of ['system', 'covers', 'proof_size', 'check_time', 'overhead']) {
    for (const dir of ['asc', 'desc']) {
      await sortBy(p, col, dir);
      const got = await order(p);
      const st = await sortState(p);
      ok(JSON.stringify(got) === JSON.stringify(await expected(p, col, dir)) && st.heads === 1 && st.aria.join() === `${col}:${dir === 'asc' ? 'ascending' : 'descending'}`
        && (col === 'system' && dir === 'asc' ? st.hash === '' : st.hash === `#sort=${col}-${dir}`), `sort ${col} ${dir}`, { got, hash: st.hash, glyphs: st.glyphs });
    }
  }
  await sortBy(p, 'proof_size', 'desc');
  ok(await cls(p) === 0, 'CLS after a sort (shifts without input) is 0');
  const said = await p.evaluate(() => document.querySelector('#sort-now').textContent);
  ok(said === 'Proof size, large to small', 'the order is named for screen readers', said);
  await ctx.close();
  const r = await pg(1440, 900);
  await r.p.goto(BASE + '#sort=check_time-desc', { waitUntil: 'networkidle' }); await r.p.waitForTimeout(settle);
  const st2 = await sortState(r.p);
  ok(st2.aria.join() === 'check_time:descending' && JSON.stringify(await order(r.p)) === JSON.stringify(await expected(r.p, 'check_time', 'desc')), 'hash round-trip', st2);
  ok(await cls(r.p) === 0, 'CLS on load with a sort hash is 0');
  await r.p.evaluate(() => { location.hash = 'sort=overhead-desc'; }); await r.p.waitForTimeout(400);
  ok((await sortState(r.p)).aria.join() === 'overhead:descending', 'hashchange applies a new order');
  await r.ctx.close();
  // Back to the page without a hash shows the default order again
  const bk = await pg(1440, 900);
  await bk.p.goto(BASE, { waitUntil: 'networkidle' }); await bk.p.waitForTimeout(settle);
  await bk.p.evaluate(() => { location.hash = 'sort=check_time-desc'; }); await bk.p.waitForTimeout(300);
  await bk.p.goBack(); await bk.p.waitForTimeout(400);
  const stb = await sortState(bk.p);
  ok(stb.aria.join() === 'system:ascending' && stb.hash === '', 'Back to no hash restores the default order', stb);
  // sorting that can fail: rows that differ in every column, with missing values among them
  await bk.p.evaluate(() => {
    const box = document.querySelector('.tbl .rows');
    const src = box.querySelector('.row');
    [['zz-a', 'aaa', { covers: 512, proof_size: null, check_time: 9, overhead: 3 }],
     ['zz-b', 'zzz', { covers: 2048, proof_size: 1, check_time: null, overhead: 7 }]].forEach(([id, name, k]) => {
      const r = src.cloneNode(true); r.id = id; r.dataset.name = name; r.dataset.k = JSON.stringify(k); box.appendChild(r);
    });
  });
  for (const col of ['covers', 'proof_size', 'check_time', 'overhead']) {
    for (const dir of ['asc', 'desc']) {
      await sortBy(bk.p, col, dir);
      const got = (await order(bk.p))[0];
      const keys = await bk.p.evaluate((col) => [...document.querySelectorAll('.tbl .rows > .row')].map((r) => JSON.parse(r.dataset.k)[col]), col);
      const firstNull = keys.findIndex((k) => k == null);
      const missingLast = firstNull === -1 || keys.slice(firstNull).every((k) => k == null);
      ok(JSON.stringify(got) === JSON.stringify((await expected(bk.p, col, dir))[0]) && missingLast, `sort with missing values: ${col} ${dir}`, { got, keys });
    }
  }
  await bk.ctx.close();
  const z = await pg(1440, 900);
  await z.p.goto(BASE + '#sort=bogus-asc', { waitUntil: 'networkidle' }); await z.p.waitForTimeout(600);
  const stz = await sortState(z.p);
  ok(stz.aria.join() === 'system:ascending' && stz.hash === '', 'unknown sort in the hash falls back and clears it', stz.hash);
  await z.ctx.close();
}

// ---------------------------------------------------------------- search
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const opts = () => p.evaluate(() => [...document.querySelectorAll('#q-list .so')].map((o) => ({ name: o.querySelector('.sn').textContent, kind: o.className.replace(/.*k-/, ''), badge: (o.querySelector('.sbadge')?.textContent || '').trim() })));
  const type = async (q) => { await p.fill('#q', q); await p.waitForTimeout(250); };
  await p.keyboard.press('/'); await p.waitForTimeout(400);
  ok(await p.evaluate(() => document.activeElement.id === 'q' && !document.getElementById('q-list').hidden), '"/" focuses search and opens the list');
  const empty = await opts();
  ok(empty.length && empty.every((o) => o.kind === 'system'), 'an empty search lists the benchmarked systems', empty.map((o) => o.name));
  const geo = await p.evaluate(() => { const f = document.querySelector('.sfield').getBoundingClientRect(); const l = document.querySelector('#q-list').getBoundingClientRect(); const n = document.querySelector('.tl').getBoundingClientRect(); const g = document.querySelector('.repo').getBoundingClientRect(); return { w: Math.round(f.width), gaps: [Math.round(f.left - n.right), Math.round(g.left - f.right)], list: Math.round(l.width - f.width) }; });
  ok(geo.w >= 560 && Math.abs(geo.gaps[0] - geo.gaps[1]) <= 2 && geo.list === 0, 'the field is wide and centred between the pages and GitHub, its list as wide', geo);
  await type('flash');
  ok((await opts())[0]?.name === 'FlashProve', '"flash" finds FlashProve first');
  await type('zk');
  const zk = await opts();
  const firstNb = zk.findIndex((o) => o.kind === 'unbenchmarked');
  ok(firstNb > 0 && zk.slice(firstNb).every((o) => o.kind === 'unbenchmarked' && o.badge === 'Not benchmarked'), 'not-benchmarked systems come after the others, each marked', zk.map((o) => `${o.name}:${o.kind}`));
  await type('atestable');
  ok((await opts())[0]?.name === 'Attestable prover', 'one typo still finds the system');
  await p.keyboard.press('Enter'); await p.waitForTimeout(500);
  const tgt = await p.evaluate(() => ({ url: location.pathname + location.hash, bar: getComputedStyle(document.querySelector('#nb-attestable'), '::before').content, label: getComputedStyle(document.querySelector('#nb-attestable .nbn'), '::after').content }));
  ok(tgt.url === '/#nb-attestable' && tgt.bar !== 'none' && /Not benchmarked/.test(tgt.label), 'a not-benchmarked result leads to its card in the overview, marked and labelled', tgt);
  await type('qqqqzz');
  ok(await p.evaluate(() => document.querySelector('#q-list .snone')?.textContent === 'No match'), 'no match says so');
  for (const [q, want] of [['atest', 'Attestable prover'], ['flsh', 'FlashProve'], ['flahsprove', 'FlashProve'], ['sahs', 'SASH'], ['llama4', 'FlashProve']]) {
    await type(q);
    ok((await opts())[0]?.name === want, `"${q}" finds ${want} first`, (await opts()).map((o) => o.name).slice(0, 3));
  }
  await type('sash');
  ok((await opts()).length === 1, 'an exact word brings no typo noise ("sash" finds SASH only)', (await opts()).map((o) => o.name));
  await type('stark');
  ok(JSON.stringify((await opts()).map((o) => o.name)) === '["SASH","LuminAIR"]', '"stark" finds only the systems whose stated technique is one');
  await type('a');
  ok((await opts()).some((o) => o.name === 'Attestable prover'), 'one letter still lists the not-benchmarked names that start with it');
  await type('weights hidden');
  await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname + new URL(p.url()).hash === '/criteria#weights_hidden', 'Enter goes to the first result of a typed search', p.url());
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300); await type('weights');
  await p.keyboard.press('ArrowDown'); await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname + new URL(p.url()).hash === '/reference#ref-recompute', 'the arrows choose another result', p.url());
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(400);
  ok(new URL(p.url()).pathname === '/', 'Enter in an empty field picks nothing', p.url());
  await ctx.close();
  // phones: a button opens the field over the first line
  const ph = await pg(390, 844, { touch: true });
  await ph.p.goto(BASE + 'flashprove', { waitUntil: 'networkidle' }); await ph.p.waitForTimeout(settle);
  ok(await ph.p.locator('.sopen').isVisible() && !(await ph.p.locator('#q').isVisible()), 'phone: a search button, the field hidden');
  await ph.p.click('.sopen'); await ph.p.waitForTimeout(400);
  await ph.p.fill('#q', 'llama'); await ph.p.waitForTimeout(300);
  const o = await overflow(ph.p);
  ok(await ph.p.locator('#q').isVisible() && (await ph.p.locator('#q-list .so').count()) > 0 && o.over <= 0, 'phone: the button opens the field and its results, nothing overflows', o);
  await ph.ctx.close();
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
    ok(o.over <= 0 && !o.clipped.length, `${tagOf(name)}-${w} no overflow, no clipped figure`, o);
    await ctx.close();
  }
}
for (const w of [390, 360, 320]) {
  for (const name of PAGES) {
    const { ctx, p } = await pg(w, 844, { touch: true });
    await p.goto(BASE + name, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
    const tag = tagOf(name);
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
  await p.goto(BASE + name, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  await full(p, OUT + `${tagOf(name)}-1440.png`);
  ok(await cls(p) === 0, `${tagOf(name)}-1440 CLS 0`);
  const o = await overflow(p);
  ok(o.over <= 0 && !o.clipped.length, `${tagOf(name)}-1440 no overflow`, o);
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
  ok(v.length >= 1 && v.every((x) => x.pie <= 220 && x.n === 6 && x.sides && x.downward && x.facts), `${tagOf(name)}: small pie, slices 1-3 described on its right and 4-6 on its left, facts beside`, v);
  const firstScreen = await p.evaluate(() => Math.round(document.querySelector('.rose').getBoundingClientRect().bottom));
  ok(firstScreen <= 900, `${tagOf(name)}: the six properties fit the first screen`, firstScreen);
  ok(await p.evaluate(() => document.querySelectorAll('blockquote, details').length === 0), `${tagOf(name)}: no quotes, nothing folded`);
  // pointing at a property lifts its slice
  await p.hover('.rp[data-n="2"]'); await p.waitForTimeout(300);
  const lift = await p.evaluate(() => getComputedStyle(document.querySelector('.rpie .s2')).transform);
  ok(lift !== 'none', `${tagOf(name)}: pointing at a property lifts its slice`, lift);
  await ctx.close();
}
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + 'sash', { waitUntil: 'networkidle' });
  ok(!/work in progress/i.test(await p.locator('body').innerText()) && /^Llama\s4\sMaverick/.test(await p.locator('#figures .sec-l').innerText()), 'sash: no work-in-progress label; its figures name their model');
  // an unknown address: the site's own 404 page, with the site's header, at any depth
  for (const u of ['nope', 'a/b/c']) {
    const res = await p.goto(BASE + u, { waitUntil: 'networkidle' });
    ok(res.status() === 404 && (await p.locator('.top .logo, .top nav a').count()) >= 3 && (await p.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(11, 11, 12)', `/${u} answers the styled 404 page`, res.status());
  }
  // an older address redirects to the first system page
  for (const u of ['system', 'system.html']) {
    await p.goto(BASE + u, { waitUntil: 'networkidle' });
    ok(new URL(p.url()).pathname === '/flashprove', `/${u} redirects to /flashprove`, p.url());
  }
  // a malformed escape in the hash breaks nothing: sorting and Back keep working
  await p.goto(BASE + '#100%', { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
  await p.evaluate(() => { location.hash = 'sort=proof_size-desc'; }); await p.waitForTimeout(300);
  ok((await sortState(p)).aria.join() === 'proof_size:descending', 'a malformed hash does not stop hash sorting');
  // a phone held sideways: the first table's heading shows on landing
  await ctx.close();
  const ls = await pg(844, 390, { touch: true });
  await ls.p.goto(BASE, { waitUntil: 'networkidle' }); await ls.p.waitForTimeout(settle);
  const hb = await ls.p.evaluate(() => Math.round(document.querySelector('.bench .sect').getBoundingClientRect().bottom));
  ok(hb <= 390, 'landscape phone: the model heading shows on landing', hb);
  await ls.ctx.close();
}

// ---------------------------------------------------------------- words: cut sentences, neutrality, numbered names, links
{
  const { ctx, p } = await pg(1440, 900);
  const bad = [];
  for (const name of PAGES) {
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const t = await p.evaluate(() => {
      const all = document.body.innerText + ' ' + [...document.querySelectorAll('[aria-label],[title]')].map((n) => (n.getAttribute('aria-label') || '') + ' ' + (n.title || '')).join(' ');
      const vis = document.body.innerText;
      const chrome = [...document.querySelectorAll('.top, .mast, .heads, .sec-h')].map((n) => n.textContent).join(' ');
      const ids = {};
      document.querySelectorAll('[id]').forEach((n) => { ids[n.id] = (ids[n.id] || 0) + 1; });
      return { all, vis, chrome, dup: Object.keys(ids).filter((k) => ids[k] > 1) };
    });
    ok(!/These tests show only what happened|Printed as text/.test(t.all), `${tagOf(name)}: cut sentences absent`);
    ok(!/\bmock\b/i.test(t.all), `${tagOf(name)}: no placeholder marking on the page`);
    ok(!/\b(best|top|fastest|leader|leaderboard|winner|rank(ed|ing)?)\b|#\s?1\b|🥇/i.test(t.chrome), `${tagOf(name)}: no ranking words in the site's own controls`);
    ok(!/\d\s*(Weights hidden|Model bound|Whole output proved|Formally verified|Security level|No trusted party)/.test(t.all), `${tagOf(name)}: no numbered property names`);
    ok(!/step \d of \d/i.test(t.all), `${tagOf(name)}: no "step N of M"`);
    ok(!t.dup.length, `${tagOf(name)}: no duplicate ids`, t.dup);
    ok(!/\bfixture\b|n_failed|RFC-\d{4} [A-Z]+-\d/.test(t.vis), `${tagOf(name)}: no placeholder words, field names or bare rule codes in visible text`);
    // every local link resolves, and its #fragment names exactly one element on the target page
    const local = await p.evaluate(() => [...new Set([...document.querySelectorAll('a[href]')].map((a) => a.href).filter((h) => h.startsWith(location.origin)))]);
    for (const u of local) {
      const [page, frag] = u.split('#');
      const r = await p.request.get(page);
      if (r.status() >= 400) { bad.push(`${tagOf(name)} -> ${u} ${r.status()}`); continue; }
      if (frag && !/^sort=/.test(frag)) {
        const n = ((await r.text()).match(new RegExp(` id="${frag}"`, 'g')) || []).length;
        if (n !== 1) bad.push(`${tagOf(name)} -> ${u} has ${n} #${frag}`);
      }
    }
  }
  ok(!bad.length, 'no dead local links', bad);
  await ctx.close();
}

// ---------------------------------------------------------------- axe: every page and a sorted home, at 1440 and 390
if (AxeBuilder) {
  const runs = [];
  for (const w of [1440, 390]) {
    for (const name of PAGES) runs.push([w, name, null]);
    runs.push([w, '#sort=overhead-desc', null], [w, 'nope', null], [w, '', 'search']);
  }
  for (const [w, url, mode] of runs) {
    const { ctx, p } = await pg(w, 900, { reduce: true });
    await p.goto(BASE + url, { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
    if (mode === 'search') {  // the results list open, with not-benchmarked entries in it
      if (await p.locator('.sopen').isVisible()) await p.click('.sopen'); else await p.focus('#q');
      await p.fill('#q', 'zk'); await p.waitForTimeout(300);
    }
    const res = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    ok(res.violations.length === 0, `axe ${w} ${url}${mode ? ' ' + mode : ''}`, res.violations.map((v) => `${v.id} x${v.nodes.length} ${v.nodes[0]?.target}`));
    await ctx.close();
  }
} else {
  log('SKIP axe: @axe-core/playwright not found (set AXE_MODULE)');
}

// the 404 checks load unknown addresses on purpose; the browser logs their status as an error
const realErrs = errs.filter((e) => !/\/(nope|a\/b\/c): Failed to load resource: .* 404/.test(e));
ok(!realErrs.length, 'no console or page errors', realErrs);
log(`${fails} failed check(s)`);
fs.writeFileSync(OUT + 'checks.txt', report.join('\n') + '\n');
await b.close();
process.exitCode = fails ? 1 : 0;
