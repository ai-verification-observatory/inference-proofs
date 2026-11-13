// MADE OF WORDS: behaviour only. No value, label or quote is typed here: everything printed
// comes from the page, which iproofs site build wrote.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const live = $('#live');
  const say = (t) => { if (live) { live.textContent = ''; requestAnimationFrame(() => { live.textContent = t; }); } };
  const mouse = (ev) => ev.pointerType === 'mouse';
  const typing = (t) => t && t.closest && t.closest('input, textarea, select, [contenteditable]');
  // a figure carrying labels (the probe, below), and the press under way: what it was made with and on what figure,
  // and whether that figure's labels were already shown. A tap's focus and its click are left to the probe's click
  const FIG = '.fig[title], .fig[data-t], .na[title], .na[data-t], .part[title], .part[data-t]';
  let press = null;

  // ------------------------------------------------------------ search: a combobox over search.json (written by build.py)
  // Matching is local and forgiving: the start of a name, a word inside it, then the other words; a
  // typo (one letter added, missing, wrong or two swapped) is tried only for a word no entry has, and
  // only from its first letter on. Order: systems not run after every other match; within
  // each part, a match in the name before one in the other words only, then the kind of entry, the
  // page in view, how closely, then the name (models, petals, checks and figures in their own
  // order, the ladder's for models). It never orders by how good a system is. Each group is listed
  // once, where its first result falls, and the words that matched are marked.
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
    list.addEventListener('pointerdown', hold);  // a press in the list (a result, its scroll bar) keeps focus in the field
    addEventListener('click', () => { pressing = false; }, true);
    addEventListener('pointercancel', () => { pressing = false; }, true);
    // lower case, no accents, a number apart from the word it is glued to ("llama4" is "llama 4")
    const norm = (s) => s.toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '')
      .replace(/([a-z])(\d)/g, '$1 $2').replace(/[^a-z0-9.]+/g, ' ').trim();
    const load = () => {
      loading = loading || fetch(list.dataset.index).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }).then((d) => {
        entries = d.entries.map((x, i) => ({ ...x, i, nw: norm(x.name).split(' '), tw: norm(x.terms).split(' '), n: norm(x.name) }));
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
      if (inAll.every((s) => s < 9)) return [2, inAll.reduce((a, b) => a + b, 0)];
      return null;
    };
    // kinds listed in their own order (the build writes them so: the models largest first), not A to Z
    const ordered = new Set(['model', 'petal', 'check', 'figure', 'learn']);
    // every match: not run last; a match in the name before one in the other words only; then by group
    // (systems first, the page in view first), within a group where the words matched (a name that starts
    // with the query first), then how closely, then its own order or the name; then each group once
    const results = (q) => {
      const whole = norm(q);
      if (!whole) return entries.filter((x) => x.kind === 'system');
      const qs = whole.split(' ');
      // a word some entry has is matched as typed; only a word no entry has gets typo matching
      const typo = qs.map((w) => !entries.some((x) => wordScore(w, x.nw, false) < 9 || wordScore(w, x.tw, false) < 9));
      const here = (m) => m.x.url.split('#')[0] === location.pathname;
      const sorted = entries.map((x) => ({ x, r: rank(x, qs, whole, typo) })).filter((m) => m.r)
        .sort((a, b) => (a.x.tier === 5) - (b.x.tier === 5) || (a.r[0] === 2) - (b.r[0] === 2)
          || a.x.tier - b.x.tier || here(b) - here(a) || a.x.group.localeCompare(b.x.group) || a.r[0] - b.r[0] || a.r[1] - b.r[1]
          || (ordered.has(a.x.kind) && a.x.kind === b.x.kind ? a.x.i - b.x.i : a.x.name.localeCompare(b.x.name)))
        .map((m) => m.x);
      const groups = [...new Set(sorted.map((x) => x.group))];
      return groups.flatMap((g) => sorted.filter((x) => x.group === g));
    };
    // a name with the words that matched marked: the start of a word, as long as the query word
    const marked = (text) => {
      const qs = norm(input.value).split(' ').filter(Boolean);
      const out = [];
      text.split(/(\s+)/).forEach((w) => {
        const k = norm(w);
        const q = k && qs.find((x) => k.startsWith(x));
        const at = w.search(/[\p{L}\p{N}]/u);
        if (q && at >= 0 && w.length - at >= q.length) {
          const m = document.createElement('mark'); m.textContent = w.slice(at, at + q.length);
          out.push(w.slice(0, at), m, w.slice(at + q.length));
        } else out.push(w);
      });
      return out;
    };
    const note = (text) => {
      const li = document.createElement('li'); li.className = 'snone'; li.setAttribute('role', 'presentation'); li.textContent = text;
      return li;
    };
    const option = (x, i) => {
      const li = document.createElement('li');
      li.id = `q-o${i}`; li.className = 'so'; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
      // name, then the line of context: the order a screen reader reads; the group names the kind; a section has
      // no glyph and no room kept for one
      const b = document.createElement('b'); b.className = 'sn'; b.append(...marked(x.name));
      if (x.pie) {
        const pie = document.createElement('span'); pie.className = 'sp'; pie.innerHTML = x.pie;  // the build's own svg
        li.append(pie, b);
      } else { li.classList.add('np'); li.append(b); }
      if (x.meta) { const m = document.createElement('span'); m.className = 'sm'; m.textContent = x.meta; li.append(m); }
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
          // the heading names its group (aria-labelledby reads a hidden element), so it is not read again as loose text
          const h = document.createElement('span'); h.className = 'sgh'; h.id = `q-g${i}`; h.textContent = x.group; h.setAttribute('aria-hidden', 'true');
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
      if (i < 0) { input.removeAttribute('aria-activedescendant'); return; }
      input.setAttribute('aria-activedescendant', `q-o${i}`);
      // the marked option is brought into the list's view by scrolling the list only: the list sits in the sticky
      // bar, and scrollIntoView would scroll the page under it too
      const o = $(`#q-o${i}`);
      if (o) {
        const lb = list.getBoundingClientRect(); const ob = o.getBoundingClientRect();
        if (ob.top < lb.top) list.scrollTop += ob.top - lb.top; else if (ob.bottom > lb.bottom) list.scrollTop += ob.bottom - lb.bottom;
      }
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
      if (here) input.blur();  // the page's scroll padding is back before the jump (words.css drops it while the field has focus)
      if (here && frag) ahead(document.getElementById(decodeURIComponent(frag)));
      location.href = x.url;
      if (here) {
        setPhone(false);
        // the page stays: focus moves to what the result names, not to the page's start
        const at = frag ? document.getElementById(decodeURIComponent(frag)) : null;
        if (at) { if (!at.hasAttribute('tabindex')) at.setAttribute('tabindex', '-1'); at.focus({ preventScroll: true }); }
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
        vv.addEventListener('resize', fit); requestAnimationFrame(fit);
      }
    }
    // Ctrl/Cmd + K, or "/" from anywhere but a field: the field in the header, or, with the header scrolled away, the
    // sheet, so the page never jumps to its top
    addEventListener('keydown', (ev) => {
      const slash = ev.key === '/' && !typing(ev.target);
      if ((slash && !ev.metaKey && !ev.ctrlKey && !ev.altKey) || (ev.key.toLowerCase() === 'k' && (ev.metaKey || ev.ctrlKey))) {
        ev.preventDefault();
        want();
        document.body.classList.remove('tophide');
        if (phone()) setPhone(true);
        else if (top.getBoundingClientRect().bottom < 0) { back = document.activeElement; setPhone(true); } else input.focus({ preventScroll: true });
        input.select();
      }
    });
  }

  const smooth = () => document.documentElement.classList.contains('anim');

  // ------------------------------------------------------------ the ladder's rows: the whole row leads to its page, but
  // a tap on one of its figures shows that figure's labels
  const rows = $$('.lad .row, .scl .row');
  rows.forEach((tr) => {
    const a = $('.sname', tr);
    if (!a) return;
    tr.addEventListener('click', (ev) => {
      if (ev.defaultPrevented || ev.button !== 0 || ev.target.closest('a, button')) return;
      if (press && !press.mouse && ev.target.closest(FIG)) return;
      if (String(getSelection())) return;  // a selection made in the row is not a press
      if (ev.metaKey || ev.ctrlKey) { window.open(a.href, '_blank', 'noopener'); return; }
      // a mouse click on a figure's words waits one double-click's time: a second press selects them instead
      if (press && press.mouse && ev.target.closest(`${FIG}, .sub`)) {
        const t = setTimeout(() => { if (!String(getSelection())) a.click(); }, 250);
        tr.addEventListener('pointerdown', () => clearTimeout(t), { once: true });
        return;
      }
      a.click();
    });
  });
  // the band's block leads to its rung the same way: a tap on its figure shows its labels
  $$('a.bx').forEach((a) => a.addEventListener('click', (ev) => { if (press && !press.mouse && ev.target.closest(FIG)) ev.preventDefault(); }));
  // back on the ladder from a system's page, its row stays marked as the one in hand until another is taken
  let cur = null;
  try {
    const from = document.referrer && new URL(document.referrer);
    if (from && from.origin === location.origin) cur = document.getElementById(`row-${from.pathname.slice(1)}`);
  } catch (_) { cur = null; }
  if (cur) cur.classList.add('cur');
  const dropCur = () => { if (cur) { cur.classList.remove('cur'); cur = null; } };
  rows.forEach((tr) => { tr.addEventListener('pointerenter', () => { if (tr !== cur) dropCur(); }); tr.addEventListener('focusin', () => { if (tr !== cur) dropCur(); }); });

  // ------------------------------------------------------------ the keyboard: j and k step through the rows of the ladder,
  // the arrows from a row that has focus
  const pnav = $('.pnav');
  const links = pnav ? $$('.ps a', pnav) : [];
  const secs = links.map((a) => document.getElementById(decodeURIComponent(a.hash.slice(1))));
  // The keys act once focus is in the ladder, never from the page as a whole; at the first or last row an arrow is
  // left to the browser, which scrolls
  addEventListener('keydown', (ev) => {
    if (!rows.length || ev.metaKey || ev.ctrlKey || ev.altKey || $('.top.s-on') || !(ev.target.closest && ev.target.closest('.ladder'))) return;
    const k = ev.key;
    const inRow = ev.target.closest('.lad .row');
    const step = k === 'j' || (inRow && k === 'ArrowDown') ? 1 : k === 'k' || (inRow && k === 'ArrowUp') ? -1 : 0;
    if (!step) return;
    const i = rows.indexOf(inRow || cur);
    const n = i < 0 ? (step > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + step));
    if (inRow && n === i) return;
    ev.preventDefault();
    $('.sname', rows[n]).focus({ preventScroll: true });
    rows[n].scrollIntoView({ block: 'nearest' });
  });

  // ------------------------------------------------------------ what stays in view: the section in view marked in the strip,
  // the page's title in the strip once the band is gone, and on a phone the top bar stepping away on the way down.
  // The page's one scroll handler, run once a frame at most; it also puts away a pointer's figure labels (the probe,
  // below) and glossary peek, and keeps those focus showed beside their figure or term
  const body = document.body;
  const bar = $('.top');
  const mast = $('.mast');
  // a phone held either way (words.css keys its phone rules on the same two)
  const narrow = matchMedia('(max-width: 760px), (max-height: 500px) and (pointer: coarse)');
  let inView = -2;
  let lastY = scrollY;
  // where the browser cannot tell a sticky head is stuck (no scroll-state query), the ladder's heads are marked here:
  // stuck while the table has moved on under its head and has rows left under it
  const heads = window.CSS && CSS.supports('container-type', 'scroll-state') ? [] : $$('.lad thead th:first-child');
  const spy = () => {
    // (below 1180 px the whole head sticks, and its first cell is laid over it once stuck: the head is what is measured)
    const stuck = heads.map((h) => { const hd = h.closest('thead'); const r = (getComputedStyle(hd).position === 'sticky' ? hd : h).getBoundingClientRect(); const t = h.closest('table').getBoundingClientRect(); return t.top < r.top - 1 && t.bottom > r.top + 40; });
    heads.forEach((h, i) => h.classList.toggle('stuck', stuck[i]));
    const y = scrollY;
    // the bar stays while its search field has focus (a phone held sideways types in the bar itself)
    if (narrow.matches && bar && !bar.classList.contains('s-on') && !(document.activeElement && document.activeElement.id === 'q')) {
      if (y > lastY + 6 && y > bar.offsetHeight + 40) body.classList.add('tophide');
      else if (y < lastY - 6 || y < bar.offsetHeight) body.classList.remove('tophide');
    } else body.classList.remove('tophide');
    lastY = y;
    if (!pnav) return;
    const edge = pnav.getBoundingClientRect().bottom;
    pnav.classList.toggle('stuck', !!mast && mast.getBoundingClientRect().bottom < pnav.getBoundingClientRect().top - 1);
    // the scale page's strip marks the figure drawn, not the section in view (below)
    if (panels.length) { petalSpy(); return; }
    let k = -1;
    // a section is in view once its top has passed a third of the window under the strip (48 px at least); of two
    // that have, the earlier while its own top is still under the strip (a short section is not passed over)
    const line = edge + Math.max(48, (innerHeight - edge) / 3);
    const tops = secs.map((s) => (s ? s.getBoundingClientRect().top - edge : Infinity));
    tops.forEach((t, i) => { if (t <= line - edge) k = i; });
    while (k > 0 && tops[k - 1] >= -8) k -= 1;
    // a section whose top sits right under the strip (where its link or an anchor lands it) is the one in view
    const here = tops.findIndex((t) => t >= -8 && t <= 40);
    if (here >= 0) k = here;
    // at the page's end, the last section, unless the one the address names (its link, an anchor) is in view
    if (innerHeight + y >= document.documentElement.scrollHeight - 4 && k >= 0) {
      const t = secs.findIndex((s) => s && s.matches(':target'));
      k = t >= 0 && tops[t] >= -8 && tops[t] < innerHeight - edge ? t : secs.length - 1;
    }
    if (k !== inView) {
      inView = k;
      links.forEach((a, i) => { a.classList.toggle('on', i === k); if (i === k) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current'); snug(a); });
      if (links[k]) whole(links[k], smooth() ? 'smooth' : 'auto');
    }
    petalSpy();
  };
  // a strip's label brought into the strip a third of the way along, but always whole: its end in view, and its start
  // before that. The marked label is, and so is a label that takes keyboard focus (not a press: a label that moves
  // between a press and its release loses the click)
  const strip = pnav && $('.ps', pnav);
  const whole = (a, behavior) => {
    if (!strip || strip.scrollWidth <= strip.clientWidth) return;
    const s = strip.getBoundingClientRect();
    // the page's title, once it has slid into the strip, holds the strip's start: a label is whole after it
    const t = $('.ps-t', strip);
    const lead = t ? Math.max(0, t.getBoundingClientRect().right - s.left) : 0;
    const x = a.getBoundingClientRect().left - s.left + strip.scrollLeft - lead;
    const aw = a.offsetWidth; const room = strip.clientWidth - lead;
    strip.scrollTo({ left: aw >= room ? x : Math.min(x, Math.max(x + aw - room, x - room / 3)), behavior });
  };
  // a label in view that takes two lines (a phone's strip, words.css) is as wide as its longer line, so its bar ends
  // with its words
  const snug = (a) => {
    a.style.removeProperty('width');
    if (!a.classList.contains('on')) return;
    const r = document.createRange(); r.selectNodeContents(a);
    const rs = [...r.getClientRects()];
    if (rs.length < 2) return;
    const cs = getComputedStyle(a);
    const w = Math.max(...rs.map((x) => x.right)) - Math.min(...rs.map((x) => x.left));
    a.style.setProperty('width', `${Math.ceil(w + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight))}px`);
  };
  addEventListener('resize', () => links.forEach(snug), { passive: true });

  // ------------------------------------------------------------ the scale page: its strip picks the one figure drawn, and
  // the address keeps it (no history entry, no scroll); an address naming none draws the first. With no script every
  // figure is drawn
  const panels = body.classList.contains('scalepage') ? secs.filter(Boolean) : [];
  const pick = (id, keep) => {
    const k = Math.max(0, panels.findIndex((s) => s.id === id));
    panels.forEach((s, i) => { s.hidden = i !== k; });
    links.forEach((a, i) => { a.classList.toggle('on', i === k); if (i === k) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); snug(a); });
    if (links[k]) whole(links[k], 'auto');
    if (!keep) return;
    history.replaceState(null, '', `#${panels[k].id}`);
    // a figure picked further down the page starts at its top, under the strip
    if (panels[k].getBoundingClientRect().top < pnav.getBoundingClientRect().bottom) panels[k].scrollIntoView({ block: 'start' });
  };
  if (panels.length) {
    pick(decodeURIComponent(location.hash.slice(1)));
    links.forEach((a) => a.addEventListener('click', (ev) => {
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      pick(decodeURIComponent(a.hash.slice(1)), true);
    }));
    addEventListener('hashchange', () => pick(decodeURIComponent(location.hash.slice(1))));
  }
  if (strip) strip.addEventListener('focusin', (ev) => { const a = ev.target.closest('a'); if (a && a.matches(':focus-visible')) whole(a, 'auto'); });
  // on a phone, a jump within the page first sets the bar as the scroll will leave it (away on the way down, back on
  // the way up), so the scroll padding the browser reads is the one in force when the section lands (words.css)
  function ahead(t) {
    if (t && narrow.matches) body.classList.toggle('tophide', t.getBoundingClientRect().top > (pnav ? pnav.offsetHeight : 0) + 24);
  }
  document.addEventListener('click', (ev) => {
    const a = !ev.defaultPrevented && ev.target.closest && ev.target.closest('a[href^="#"]');
    if (a) ahead(document.getElementById(decodeURIComponent((a.getAttribute('href') || '').slice(1))));
  });
  // and a page opened at an anchor lands it the same way (not on a return, which keeps the reader's place)
  const nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
  if (location.hash && narrow.matches && bar && (!nav || nav.type === 'navigate')) {
    const t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (t) {
      body.classList.add('tophide');
      t.scrollIntoView({ block: 'start' });
      if (scrollY < bar.offsetHeight + 40) { body.classList.remove('tophide'); t.scrollIntoView({ block: 'start' }); }
      lastY = scrollY;
    }
  }
  let ticking = false;
  let moved = false;
  // what a scroll puts away (the figure probe, a glossary term's peek), run once a frame from the one handler
  const away = [];
  const onScroll = (ev) => {
    if (ev && ev.type === 'scroll') moved = true;
    if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; if (moved) { moved = false; away.forEach((f) => f()); } spy(); }); }
  };

  // ------------------------------------------------------------ a petal and its line light each other: the large glyph's
  // petals and the petals' table (a system page), the key's petals and the petals' sections (the checks page, where the
  // section read lights its petal). On a system page a petal also lights the checks its red names (data-to on a
  // check's name, p1 to p5), and a check lights those petals: the rest dim, never hide
  const gb = $('.gbig');
  const petals = gb ? $$('.sl', gb) : [];
  const names = gb ? $$('.t', gb) : [];
  const lines = $$('.ckt tr.pt').length ? $$('.ckt tr.pt') : $$('.cwrap .chk');
  const checks = $$('.ckt tr.ck');
  const decides = checks.map((tr) => { const a = $('th a[data-to]', tr); return a ? a.dataset.to.split(' ').map((k) => +k.slice(1) - 1) : []; });
  let hand = null;  // { p: petals in hand, c: checks in hand }
  let read = -1;
  const light = () => {
    const ps = hand ? hand.p : (read >= 0 ? [read] : []);
    const cs = hand ? hand.c : [];
    if (gb) gb.classList.toggle('lit-on', ps.length > 0);
    petals.forEach((p, k) => p.classList.toggle('lit', ps.includes(k)));
    names.forEach((p, k) => p.classList.toggle('lit', ps.includes(k)));
    lines.forEach((l, k) => l.classList.toggle('lit', ps.includes(k)));
    checks.forEach((l, k) => l.classList.toggle('lit', cs.includes(k)));
    $$('.ckt').forEach((t) => t.classList.toggle('dim', !!hand && checks.length > 0));
  };
  // the petal read is the last whose heading has passed a line a sixth of the way down the view under the
  // strip, so a petal arrived at by its link is the one read
  const petalSpy = () => {
    if (!gb || !lines.length || lines[0].tagName === 'TR') return;
    const wrap = gb.closest('.cwrap').getBoundingClientRect();
    const edge = pnav ? pnav.getBoundingClientRect().bottom : 0;
    const mid = edge + (innerHeight - edge) * 0.15;
    let k = -1;
    if (wrap.top < mid && wrap.bottom > mid) lines.forEach((l, i) => { if (l.getBoundingClientRect().top < mid) k = i; });
    if (k !== read) { read = k; light(); }
  };
  if (gb && lines.length === petals.length) {
    const petalIn = (i) => () => { hand = { p: [i], c: decides.flatMap((d, k) => (d.includes(i) ? [k] : [])) }; light(); };
    const checkIn = (k) => () => { hand = { p: decides[k], c: [k] }; light(); };
    const drop = () => { hand = null; light(); };
    [petals, names].forEach((set) => set.forEach((p, i) => {
      // a system page's arm heads its own row: the row's handlers light it
      if (lines[i].contains(p)) return;
      p.addEventListener('pointerenter', petalIn(i));
      p.addEventListener('pointerleave', drop);
      // a petal that is a link (the checks page's key) goes there itself
      if (!p.closest('a')) p.addEventListener('click', () => lines[i].scrollIntoView({ block: 'nearest', behavior: smooth() ? 'smooth' : 'auto' }));
    }));
    gb.classList.add('linked');
    const hold = (els, on) => els.forEach((l, i) => {
      l.addEventListener('pointerenter', on(i));
      l.addEventListener('pointerleave', drop);
      l.addEventListener('focusin', on(i));
      l.addEventListener('focusout', drop);
    });
    hold(lines, petalIn);
    hold(checks, checkIn);
  }
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onScroll, { passive: true });
  // a link to a section already in view scrolls nothing, but marks it
  addEventListener('hashchange', onScroll);
  // after the first frame, so a view transition into this page is not held up by layout read here
  requestAnimationFrame(() => requestAnimationFrame(spy));

  // ------------------------------------------------------------ the probe: pointing at a figure (or anything carrying
  // labels in its title) shows its labels where it is, one per line; a petal of a row's glyph shows its name and state
  // The labels are the figure's description for a screen reader while they are shown.
  const probe = document.createElement('div');
  probe.className = 'probe';
  probe.id = 'probe';
  probe.setAttribute('role', 'tooltip');
  probe.hidden = true;
  requestAnimationFrame(() => body.append(probe));
  let at = null;
  let size = [0, 0];  // the probe's width and height, measured once when it is filled
  let byKey = false;  // shown by keyboard focus: the labels follow their figure on a scroll; a pointer's or a tap's are put away
  // the bottom of what is pinned at the top of the window: the top bar, and the strip once it is stuck under it
  const pinned = () => {
    const t = bar ? Math.max(0, bar.getBoundingClientRect().bottom) : 0;
    const s = pnav && pnav.getBoundingClientRect();
    return s && s.top <= t + 1 ? Math.max(t, s.bottom) : t;
  };
  // the page's column: a box over a figure keeps to the gutters, as everything else does (the window's edge when the
  // column is narrower than the box)
  const gutters = (el, w) => {
    const c = (el.closest('.wrap, .mast-in') || $('main .wrap') || body).getBoundingClientRect();
    const lo = Math.max(12, c.left); const hi = Math.min(innerWidth - 12, c.right);
    return hi - lo >= w ? [lo, hi] : [12, innerWidth - 12];
  };
  // the top of what names a figure: its cell's label (a fact's term, a cell, a block), so labels put over the figure
  // cover neither the figure nor its name
  const named = (el, r) => {
    const cell = el.closest('.meta > div, td, .bx-f, .sb, .parts > div, dd');
    if (!cell) return r.top;
    const t = (cell.matches('dd') && cell.previousElementSibling ? cell.previousElementSibling : cell).getBoundingClientRect().top;
    return t <= r.top && r.top - t < 120 ? t : r.top;
  };
  let col = [12, 12];  // the column's sides, read once when the probe is filled
  let near = [];  // the page's other labelled things, read once when the probe is filled
  // under the figure and the line under it, so the probe hides neither; over the figure and its name when the
  // window ends first and there is room under what is pinned. Where that would cover another figure, the first of
  // these places that covers none: under, over its name, over it, beside it on the right, then on the left (so a
  // pointer can move onto the labels without reaching another figure). A petal's labels go by its whole glyph, so
  // they cover none of its petals. With room on neither side (a short window, a large zoom) it takes the larger side
  // and scrolls inside, and focus from the keyboard first brings the figure up under what is pinned (`bring`, on
  // focus only: a scroll is never undone). A figure scrolled out of the window takes its labels with it
  const place = (el, bring) => {
    const box = el.matches('.sl') ? el.closest('svg') : el;
    const next = box.nextElementSibling;
    let r = box.getBoundingClientRect();
    const top = pinned();
    const [w, h] = size;
    if (bring && innerHeight - top < h + r.height + 24 && Math.abs(r.top - top - 8) > 2) { scrollBy(0, r.top - top - 8); r = box.getBoundingClientRect(); }
    const sub = next && next.classList.contains('sub') ? next.getBoundingClientRect() : null;
    const low = sub ? sub.bottom : r.bottom;
    const head = named(box, r);
    const below = innerHeight - low - 16; const over = head - top - 16; const above = r.top - top - 16;
    const x = Math.max(col[0], Math.min(r.left, col[1] - w));
    let y = low + 8;
    if (h > below && h <= over) y = head - h - 8;
    else if (h > below && h <= above) y = r.top - h - 8;
    else if (h > below && above > below) y = top + 8;
    const others = near.map((e) => e.getBoundingClientRect()).filter((o) => o.width && o.bottom > top && o.top < innerHeight);
    if (sub) others.push(sub);
    const side = Math.max(top + 8, Math.min(r.top - 11, innerHeight - 8 - h));
    const free = [[x, low + 8], [x, head - h - 8], [x, r.top - h - 8], [r.right + 12, side], [r.left - 12 - w, side]].find(([cx, cy]) =>
      cx >= col[0] && cx + w <= col[1] && cy >= top + 8 && cy + h <= innerHeight - 8
      && !others.some((o) => cx < o.right && cx + w > o.left && cy < o.bottom && cy + h > o.top));
    let px = x;
    if (free) [px, y] = free;
    probe.style.setProperty('max-height', !free && h > Math.max(below, above) ? `${Math.max(0, below, above)}px` : 'none');
    probe.style.setProperty('transform', `translate(${Math.round(px)}px, ${Math.round(y)}px)`);
    probe.hidden = r.bottom <= top || r.top >= innerHeight;
  };
  const hide = () => {
    if (!at) return;
    if (at.dataset.t !== undefined) { at.setAttribute('title', at.dataset.t); delete at.dataset.t; }
    if (at.getAttribute('aria-describedby') === 'probe') at.removeAttribute('aria-describedby');
    at.classList.remove('probed');
    at = null;
    byKey = false;
    probe.hidden = true;
  };
  const show = (el, fill) => {
    stay();
    if (at === el) return;
    hide();
    at = el;
    probe.replaceChildren();
    fill();
    probe.style.setProperty('max-height', 'none');
    probe.hidden = false;
    probe.scrollTop = 0;
    size = [probe.offsetWidth, probe.offsetHeight];
    col = gutters(el, size[0]);
    near = $$('[title], [data-t]', main).filter((e) => e !== el && !e.contains(el) && !el.contains(e));
    place(el);
  };
  const labelled = (el) => show(el, () => {
    const t = el.getAttribute('title');
    el.dataset.t = t;  // the reader's own tooltip would cover the probe
    el.removeAttribute('title');
    if (!el.hasAttribute('aria-describedby')) el.setAttribute('aria-describedby', 'probe');
    if (!el.matches('a')) el.classList.add('probed');
    const dl = document.createElement('dl');
    t.split('; ').forEach((part) => {
      const m = /^([a-z][a-z ]*?)(:| =) (.+)$/i.exec(part);
      const d = document.createElement('div');
      const dt = document.createElement('dt'); const dd = document.createElement('dd');
      dt.textContent = m ? m[1] : '';
      // a record's path breaks after a slash or a hash, never inside a word
      if (m && m[1].toLowerCase() === 'record') m[3].match(/[^/#]+[/#]?|[/#]/g).forEach((p, j) => { if (j) dd.append(document.createElement('wbr')); dd.append(p); });
      else dd.textContent = m ? m[3] : part;
      d.append(dt, dd); dl.append(d);
    });
    probe.append(dl);
  });
  const petal = (p) => {
    const g = p.closest('.glyph');
    const row = p.closest('.row');
    const words = row && $$('.pw > span', row);
    const svg = p.closest('svg');
    const i = $$('.sl', svg).indexOf(p);
    if (!words || !words[i]) return;
    show(p, () => {
      const d = document.createElement('div'); d.className = 'prk';
      const state = ['green', 'amber', 'red', 'hollow'].find((s) => p.classList.contains(s));
      // the arm's form (cut: amber in lesser part; open: a silent red) is drawn on the chip too
      const form = ['cut', 'open'].find((f) => p.classList.contains(f));
      const chip = document.createElement('span'); chip.className = form ? `schip ${state} ${form}` : `schip ${state}`;
      // the words: the step, then for a red or hollow petal its cause after the name
      const [step, ...cause] = words[i].textContent.slice(words[i].firstChild.textContent.length).trim().split(', ');
      chip.textContent = step;
      d.append(chip, words[i].firstChild.textContent);
      if (cause.length) { const c = document.createElement('span'); c.className = 'prc'; c.textContent = cause.join(', '); d.append(c); }
      probe.append(d);
      g.classList.add('lit-on'); p.classList.add('lit');
    });
  };
  const clearPetal = () => { $$('.glyph.lit-on').forEach((g) => { g.classList.remove('lit-on'); $$('.lit', g).forEach((p) => p.classList.remove('lit')); }); };
  // a mouse leaving a figure puts its labels away a moment later, so the pointer can move onto them (to read or
  // select them) without losing them
  let leaving = 0;
  function stay() { clearTimeout(leaving); }
  const later = () => { stay(); leaving = setTimeout(() => { clearPetal(); hide(); }, 250); };
  probe.addEventListener('pointerenter', stay);
  probe.addEventListener('pointerleave', (ev) => { if (mouse(ev)) later(); });
  const main = $('main');
  if (main) {
    // labels that could find no free place give way to a figure or petal under them when the pointer moves there:
    // the pointer on the labels over empty ground keeps them
    probe.addEventListener('pointermove', (ev) => {
      if (!mouse(ev)) return;
      const els = document.elementsFromPoint(ev.clientX, ev.clientY).filter((e) => !probe.contains(e));
      const pt = els.map((e) => e.closest('.glyph .sl')).find((e) => e && main.contains(e) && e !== at);
      if (pt) { stay(); clearPetal(); petal(pt); return; }
      const f = els.map((e) => e.closest('[title], [data-t]')).find((e) => e && main.contains(e) && e !== at);
      if (f) { stay(); clearPetal(); labelled(f); }
    });
    main.addEventListener('pointerover', (ev) => {
      if (ev.pointerType !== 'mouse') return;
      const p = ev.target.closest('.glyph .sl');
      if (p) { stay(); clearPetal(); petal(p); return; }
      const el = ev.target.closest('[title], [data-t]');
      if (el && main.contains(el)) { stay(); if (el !== at) labelled(el); } else later();
    });
    main.addEventListener('pointerleave', (ev) => { if (mouse(ev)) later(); });
    // A tap on a figure shows its labels, a second tap or a tap elsewhere puts them away. A mouse has pointed at the
    // figure before its click, so the click keeps the labels. The focus a press gives a figure is left to its click;
    // focus from the keyboard shows the labels
    addEventListener('pointerdown', (ev) => {
      const el = ev.target.closest ? ev.target.closest(FIG) : null;
      press = { mouse: mouse(ev), el, open: !!el && el === at };
    }, true);
    addEventListener('pointercancel', () => { press = null; }, true);
    addEventListener('keydown', () => { press = null; }, true);
    addEventListener('click', (ev) => {
      const p = press;
      press = null;
      if (probe.contains(ev.target)) return;  // a press inside the labels (selecting them) keeps them
      const el = ev.target.closest ? ev.target.closest(FIG) : null;
      // a figure inside a link shows its labels only when the link let the tap pass (the band's block)
      if (el && main.contains(el) && (!el.closest('a') || ev.defaultPrevented)) {
        if (p && p.mouse) { if (el !== at) labelled(el); } else if (p && p.open && p.el === el) hide(); else labelled(el);
      } else if (!(ev.target.closest && ev.target.closest('.glyph'))) { clearPetal(); hide(); }
    });
    main.addEventListener('focusin', (ev) => {
      if (press) return;
      const el = ev.target.closest('a[title], .fig[title], .na[title], .part[title]');
      if (el) { labelled(el); byKey = true; place(el, true); }
    });
    main.addEventListener('focusout', (ev) => { if (at && ev.target.contains(at)) hide(); });
    away.push(() => { if (!at) return; if (byKey && at === document.activeElement) place(at); else { clearPetal(); hide(); } });
    // a figure's labels reach the keyboard too: outside the ladder's rows (each row leads to the page that
    // holds the same figures) and outside links, a figure takes focus and shows them
    $$('.fig[title], .na[title], .part[title]', main).forEach((el) => { if (!el.closest('a, .lad, .scl')) el.tabIndex = 0; });
    // Escape puts the labels away. Labels shown by the keyboard and cut by a short window scroll with the arrows while
    // their figure has focus; at either end the arrow is left to the browser, which scrolls the page
    addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') { clearPetal(); hide(); return; }
      if (!at || !byKey || at !== document.activeElement || probe.scrollHeight <= probe.clientHeight + 1) return;
      const d = ev.key === 'ArrowDown' ? 1 : ev.key === 'ArrowUp' ? -1 : 0;
      if (!d) return;
      const before = probe.scrollTop;
      probe.scrollBy(0, d * 24);
      if (probe.scrollTop !== before) ev.preventDefault();
    });
  }

  // ------------------------------------------------------------ one page into the next: leaving the ladder for a system's
  // page, that row's name takes the name the page gives its title, so it morphs into it (the page has no glyph of its
  // own to morph into: its arms head the petals' table). A system's page morphs back into the ladder only: leaving for
  // any other page, its name gives up its name
  addEventListener('pageswap', (ev) => {
    hide();
    if (!ev.viewTransition) return;
    // where the browser does not say where it goes, a system's page gives up its names (no morph is lost: the
    // ladder cannot name its row there either)
    const entry = ev.activation && ev.activation.entry;
    const to = entry ? new URL(entry.url).pathname : null;
    if (body.classList.contains('syspage') && to !== '/') {
      $$('.syspage .sysname').forEach((el) => el.style.setProperty('view-transition-name', 'none'));
      return;
    }
    if (!to) return;
    const row = document.getElementById(`row-${to.slice(1)}`);
    if (!row) return;
    const el = $('.sname', row); if (el) el.style.setProperty('view-transition-name', 'sysname');
  });
  addEventListener('pageshow', (ev) => {
    if (ev.persisted) $$('.row .sname, .syspage .sysname').forEach((el) => el.style.removeProperty('view-transition-name'));
  });

  // the Learn pages' explorers keep their own names (a block of their own)
  {
    // ------------------------------------------------------------ the Learn pages' explorers (draw/figures.py)
    // The build draws each one in full: every step, every case, the worked examples and every sentence. Here one
    // state is shown at a time and the controls are added. The arithmetic is the build's own (figures.py), on the
    // numbers the page holds; a sentence is a template of the page ({name} filled in).
    const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
    const button = (label, on, cls = 'xb') => { const b = el('button', cls, label); b.type = 'button'; b.addEventListener('click', on); return b; };
    const check = (label, checked, on) => {
      const l = el('label', 'xc'); const c = el('input'); c.type = 'checkbox'; c.checked = checked;
      c.addEventListener('change', () => on(c.checked)); l.append(c, label);
      return l;
    };
    const fill = (t, v) => t.replace(/\{(\w+)\}/g, (_, k) => v[k]);
    const num = (x, d = 2) => x.toLocaleString('en-US', { maximumFractionDigits: d });
    const rows = (s) => s.split(',').map((r) => r.trim().split(' ').map(Number));
    const mod = (x, p) => ((x % p) + p) % p;
    const list = (ws) => ws.length < 2 ? ws.join('') : `${ws.slice(0, -1).join(', ')} and ${ws[ws.length - 1]}`;
    // a matrix as the build draws one (figures.grid): a table of its entries
    const grid = (m) => {
      const t = el('table', 'mx'); const body = el('tbody');
      m.forEach((r) => { const tr = el('tr'); r.forEach((v) => tr.append(el('td', '', String(v)))); body.append(tr); });
      t.append(body);
      return t;
    };
    const column = (v) => grid(v.map((x) => [x]));

    const explorers = {
      // a walk: one step at a time, with a bar of the steps above it
      steps(root) {
        const items = $$('.xst', root);
        if (items.length < 2) return;
        let k = 0;
        const dots = el('ol', 'xdots');
        const show = (i, told) => {
          k = Math.max(0, Math.min(items.length - 1, i));
          items.forEach((li, j) => { li.hidden = j !== k; });
          $$('.xdot', dots).forEach((b, j) => { b.classList.toggle('on', j === k); if (j === k) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current'); });
          prev.setAttribute('aria-disabled', String(k === 0)); next.setAttribute('aria-disabled', String(k === items.length - 1));
          if (told) say(`${$('.xn', items[k]).textContent}: ${$('.xh', items[k]).textContent}`);
        };
        // at an end the button stays in place and focusable (aria-disabled): disabling it would drop the focus
        const prev = button('Back', () => { if (k > 0) show(k - 1, true); });
        const next = button('Next', () => { if (k < items.length - 1) show(k + 1, true); });
        items.forEach((li, i) => {
          const d = el('li'); const b = button(String(i + 1), () => show(i, true), 'xdot');
          b.setAttribute('aria-label', `${$('.xn', li).textContent}: ${$('.xh', li).textContent}`);
          d.append(b); dots.append(d);
        });
        const bar = el('div', 'xbar'); bar.append(prev, dots, next);
        root.prepend(bar);
        show(0, false);
      },

      // what is changed against what the verifier binds: refused when it binds a changed part
      tamper(root) {
        const panel = $('.xpn', root);
        const picked = (name) => $$(`input[name=${name}]`, panel).filter((c) => c.checked);
        const update = () => {
          const changed = picked('change'); const bound = new Set(picked('bind').map((c) => c.value));
          const caught = changed.filter((c) => bound.has(c.value)); const missed = changed.filter((c) => !bound.has(c.value));
          const verdict = !changed.length ? 'twin' : caught.length ? 'refuse' : 'false';
          $$('[data-v]', panel).forEach((p) => { p.hidden = p.dataset.v !== verdict; });
          const shown = $(`[data-v=${verdict}]`, panel);
          const parts = $('[data-slot=parts]', shown); const checks = $('[data-slot=checks]', shown);
          const of = (cs) => cs.map((c) => $(`input[name=bind][value=${c.value}]`, panel).dataset.words);
          if (parts) parts.textContent = list(of(verdict === 'refuse' ? caught : missed));
          if (checks) checks.textContent = list(missed.map((c) => c.dataset.check));
          $$('.xk li', panel).forEach((li) => {
            const held = bound.has(li.dataset.check); const word = $('span', li);
            $('.sw', li).className = `sw ${held ? 'held' : 'failed'}`;
            word.textContent = held ? word.dataset.held : word.dataset.failed;
          });
        };
        panel.addEventListener('change', update);
        panel.before(el('p', 'xf xhn', root.dataset.wHint));
        panel.hidden = false;
        update();
      },

      // a claimed matrix product checked with one random vector: A·(B·r) against C·r
      'random-check'(root) {
        const d = root.dataset; const p = Number(d.p);
        const A = rows(d.a); const B = rows(d.b); const wrong = rows(d.c); const right = rows(d.ok);
        const mv = (m, v) => m.map((r) => mod(r.reduce((s, x, i) => s + x * v[i], 0), p));
        const out = $('.xo', root); const shownC = $('.cl', root); const marked = shownC.innerHTML;
        let honest = false; let counts = {};  // one tally per set r is drawn from: the two miss at different rates
        const tally = el('p', 'xf'); const many = Number(d.runs);
        const set = (top) => top === 1 ? d.wSetbits : fill(d.wSetfield, { top });
        const one = (top) => {
          const r = A[0].map(() => Math.floor(Math.random() * (top + 1)));
          const left = mv(A, mv(B, r)); const got = mv(honest ? right : wrong, r);
          const c = counts[top] || (counts[top] = { n: 0, k: 0 });
          const equal = left.every((x, i) => x === got[i]);
          c.n += 1; if (!equal) c.k += 1;
          return { r, left, got, equal, c };
        };
        const draw = (top) => {
          const { r, left, got, equal, c } = one(top);
          const eq = el('div', 'eq'); const lb = (t) => el('span', 'lb', t);
          eq.append(lb('r'), column(r), lb('A·(B·r)'), column(left), lb('C·r'), column(got));
          const box = el('div', 'dr'); box.append(eq, el('p', 'vd', equal ? (honest ? d.wTrue : d.wMiss) : d.wDiff));
          out.replaceChildren(box);
          tally.textContent = fill(d.wTally, { n: num(c.n), k: num(c.k), set: set(top) });
          say(`${$('.vd', box).textContent} ${tally.textContent}`);
        };
        const batch = (top) => {
          let c; for (let i = 0; i < many; i++) c = one(top).c;
          out.replaceChildren();
          tally.textContent = fill(d.wTally, { n: num(c.n), k: num(c.k), set: set(top) });
          say(tally.textContent);
        };
        const claim = check(d.wWrong, true, (on) => {
          honest = !on; counts = {}; tally.textContent = '';
          if (honest) shownC.replaceChildren(grid(right)); else shownC.innerHTML = marked;  // the build's own table
          out.replaceChildren();
        });
        const bar = el('div', 'xbar');
        bar.append(button(d.wBits, () => draw(1)), button(fill(d.wField, { top: p - 1 }), () => draw(p - 1)),
          button(fill(d.wMany, { n: num(many), top: p - 1 }), () => batch(p - 1)), claim);
        out.before(bar); out.after(tally);
      },

      // the sumcheck of an inner product over the field of p elements, as figures.sumcheck runs it
      sumcheck(root) {
        const d = root.dataset; const p = Number(d.p); const lie = Number(d.lie); const many = Number(d.runs);
        const a0 = rows(d.a)[0]; const b0 = rows(d.b)[0];
        const fold = (v, r) => v.slice(0, v.length / 2).map((x, i) => mod((1 - r) * x + r * v[v.length / 2 + i], p));
        const dot = (a, b) => mod(a.reduce((s, x, i) => s + x * b[i], 0), p);
        const inv2 = (p + 1) / 2;
        const at = (s, r) => mod(s[0] * mod((r - 1) * (r - 2) * inv2, p) + s[1] * mod(-r * (r - 2), p) + s[2] * mod(r * (r - 1) * inv2, p), p);
        const run = (challenges, off) => {
          let a = a0; let b = b0; const claim = mod(dot(a, b) + off, p);
          let running = claim; const rounds = [];
          challenges.forEach((r) => {
            const s = [0, 1, 2].map((t) => dot(fold(a, t), fold(b, t)));
            s[0] = mod(running - s[1], p);
            const next = at(s, r);
            rounds.push({ s, claim: running, r, next });
            running = next; a = fold(a, r); b = fold(b, r);
          });
          const final = mod(a[0] * b[0], p);
          return { claim, rounds, a: a[0], b: b[0], final, accepted: final === running };
        };
        // the build's worked example, run again here: the two must agree
        const first = $('.tr', root);
        const draws = () => $$('tbody tr', first).map(() => Math.floor(Math.random() * p));
        const built = $$('tbody tr', first).map((tr) => Number(tr.lastElementChild.textContent));
        const again = run($$('tbody tr', first).map((tr) => Number(tr.children[4].textContent)), 0);
        console.assert(again.accepted && again.rounds.every((rd, i) => rd.next === built[i]), 'sumcheck: the page and the script differ');
        const out = $('.xo', root); const shown = first.cloneNode(true);
        let lying = false; let challenges = $$('tbody tr', first).map((tr) => Number(tr.children[4].textContent));
        const result = el('p', 'xf');
        const show = () => {
          const t = run(challenges, lying ? lie : 0);
          $('.vd', shown).textContent = fill(lying ? d.wLying : d.wHonest, { claim: t.claim });
          $$('tbody tr', shown).forEach((tr, i) => {
            const rd = t.rounds[i]; const [s0, s1, s2] = rd.s; const c = tr.children;
            c[1].textContent = rd.claim; c[2].textContent = fill(d.wSent, { s0, s1, s2 });
            c[3].textContent = fill(d.wCheck, { s0, s1, sum: mod(s0 + s1, p) });
            c[4].textContent = rd.r; c[5].textContent = rd.next;
          });
          const last = fill(d.wLast, { a: t.a, b: t.b, final: t.final, last: t.rounds[t.rounds.length - 1].next, verdict: t.accepted ? d.wAccepted : d.wRefused });
          $('.vl', shown).textContent = last;
          return last;
        };
        const who = check(d.wLies, false, (on) => { lying = on; result.textContent = ''; say(show()); });
        const redraw = button(d.wRedraw, () => { challenges = draws(); result.textContent = ''; say(show()); });
        const batch = button(fill(d.wMany, { n: num(many) }), () => {
          let k = 0;
          for (let i = 0; i < many; i++) if (run(draws(), lying ? lie : 0).accepted) k += 1;
          result.textContent = `${$('.vd', shown).textContent}. ${fill(d.wRuns, { n: num(many), k: num(k) })}`;
          say(result.textContent);
        });
        const bar = el('div', 'xbar'); bar.append(who, redraw, batch);
        out.replaceChildren(shown); out.before(bar); out.after(result);
        show();
      },

      // the bill for proving a share of replies, in units of the serving bill (figures.bill): generation is paid on
      // every reply, proving on the share. The fields start on example values; a row of the board fills them when pressed
      cost(root) {
        const d = root.dataset;
        const presets = $$('.pre li', root);
        const sig = (x) => Number(Number(x).toPrecision(4));  // four significant digits, as the board prints a figure
        const share = el('input'); share.type = 'range'; share.min = '0'; share.max = '400'; share.step = '1'; share.value = '200';
        const part = (value) => { const i = el('input'); i.type = 'number'; i.min = '0'; i.step = 'any'; i.inputMode = 'decimal'; i.value = value; return i; };
        const gen = part(d.g); const prove = part(d.p);
        const field = (input, words) => { const l = el('label', 'xl'); l.append(el('span', 'xll', words), input); return l; };
        const shown = el('span', 'xsv'); const out = el('p', 'xr'); out.setAttribute('role', 'status');
        const last = new Map([[gen, Number(d.g)], [prove, Number(d.p)]]);  // a field's last valid value stands while it is empty
        const read = (i) => { const x = i.value === '' ? NaN : Number(i.value); if (x >= 0) last.set(i, x); return last.get(i); };
        const update = () => {
          // the share as the page shows it, so a reader who multiplies the numbers shown gets the total shown
          const s = Number((10 ** (Number(share.value) / 100 - 4)).toPrecision(2));
          const g = read(gen); const p = read(prove);
          const pct = `${Number((s * 100).toPrecision(2))} %`;
          shown.textContent = pct; share.setAttribute('aria-valuetext', pct);
          out.textContent = fill(d.wOut, { share: pct, g: `${num(sig(g), 4)}×`, p: `${num(sig(p), 4)}×`, total: `${num(sig(g + s * p), 4)}×` });
        };
        presets.forEach((li) => {
          const b = button('', () => { gen.value = String(sig(li.dataset.g)); prove.value = String(sig(li.dataset.p)); update(); }, 'pb');
          b.append(...li.childNodes); li.append(b);
        });
        const bar = el('div', 'xbar xin'); const sl = field(share, d.wShare); sl.append(shown);
        bar.append(sl, field(gen, d.wGeneration), field(prove, d.wProving));
        [share, gen, prove].forEach((i) => i.addEventListener('input', update));
        const table = $('.tw', root);
        table.before(el('p', 'xf xhn', presets.length ? d.wHintrows : d.wHint), bar, out);
        update();
      },
    };
    $$('.xpl[data-x]').forEach((root) => {
      const start = explorers[root.dataset.x];
      if (start) { start(root); root.classList.add('on'); }
    });

    // ------------------------------------------------------------ who holds what (figures.parties): a thing pointed at lights
    // wherever it is held or passed, the rest dims
    $$('.pt3').forEach((fig) => {
      const keyed = $$('[data-k]', fig);
      const lit = (k) => { fig.classList.toggle('k-on', !!k); keyed.forEach((x) => x.classList.toggle('k-lit', !!k && x.dataset.k === k)); };
      keyed.forEach((x) => { x.addEventListener('pointerenter', () => lit(x.dataset.k)); x.addEventListener('pointerleave', () => lit(null)); });
    });

    // ------------------------------------------------------------ a glossary term, pointed at or given focus: its name and first
    // sentence beside it (the build put them on the link); the link still leads to the glossary
    const terms = $$('a[data-d]');
    if (terms.length) {
      const peek = el('p', 'gpk'); peek.id = 'gpk'; peek.setAttribute('role', 'tooltip'); peek.hidden = true;
      requestAnimationFrame(() => body.append(peek));
      let on = null;
      let byKey = false;  // shown by keyboard focus: the peek follows its term on a scroll; a pointer's is put away
      const off = () => { if (!on) return; on.removeAttribute('aria-describedby'); on = null; byKey = false; peek.hidden = true; };
      // under the link's last line, or over it when the window ends first; inside the page's gutters
      const place = (a) => {
        const rs = a.getClientRects(); const r = rs[rs.length - 1] || a.getBoundingClientRect(); const top = (rs[0] || r).top;
        const w = peek.offsetWidth; const h = peek.offsetHeight;
        const [lo, hi] = gutters(a, w);
        const x = Math.max(lo, Math.min(r.left, hi - w));
        const y = r.bottom + 8 + h > innerHeight ? top - h - 8 : r.bottom + 8;
        peek.style.setProperty('transform', `translate(${Math.round(x)}px, ${Math.round(y)}px)`);
      };
      const show = (a) => {
        if (on === a) return;
        off(); on = a;
        peek.replaceChildren(el('b', '', a.dataset.g), el('span', '', a.dataset.d));
        peek.hidden = false;
        a.setAttribute('aria-describedby', 'gpk');
        place(a);
      };
      // a mouse leaving the link or the peek puts the peek away a moment later, so the pointer can move onto it
      let going = 0;
      const later = () => { clearTimeout(going); going = setTimeout(off, 250); };
      peek.addEventListener('pointerenter', () => clearTimeout(going));
      peek.addEventListener('pointerleave', (ev) => { if (mouse(ev)) later(); });
      terms.forEach((a) => {
        a.addEventListener('pointerenter', (ev) => { if (mouse(ev)) { clearTimeout(going); show(a); } });
        a.addEventListener('pointerleave', (ev) => { if (mouse(ev)) later(); else off(); });
        a.addEventListener('focus', () => { if (a.matches(':focus-visible')) { show(a); byKey = true; } });
        a.addEventListener('blur', off);
      });
      // a scroll puts a pointer's peek away; one shown by focus follows its term (the scroll focus itself causes too)
      away.push(() => { if (on && byKey && on === document.activeElement) place(on); else off(); });
      addEventListener('keydown', (ev) => { if (ev.key === 'Escape') off(); });
    }
  }
})();
