// MADE OF WORDS: behaviour only. No value, label or quote is typed here: everything printed
// comes from the page, which iproofs site build wrote (sort keys included, in data-k).
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
  // The pointer is read on the still .hit copy of the wedges, so a lifted slice never slips out from under it.
  $$('.row .pie').forEach((pie) => {
    const tip = $('.tip', pie);
    let hot = 0;
    const set = (n) => {
      if (n === hot) return;
      hot = n;
      if (!n) { delete pie.dataset.hot; return; }
      pie.dataset.hot = n;
      const sl = $(`.sl.s${n}`, pie);
      // a row drawn with no state carries no words on its slices (RFC-0016 OVR-8): no tip
      if (tip && sl && sl.dataset.word) {
        const b = document.createElement('b');
        b.textContent = sl.dataset.name;
        const sw = document.createElement('i');
        // the slice's state class (yes, partly, no, unstated) is the one besides sl, sN
        sw.className = `sw ${[...sl.classList].find((c) => c !== 'sl' && !/^s\d$/.test(c)) || ''}`;
        tip.replaceChildren(b, sw, document.createTextNode(sl.dataset.word));
      }
    };
    pie.addEventListener('pointermove', (ev) => { if (mouse(ev)) set(+(ev.target.closest('.hit path')?.dataset.n || 0)); });
    pie.addEventListener('pointerleave', (ev) => { if (mouse(ev)) set(0); });
    // touch: the first tap on a triangle names it; a second tap on the same one follows the link
    let kind = '';
    pie.addEventListener('pointerdown', (ev) => { kind = ev.pointerType; });
    pie.addEventListener('click', (ev) => {
      if (kind === 'mouse') return;
      const n = +(ev.target.closest('.hit path')?.dataset.n || 0);
      if (n && n !== hot) { ev.preventDefault(); set(n); }
    });
    document.addEventListener('pointerdown', (ev) => { if (!pie.contains(ev.target)) set(0); });
  });

  // ------------------------------------------------------------ system pages: on a touch screen, a tap on a slice or
  // on a property (not its link) lifts the slice and marks the property, as pointing does with a mouse
  $$('.rose').forEach((rose) => {
    let kind = '';
    const cool = () => { rose.removeAttribute('data-hot'); };
    rose.addEventListener('pointerdown', (ev) => { kind = ev.pointerType; });
    rose.addEventListener('click', (ev) => {
      if (kind === 'mouse' || ev.target.closest('a')) return;
      const at = ev.target.closest('.rpie .hit path') || ev.target.closest('.rp');
      const n = at ? at.dataset.n : '';
      if (!n) return;
      if (rose.dataset.hot === n) cool(); else rose.dataset.hot = n;
    });
    document.addEventListener('pointerdown', (ev) => { if (!rose.contains(ev.target)) cool(); });
  });

  // ------------------------------------------------------------ system pages: a link or an address naming an entry of a
  // folded section (a property's "source", How we read it) opens the fold and moves focus to the entry. Without script
  // the entry keeps its id and the fold opens with one press.
  const reveal = (id, scroll) => {
    let at = null;
    try { at = id ? document.getElementById(decodeURIComponent(id)) : null; } catch (_) { /* a malformed escape */ }
    const fold = at && at.closest('details');
    if (!fold) return;
    fold.open = true;
    if (scroll) at.scrollIntoView({ block: 'start' });
    if (at.tabIndex < 0 && !at.hasAttribute('tabindex')) at.setAttribute('tabindex', '-1');
    at.focus({ preventScroll: true });
  };
  const fromHash = () => reveal(location.hash.slice(1), true);
  fromHash();
  addEventListener('hashchange', fromHash);
  // a press opens the fold before the browser follows the link, so it lands on the entry (also when the address
  // already names it, and no hashchange follows); a press that opens a new tab or window leaves this page as it is
  document.addEventListener('click', (ev) => {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    const a = ev.target.closest && ev.target.closest('a[href^="#"]');
    if (a) reveal(a.getAttribute('href').slice(1), false);
  });

  // ------------------------------------------------------------ search: a combobox over search.json (written by build.py)
  // Matching is local and forgiving: the start of a name, a word inside it, then the other words; a
  // typo (one letter added, missing, wrong or two swapped) is tried only for a word no entry has, and
  // only from its first letter on. Order: not-benchmarked systems after every other match; within
  // each part, where the words matched, then the kind of entry, then how closely, then the name. It
  // never orders by how good a system is.
  const sbox = $('.search');
  if (sbox) {
    const input = $('#q', sbox);
    const list = $('#q-list', sbox);
    const opener = $('.sopen', sbox);
    const top = sbox.closest('.top');
    const CAP = 12;  // per part: other matches, then not-benchmarked ones; the rest is counted, not hidden
    let entries = null;
    let loading = null;
    let failed = false;
    let shown = [];
    let active = -1;
    // A press on a result or a search button keeps the field's focus: a mouse press is cancelled; a
    // touch press is not (WebKit then drops the tap's click), so the blur it causes is let pass once.
    let pressing = false;
    const hold = (ev) => { if (mouse(ev)) ev.preventDefault(); else pressing = true; };
    addEventListener('click', () => { pressing = false; }, true);
    addEventListener('pointercancel', () => { pressing = false; }, true);
    // lower case, no accents, a number apart from the word it is glued to ("llama4" is "llama 4")
    const norm = (s) => s.toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '')
      .replace(/([a-z])(\d)/g, '$1 $2').replace(/[^a-z0-9.]+/g, ' ').trim();
    const load = () => {
      loading = loading || fetch(list.dataset.index).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }).then((d) => {
        entries = d.entries.map((x) => ({ ...x, nw: norm(x.name).split(' '), tw: norm(x.terms).split(' '), n: norm(x.name) }));
      }).catch(() => { failed = true; });
      return loading;
    };
    // one letter added, missing or wrong, or two neighbours swapped
    const near = (a, b) => {
      if (a === b) return true;
      if (Math.abs(a.length - b.length) > 1) return false;
      let i = 0;
      while (i < a.length && a[i] === b[i]) i++;
      if (a.length === b.length) return a.slice(i + 1) === b.slice(i + 1) || (a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2));
      const [s, l] = a.length < b.length ? [a, b] : [b, a];
      return s.slice(i) === l.slice(i + 1);
    };
    // how one query word matches a list of words: 0 starts one, 1 sits inside one, 2 one typo away
    const wordScore = (q, ws, typo) => {
      let best = 9;
      for (const w of ws) {
        if (w.startsWith(q)) return 0;
        if (q.length >= 3 && w.includes(q)) best = Math.min(best, 1);
        else if (typo && q.length >= 4 && w[0] === q[0] && [q.length - 1, q.length, q.length + 1].some((L) => near(q, w.slice(0, L)))) best = Math.min(best, 2);
      }
      return best;
    };
    const rank = (x, qs, whole, typo) => {
      if (x.n.startsWith(whole)) return [0, 0];
      const inName = qs.map((q, k) => wordScore(q, x.nw, typo[k]));
      if (inName.every((s) => s < 9)) return [1, inName.reduce((a, b) => a + b, 0)];
      if (whole.length < 2) return null;  // one letter: names only
      const inAll = qs.map((q, k) => Math.min(wordScore(q, x.nw, typo[k]), wordScore(q, x.tw, typo[k])));
      if (inAll.every((s) => s < 9)) return [2, inAll.reduce((a, b) => a + b, 0)];
      return null;
    };
    const results = (q) => {
      const whole = norm(q);
      if (!whole) { const all = entries.filter((x) => x.kind === 'system'); return { shown: all, total: all.length }; }
      const qs = whole.split(' ');
      // a word some entry has is matched as typed; only a word no entry has gets typo matching
      const typo = qs.map((w) => !entries.some((x) => wordScore(w, x.nw, false) < 9 || wordScore(w, x.tw, false) < 9));
      const ms = entries.map((x) => ({ x, r: rank(x, qs, whole, typo) })).filter((m) => m.r)
        .sort((a, b) => a.r[0] - b.r[0] || a.x.tier - b.x.tier || a.r[1] - b.r[1] || a.x.name.localeCompare(b.x.name))
        .map((m) => m.x);
      const others = ms.filter((x) => x.kind !== 'unbenchmarked');
      const nb = ms.filter((x) => x.kind === 'unbenchmarked');
      return { shown: [...others.slice(0, CAP), ...nb.slice(0, CAP)], total: ms.length };
    };
    const note = (text) => {
      const li = document.createElement('li'); li.className = 'snone'; li.setAttribute('role', 'presentation'); li.textContent = text;
      return li;
    };
    const option = (x, i) => {
      const li = document.createElement('li');
      li.id = `q-o${i}`; li.className = `so k-${x.kind}`; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
      // name, then what kind of entry it is, then the line of context: the order a screen reader reads
      // (the grid shows the badge at the right)
      const pie = document.createElement('span'); pie.className = 'sp'; pie.innerHTML = x.pie;  // the build's own svg
      const b = document.createElement('b'); b.className = 'sn'; b.textContent = x.name;
      li.append(pie, b);
      if (x.badge) { const t = document.createElement('span'); t.className = 'sbadge'; t.textContent = ` ${x.badge} `; li.append(t); }
      if (x.meta) { const m = document.createElement('span'); m.className = 'sm'; m.textContent = x.meta; li.append(m); }
      li.addEventListener('pointerdown', hold);  // keep focus in the field
      li.addEventListener('click', () => go(x));
      return li;
    };
    const mark = (i) => {
      active = i;
      $$('.so', list).forEach((li, k) => { li.classList.toggle('on', k === i); li.setAttribute('aria-selected', String(k === i)); });
      if (i >= 0) { input.setAttribute('aria-activedescendant', `q-o${i}`); $(`#q-o${i}`)?.scrollIntoView({ block: 'nearest' }); } else input.removeAttribute('aria-activedescendant');
    };
    const open = (yes) => {
      list.hidden = !yes;
      input.setAttribute('aria-expanded', String(yes));
      if (!yes) mark(-1);
    };
    const render = () => {
      if (document.activeElement !== input) return;  // the index may arrive after the field was left
      if (failed) { list.replaceChildren(note('Search could not load')); shown = []; open(true); return; }
      if (!entries) return;
      const typed = norm(input.value);
      const r = results(input.value);
      shown = r.shown;
      list.replaceChildren(...shown.map(option));
      if (!shown.length) list.append(note('No match'));
      else if (r.total > shown.length) list.append(note(`${r.total - shown.length} more: type more letters`));
      open(true);
      mark(typed && shown.length ? 0 : -1);
      if (typed) say(!shown.length ? 'No match' : r.total > shown.length ? `${r.total} results, ${shown.length} shown` : `${shown.length} result${shown.length > 1 ? 's' : ''}`);
    };
    const go = (x) => {
      open(false);
      const here = location.pathname === x.url.split('#')[0];
      location.href = x.url;
      if (here) { input.blur(); setPhone(false); }
    };
    const phone = () => opener && getComputedStyle(opener).display !== 'none';
    // while the sheet is open, what it covers is out of reach (Tab, screen readers): only the search stays live
    const covered = () => [...document.body.children, ...top.children].filter((el) => el !== top && el !== sbox && !el.contains(sbox) && el.tagName !== 'SCRIPT');
    const setPhone = (on) => {
      covered().forEach((el) => { el.inert = on; });
      top.classList.toggle('s-on', on);
      if (opener) opener.setAttribute('aria-expanded', String(on));
      if (on) input.focus();
    };
    // phones: the open field is a sheet; closing it returns focus to the button that opened it
    const close = () => { open(false); setPhone(false); opener.focus(); };
    input.addEventListener('focus', () => { if (failed) { failed = false; loading = null; } load().then(render); });
    input.addEventListener('input', () => { load().then(render); });
    // on a phone, hiding the keyboard blurs the field: the sheet and its list stay until closed
    input.addEventListener('blur', () => { if (pressing) pressing = false; else if (!phone()) open(false); });
    input.addEventListener('keydown', (ev) => {
      const n = shown.length;
      if (ev.key === 'ArrowDown' && n) { ev.preventDefault(); if (list.hidden) render(); mark((active + 1) % n); } else if (ev.key === 'ArrowUp' && n) { ev.preventDefault(); if (list.hidden) render(); mark(active <= 0 ? n - 1 : active - 1); } else if (ev.key === 'Enter') {
        // the chosen option, or the first result of a typed search; never a pick nobody made
        const x = active >= 0 ? shown[active] : (norm(input.value) ? shown[0] : null);
        if (x) { ev.preventDefault(); go(x); }
      } else if (ev.key === 'Escape') {
        if (!list.hidden && input.value) { input.value = ''; render(); } else if (phone()) close(); else open(false);
      }
    });
    if (opener) {
      opener.addEventListener('pointerdown', hold);  // the field keeps focus while it toggles
      opener.addEventListener('click', () => setPhone(!top.classList.contains('s-on')));
      const shut = $('.sclose', sbox);
      if (shut) {
        shut.addEventListener('pointerdown', hold);
        shut.addEventListener('click', close);
      }
      // a tap on the sheet around the field and its list closes it, and reaches nothing under it
      top.addEventListener('pointerdown', (ev) => { if (top.classList.contains('s-on') && ev.target === top) hold(ev); });
      top.addEventListener('click', (ev) => { if (top.classList.contains('s-on') && ev.target === top) { ev.preventDefault(); close(); } });
      // the list ends above the on-screen keyboard
      const vv = window.visualViewport;
      if (vv) {
        const fit = () => document.documentElement.style.setProperty('--vvh', `${vv.height}px`);
        vv.addEventListener('resize', fit); fit();
      }
    }
    // "/" or Ctrl/Cmd + K, from anywhere but a field
    addEventListener('keydown', (ev) => {
      const typing = ev.target.closest && ev.target.closest('input, textarea, select, [contenteditable]');
      if ((ev.key === '/' && !typing && !ev.metaKey && !ev.ctrlKey) || (ev.key.toLowerCase() === 'k' && (ev.metaKey || ev.ctrlKey))) {
        ev.preventDefault();
        if (phone()) setPhone(true); else input.focus();
      }
    });
  }

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
  const words = () => { const b = btn(state.col); return b ? `${b.firstChild.textContent.trim()}, ${b.dataset[state.dir]}` : ''; };

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

  // the hash: #sort=proof_size-asc; no hash at all is the default order (Back to a page without one)
  const readHash = (animate) => {
    let h = location.hash.slice(1);
    try { h = decodeURIComponent(h); } catch (_) { /* a malformed escape: read the hash as it is */ }
    if (h === '') { setSort(DEFAULT, { animate, hash: false }); return; }
    if (!/^sort=/.test(h)) return;
    const want = h.slice(5);
    setSort(want, { animate, hash: false });
    if (`${state.col}-${state.dir}` !== want) writeHash(); // an unknown order in the link: name the one shown
  };
  readHash(false);
  addEventListener('hashchange', () => readHash(true));
  addEventListener('popstate', () => readHash(true));
})();
