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

  // ------------------------------------------------------------ tabs
  const tabs = $$('[role=tab]');
  const bar = $('.tab-bar');
  const placeBar = () => {
    const t = tabs.find((x) => x.getAttribute('aria-selected') === 'true');
    if (!t || !bar) return;
    bar.style.setProperty('--x', `${t.offsetLeft}px`);
    bar.style.setProperty('--s', String(t.offsetWidth / 100));
  };
  const select = (t, focus) => {
    tabs.forEach((x) => {
      const on = x === t;
      x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1;
      $(`#${x.getAttribute('aria-controls')}`).hidden = !on;
    });
    document.body.dataset.tab = t.id.replace('tab-', '');
    if (focus) t.focus();
    placeBar();
  };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => { document.body.classList.add('tabbed'); select(t); });
    t.addEventListener('keydown', (ev) => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
      if (d) { ev.preventDefault(); document.body.classList.add('tabbed'); select(tabs[(i + d + tabs.length) % tabs.length], true); }
    });
  });
  placeBar();
  if (document.fonts) document.fonts.ready.then(placeBar);
  addEventListener('resize', placeBar);

  // ------------------------------------------------------------ sorting the benchmarked table
  // Keys come from data-k (computed by build.py from the raw numbers). Rows with no number go last in
  // both directions; ties and the default fall back to the name, A to Z. The order lives in the hash.
  const tbl = $('.tbl');
  const sel = $('#sort');
  const view = () => (document.body.classList.contains('view-run') ? 'run' : 'published');
  const state = { col: 'system', dir: 'asc' };
  const DEFAULT = 'system-asc';
  const keys = new Map();
  const words = (v) => (sel ? [...sel.options].find((o) => o.value === v)?.textContent : '') || '';

  const sortRows = (animate) => {
    if (!tbl) return;
    const box = $('.rows', tbl);
    const rows = $$(':scope > .row', box);
    rows.forEach((r) => { if (!keys.has(r)) keys.set(r, JSON.parse(r.dataset.k)); });
    const v = view();
    const s = state.dir === 'desc' ? -1 : 1;
    const byName = (a, b) => a.dataset.name.localeCompare(b.dataset.name);
    const sorted = [...rows].sort((a, b) => {
      if (state.col === 'system') return s * byName(a, b);
      const x = keys.get(a)[v][state.col];
      const y = keys.get(b)[v][state.col];
      if (x == null && y == null) return byName(a, b);
      if (x == null) return 1;
      if (y == null) return -1;
      return s * (x - y) || byName(a, b);
    });
    const moved = sorted.some((r, i) => r !== rows[i]);
    const first = animate && moved && !reduce && tbl.offsetParent ? new Map(rows.map((r) => [r, r.getBoundingClientRect().top])) : null;
    if (moved && animate) document.body.classList.add('sorted'); // re-inserted rows must not replay their entrance
    if (moved) sorted.forEach((r) => box.appendChild(r));
    if (first) {
      sorted.forEach((r) => {
        const d = first.get(r) - r.getBoundingClientRect().top;
        if (d) r.animate([{ transform: `translateY(${d}px)` }, { transform: 'none' }], { duration: 200, easing: 'cubic-bezier(.2,.7,.3,1)' });
      });
    }
  };

  const paintHeads = () => {
    if (!tbl) return;
    tbl.dataset.col = state.col; tbl.dataset.dir = state.dir;
    $$('.hc', tbl).forEach((h) => {
      const on = h.dataset.col === state.col;
      if (on) h.setAttribute('aria-sort', state.dir === 'asc' ? 'ascending' : 'descending'); else h.removeAttribute('aria-sort');
      $('.g', h).textContent = on ? (state.dir === 'asc' ? '↑' : '↓') : '↕';
    });
    const v = `${state.col}-${state.dir}`;
    if (sel) sel.value = v;
    const now = $('#sort-now');
    if (now) now.textContent = words(v);
  };

  const writeHash = () => {
    const v = `${state.col}-${state.dir}`;
    const parts = [];
    if (v !== DEFAULT) parts.push(`sort=${v}`);
    if (view() === 'run') parts.push('view=run');
    const url = location.pathname + location.search + (parts.length ? `#${parts.join('&')}` : '');
    try { history.replaceState(null, '', url); } catch (_) { /* file: URLs */ }
  };

  const setSort = (v, { animate = true, announce = false, hash = true } = {}) => {
    if (!sel || ![...sel.options].some((o) => o.value === v)) v = DEFAULT;
    const i = v.lastIndexOf('-');
    state.col = v.slice(0, i); state.dir = v.slice(i + 1);
    paintHeads();
    sortRows(animate);
    if (hash) writeHash();
    if (announce) say(`Sorted: ${words(v)}.`);
  };

  if (tbl) {
    $$('.sb', tbl).forEach((b) => b.addEventListener('click', () => {
      const col = b.dataset.col;
      const dir = col === state.col && state.dir === 'asc' ? 'desc' : 'asc';
      setSort(`${col}-${dir}`, { announce: true });
    }));
    if (sel) sel.addEventListener('change', () => setSort(sel.value, { announce: true }));
  }

  // ------------------------------------------------------------ published / run here (MOCK)
  const setView = (run, announce) => {
    document.body.classList.toggle('view-run', run);
    $$('.vk').forEach((x) => x.setAttribute('aria-pressed', String((x.dataset.view === 'run') === run)));
    if (announce) say(run ? 'Showing run-here values. They are MOCK.' : 'Showing the values each system published.');
  };
  $$('.vk').forEach((k) => k.addEventListener('click', () => {
    document.body.classList.add('switched');
    setView(k.dataset.view === 'run', true);
    if (tbl) { sortRows(true); writeHash(); }
  }));

  // ------------------------------------------------------------ the hash: #sort=proof_size-asc&view=run on the home;
  // a run-here figure link on a system page ends in "-run" and opens its target in the run view
  const readHash = (animate) => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (tbl && /(^|&)(sort|view)=/.test(h)) {
      const p = new URLSearchParams(h);
      setView(p.get('view') === 'run');
      const want = p.get('sort') || DEFAULT;
      setSort(want, { animate, hash: false });
      if (`${state.col}-${state.dir}` !== want) writeHash(); // an unknown order in the link: name the one shown
      return;
    }
    if (/-run$/.test(h)) {
      const t = document.getElementById(h.slice(0, -4));
      if (t) { setView(true); requestAnimationFrame(() => t.scrollIntoView()); }
    }
  };
  // the draft-criteria link scrolls to the footer without replacing the order kept in the hash
  if (tbl) {
    $$('a[href="#criteria"]').forEach((a) => a.addEventListener('click', (ev) => {
      const t = $('#criteria');
      if (!t || !/(^|&)(sort|view)=/.test(location.hash.slice(1))) return;
      ev.preventDefault();
      t.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
    }));
  }
  readHash(false);
  addEventListener('hashchange', () => readHash(true));
})();
