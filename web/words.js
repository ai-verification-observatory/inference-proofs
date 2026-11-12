// MADE OF WORDS: behaviour only. No value, label or quote is typed here: everything printed
// comes from the page, which iproofs site build wrote.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const live = $('#live');
  const say = (t) => { if (live) { live.textContent = ''; requestAnimationFrame(() => { live.textContent = t; }); } };
  const mouse = (ev) => ev.pointerType === 'mouse';

  // ------------------------------------------------------------ search: a combobox over search.json (written by build.py)
  // Matching is local and forgiving: the start of a name, a word inside it, then the other words; a
  // typo (one letter added, missing, wrong or two swapped) is tried only for a word no entry has, and
  // only from its first letter on. Order: systems not run after every other match; within
  // each part, a match in the name before one in the other words only, then the kind of entry, the
  // page in view, how closely, then the name. It never orders by how good a system is. A result
  // found by its other words shows the phrase that holds them (a figure leads to its plate).
  const sbox = $('.search');
  if (sbox) {
    const input = $('#q', sbox);
    const list = $('#q-list', sbox);
    const opener = $('.sopen', sbox);
    const top = sbox.closest('.top');
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
        const said = (p) => ({ ...p, w: norm(p.name).split(' ') });
        entries = d.entries.map((x) => ({ ...x, nw: norm(x.name).split(' '), tw: norm(x.terms).split(' '), n: norm(x.name), cw: x.context ? norm(x.context).split(' ') : [],
          mw: norm(x.meta).split(' '), why: [...(x.figures || []).map(said), ...(x.found || []).map((name) => said({ name }))] }));
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
    // how one query word matches a list of words: 0 starts one, 1 sits inside one, 2 one typo away. A typo is
    // tried from 4 letters in a name ("sahs" finds SASH) and from 5 in the other words, where a short word
    // has too many neighbours ("time" is one letter from "tied")
    const wordScore = (q, ws, typo, least = 5) => {
      let best = 9;
      for (const w of ws) {
        if (w.startsWith(q)) return 0;
        if (q.length >= 3 && w.includes(q)) best = Math.min(best, 1);
        else if (typo && q.length >= least && w[0] === q[0] && [q.length - 1, q.length, q.length + 1].some((L) => near(q, w.slice(0, L)))) best = Math.min(best, 2);
      }
      return best;
    };
    const nameScore = (q, ws, typo) => wordScore(q, ws, typo, 4);
    const rank = (x, qs, whole, typo) => {
      if (x.n.startsWith(whole)) return [0, 0];
      const inName = qs.map((q, k) => nameScore(q, x.nw, typo[k]));
      if (inName.every((s) => s < 9)) return [1, inName.reduce((a, b) => a + b, 0)];
      if (whole.length < 2) return null;  // one letter: names only
      const inAll = qs.map((q, k) => Math.min(nameScore(q, x.nw, typo[k]), wordScore(q, x.tw, typo[k])));
      // a section's system and models count only beside a word of its own
      const inCtx = qs.map((q, k) => Math.min(inAll[k], wordScore(q, x.cw, typo[k])));
      if (inCtx.every((s) => s < 9) && inAll.some((s) => s < 9)) return [2, inCtx.reduce((a, b) => a + b, 0)];
      return null;
    };
    // why a result found by its other words was found: the words its name does not hold, in its line of context,
    // or else the figure or phrase holding the most of them (the first such); null when its line already says it
    const reason = (x, qs, typo) => {
      const rest = qs.filter((q, k) => nameScore(q, x.nw, typo[k]) === 9);
      const held = (ws) => rest.filter((q) => wordScore(q, ws, typo[qs.indexOf(q)]) < 9).length;
      if (!rest.length || held(x.mw) === rest.length) return null;
      let best = null; let most = 0;
      x.why.forEach((p) => { const n = held(p.w); if (n > most) { best = p; most = n; } });
      return best;
    };
    // every match: not run last; a match in the name before one in the other words only; then by group
    // (systems first; a system's sections under its name, the page in view first, the systems A to Z), within a
    // group where the words matched (a name that starts with the query first), then how closely, then the name
    const results = (q) => {
      const whole = norm(q);
      if (!whole) return entries.filter((x) => x.kind === 'system');
      const qs = whole.split(' ');
      // a word some entry has is matched as typed; only a word no entry has gets typo matching
      const typo = qs.map((w) => !entries.some((x) => wordScore(w, x.nw, false) < 9 || wordScore(w, x.tw, false) < 9 || wordScore(w, x.cw, false) < 9));
      const here = (m) => m.x.url.split('#')[0] === location.pathname;
      return entries.map((x) => ({ x, r: rank(x, qs, whole, typo) })).filter((m) => m.r)
        .sort((a, b) => (a.x.tier === 5) - (b.x.tier === 5) || (a.r[0] === 2) - (b.r[0] === 2)
          || a.x.tier - b.x.tier || here(b) - here(a) || a.x.group.localeCompare(b.x.group) || a.r[0] - b.r[0] || a.r[1] - b.r[1] || a.x.name.localeCompare(b.x.name))
        .map((m) => {
          const why = m.r[0] === 2 ? reason(m.x, qs, typo) : null;
          return why ? { ...m.x, meta: why.name, url: why.url || m.x.url } : m.x;
        });
    };
    const note = (text) => {
      const li = document.createElement('li'); li.className = 'snone'; li.setAttribute('role', 'presentation'); li.textContent = text;
      return li;
    };
    const option = (x, i) => {
      const li = document.createElement('li');
      li.id = `q-o${i}`; li.className = `so k-${x.kind}`; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
      // name, then the line of context: the order a screen reader reads; the group names the kind; a section has
      // no glyph and no room kept for one
      const b = document.createElement('b'); b.className = 'sn'; b.textContent = x.name;
      if (x.pie) {
        const pie = document.createElement('span'); pie.className = 'sp'; pie.innerHTML = x.pie;  // the build's own svg
        li.append(pie, b);
      } else { li.classList.add('np'); li.append(b); }
      if (x.meta) { const m = document.createElement('span'); m.className = 'sm'; m.textContent = x.meta; li.append(m); }
      li.addEventListener('pointerdown', hold);  // keep focus in the field
      li.addEventListener('pointermove', () => { if (active !== i) mark(i); });  // hover and the arrows mark one row
      li.addEventListener('click', () => go(x));
      return li;
    };
    // one quiet heading per group, its options in a group the heading names
    const grouped = (xs) => {
      const out = [];
      let ul = null;
      xs.forEach((x, i) => {
        if (!ul || ul.dataset.g !== x.group) {
          const li = document.createElement('li'); li.setAttribute('role', 'presentation'); li.className = 'sg';
          const h = document.createElement('span'); h.className = 'sgh'; h.id = `q-g${i}`; h.textContent = x.group;
          ul = document.createElement('ul'); ul.setAttribute('role', 'group'); ul.setAttribute('aria-labelledby', h.id); ul.dataset.g = x.group;
          li.append(h, ul); out.push(li);
        }
        ul.append(option(x, i));
      });
      return out;
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
      shown = results(input.value);
      list.replaceChildren(...grouped(shown));
      if (!shown.length) list.append(note('No match'));
      open(true);
      mark(typed && shown.length ? 0 : -1);
      if (typed) say(!shown.length ? 'No match' : `${shown.length} result${shown.length > 1 ? 's' : ''}`);
    };
    const go = (x) => {
      open(false);
      const [path, frag] = x.url.split('#');
      const here = location.pathname === path;
      input.value = '';  // the next search starts afresh
      location.href = x.url;
      if (here) {
        setPhone(false);
        // the page stays: focus moves to what the result names, not to the page's start
        const at = frag ? document.getElementById(decodeURIComponent(frag)) : null;
        if (at) { if (!at.hasAttribute('tabindex')) at.setAttribute('tabindex', '-1'); at.focus({ preventScroll: true }); } else input.blur();
      }
    };
    const phone = () => opener && getComputedStyle(opener).display !== 'none';
    const sheet = () => top.classList.contains('s-on');
    // while the sheet is open, what it covers is out of reach (Tab, screen readers): only the search stays live
    const covered = () => [...document.body.children, ...top.children].filter((el) => el !== top && el !== sbox && !el.contains(sbox) && el.tagName !== 'SCRIPT' && el !== live);
    // the field the sheet holds is on screen: focusing it never scrolls the page
    const setPhone = (on) => {
      covered().forEach((el) => { el.inert = on; });
      top.classList.toggle('s-on', on);
      if (opener) opener.setAttribute('aria-expanded', String(on));
      if (on) input.focus({ preventScroll: true });
    };
    // the open field is a sheet on phones, and on wider screens when "/" opens it mid-page; closing it returns focus
    // to the button that opened it, or to what had it before the shortcut, the page where it was
    let back = null;
    const close = () => {
      open(false); setPhone(false);
      const to = phone() ? opener : back;
      back = null;
      if (to && to !== document.body && to.isConnected) to.focus({ preventScroll: true }); else input.blur();
    };
    // the list opens on typing, the arrow down, a press on the field or the shortcut; a Tab onto the field
    // only loads the index
    let wanted = false;
    const want = () => { wanted = true; };
    input.addEventListener('pointerdown', want);
    input.addEventListener('focus', () => { if (failed) { failed = false; loading = null; } load().then(() => { if (wanted) render(); wanted = false; }); });
    input.addEventListener('input', () => { load().then(render); });
    // on a phone, hiding the keyboard blurs the field: the sheet and its list stay until closed; elsewhere leaving
    // the field closes its list, and the sheet it opened in
    input.addEventListener('blur', () => {
      if (pressing) pressing = false;
      else if (!phone()) { open(false); if (sheet()) { setPhone(false); back = null; } }
    });
    input.addEventListener('keydown', (ev) => {
      const n = shown.length;
      if (ev.key === 'ArrowDown' && list.hidden) { ev.preventDefault(); load().then(render); } else if (ev.key === 'ArrowDown' && n) { ev.preventDefault(); mark((active + 1) % n); } else if (ev.key === 'ArrowUp' && n) { ev.preventDefault(); if (list.hidden) render(); mark(active <= 0 ? n - 1 : active - 1); } else if (ev.key === 'Enter') {
        // the chosen option, or the first result of a typed search; never a pick nobody made
        const x = active >= 0 ? shown[active] : (norm(input.value) ? shown[0] : null);
        if (x) { ev.preventDefault(); go(x); }
      } else if (ev.key === 'Escape') {
        // an open list closes first; a closed one clears the field; on a phone the sheet closes last (the
        // search field's own Escape, which clears it at once, is not let through); a sheet opened mid-page by "/"
        // closes at once, the page where it was
        ev.preventDefault();
        if (sheet() && !phone()) close();
        else if (!list.hidden) { open(false); say(''); } else if (input.value) { input.value = ''; say(''); } else if (phone()) close();
      }
    });
    if (opener) {
      opener.addEventListener('pointerdown', hold);  // the field keeps focus while it toggles
      opener.addEventListener('click', () => { want(); setPhone(!top.classList.contains('s-on')); input.select(); });
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
    // "/" or Ctrl/Cmd + K, from anywhere but a field: the field in the header, or, with the header scrolled away, the
    // sheet, so the page never jumps to its top
    addEventListener('keydown', (ev) => {
      const typing = ev.target.closest && ev.target.closest('input, textarea, select, [contenteditable]');
      if ((ev.key === '/' && !typing && !ev.metaKey && !ev.ctrlKey) || (ev.key.toLowerCase() === 'k' && (ev.metaKey || ev.ctrlKey))) {
        ev.preventDefault();
        want();
        if (phone()) setPhone(true);
        else if (top.getBoundingClientRect().bottom < 0) { back = document.activeElement; setPhone(true); } else input.focus();
        input.select();
      }
    });
  }

})();
