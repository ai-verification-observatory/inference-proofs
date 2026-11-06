// MADE OF WORDS: behaviour only. No value, label or quote is typed here: everything printed
// comes from the page, which build.py wrote from site.json (sort keys included, in data-k).
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const live = $('#live');
  const say = (t) => { if (live) { live.textContent = ''; requestAnimationFrame(() => { live.textContent = t; }); } };
  const mouse = (ev) => ev.pointerType === 'mouse';
  let reduce = false;
  try { reduce = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { /* no media queries */ }

  // ------------------------------------------------------------ row pies: the slice under the pointer lifts,
  // and its property's name and state show under the pie (positioned: nothing moves). The others keep their ink.
  $$('.row .pie').forEach((pie) => {
    const tip = $('.tip', pie);
    let hot = 0;
    const set = (sl) => {
      const n = sl ? +sl.dataset.n : 0;
      if (n === hot) return;
      hot = n;
      if (!n) { delete pie.dataset.hot; return; }
      pie.dataset.hot = n;
      if (tip) {
        const b = document.createElement('b');
        b.textContent = sl.dataset.name;
        const sw = document.createElement('i');
        sw.className = `sw ${[...sl.classList].find((c) => ['yes', 'partly', 'no', 'unstated'].includes(c)) || ''}`;
        tip.replaceChildren(b, sw, document.createTextNode(sl.dataset.word));
      }
    };
    pie.addEventListener('pointermove', (ev) => { if (mouse(ev)) set(ev.target.closest('.sl')); });
    pie.addEventListener('pointerleave', () => set(null));
  });

  // ------------------------------------------------------------ sorting the benchmarked tables by their column heads
  // One order for every model's table. Keys come from data-k (computed by build.py from the raw numbers).
  // Rows with no number go last in both directions; ties and the default fall back to the name, A to Z.
  // The order lives in the hash.
  const tbls = $$('.tbl');
  if (!tbls.length) return;
  const state = { col: 'system', dir: 'asc' };
  const DEFAULT = 'system-asc';
  const keys = new Map();
  const btn = (col) => $(`.tbl .sb[data-col="${col}"]`);
  const words = () => { const b = btn(state.col); return b ? `${b.firstChild.textContent}, ${b.dataset[state.dir]}` : ''; };

  const sortRows = (animate) => tbls.forEach((tbl) => {
    const box = $('.rows', tbl);
    const rows = $$(':scope > .row', box);
    rows.forEach((r) => { if (!keys.has(r)) keys.set(r, JSON.parse(r.dataset.k)); });
    const s = state.dir === 'desc' ? -1 : 1;
    const byName = (a, b) => a.dataset.name.localeCompare(b.dataset.name);
    const sorted = [...rows].sort((a, b) => {
      if (state.col === 'system') return s * byName(a, b);
      const x = keys.get(a)[state.col];
      const y = keys.get(b)[state.col];
      if (x == null && y == null) return byName(a, b);
      if (x == null) return 1;
      if (y == null) return -1;
      return s * (x - y) || byName(a, b);
    });
    const moved = sorted.some((r, i) => r !== rows[i]);
    const first = animate && moved && !reduce ? new Map(rows.map((r) => [r, r.getBoundingClientRect().top])) : null;
    if (moved && animate) document.body.classList.add('sorted'); // re-inserted rows must not replay their entrance
    if (moved) sorted.forEach((r) => box.appendChild(r));
    if (first) {
      sorted.forEach((r) => {
        const d = first.get(r) - r.getBoundingClientRect().top;
        if (d) r.animate([{ transform: `translateY(${d}px)` }, { transform: 'none' }], { duration: 200, easing: 'cubic-bezier(.2,.7,.3,1)' });
      });
    }
  });

  const paintHeads = () => {
    tbls.forEach((tbl) => { tbl.dataset.col = state.col; tbl.dataset.dir = state.dir; });
    $$('.tbl .hc').forEach((h) => {
      const on = h.dataset.col === state.col;
      if (on) h.setAttribute('aria-sort', state.dir === 'asc' ? 'ascending' : 'descending'); else h.removeAttribute('aria-sort');
      $('.g', h).textContent = on ? (state.dir === 'asc' ? '↑' : '↓') : '↕';
    });
    const now = $('#sort-now');
    if (now) now.textContent = words();
  };

  const writeHash = () => {
    const v = `${state.col}-${state.dir}`;
    const url = location.pathname + location.search + (v !== DEFAULT ? `#sort=${v}` : '');
    try { history.replaceState(null, '', url); } catch (_) { /* file: URLs */ }
  };

  const valid = (v) => { const i = v.lastIndexOf('-'); return i > 0 && !!btn(v.slice(0, i)) && ['asc', 'desc'].includes(v.slice(i + 1)); };
  const setSort = (v, { animate = true, announce = false, hash = true } = {}) => {
    if (!valid(v)) v = DEFAULT;
    const i = v.lastIndexOf('-');
    state.col = v.slice(0, i); state.dir = v.slice(i + 1);
    paintHeads();
    sortRows(animate);
    if (hash) writeHash();
    if (announce) say(`Sorted: ${words()}.`);
  };

  $$('.tbl .sb').forEach((b) => b.addEventListener('click', () => {
    const col = b.dataset.col;
    const dir = col === state.col && state.dir === 'asc' ? 'desc' : 'asc';
    setSort(`${col}-${dir}`, { announce: true });
  }));

  // the hash: #sort=proof_size-asc
  const readHash = (animate) => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (!/^sort=/.test(h)) return;
    const want = h.slice(5);
    setSort(want, { animate, hash: false });
    if (`${state.col}-${state.dir}` !== want) writeHash(); // an unknown order in the link: name the one shown
  };
  // the draft-criteria link scrolls to the footer without replacing the order kept in the hash
  $$('a[href="#criteria"]').forEach((a) => a.addEventListener('click', (ev) => {
    const t = $('#criteria');
    if (!t || !/^sort=/.test(location.hash.slice(1))) return;
    ev.preventDefault();
    t.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
  }));
  readHash(false);
  addEventListener('hashchange', () => readHash(true));
})();
