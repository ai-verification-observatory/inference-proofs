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
const PAGES = ['', 'flashprove', 'sash', 'reference', 'criteria', 'release', 'sponsors'];  // clean addresses, as on the site
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
  // a Not stated slot is filled like the others, in its own grey, and lifts like them
  const sb = await p.locator('#sash .pie .h1').boundingBox();
  await p.mouse.move(sb.x + sb.width * 0.6, sb.y + sb.height * 0.4); await p.waitForTimeout(400);
  const emp = await p.evaluate(() => {
    const pie = document.querySelector('#sash .pie'); const s = pie.querySelector('.s1'); const cs = getComputedStyle(s);
    const grey = getComputedStyle(document.documentElement).getPropertyValue('--unstated').trim();
    const rgb = '#' + cs.fill.match(/\d+/g).map((v) => (+v).toString(16).padStart(2, '0')).join('');
    return { hot: pie.dataset.hot, unstated: s.classList.contains('unstated'), fill: rgb, grey, moved: cs.transform !== 'none', loose: pie.querySelectorAll('svg > path:not(.sl)').length };
  });
  ok(emp.hot === '1' && emp.unstated && emp.fill === emp.grey && emp.moved && emp.loose === 0, 'a Not stated slot is filled in its own grey and lifts like the others', emp);
  await p.mouse.move(0, 0);
  const spreads = await p.evaluate(() => [...document.querySelectorAll('.tbl .val')].filter((a) => /spread: /.test(a.title))
    .map((a) => /\d+\s+completed, \d+\s+failed/.test(a.querySelector('.sub').textContent) && / to /.test(a.querySelector('.sub').textContent)));
  // two systems, three measured figures each: One proof covers carries its spread too (D-TPP, #320)
  ok(spreads.length === 6 && spreads.every(Boolean), 'figures with a spread show sample size and range', spreads);
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
// each property's text beside its own triangle, as on main before #320: the rose's height at 1440 px, measured on
// origin/main at c81832d, is the composition the system page keeps (within 10 %)
const ROSE_MAIN = { flashprove: 309, sash: 309, reference: 275 };
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
  // the six names and states on the first screen (on a system page, what each rests on follows under it)
  const firstScreen = await p.evaluate(() => Math.max(...[...document.querySelector('.rose').querySelectorAll('.rp .rs')].map((x) => Math.round(x.getBoundingClientRect().bottom))));
  ok(firstScreen <= 900, `${tagOf(name)}: the six properties' states fit the first screen`, firstScreen);
  const roseH = await p.evaluate(() => Math.round(document.querySelector('.rose').getBoundingClientRect().height));
  ok(Math.abs(roseH - ROSE_MAIN[name]) <= ROSE_MAIN[name] * 0.1, `${tagOf(name)}: the rose keeps main's height, each text beside its triangle`, { now: roseH, main: ROSE_MAIN[name] });
  // quotes only in how we read it, none beside the glyph; the two folds, how we read it and the card in full,
  // closed as sent
  const fold = await p.evaluate(() => ({ stray: [...document.querySelectorAll('blockquote')].filter((q) => !q.closest('.howread')).length, details: [...document.querySelectorAll('details')].map((d) => `${d.className}:${d.open}`) }));
  const sys = name !== 'reference';
  ok(!fold.stray && fold.details.join() === (sys ? 'howread:false,cardfull:false' : ''), `${tagOf(name)}: quotes only in how we read it; ${sys ? 'how we read it and the card in full folded' : 'nothing folded'}`, fold);
  if (sys) {
    // a property's "source" opens how we read it and lands on its entry, focus on it; so does an address naming one
    const land = (pp, id) => pp.evaluate((id) => {
      const at = document.getElementById(id);
      const r = at.getBoundingClientRect();
      return { open: at.closest('details').open, focus: document.activeElement === at, top: Math.round(r.top), seen: r.top >= 0 && r.top < innerHeight / 2 };
    }, id);
    const links = await p.evaluate(() => [...document.querySelectorAll('.rp .psrc')].map((a) => a.getAttribute('href')));
    const entries = await p.evaluate(() => [...document.querySelectorAll('.howread [id^="read-"]')].map((x) => `#${x.id}`));
    ok(links.length === 6 && links.every((h) => entries.includes(h)), `${tagOf(name)}: each property's source names its own entry in how we read it`, { links, entries });
    await p.evaluate(() => scrollTo(0, 0));
    await p.click('.rp[data-n="3"] .psrc'); await p.waitForTimeout(400);
    const id3 = links[2].slice(1);
    const l3 = await land(p, id3);
    ok(l3.open && l3.focus && l3.seen, `${tagOf(name)}: a source link opens how we read it and lands on its entry`, l3);
    const q = await pg(1440, 900);
    await q.p.goto(`${BASE}${name}#${id3}`, { waitUntil: 'networkidle' }); await q.p.waitForTimeout(600);
    const l4 = await land(q.p, id3);
    ok(l4.open && l4.focus && l4.seen, `${tagOf(name)}: an address naming an entry opens how we read it on it`, l4);
    await q.ctx.close();
    // a press that opens a new tab or window (Cmd, Ctrl, Shift) leaves this page as it was: fold closed, no focus moved
    const m = await pg(1440, 900);
    await m.p.goto(BASE + name, { waitUntil: 'networkidle' });
    for (const k of ['Meta', 'Control', 'Shift']) {
      await m.p.evaluate(() => document.addEventListener('click', (ev) => { if (ev.target.closest('.psrc')) ev.preventDefault(); }, { once: true }));
      await m.p.click('.rp[data-n="3"] .psrc', { modifiers: [k] }); await m.p.waitForTimeout(150);
    }
    const kept = await m.p.evaluate(() => ({ open: document.querySelector('.howread').open, focus: document.activeElement.closest('.howread') !== null }));
    ok(!kept.open && !kept.focus, `${tagOf(name)}: a modified press on a source link changes nothing in the page`, kept);
    await m.ctx.close();
  }
  // pointing at a property lifts its slice
  await p.hover('.rp[data-n="2"]'); await p.waitForTimeout(300);
  const lift = await p.evaluate(() => getComputedStyle(document.querySelector('.rpie .s2')).transform);
  ok(lift !== 'none', `${tagOf(name)}: pointing at a property lifts its slice`, lift);
  await ctx.close();
}
// each property beside its own triangle at 1000 to 1440 px: its middle within 40 px of the pie's top and bottom, also
// with an overridden cell's line (RFC-0016 OVR-7) added where the extras golden page prints one (the deployed release
// has none), so a long line never pushes the other properties off their triangles
{
  const golden = fs.readFileSync(new URL('../harness/tests/golden/site/flashprove.html', import.meta.url), 'utf8');
  const ov = golden.match(/<li class="rp [rl]" id="p-[a-z_]+" data-n="(\d)">(?:(?!<\/li>).)*?(<div class="ev">(?:(?!<\/li>).)*?<\/div>)<\/li>/s);
  ok(!!ov, 'the extras golden page prints an overridden cell\'s line beside the glyph');
  for (const name of ['flashprove', 'sash']) for (const w of [1000, 1240, 1440]) {
    const { ctx, p } = await pg(w, 900);
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const beside = () => p.evaluate(() => {
      const pie = document.querySelector('.rose .rpie .pie-svg').getBoundingClientRect();
      const off = [...document.querySelectorAll('.rose .rp')].map((li) => { const r = li.getBoundingClientRect(); return { n: +li.dataset.n, mid: Math.round((r.top + r.bottom) / 2 - pie.top), h: Math.round(r.height) }; })
        .filter((x) => x.mid < -40 || x.mid > pie.height + 40);
      return { pie: Math.round(pie.height), off, rose: Math.round(document.querySelector('.rose').getBoundingClientRect().height) };
    });
    const a = await beside();
    ok(!a.off.length, `${tagOf(name)}-${w}: each property beside its own triangle`, a);
    if (ov) {
      await p.evaluate(([n, html]) => { document.querySelector(`.rose .rp[data-n="${n}"]`).insertAdjacentHTML('beforeend', html); }, [ov[1], ov[2]]);
      const c = await beside();
      const line = await p.evaluate(() => Math.round(document.querySelector('.rose .ev').getBoundingClientRect().height));
      ok(!c.off.length && line <= 20, `${tagOf(name)}-${w}: with an overridden cell's line (one line), each property still beside its triangle`, { ...c, line });
    }
    await ctx.close();
  }
}
// a row header's link (#claims-<configuration>) shows the system page from its top, the name in view
for (const w of [1440, 390]) {
  const { ctx, p } = await pg(w, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' });
  const href = await p.evaluate(() => document.querySelector('a[href^="/sash#claims-"]')?.getAttribute('href'));
  await p.goto(BASE + (href || '/sash').slice(1), { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
  const at = await p.evaluate(() => { const r = document.querySelector('.sysname').getBoundingClientRect(); return { y: Math.round(scrollY), name: r.top >= 0 && r.bottom <= innerHeight }; });
  ok(!!href && at.name, `overview-${w}: following a row header's link leaves the system's name in view`, { href, ...at });
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

// ---------------------------------------------------------------- phones: search sheet, header, legend, strip, taps, targets
{
  // the search sheet: 16 px type (no zoom on focus), a tap around it closes it and reaches nothing, a close button
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  const fs16 = await p.evaluate(() => parseFloat(getComputedStyle(document.getElementById('q')).fontSize));
  ok(fs16 >= 16, 'phone: the search field is set at 16 px or more, so focusing it does not zoom', fs16);
  await p.tap('.sopen'); await p.fill('#q', 'sash'); await p.waitForTimeout(300);
  await p.touchscreen.tap(200, 780); await p.waitForTimeout(400);
  const after = await p.evaluate(() => ({ path: location.pathname + location.hash, on: document.querySelector('.top').classList.contains('s-on') }));
  ok(after.path === '/' && !after.on, 'phone: a tap on the sheet closes search and activates nothing under it', after);
  await p.tap('.sopen'); await p.waitForTimeout(300);
  await p.evaluate(() => document.getElementById('q').blur()); await p.waitForTimeout(200);
  ok(await p.evaluate(() => !document.getElementById('q-list').hidden), 'phone: hiding the keyboard keeps the results');
  const cb = await p.locator('.sclose').boundingBox();
  await p.tap('.sclose'); await p.waitForTimeout(300);
  const closed = await p.evaluate(() => ({ on: document.querySelector('.top').classList.contains('s-on'), focus: document.activeElement.className }));
  ok(cb.width >= 44 && cb.height >= 44 && !closed.on && closed.focus === 'sopen', 'phone: a 44 px close button closes search and returns focus to the search button', { cb, closed });
  // open, the sheet holds still and what it covers is out of reach; closed, everything is back
  await p.tap('.sopen'); await p.fill('#q', 'z'); await p.waitForTimeout(300);
  await p.evaluate(() => scrollBy(0, 600)); await p.waitForTimeout(200);
  const held = await p.evaluate(() => ({ field: Math.round(document.querySelector('.sfield').getBoundingClientRect().top), lock: getComputedStyle(document.documentElement).overflow, main: document.querySelector('main').inert, repo: document.querySelector('.repo').inert, search: !!document.querySelector('.search').closest('[inert]') }));
  ok(held.field === 4 && held.lock === 'hidden' && held.main && held.repo && !held.search, 'phone: the open sheet stays on screen, the page under it is locked and inert', held);
  await p.tap('.sclose'); await p.waitForTimeout(300);
  ok(await p.evaluate(() => !document.querySelector('[inert]') && getComputedStyle(document.documentElement).overflow !== 'hidden'), 'phone: closing the sheet gives the page back');
  await p.evaluate(() => scrollTo(0, 0));
  await p.setViewportSize({ width: 390, height: 500 }); await p.waitForTimeout(200);
  await p.tap('.sopen'); await p.fill('#q', 'zk'); await p.waitForTimeout(300);
  const lb = await p.evaluate(() => Math.round(document.getElementById('q-list').getBoundingClientRect().bottom));
  ok(lb <= 488, 'phone: the results end above the keyboard (390 x 500 visible)', lb);
  await p.tap('#q-list .so'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname === '/flashprove', 'phone: a tap on a result opens it', p.url());
  await ctx.close();
}
{
  // the header: one line from 561 px, two lines and 44 px search and GitHub targets below
  for (const [w, h] of [[600, 900], [768, 1024], [844, 390]]) {
    const { ctx, p } = await pg(w, h, { touch: true });
    await p.goto(BASE + 'sash', { waitUntil: 'networkidle' });
    const t = await p.evaluate(() => {
      const c = (s) => document.querySelector(s).getBoundingClientRect();
      const l = c('.logo'); const mid = (r) => (r.top + r.bottom) / 2;
      return { h: Math.round(c('.top').height), dy: [...document.querySelectorAll('.top nav a')].map((a) => Math.round(Math.abs(mid(a.getBoundingClientRect()) - mid(l)))) };
    });
    ok(t.h <= 60 && t.dy.every((d) => d <= 4), `header-${w}x${h}: the pages share the logo's line`, t);
    await ctx.close();
  }
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE, { waitUntil: 'networkidle' });
  const t = await p.evaluate(() => ({ sopen: Math.round(document.querySelector('.sopen').getBoundingClientRect().height), repo: Math.round(document.querySelector('.top .repo').getBoundingClientRect().height), nav: [...document.querySelectorAll('.top nav a')].map((a) => Math.round(a.getBoundingClientRect().height)) }));
  ok(t.sopen >= 44 && t.repo >= 44 && t.nav.every((x) => x >= 32), 'header-390: search and GitHub 44 px to press, the pages 32 px', t);
  await ctx.close();
}
for (const [w, h] of [[375, 667], [320, 568]]) {
  // the legend: a 2 x 3 key, so the first glyph shows on landing; the questions still read aloud
  const { ctx, p } = await pg(w, h, { touch: true });
  await p.goto(BASE, { waitUntil: 'networkidle' });
  // 375 x 667: the first glyph whole; 320 x 568: the first row starts on screen
  const l = await p.evaluate((w) => ({ pie: Math.round(document.querySelector(w >= 375 ? '.tbl .row .pie' : '.tbl .row').getBoundingClientRect()[w >= 375 ? 'bottom' : 'top']), cols: new Set([...document.querySelectorAll('.q')].map((q) => Math.round(q.getBoundingClientRect().left))).size, qq: [...document.querySelectorAll('.qq')].every((q) => q.textContent.length > 10 && getComputedStyle(q).clipPath === 'inset(50%)') }), w);
  ok(l.pie < h && l.cols === 2 && l.qq, `home-${w}x${h}: the legend in two columns, the first system on landing, the questions kept for screen readers`, l);
  // the board: System on its own line, the four column heads on one line above their own figures, every
  // button at least 32 px tall; each row two lines (name, figures), so several systems fit on one screen
  const s = await p.evaluate(() => {
    const r = (x) => x.getBoundingClientRect();
    const b = [...document.querySelectorAll('.bench .hc:not(.hsys) .sb')];
    const sys = r(document.querySelector('.bench .hsys .sb'));
    const row = document.querySelector('.bench .row');
    const lefts = b.map((x) => Math.round(r(x).left));
    const cols = [...row.querySelectorAll('.vc')].map((c) => Math.round(r(c).left));
    return { sysAlone: sys.bottom <= Math.min(...b.map((x) => r(x).top)) + 1, bottoms: new Set(b.map((x) => Math.round(r(x).bottom))).size, aligned: lefts.every((x, i) => Math.abs(x - cols[i]) <= 1), h: Math.min(...[sys, ...b.map(r)].map((x) => Math.round(x.height))), rowH: Math.round(r(row).height), lefts, cols };
  });
  ok(s.sysAlone && s.bottoms === 1 && s.aligned && s.h >= 32 && s.rowH <= 140, `home-${w}: a board, each head above its own column, buttons 32 px tall or more, rows 140 px or less`, s);
  await ctx.close();
}
{
  // touch: the first tap on a triangle names it, the second follows the link; the sorted figure is marked in each row
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE + '#sort=check_time-desc', { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const mk = await p.evaluate(() => [...document.querySelectorAll('.tbl .vc')].map((c) => `${c.dataset.col}:${getComputedStyle(c.querySelector('.n, .na')).color === 'rgb(241, 239, 233)' ? 'on' : 'off'}`));
  ok(mk.length && mk.every((x) => x.endsWith(x.startsWith('check_time') ? 'on' : 'off')), 'home-390: the sorted column is in paper in every row, the others muted', mk);
  await p.locator('#flashprove .pie').scrollIntoViewIfNeeded();
  const bx = await p.locator('#flashprove .pie').boundingBox();
  const at = [bx.x + bx.width * 0.85, bx.y + bx.height * 0.5];
  await p.touchscreen.tap(...at); await p.waitForTimeout(300);
  const tip = await p.evaluate(() => { const pie = document.querySelector('#flashprove .pie'); const t = pie.querySelector('.tip'); return { path: location.pathname, hot: pie.dataset.hot, shown: getComputedStyle(t).display !== 'none', text: t.textContent, sw: !!t.querySelector('.sw') }; });
  ok(tip.path === '/' && tip.hot === '2' && tip.shown && /Model bound/.test(tip.text) && tip.sw, 'touch: a first tap on a triangle names it and stays on the page', tip);
  await p.touchscreen.tap(...at); await p.waitForTimeout(800);
  ok(new URL(p.url()).pathname === '/flashprove', 'touch: a second tap on the same triangle follows the link', p.url());
  // the system page: the glyph once, wide, each triangle carrying its property's name and never a state
  // word; under it six ruled rows, 1 to 6, each with its state in text in one column; no key glyphs
  await p.waitForTimeout(400);
  const r = await p.evaluate(() => {
    const box = (x) => x.getBoundingClientRect();
    const svg = document.querySelector('.rpie .pie-svg');
    const g = box(svg);
    const words = ['YES', 'PARTLY', 'NO', 'NOT STATED'];
    // every corner of each line's capitals (baseline to cap height) falls in its own triangle's fill
    const out = [];
    [1, 2, 3, 4, 5, 6].forEach((n) => {
      const sl = svg.querySelector(`.sl.s${n}`);
      svg.querySelectorAll(`.t.s${n} text`).forEach((t) => {
        const bb = t.getBBox(); const y = +t.getAttribute('y'); const m = sl.getCTM().inverse().multiply(t.getCTM());
        [[bb.x, y], [bb.x + bb.width, y], [bb.x, y - 7], [bb.x + bb.width, y - 7]].forEach(([x, yy]) => {
          if (!sl.isPointInFill(new DOMPoint(x, yy).matrixTransform(m))) out.push(`${n}:${t.textContent}`);
        });
      });
    });
    const inside = !out.length;
    const names = [...svg.querySelectorAll('.t')].map((t) => [...t.querySelectorAll('text')].map((x) => x.textContent).join(' '));
    const rows = [...document.querySelectorAll('.rose .rp')].sort((a, b) => box(a).top - box(b).top);
    return {
      wide: Math.round(g.width), inside, out, names,
      stateless: names.every((t) => !words.includes(t)),
      order: rows.map((x) => x.dataset.n).join(''),
      below: rows.every((x) => box(x).top >= g.bottom - 1),
      col: new Set(rows.map((x) => Math.round(box(x.querySelector('.rs')).left))).size,
      keys: document.querySelectorAll('.rose .kmini').length,
    };
  });
  ok(r.wide >= 330 && r.inside && r.stateless && r.order === '123456' && r.below && r.col === 1 && r.keys === 0, 'flashprove-390: one wide glyph with each name in its own triangle and no state word; six rows under it, states in one column; no key glyphs', r);
  const sb = await p.locator('.rpie .h2').boundingBox();
  await p.touchscreen.tap(sb.x + sb.width * 0.7, sb.y + sb.height * 0.5); await p.waitForTimeout(400);
  const lift = await p.evaluate(() => ({ s2: getComputedStyle(document.querySelector('.rpie .s2')).transform, rn: getComputedStyle(document.querySelector('.rp[data-n="2"] .rn')).color, path: location.pathname }));
  ok(lift.s2 !== 'none' && lift.rn === 'rgb(241, 239, 233)' && lift.path === '/flashprove', 'touch: a tap on a slice lifts it and marks its property', lift);
  await ctx.close();
}
{
  // inline links on every page: hit boxes 24 px tall or more, none overlapping another
  for (const w of [390, 320]) {
    for (const name of [...PAGES, 'nope']) {
      const { ctx, p } = await pg(w, 844, { touch: true });
      await p.goto(BASE + name, { waitUntil: 'networkidle' });
      const t = await p.evaluate(() => {
        const els = [...document.querySelectorAll('a, button')].filter((a) => a.getClientRects().length && getComputedStyle(a).visibility !== 'hidden' && !a.closest('.sr, [hidden]') && !a.closest('details:not([open]) > :not(summary)'));
        const bx = els.map((a) => ({ a, rs: [...a.getClientRects()].filter((r) => r.width) }));
        const small = bx.filter((x) => x.rs.some((r) => r.height < 24)).map((x) => x.a.textContent.trim().slice(0, 24));
        const hit = [];
        for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) {
          if (bx[i].a.contains(bx[j].a) || bx[j].a.contains(bx[i].a)) continue;
          if (bx[i].rs.some((r1) => bx[j].rs.some((r2) => r1.left < r2.right - 0.5 && r2.left < r1.right - 0.5 && r1.top < r2.bottom - 0.5 && r2.top < r1.bottom - 0.5))) hit.push(`${bx[i].a.textContent.trim().slice(0, 16)} x ${bx[j].a.textContent.trim().slice(0, 16)}`);
        }
        return { small, hit };
      });
      ok(!t.small.length && !t.hit.length, `${tagOf(name)}-${w}: every link and button 24 px tall or more, none overlapping`, t);
      await ctx.close();
    }
  }
}
{
  // phones held sideways: the band and the whole glyph on the first screen
  for (const name of ['sash', 'flashprove']) {
    const { ctx, p } = await pg(844, 390, { touch: true });
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const g = await p.evaluate(() => Math.round(document.querySelector('.rpie svg').getBoundingClientRect().bottom));
    ok(g <= 390, `${name}-844x390: the whole glyph on the first screen`, g);
    await ctx.close();
  }
  // the 404 page on a phone: the search field shown, no keyboard on load
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE + 'nope', { waitUntil: 'networkidle' });
  const f = await p.evaluate(() => ({ h: Math.round(document.querySelector('.sfield').getBoundingClientRect().height), vis: document.getElementById('q').getBoundingClientRect().width > 0, focus: document.activeElement.tagName }));
  ok(f.vis && f.h >= 44 && f.focus === 'BODY', '404-390: the search field is shown, not focused', f);
  await p.tap('#q'); await p.fill('#q', 'sash'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname === '/sash', '404-390: search leads on from the 404 page', p.url());
  await ctx.close();
}

// where the figures start on a system page, as a number to read against the owner's target (the Figures heading
// within about 1,600 px on /sash at 390 px): recorded, not checked, since the claims before it are S1's to set
for (const [name, w] of [['sash', 390], ['flashprove', 390], ['sash', 1440], ['flashprove', 1440]]) {
  const { ctx, p } = await pg(w, 844, { touch: w < 1000 });
  await p.goto(BASE + name, { waitUntil: 'networkidle' });
  log(`${name}-${w} Figures heading at ${await p.evaluate(() => Math.round(document.getElementById('h-figs').getBoundingClientRect().top + scrollY))} px`);
  await ctx.close();
}

// ---------------------------------------------------------------- the validated claims, the card in full and the release's pages (#320)
// at 390 and 320 px: one press opens how we read it and the card in full; with both open, nothing overflows, and every
// link and button of the new blocks (quotes' sources, control lines, card fields, runs left out,
// unexpected outcomes, the release record) is 24 px tall or more, none overlapping another
for (const w of [390, 320]) {
  for (const name of ['flashprove', 'sash', 'release', 'sponsors']) {
    const { ctx, p } = await pg(w, 844, { touch: true });
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    for (const [cls, what] of [['howread', 'how we read it'], ['cardfull', 'the card in full']]) {
      if (await p.locator(`details.${cls} summary`).count()) {
        await p.tap(`details.${cls} summary`); await p.waitForTimeout(200);
        ok(await p.evaluate((c) => document.querySelector(`details.${c}`).open, cls), `${name}-${w}: one press opens ${what}`);
      }
    }
    const o = await overflow(p);
    ok(o.over <= 0 && !o.wide.length, `${name}-${w}: no horizontal overflow, both folds open`, o);
    const t = await p.evaluate(() => {
      const sel = '.ev a, .rp .psrc, .howread a, .howread summary, .cardfull a, .cardfull summary, .gapblk a, .facts a, .runs a, .unexp a, .reply a, .relf a, .tlab a, .es a';
      const els = [...document.querySelectorAll(sel)].filter((a) => a.getClientRects().length && !a.closest('.sr, [hidden]'));
      const bx = els.map((a) => ({ a, rs: [...a.getClientRects()].filter((r) => r.width) }));
      const small = bx.filter((x) => x.rs.some((r) => r.height < 24)).map((x) => x.a.textContent.trim().slice(0, 24));
      const hit = [];
      for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) {
        if (bx[i].a.contains(bx[j].a) || bx[j].a.contains(bx[i].a)) continue;
        if (bx[i].rs.some((r1) => bx[j].rs.some((r2) => r1.left < r2.right - 0.5 && r2.left < r1.right - 0.5 && r1.top < r2.bottom - 0.5 && r2.top < r1.bottom - 0.5))) hit.push(`${bx[i].a.textContent.trim().slice(0, 16)} x ${bx[j].a.textContent.trim().slice(0, 16)}`);
      }
      return { n: els.length, small, hit };
    });
    ok(t.n > 0 && !t.small.length && !t.hit.length, `${name}-${w}: the new blocks' links and buttons 24 px tall or more, none overlapping`, t);
    // a label wider than its column runs into its value without overflowing the page: each dt's
    // text ends before its dd starts, when the two sit on one line
    const lab = await p.evaluate(() => {
      const bad = [];
      for (const dt of document.querySelectorAll('.facts dt, .tlab dt, .cf dt, .cn dt, .plate dt')) {
        const dd = dt.nextElementSibling;
        if (!dd || dd.tagName !== 'DD' || !dt.getClientRects().length) continue;
        const r = document.createRange(); r.selectNodeContents(dt);
        const a = r.getBoundingClientRect(), b = dd.getBoundingClientRect();
        if (a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5 && a.right > b.left + 0.5) bad.push(dt.textContent.trim());
      }
      return bad;
    });
    ok(!lab.length, `${name}-${w}: no label runs into its value`, lab);
    await ctx.close();
  }
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
    ok(!/\d\s*(Weights hidden|Model bound|Whole output checked|Formally verified|Security level|No trusted party)/.test(t.all), `${tagOf(name)}: no numbered property names`);
    ok(!/step \d of \d/i.test(t.all), `${tagOf(name)}: no "step N of M"`);
    ok(!t.dup.length, `${tagOf(name)}: no duplicate ids`, t.dup);
    ok(!/\bfixture\b|n_failed|the row reads|RFC-\d{4} [A-Z]+-\d/.test(t.vis), `${tagOf(name)}: no placeholder words, field names or bare rule codes in visible text`);
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
