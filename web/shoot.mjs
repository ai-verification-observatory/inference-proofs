// Screenshots and checks: node shoot.mjs   (writes shots/*.png and shots/checks.txt)
// Env: BASE (default http://127.0.0.1:4440/, served by python3 -I serve.py), PLAYWRIGHT_MODULE (default "playwright"),
//      AXE_MODULE (default "@axe-core/playwright"; the axe checks are skipped, and say so, if it cannot be loaded).
import fs from 'node:fs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
let AxeBuilder = null;
try { AxeBuilder = (await import(process.env.AXE_MODULE || '@axe-core/playwright')).default; } catch (_) { /* reported below */ }
const BASE = process.env.BASE || 'http://127.0.0.1:4440/';
// a row's glyph tip in the page: shown, its words, and any visible text of the row it covers
const tipSeen = (row) => {
  const pie = document.querySelector(`${row} .pie`); const t = pie.querySelector('.tip'); const tr = t.getBoundingClientRect();
  const cs = getComputedStyle(t); const hp = [...pie.querySelectorAll(`.hit path[data-n="${pie.dataset.hot}"]`)].map((x) => x.getBoundingClientRect()).find((r) => r.width);
  const caret = getComputedStyle(t, '::before'); const cx = tr.left + parseFloat(caret.left);
  const nm = document.querySelector(`${row} .name`);
  const hit = (b) => b.width && b.height && b.left < tr.right && tr.left < b.right && b.top < tr.bottom && tr.top < b.bottom;
  const clipped = (x) => { for (let e = x; e; e = e.parentElement) if (getComputedStyle(e).clipPath === 'inset(50%)') return true; return false; };
  const over = [...document.querySelectorAll(`${row} .sysc *, ${row} .vals *`)].filter((x) => !t.contains(x) && !x.closest('.pie') && getComputedStyle(x).visibility === 'visible' && x.childElementCount === 0 && x.textContent.trim() && !clipped(x) && hit(x.getBoundingClientRect())).map((x) => x.textContent.trim());
  return { path: location.pathname, hot: pie.dataset.hot, shown: getComputedStyle(t).display !== 'none', pos: getComputedStyle(t).position, named: getComputedStyle(nm).visibility === 'visible' && nm.getBoundingClientRect().width > 0, card: cs.position === 'absolute' && cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && +cs.zIndex > 0 && cs.borderTopStyle === 'solid', aim: !!hp && Math.abs(cx - (hp.left + hp.width / 2)) <= 2, inView: tr.left >= 0 && tr.right <= innerWidth && tr.top >= 0 && tr.bottom <= innerHeight, text: t.textContent, sw: !!t.querySelector('.sw'), over };
};
const OUT = new URL('./shots/', import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });
const PAGES = ['', 'flashprove', 'sash', 'reference', 'criteria', 'release'];  // clean addresses, as on the site
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
// the table as a sorted set: its rows A to Z and every system a row header links; a sort reorders rows and
// never adds or drops one
const layout = (p) => p.evaluate(() => [...document.querySelectorAll('.board')].map((s) => ({
  rows: [...s.querySelectorAll('.tbl .rows > .row')].map((r) => r.id).sort(),
  systems: [...s.querySelectorAll('.tbl .rows > .row .name a')].map((a) => new URL(a.href).pathname).sort(),
})));
const sortState = (p) => p.evaluate(() => ({
  aria: [...new Set([...document.querySelectorAll('.hc[aria-sort]')].map((h) => `${h.dataset.col}:${h.getAttribute('aria-sort')}`))],
  heads: document.querySelectorAll('.hc[aria-sort]').length,
  tables: document.querySelectorAll('.tbl').length,
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
    tables: [...document.querySelectorAll('.board')].map((s) => [...s.querySelectorAll('.tbl .row')].map((r) => r.id).join('+')),
    refs: [...document.querySelectorAll('.row[id^="ref-"]')].map((r) => r.id),
    wip: document.querySelectorAll('#wip, .wip, .mwip').length + (/work in progress/i.test(document.body.innerText) ? 1 : 0),
    sameAsAbove: /same as above/i.test(document.body.innerText),
    nb: document.querySelectorAll('#not-yet .nb').length,
    sections: [...document.querySelectorAll('main .sec')].map((s) => s.id),
  }));
  ok(shape.select === 0 && shape.toggles === 0, 'no sort control, no view toggle, no tabs', shape);
  ok(shape.quotes === 0, 'no quotes on the home');
  ok(shape.tables.join() === 'flashprove+sash' && shape.wip === 0, 'one table across models, FlashProve then SASH (overhead ascending); no work-in-progress label', shape.tables);
  const lay = await layout(p);
  const systems = lay.flatMap((t) => t.systems);
  const pies = await p.evaluate(() => [...document.querySelectorAll('main .pie[href]')].map((a) => new URL(a.href).pathname).filter((x) => x !== '/reference'));
  ok(systems.length === 2 && new Set(systems).size === systems.length && JSON.stringify([...pies].sort()) === JSON.stringify(systems), 'one row per system on the overview, its glyph once', { systems, pies });
  ok(shape.refs.length === 0 && !shape.sameAsAbove, 'no reference row on the overview (the baseline is named in each overhead cell), no "same as above"', shape.refs);
  ok(shape.sections.join() === 'benchmarked,not-yet' && shape.nb === 19, 'sections in order: benchmarked, then 19 not benchmarked yet', shape.sections);
  // row slice hover: lift and a positioned label; no row moves; the other slices keep their ink
  const h0 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  const pie = await p.locator('#flashprove .pie').boundingBox();
  await p.mouse.move(pie.x + pie.width * 0.8, pie.y + pie.height * 0.5); await p.waitForTimeout(400);
  // the name and state sit in the glyph's empty column, over no text of the row
  const tip = await p.evaluate(tipSeen, '#flashprove');
  ok(tip.shown && tip.named && tip.card && tip.aim && tip.inView && tip.text.length > 3, 'row slice hover names its property and state in a raised card pointing at the petal, on screen, the system\'s name still shown', tip);
  const h1 = await p.evaluate(() => [...document.querySelectorAll('.row')].map((r) => r.getBoundingClientRect().height));
  ok(JSON.stringify(h0) === JSON.stringify(h1), 'row heights unchanged on slice hover');
  ok(await p.evaluate(() => [...document.querySelectorAll('.row .pie .sl')].every((s) => getComputedStyle(s).opacity === '1' && getComputedStyle(s).filter === 'none')), 'other slices keep opacity 1, no filter');
  // a Not stated slot is an empty red slot (a dark red fill inside No's red outline) and lifts like the others
  const sb = await p.locator('#sash .pie .w96 .h1').boundingBox();
  await p.mouse.move(sb.x + sb.width * 0.6, sb.y + sb.height * 0.4); await p.waitForTimeout(400);
  const emp = await p.evaluate(() => {
    const pie = document.querySelector('#sash .pie'); const s = pie.querySelector('.s1'); const cs = getComputedStyle(s);
    const root = getComputedStyle(document.documentElement);
    const hex = (c) => '#' + c.match(/\d+/g).slice(0, 3).map((v) => (+v).toString(16).padStart(2, '0')).join('');
    const rest = getComputedStyle(pie.querySelector('.w96 .sl.unstated:not(.s1)') || s);
    return { hot: pie.dataset.hot, unstated: s.classList.contains('unstated'), fill: hex(cs.fill), ghost: root.getPropertyValue('--ghost').trim(), stroke: hex(rest.stroke), grey: root.getPropertyValue('--unstated').trim(), moved: cs.transform !== 'none', loose: pie.querySelectorAll('svg > path:not(.sl)').length };
  });
  ok(emp.hot === '1' && emp.unstated && emp.fill === emp.ghost && emp.stroke === emp.grey && emp.moved && emp.loose === 0, 'a Not stated slot is an empty red slot (dark fill, red outline) and lifts like the others', emp);
  // one copy of each glyph per size shown, and only the copy for this width on screen
  const copies = await p.evaluate(() => [...document.querySelectorAll('.row .pie, .nbpie, .q')].every((x) => [...x.querySelectorAll('svg')].filter((v) => v.getBoundingClientRect().width).length === 1));
  ok(copies, 'each glyph shows one copy, the one drawn for its size');
  await p.mouse.move(0, 0);
  // the labels ride in each figure's title: sample size and range for the three with a spread, the
  // overhead's pairs; under each figure at most its scope in a few words
  const spreads = await p.evaluate(() => [...document.querySelectorAll('.tbl .val')].filter((a) => a.querySelector('.fig'))
    .map((a) => ({ t: /evidence: /.test(a.title) && (/\d+\s+completed, \d+\s+failed, .+(\sto\s|\sin\sall\s\d+\sruns)/.test(a.title) || /prover\sruns?\s×\s\d+\sserving/.test(a.title)), sub: [...a.querySelectorAll('.sub > span:not(.sr)')].map((x) => x.textContent).join(' ').split(' ').length <= 4 })));
  ok(spreads.length === 8 && spreads.every((x) => x.t && x.sub), 'each figure carries its labels in its title, at most a scope word under it', spreads);
  // no states key under the legend: the slice inks and their tips name the states
  ok(await p.evaluate(() => !document.querySelector('.mast .keyline, .mast .chip, .mast a')), 'the legend holds no states key and no link');
  await ctx.close();
}

// not benchmarked yet: a named petal takes the model line's place in one sentence, and no card moves, at four cards a
// row (1440) and where the longest name wraps (1340)
for (const w of [1340, 1440]) {
  const { ctx, p } = await pg(w, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  const nb = await p.evaluate(() => {
    const cards = [...document.querySelectorAll('.nb')];
    const h0 = cards.map((c) => c.getBoundingClientRect().height);
    const moved = []; let named = 0; let said = '';
    cards.forEach((c, i) => {
      const pie = c.querySelector('.nbpie');
      for (let n = 1; n <= 6; n++) {
        const hit = [...pie.querySelectorAll(`.hit path[data-n="${n}"]`)].find((x) => x.getBoundingClientRect().width);
        const r = hit.getBoundingClientRect();
        hit.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, pointerType: 'mouse', clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 }));
        const t = c.querySelector('.tip');
        if (getComputedStyle(t).display !== 'none' && /^[A-Z][a-z].*: [a-z ]+$/.test(t.textContent)) named++;
        if (c.id === 'nb-remainder' && n === 3) said = t.textContent;
        const h = c.getBoundingClientRect().height;
        if (Math.abs(h - h0[i]) > 0.5) moved.push(`${c.id}:${n}:${Math.round(h - h0[i])}`);
        pie.dispatchEvent(new PointerEvent('pointerleave', { pointerType: 'mouse' }));
      }
    });
    return { cards: cards.length, named, said, moved };
  });
  ok(nb.named === nb.cards * 6 && nb.said === 'Whole output checked: not stated' && !nb.moved.length, `home-${w}: a named petal reads "Property: state" in the model line's place, and no card moves`, nb);
  await ctx.close();
}

// ---------------------------------------------------------------- sorting by the column heads: every column, both directions
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const st0 = await sortState(p);
  const lay0 = JSON.stringify(await layout(p));
  ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'overhead', 'asc')) && st0.aria.join() === 'overhead:ascending' && st0.heads === st0.tables && st0.hash === '', 'default: overhead ascending, one sorted head, empty hash', st0);
  for (const col of ['system', 'overhead', 'per_bit', 'size_bit', 'check_bit']) {
    for (const dir of ['asc', 'desc']) {
      await sortBy(p, col, dir);
      const got = await order(p);
      const st = await sortState(p);
      ok(JSON.stringify(got) === JSON.stringify(await expected(p, col, dir)) && st.heads === st.tables && st.aria.join() === `${col}:${dir === 'asc' ? 'ascending' : 'descending'}`
        && (col === 'overhead' && dir === 'asc' ? st.hash === '' : st.hash === `#sort=${col}-${dir}`) && JSON.stringify(await layout(p)) === lay0, `sort ${col} ${dir}`, { got, hash: st.hash, glyphs: st.glyphs });
    }
  }
  await sortBy(p, 'size_bit', 'desc');
  ok(await cls(p) === 0, 'CLS after a sort (shifts without input) is 0');
  const said = await p.evaluate(() => document.querySelector('#sort-now').textContent);
  ok(said === 'Proof size, large to small', 'the order is named for screen readers', said);
  await ctx.close();
  const r = await pg(1440, 900);
  await r.p.goto(BASE + '#sort=check_bit-desc', { waitUntil: 'networkidle' }); await r.p.waitForTimeout(settle);
  const st2 = await sortState(r.p);
  ok(st2.aria.join() === 'check_bit:descending' && JSON.stringify(await order(r.p)) === JSON.stringify(await expected(r.p, 'check_bit', 'desc')), 'hash round-trip', st2);
  ok(JSON.stringify(await layout(r.p)) === lay0, 'a sort from the hash keeps every row');
  ok(await cls(r.p) === 0, 'CLS on load with a sort hash is 0');
  await r.p.evaluate(() => { location.hash = 'sort=overhead-desc'; }); await r.p.waitForTimeout(400);
  ok((await sortState(r.p)).aria.join() === 'overhead:descending', 'hashchange applies a new order');
  await r.ctx.close();
  // Back to the page without a hash shows the default order again
  const bk = await pg(1440, 900);
  await bk.p.goto(BASE, { waitUntil: 'networkidle' }); await bk.p.waitForTimeout(settle);
  await bk.p.evaluate(() => { location.hash = 'sort=check_bit-desc'; }); await bk.p.waitForTimeout(300);
  await bk.p.goBack(); await bk.p.waitForTimeout(400);
  const stb = await sortState(bk.p);
  ok(stb.aria.join() === 'overhead:ascending' && stb.hash === '', 'Back to no hash restores the default order', stb);
  // sorting that can fail: rows that differ in every column, with missing values among them
  await bk.p.evaluate(() => {
    const box = document.querySelector('.tbl .rows');
    const src = box.querySelector('.row');
    [['zz-a', 'aaa', { per_bit: 5e-13, size_bit: null, check_bit: 9, overhead: 3 }],
     ['zz-b', 'zzz', { per_bit: null, size_bit: 1, check_bit: null, overhead: 7 }]].forEach(([id, name, k]) => {
      const r = src.cloneNode(true); r.id = id; r.dataset.name = name; r.dataset.k = JSON.stringify(k); box.appendChild(r);
    });
  });
  for (const col of ['per_bit', 'size_bit', 'check_bit', 'overhead']) {
    for (const dir of ['asc', 'desc']) {
      await sortBy(bk.p, col, dir);
      const got = (await order(bk.p))[0];
      const keys = await bk.p.evaluate((col) => [...document.querySelector('.tbl .rows').children].map((r) => JSON.parse(r.dataset.k)[col]), col);
      const firstNull = keys.findIndex((k) => k == null);
      const missingLast = firstNull === -1 || keys.slice(firstNull).every((k) => k == null);
      ok(JSON.stringify(got) === JSON.stringify((await expected(bk.p, col, dir))[0]) && missingLast, `sort with missing values: ${col} ${dir}`, { got, keys });
    }
  }
  await bk.ctx.close();
  const z = await pg(1440, 900);
  await z.p.goto(BASE + '#sort=bogus-asc', { waitUntil: 'networkidle' }); await z.p.waitForTimeout(600);
  const stz = await sortState(z.p);
  ok(stz.aria.join() === 'overhead:ascending' && stz.hash === '', 'unknown sort in the hash falls back and clears it', stz.hash);
  await z.ctx.close();
}

// ---------------------------------------------------------------- search
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const opts = () => p.evaluate(() => [...document.querySelectorAll('#q-list .so')].map((o) => ({ name: o.querySelector('.sn').textContent, kind: o.className.replace(/.*k-/, ''), group: document.getElementById(o.closest('[role=group]')?.getAttribute('aria-labelledby') || '')?.textContent || '', url: '' })));
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
  ok(firstNb > 0 && zk.slice(firstNb).every((o) => o.kind === 'unbenchmarked' && o.group === 'Not benchmarked'), 'not-benchmarked systems come after the others, under their group heading, no badge', zk.map((o) => `${o.name}:${o.group}`));
  ok(await p.evaluate(() => !document.querySelector('.sbadge') && !/more: type more letters/.test(document.getElementById('q-list').textContent)), 'no badge and no instruction in the results, every match listed');
  await type('atestable');
  ok((await opts())[0]?.name === 'Attestable prover', 'one typo still finds the system');
  await p.keyboard.press('Enter'); await p.waitForTimeout(500);
  const tgt = await p.evaluate(() => ({ url: location.pathname + location.hash, bar: getComputedStyle(document.querySelector('#nb-attestable'), '::before').content, label: getComputedStyle(document.querySelector('#nb-attestable .nbn'), '::after').content, field: document.getElementById('q').value }));
  ok(tgt.url === '/#nb-attestable' && tgt.bar !== 'none' && tgt.label === 'none' && tgt.field === '', 'a not-benchmarked result leads to its card in the overview, marked by its edge only, the field cleared', tgt);
  await type('qqqqzz');
  ok(await p.evaluate(() => document.querySelector('#q-list .snone')?.textContent === 'No match'), 'no match says so');
  for (const [q, want] of [['atest', 'Attestable prover'], ['flsh', 'FlashProve'], ['flahsprove', 'FlashProve'], ['sahs', 'SASH'], ['llama4', 'FlashProve']]) {
    await type(q);
    ok((await opts())[0]?.name === want, `"${q}" finds ${want} first`, (await opts()).map((o) => o.name).slice(0, 3));
  }
  await type('sash');
  const sash = await opts();
  ok(sash[0]?.name === 'SASH' && !sash.some((o) => o.kind === 'unbenchmarked'), 'an exact word brings no typo noise ("sash" finds SASH first, and what ran its workload)', sash.map((o) => o.name));
  for (const [q, want] of [['criteria', '/criteria'], ['release', '/release'], ['h200', '/flashprove'], ['vllm', '/reference#ref-serve']]) {
    await type(q);
    const first = await p.evaluate(() => document.querySelector('#q-list .so')?.querySelector('.sn')?.textContent);
    ok(!!first, `"${q}" finds something (pages, hardware, engines are indexed)`, { q, first, want });
  }
  // a system page's sections are found by what they hold, under the system's name; an absence is never a match
  await type('proof size');
  const ps = await opts();
  ok(ps[0]?.name === 'Figures' && ps[0]?.group === 'FlashProve' && !ps.some((o) => o.name === 'EZKL'), '"proof size" finds each system\'s Figures first, no system by "size not stated"', ps.map((o) => `${o.group}:${o.name}`));
  await type('check time');
  const ct = await opts();
  ok(ct.length === 2 && ct.every((o) => o.name === 'Figures'), '"check time" finds the two Figures and nothing one typo away ("tied")', ct.map((o) => `${o.group}:${o.name}`));
  await type('model');
  const md = await opts();
  ok(!md.some((o) => ['NanoZK', 'Tinfoil', 'Verde (with RepOps)', 'Private ML SDK'].includes(o.name)), '"model" finds no system by "Model not named"', md.map((o) => o.name));
  await type('reference');
  const rf = await opts();
  ok(rf[0]?.name === 'Production serving' && !rf.some((o) => o.name === 'Reference'), '"reference" finds the one reference once, no page entry beside it', rf.map((o) => o.name));
  await type('w8a8');
  const wa = await opts();
  ok(wa.length === 1 && wa[0].name === 'SASH', '"w8a8" finds the system that proves at that precision, and only it', wa.map((o) => o.name));
  await type('stark');
  ok(JSON.stringify((await opts()).map((o) => o.name)) === '["SASH","LuminAIR"]', '"stark" finds only the systems whose stated technique is one');
  await type('a');
  ok((await opts()).some((o) => o.name === 'Attestable prover'), 'one letter still lists the not-benchmarked names that start with it');
  // a match in the name comes before one in the other words only; not-benchmarked systems stay last
  for (const [q, want] of [['weights', ['Weights hidden']], ['model', ['Model bound']], ['zk', ['FlashProve', 'SASH']], ['sash tamper', ['Tamper tests']]]) {
    await type(q);
    const got = await opts();
    ok(JSON.stringify(got.slice(0, want.length).map((o) => o.name)) === JSON.stringify(want) && (q !== 'sash tamper' || (got.length === 1 && got[0].group === 'SASH')), `"${q}" lists ${want.join(', ')} first`, got.map((o) => `${o.group}:${o.name}`).slice(0, 6));
  }
  // a result found by its other words shows the phrase that holds them, a figure its plate; a section has no glyph gutter
  await type('proving time');
  const pt = await p.evaluate(() => [...document.querySelectorAll('#q-list .so')].map((o) => ({ meta: o.querySelector('.sm')?.textContent, gutter: !!o.querySelector('.sp'), x: Math.round(o.querySelector('.sn').getBoundingClientRect().left - o.getBoundingClientRect().left) })));
  ok(pt.length === 2 && pt.every((o) => /^Proving time per token/.test(o.meta) && !o.gutter && o.x <= 12), '"proving time" names the figure each Figures result was found by, no empty glyph gutter', pt);
  await type('weights');
  const ws = await opts();
  const sashWhy = await p.evaluate(() => [...document.querySelectorAll('#q-list .so')].find((o) => o.querySelector('.sn').textContent === 'SASH')?.querySelector('.sm')?.textContent);
  ok(/weights/i.test(sashWhy || ''), '"weights" shows the phrase SASH was found by', { sashWhy, ws: ws.map((o) => o.name) });
  await type('proving time');
  await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(/^\/flashprove#.*fig-per_bit$/.test(new URL(p.url()).pathname + new URL(p.url()).hash), 'Enter on a figure found by its name opens its plate', p.url());
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300);
  await type('weights hidden');
  await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname + new URL(p.url()).hash === '/criteria#weights_hidden', 'Enter goes to the first result of a typed search', p.url());
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300); await type('weights');
  const second = await p.evaluate(() => [...document.querySelectorAll('#q-list .so')].length);
  await p.keyboard.press('ArrowDown'); await p.waitForTimeout(100);
  const marked = await p.evaluate(() => document.querySelectorAll('#q-list .so.on').length === 1 && document.querySelectorAll('#q-list .so')[1]?.classList.contains('on'));
  ok(second > 1 && marked, 'the arrows mark one other result', { second, marked });
  // Escape closes an open list first, then clears the field
  await p.keyboard.press('Escape'); await p.waitForTimeout(100);
  const esc = await p.evaluate(() => ({ hidden: document.getElementById('q-list').hidden, value: document.getElementById('q').value }));
  await p.keyboard.press('Escape'); await p.waitForTimeout(100);
  const esc2 = await p.evaluate(() => document.getElementById('q').value);
  ok(esc.hidden && esc.value === 'weights' && esc2 === '', 'Escape closes the list, then clears the field', { esc, esc2 });
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(400);
  ok(new URL(p.url()).pathname === '/', 'Enter in an empty field picks nothing', p.url());
  // on a system page its own sections come first: "tamper" and Enter stay on /sash
  await p.goto(BASE + 'sash', { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.focus('#q'); await p.waitForTimeout(300); await type('tamper');
  await p.keyboard.press('Enter'); await p.waitForTimeout(600);
  ok(new URL(p.url()).pathname + new URL(p.url()).hash === '/sash#tamper', '"tamper" from /sash opens its own tamper tests', p.url());
  // "/" mid-page opens the field over the page where it is; Escape closes it, the page where it was
  await p.goto(BASE + 'flashprove', { waitUntil: 'networkidle' }); await p.waitForTimeout(400);
  await p.evaluate(() => scrollTo(0, 3300)); await p.waitForTimeout(200);
  await p.keyboard.press('/'); await p.waitForTimeout(400);
  const mid = await p.evaluate(() => ({ y: Math.round(scrollY), focus: document.activeElement.id, top: Math.round(document.querySelector('.sfield').getBoundingClientRect().top), list: !document.getElementById('q-list').hidden }));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  const after = await p.evaluate(() => ({ y: Math.round(scrollY), on: document.querySelector('.top').classList.contains('s-on'), inert: !!document.querySelector('[inert]') }));
  ok(mid.y === 3300 && mid.focus === 'q' && mid.top >= 0 && mid.top < 60 && mid.list && after.y === 3300 && !after.on && !after.inert, '"/" mid-page opens search on screen without scrolling; Escape leaves the page where it was', { mid, after });
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
  await p.locator('.sb[data-col="size_bit"]').first().focus();
  await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  let st = await sortState(p);
  ok(st.aria.join() === 'size_bit:ascending', 'Enter on Proof size sorts ascending', st);
  await p.keyboard.press('Space'); await p.waitForTimeout(300);
  st = await sortState(p);
  ok(st.aria.join() === 'size_bit:descending', 'Space on it again sorts descending', st);
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
      ok(await p.locator('.sb[data-col="check_bit"]').first().isVisible(), `home-${w} the column heads stay as sort buttons`);
      await sortBy(p, 'check_bit', 'desc');
      ok(JSON.stringify(await order(p)) === JSON.stringify(await expected(p, 'check_bit', 'desc')), `home-${w} sorts from the heads`);
    }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- system pages and the reference page: the pie with its properties around it
// each property's text beside its own triangle, as on main before #320: the rose's height at 1440 px, measured on
// origin/main at c81832d, is the composition the system page keeps (within 10 %)
const ROSE_MAIN = { flashprove: 309, sash: 309 };
// the reference page: a reference whose six states are one shows its glyph once, small, beside one line, then what
// production serving measured, one row per configuration it ran
{
  const { ctx, p } = await pg(1440, 900);
  await p.goto(BASE + 'reference', { waitUntil: 'networkidle' });
  const r = await p.evaluate(() => ({ glyphs: [...document.querySelectorAll('.refpie svg')].filter((s) => s.getBoundingClientRect().width).length, roses: document.querySelectorAll('.rose').length, rows: document.querySelectorAll('.stab tbody tr').length, plates: document.querySelectorAll('.plate').length }));
  ok(r.glyphs === 1 && r.roses === 0 && r.rows >= 1 && r.plates === 0, 'reference: one small glyph, the measured table, no empty plates', r);
  // its glyph, a link to the criteria, names a petal under the pointer in its line's place, as every glyph does: the
  // petal lifts, nothing moves
  const at = await p.evaluate(() => { const h = [...document.querySelectorAll('.refpie .hit path[data-n="2"]')].find((x) => x.getBoundingClientRect().width).getBoundingClientRect(); return [h.x + h.width * 0.7, h.y + h.height / 2, Math.round(document.querySelector('.refone').getBoundingClientRect().height)]; });
  await p.mouse.move(at[0], at[1]); await p.waitForTimeout(400);
  const hv = await p.evaluate(() => ({ tip: document.querySelector('.reft .tip').textContent, line: getComputedStyle(document.querySelector('.refline')).visibility, lift: getComputedStyle([...document.querySelectorAll('.refpie .s2')].find((x) => x.getBoundingClientRect().width)).transform, h: Math.round(document.querySelector('.refone').getBoundingClientRect().height) }));
  ok(/^Model bound: [a-z ]+$/.test(hv.tip) && hv.line === 'hidden' && hv.lift !== 'none' && hv.h === at[2], 'reference: a hovered petal of the glyph lifts and names itself in the line\'s place, nothing moves', hv);
  await ctx.close();
}
for (const name of ['flashprove', 'sash']) {
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
  const fold = await p.evaluate(() => ({ stray: [...document.querySelectorAll('blockquote')].filter((q) => !q.closest('.howread')).length, details: [...document.querySelectorAll('details.howread, details.cardfull')].map((d) => `${d.className}:${d.open}`) }));
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
  ok(!/work in progress/i.test(await p.locator('body').innerText()) && /^Llama\s3\.1\s8B/.test(await p.locator('#figures h3.setup').first().innerText()), 'sash: no work-in-progress label; its figures name their model, Llama 3.1 8B');
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
  await p.evaluate(() => { location.hash = 'sort=size_bit-desc'; }); await p.waitForTimeout(300);
  ok((await sortState(p)).aria.join() === 'size_bit:descending', 'a malformed hash does not stop hash sorting');
  // a phone held sideways: the first table's heading shows on landing
  await ctx.close();
  const ls = await pg(844, 390, { touch: true });
  await ls.p.goto(BASE, { waitUntil: 'networkidle' }); await ls.p.waitForTimeout(settle);
  const hb = await ls.p.evaluate(() => Math.round(document.querySelector('.board .sect').getBoundingClientRect().bottom));
  ok(hb <= 390, 'landscape phone: the table heading shows on landing', hb);
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
  for (const [w, h] of [[320, 640], [390, 844], [600, 900], [768, 1024], [844, 390]]) {
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
for (const [w, h] of [[375, 667], [360, 640], [320, 568]]) {
  // the legend: a 2 x 3 key, so the first glyph shows on landing; the questions still read aloud
  const { ctx, p } = await pg(w, h, { touch: true });
  await p.goto(BASE, { waitUntil: 'networkidle' });
  // 375 x 667: the first glyph whole; 320 x 568: the first row starts on screen
  const l = await p.evaluate((w) => ({ pie: Math.round(document.querySelector(w >= 375 ? '.tbl .row .pie' : '.tbl .row').getBoundingClientRect()[w >= 375 ? 'bottom' : 'top']), cols: new Set([...document.querySelectorAll('.q')].map((q) => Math.round(q.getBoundingClientRect().left))).size, qq: [...document.querySelectorAll('.qq')].every((q) => q.textContent.length > 10 && getComputedStyle(q).clipPath === 'inset(50%)') }), w);
  ok(l.pie < h && l.cols === 2 && l.qq, `home-${w}x${h}: the legend in two columns, the first system on landing, the questions kept for screen readers`, l);
  // the table on a phone: one note over the heads, then the four figure heads, level, sort buttons 32 px
  // tall or more (no System head: the rows stack); each system's four figures on one line, under their
  // heads (each cell's label read aloud), each with its labels in its title
  const s = await p.evaluate(() => {
    const r = (x) => x.getBoundingClientRect();
    const t = document.querySelector('.board');
    const b = [...t.querySelectorAll('.hc .sb')].filter((x) => r(x).height);
    const cells = [...t.querySelectorAll('.row .vc')];
    const note = t.querySelector('.hn'); const heads = b.length === 4 && new Set(b.map((x) => Math.round(r(x).bottom))).size === 1 && !!note && r(note).height > 0 && r(note).bottom <= Math.min(...b.map((x) => r(x).top));
    const line = [...t.querySelectorAll('.row')].every((row) => new Set([...row.querySelectorAll('.vc')].map((c) => Math.round(r(c).top))).size === 1);
    // each unit on its number's line: its box inside the number's, never wrapped under it
    const units = [...t.querySelectorAll('.row .fig')].every((f) => { const n = r(f.querySelector('.n')); const u = f.querySelector('.u'); if (!u) return true; const b = r(u); return b.top >= n.top - 1 && b.bottom <= n.bottom + 1; });
    return { h: Math.min(...b.map((x) => Math.round(r(x).height))), heads, labels: cells.every((c) => c.querySelector('.lbl').textContent.length > 4), subs: cells.every((c) => !c.querySelector('.fig') || /evidence: /.test(c.querySelector('.val').title)), line, units, n: cells.length };
  });
  ok(s.h >= 32 && s.heads && s.labels && s.subs && s.line && s.units && s.n === 8, `home-${w}: one note over four level figure heads, sort buttons 32 px tall or more; each system's figures on one line, each unit beside its number, each with its labels in its title`, s);
  await ctx.close();
}
{
  // touch: the first tap on a triangle names it, the second follows the link; every figure in paper, sorted or not
  // (no column reads as the primary one; the pressed head marks the order)
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE + '#sort=check_bit-desc', { waitUntil: 'networkidle' }); await p.waitForTimeout(settle);
  const mk = await p.evaluate(() => [...document.querySelectorAll('.tbl .vc')].map((c) => `${c.dataset.col}:${getComputedStyle(c).color === 'rgb(241, 239, 233)' ? 'on' : 'off'}`));
  ok(mk.length && mk.every((x) => x.endsWith('on')), 'home-390: every figure in paper, whichever column sorts', mk);
  await p.locator('#flashprove .pie').scrollIntoViewIfNeeded();
  const bx = await p.locator('#flashprove .pie').boundingBox();
  const at = [bx.x + bx.width * 0.85, bx.y + bx.height * 0.5];
  await p.touchscreen.tap(...at); await p.waitForTimeout(300);
  const tip = await p.evaluate(tipSeen, '#flashprove');
  ok(tip.path === '/' && tip.hot === '2' && tip.shown && /Model bound/.test(tip.text) && tip.sw && tip.named && tip.card && tip.aim && tip.inView, 'touch: a first tap on a triangle names it in a card pointing at it, on screen, the system\'s name still shown, and stays on the page', tip);
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
// bound phrases on one line, folds open, phones and laptops: "sd < 0.1 %", a record key's factor, a pair count, a date,
// a count and its unit word never part at a line's end
for (const w of [320, 360, 390, 1100, 1280]) {
  for (const name of ['flashprove', 'sash']) {
    const { ctx, p } = await pg(w, 844);
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    await p.evaluate(() => document.querySelectorAll('details').forEach((d) => { d.open = true; }));
    const bound = await p.evaluate(() => {
      const phrases = [/sd\s<\s0\.1\s%/g, /\.session\s×\s1,000/g, /\d+\s×\s\d+\spairs/g, /\b\d{4}-\d{2}-\d{2}\b/g, /\b\d+\s(?:runs?|bits|tokens|threads|trials)\b/g];
      const out = []; let n = 0;
      const tw = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT);
      const lines = (r) => new Set([...r.getClientRects()].filter((x) => x.width > 0.5).map((x) => Math.round(x.top))).size;
      for (let t = tw.nextNode(); t; t = tw.nextNode()) {
        // read aloud only, or a failed run's last line as logged (a raw path breaks anywhere)
        if (t.parentElement.closest('.sr, .ll p')) continue;
        for (const re of phrases) {
          for (const m of t.data.matchAll(re)) {
            const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
            const k = lines(r);
            if (!k) continue;
            n++;
            if (k > 1) out.push(t.data.slice(Math.max(0, m.index - 16), m.index + m[0].length + 4));
          }
        }
      }
      // a record key in parts: its last part holds its factor (".session × 1,000") on one line
      document.querySelectorAll('.src').forEach((src) => {
        const last = [...src.querySelectorAll('.seg')].pop();
        if (!last || !/×\s1,000$/.test(last.textContent)) return;
        const r = document.createRange(); r.selectNodeContents(last); n++;
        if (lines(r) > 1) out.push(src.textContent);
      });
      return { n, out };
    });
    ok(bound.n > 0 && !bound.out.length, `${name}-${w}: bound phrases never part at a line's end`, bound);
    await ctx.close();
  }
}
// the claims block in the order focus takes (WCAG 2.4.3): the glyph, then how we read it under it, then the facts, beside
// both on wide screens and under them below 1241 px
for (const w of [1440, 1240, 390]) {
  for (const name of ['flashprove', 'sash']) {
    const { ctx, p } = await pg(w, 900);
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const o = await p.evaluate(() => {
      const b = (s) => document.querySelector(s).getBoundingClientRect();
      const rose = b('.over > .rose'); const how = b('.over > .howread'); const facts = b('.over > .facts');
      return { under: how.top >= rose.bottom - 1, facts: facts.top >= how.bottom - 1 || facts.left >= how.right - 1 };
    });
    ok(o.under && o.facts, `${name}-${w}: the glyph, how we read it, the facts, in focus order`, o);
    await ctx.close();
  }
}
// how we read it: one tamper-tests label per property, the run set named once (a link to the tamper tests), never a
// run list repeated from line to line; the open fold's height at 320 px recorded
for (const name of ['flashprove', 'sash']) {
  const { ctx, p } = await pg(320, 844, { touch: true });
  await p.goto(BASE + name, { waitUntil: 'networkidle' });
  await p.tap('details.howread summary'); await p.waitForTimeout(200);
  const hw = await p.evaluate(() => {
    const entries = [...document.querySelectorAll('.hw > div')];
    const labels = entries.map((d) => d.querySelectorAll('.ec').length);
    const runs = entries.map((d) => [...d.querySelectorAll('.ec a.run')].map((a) => a.title));
    const sets = [...document.querySelectorAll('.ec a.psrc')].map((a) => a.getAttribute('href'));
    return { labels, repeated: runs.filter((r) => r.length !== new Set(r).size).length, sets: [...new Set(sets)], fold: Math.round(document.querySelector('.howread').getBoundingClientRect().height) };
  });
  log(`${name}-320 how we read it open: ${hw.fold} px`);
  ok(hw.labels.every((n) => n <= 1) && !hw.repeated && hw.sets.every((h) => h === '#tamper'), `${name}-320: one tamper-tests label per property, no run listed twice, the run set linked to the tamper tests`, hw);
  await ctx.close();
}
// from 1241 px the facts sit beside the glyph and how we read it: opening the fold moves neither
for (const w of [1280, 1440]) {
  for (const name of ['flashprove', 'sash']) {
    const { ctx, p } = await pg(w, 900);
    await p.goto(BASE + name, { waitUntil: 'networkidle' });
    const at = () => p.evaluate(() => ['.over > .facts', '.over .rpie'].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().top + scrollY)));
    const shut = await at();
    await p.click('.howread summary'); await p.waitForTimeout(200);
    const open = await at();
    ok(JSON.stringify(shut) === JSON.stringify(open), `${name}-${w}: opening how we read it leaves the facts and the glyph where they were`, { shut, open });
    await ctx.close();
  }
}
// a figure link from the overview to a page of several setups lands under that setup's heading, held at the top
// in one line, never over the plate's label
for (const w of [320, 390, 768, 1440]) {
  const { ctx, p } = await pg(w, 844);
  await p.goto(BASE, { waitUntil: 'networkidle' });
  const hrefs = await p.evaluate(() => [...document.querySelectorAll('a.val')].map((a) => a.getAttribute('href')).filter((h) => /--/.test(h)));
  const bad = [];
  for (const href of hrefs) {
    await p.goto(BASE + href.slice(1), { waitUntil: 'networkidle' }); await p.waitForTimeout(300);
    const r = await p.evaluate(() => {
      const t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      const h = t.closest('.cfgfigs')?.querySelector('h3.setup');
      if (!h) return { href: location.hash, none: true };
      const hb = h.getBoundingClientRect(); const lb = t.querySelector('.lbl').getBoundingClientRect();
      const lh = parseFloat(getComputedStyle(h).fontSize) * 1.6;
      return { href: location.hash, top: Math.round(hb.top), one: h.querySelector('[aria-hidden]').getBoundingClientRect().height < lh, clear: lb.top >= hb.bottom };
    });
    if (r.none || r.top !== 0 || !r.one || !r.clear) bad.push(r);
  }
  ok(hrefs.length > 0 && !bad.length, `figure links-${w}: the landing names its setup in one line at the top, over no label`, { n: hrefs.length, bad });
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
  // the 404 page on a phone: the one-row header, the systems listed (the header and footer link the rest), search from the button
  const { ctx, p } = await pg(390, 844, { touch: true });
  await p.goto(BASE + 'nope', { waitUntil: 'networkidle' });
  const f = await p.evaluate(() => ({ h: Math.round(document.querySelector('.top').getBoundingClientRect().height), links: document.querySelectorAll('.lost a').length, focus: document.activeElement.tagName }));
  ok(f.h <= 60 && f.links === 2 && f.focus === 'BODY', '404-390: the header on one row, the systems listed, nothing focused', f);
  await p.tap('.sopen'); await p.fill('#q', 'sash'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(600);
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
  for (const name of ['flashprove', 'sash', 'release']) {
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
    // the whole page in view, so a press can be tried anywhere on it: each target's hit height is what a press at its
    // middle reaches (document.elementFromPoint), so a box the next line covers counts only where it is reached
    const vp = p.viewportSize();
    await p.setViewportSize({ width: vp.width, height: await p.evaluate(() => document.documentElement.scrollHeight) }); await p.waitForTimeout(200);
    const t = await p.evaluate(() => {
      const sel = '.ev a, .rp .psrc, .howread a, .howread summary, .cardfull a, .cardfull summary, .gapblk a, .facts a, .runs a, .unexp a, .reply a, .relf a, .tlab a, .es a, .mtab a';
      const els = [...document.querySelectorAll(sel)].filter((a) => a.getClientRects().length && !a.closest('.sr, [hidden]'));
      const bx = els.map((a) => ({ a, rs: [...a.getClientRects()].filter((r) => r.width) }));
      const reach = (a, r) => { let n = 0; const x = r.left + Math.min(r.width / 2, 8); for (let y = r.top - 8; y < r.bottom + 8; y += 0.5) { const at = document.elementFromPoint(x, y); if (at && (at === a || a.contains(at))) n += 0.5; } return n; };
      const small = bx.filter((x) => x.rs.some((r) => reach(x.a, r) < 24)).map((x) => `${x.a.textContent.trim().slice(0, 24)} ${Math.min(...x.rs.map((r) => reach(x.a, r)))}`);
      const hit = [];
      for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) {
        if (bx[i].a.contains(bx[j].a) || bx[j].a.contains(bx[i].a)) continue;
        if (bx[i].rs.some((r1) => bx[j].rs.some((r2) => r1.left < r2.right - 0.5 && r2.left < r1.right - 0.5 && r1.top < r2.bottom - 0.5 && r2.top < r1.bottom - 0.5))) hit.push(`${bx[i].a.textContent.trim().slice(0, 16)} x ${bx[j].a.textContent.trim().slice(0, 16)}`);
      }
      return { n: els.length, small, hit };
    });
    ok(t.n > 0 && !t.small.length && !t.hit.length, `${name}-${w}: the new blocks' links and buttons reached over 24 px or more where pressed, none overlapping`, t);
    await p.setViewportSize(vp);
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
