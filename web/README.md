# The public site

The public site at www.inferenceproofs.ai, its design named "Made of words". Draft criteria, needs an RFC (RFC-0001). The site shows only the benchmark's own runs. **Every benchmark result in this prototype is a placeholder** from the data fixture; the pages do not mark them, because the published site will only ever show real runs. Model sizes, pins and workloads come from the data and are real.

Static pages built from two data files, served at clean addresses: `/` (the overview, `index.html`), `/flashprove` and `/sash` (one page per benchmarked system), `/reference` (the two references), `/criteria` (what each state means for each property) and the 404 page.

## Build and check

From this folder:

```
python3 -I build.py                      # the pages, 404.html, vercel.json, the card sources in og/, the fonts block in words.css, the contrast table below
PLAYWRIGHT_MODULE=<path to playwright/index.mjs> node og.mjs && python3 -I build.py   # when a card source changed
python3 -I test_sort_keys.py             # or: python3 -m pytest test_sort_keys.py
python3 -I test_cards.py                 # each picture rendered from its committed source; every page names one
python3 -I test_search.py                # the search index
python3 -I serve.py                      # http://127.0.0.1:4440/ as on Vercel: the deployed files only, clean addresses, redirects, headers (CSP included), 404
PLAYWRIGHT_MODULE=<path to playwright/index.mjs> \
AXE_MODULE=<path to @axe-core/playwright/dist/index.mjs> \
BASE=http://127.0.0.1:4440/ node shoot.mjs    # screenshots and checks into shots/ (shots/checks.txt)
```

`PLAYWRIGHT_MODULE` and `AXE_MODULE` default to the package names `playwright` and `@axe-core/playwright`. Locally they can be installed under `web/.tools/` (ignored by git): `npm i --prefix .tools playwright @axe-core/playwright`. `node peek.mjs <page> <width> <height> <out.png> [1 for full page] [script]` takes one screenshot. `shoot.mjs` exits non-zero when any check fails.

## Deploy

www.inferenceproofs.ai serves this folder from Vercel's Git integration (the Vercel project's Root Directory is `web`). `build.py` writes `vercel.json`, since parts of it come from the build:

- `ignoreCommand`: `git diff --quiet HEAD^ HEAD -- .` skips a deployment when the commit (on main, the merge commit against its first parent) does not change this folder.
- `buildCommand`: no build on Vercel; it copies the committed pages, `words.css`, `words.js`, the pictures and icon in `og/` and the fonts in `fonts/` into `public/`, the only folder served. The data, scripts, card sources, screenshots and README are not.
- `cleanUrls` and `trailingSlash: false`: `/flashprove` serves `flashprove.html`; `/flashprove.html` and `/flashprove/` redirect to it. Every link on the pages is root-relative and clean, so no click costs a redirect and the 404 page works at any depth. `/system` (an older address) redirects to the first system page.
- Headers on every response: `noindex` while the results are placeholders, a Content-Security-Policy that allows only this site's own files plus the one inline script by its sha256 (computed by the build), `X-Frame-Options: DENY`, a Permissions-Policy, `nosniff` and a referrer policy.
- Caching: `words.css` and `words.js` are linked with `?v=` and the first 12 hex of their sha256, the pictures likewise, and each font file carries its hash in its name; all four get a one-year immutable cache. Pages revalidate on every visit.

The pages are served as committed, so `.github/workflows/site.yml` holds them to the build: on every pull request that touches this folder it runs `build.py`, `test_sort_keys.py`, `test_cards.py` and `test_search.py` and fails if any file differs from what the build writes, new files included.

## Fonts

Archivo (variable width and weight) and IBM Plex Mono 400, 500 and 600 are served from `fonts/`, not from Google Fonts: no third-party request, no visitor's address sent elsewhere, and text that shows as soon as this site's files arrive. The files are Google Fonts' own Latin and Latin Extended subsets, plus a Plex Mono subset for the arrows (← ↑ → ↓ ↕ ↗), × and ≈ so every arrow is set in the same face. `fonts/faces.json` lists each file with its family, weights, widths and unicode range; each file's name carries the first 10 hex of its sha256, which `build.py` checks. The build writes the `@font-face` rules into `words.css` between its markers and preloads the three most used files. Both fonts are under the SIL Open Font License 1.1 (`fonts/OFL-*.txt`).

## Data

`build.py` reads `_data/site.json`, `_data/criteria.json`, `fonts/faces.json`, `words.css` (for its inks and slice lifts) and the RFC file names in `../rfcs`. It stops if a pie's states differ from `criteria.json`, if a state ink steps less than 1.7:1 from the one below, if a text pair falls under 4.5:1, if `words.css` holds different inks or slice lifts than the ones the build computes with, if a home figure's sort key disagrees with the number the figure prints, if a benchmarked row is not on `TARGET_MODEL`, if a font file's name does not carry its hash, if a reworded phrase is no longer in the data, or if a rule code names an RFC that does not exist. Every value, label, pin and hash on the pages comes from the data. The footer pins the committed `criteria.json` by its sha256.

What the pages leave out of the data, or say differently, on purpose:

- The systems' own published figures and every quote. The benchmark measures; who said what is not shown. The glyph's states and our short reasons stay. Where a reason left out a limit the system's own source states, the reason says it (FlashProve, Formally verified: "proved in Lean for the protocol; the C++ verifier and CUDA prover are tested, not proved").
- Every placeholder marking: MOCK chips, the placeholder banner, and the parts of the data's label text that speak of mock values or "the fixture" (`words`, `clean` and `clean_prose` in `build.py`). A label left empty by that is not printed.
- RFC rule codes ("RFC-0015 NM-1") never print bare: on plates and in the more-numbers table they become a small "rule ↗" link to the RFC after the sentence's full stop, its code read to screen readers; in home cells and titles they are left out.
- A few data phrases are worded for a reader who has not read the RFCs (`PHRASES` in `build.py`): the overhead's missing value reads "Plain serving could not run this model on one H100, so there is no baseline to divide by"; the rerun reference is never called "recompute"; the criteria page does not speak of quotes, cards, glyphs or "not copied yet", which the site does not show. A row that names its own basis ("GPU cost per 1,000 positions") prints its value without repeating it.
- Spreads read in words ("3 completed, 1 failed", not "n = 3 runs, n_failed = 1": n counts the completed runs, the failed ones are not in the figure), a per-unit line reads "per proof", raw floats are dropped from titles, a number never wraps away from its unit (nor a count word or a statistic from what it counts), an id, date or model name never breaks at a hyphen, and a "·" separator never starts a line. A missing number's title gives only why it is missing.
- A missing number carries no grade or check: its plate shows why it is missing and where that is recorded, its more-numbers row only why.
- The references' rows per model. Each reference is one row (`ref_summary` in `build.py`): a figure the models share is printed once; where they differ, the one that holds a value (plain serving's overhead is 1× by definition, run or not); what one proof covers, stored as "same as above", reads "Same as the system".
- Not benchmarked yet: each system's models in full (never cut mid-phrase), and its status without repeating what the heading or the status already says ("no adapter yet", a second "archived").
- Two data sentences: "These tests show only what happened to these attempts, nothing more." and "Printed as text.".

## Models

The site compares systems on one model, Llama 4 Maverick (400B parameters, 17B active per token), and shows only systems run on it: `TARGET_MODEL` in `build.py`. The code still sets rows side by side per model, biggest first, should the data ever hold more than one.

**SASH's figures on Llama 4 Maverick are placeholders placed there for layout.** SASH's pinned code runs Llama 3.1 8B only (RFC-0003). `_data/maverick_only.py` moved its placeholder row from Llama 3.1 8B onto FlashProve's workload: what one proof covers, the overhead and the per-unit lines are the workload's, taken from FlashProve's cells; proof size, check time and the more-numbers keep SASH's placeholder values. It also removed the reference rows on Llama 3.1 8B. The script edits only what `build.py` reads and does nothing when run again; the rest of `site.json` (configurations, the overview's precomputed orders) still describes the earlier snapshot.

## Design

Dark ground, paper text. Violet is the benchmark's own frame: the six properties and page titles, never a value or a state. Green, amber, red and empty mean Yes, Partly, No and Not stated, and appear only in pie slices and state squares. Archivo for display, IBM Plex Mono for data. No cards, shadows or double rules; no helper sentences, taglines or captions.

Each system is drawn as the **hex asterisk**: six triangles that make a point-top hexagon, one per property, clockwise from twelve (Weights hidden, Model bound, Whole output proved, Formally verified, Security level, No trusted party), so 1 to 3 sit on the right and 4 to 6 on the left, on a pie's own 60-degree axes. The cuts between the triangles widen toward the centre, so the ground they leave draws an asterisk, the footnote mark that sends a reader to the fine print. A Not stated slot keeps only its side, as a line, so it reads as empty inside an outline that stays whole; where two empty slots meet, a short tick down the cut keeps them countable. The glyph is drawn in device pixels (`hex_svg` in `build.py`): gaps and lines are sized for each size, and up to 40 px the centre and the flat sides sit on the pixel grid. In one colour (`mark_svg`, wider cuts so the asterisk leads) it is the logo, the favicon and the touch icon. It was chosen in a study of six directions (hexagon, ring, pinwheel, asterisk, pixel disc, cut pie) judged on reading, brand and fit. The properties carry no numbers anywhere.

### Header and footer

The top bar: the logo (the site's mark, the hex asterisk in violet, and its name; it leads to the overview and marks it as the current page there) and the pages (References, Criteria) at the left, a wide search field (up to 600 px) centred in the room between them and GitHub at the right. Up to 960 px, below the width a centred field needs, the name, a search button and GitHub share the first line and the pages the second; the button opens the field over the first line.

### Search

Systems are reached by search, not by one nav link each, since there will be many. `build.py` writes `search.json` (linked by its hash): every benchmarked system, reference, not-benchmarked system and property (the pages are in the nav), with a line of context, its pie and the words it is found by: its name, models, kind and status, its stated technique, its code status ("no public code", "closed source"), its badge, and a few words true of its whole family (`TERMS`: "zk", "TEE", "enclave"...; how a system proves, STARK or SNARK, comes only from its own stated technique). People's names are not indexed.

`words.js` loads it on first focus and matches locally (nothing leaves the browser): the start of a name, a word in the name, then the other words. A typo (a letter added, missing or wrong, or two swapped) is tried only for a word no entry has, and only from its right first letter. A number glued to a word is apart ("llama4" is "llama 4"); one letter searches names only.

Not-benchmarked systems come after every other match, each marked "Not benchmarked" (most are closed source, so they cannot be run here). Within each part results are ordered by where the words matched, then by kind of entry (benchmarked systems, properties, references), then by closeness. Up to 12 of each part are listed, and a line counts the rest. A not-benchmarked result leads to its card in the overview, marked and labelled "Not benchmarked". An empty field lists the benchmarked systems.

`/` or Ctrl/Cmd + K focuses it from anywhere (`aria-keyshortcuts`); arrows choose, Enter goes to the chosen result or the first of a typed search, Escape clears then closes. It is an ARIA combobox with a listbox; the count is announced; without script it is not shown. If `search.json` cannot load, the list says so and the next focus tries again.

### Overview

1. A plain legend on the violet field: six small key glyphs (each property's own triangle filled in ground ink, 5.92:1 on violet, the others as line), each property's name and question, the states key and the link to the criteria page. Nothing in it reacts to the pointer. On a phone held sideways it folds into three short columns so the first table's heading shows on landing.
2. **Llama 4 Maverick**: the model's name, its size and workload in one line, and a sortable table of the systems on it (glyph, name and pin, then One proof covers, Proof size, Check time, Overhead). Each figure links to its plate on the system page and shows its sample size and range when it has them. Each figure link is named after its column for screen readers, also where the column heads are out of view.
3. **References**, after the models: two rows, plain serving and a rerun by a weights holder, on the same columns. Not sorted. Their figures link to the reference's figures.
4. **Not benchmarked yet**: a compact grid, A to Z, of glyph, name, models and status.

Pointing at a row's triangle with a mouse lifts it (the others keep their ink) and shows its name and state under the glyph. A still copy of the triangles takes the pointer, so a lifted one never flickers out from under it.

### Sorting

The column heads are the only sort control, and one order applies to every model's table. Each head is a button with a glyph: ↕ idle, ↑ or ↓ when it sorts, a second press reverses. The sorting head is in paper with a rule under it and its cell has `aria-sort`; the order is also named for screen readers ("Proof size, large to small", from the data's direction words). Below 920 px the heads wrap into a strip of the same buttons above the rows. Without script the heads do not look pressable.

- The order is kept in the hash: `#sort=proof_size-desc`. The default (System, A to Z) has no hash; an unknown order falls back to it, and so does going Back to the page without a hash.
- A figure with no number goes last in both directions. Ties fall back to the name.
- Rows move in 200 ms (FLIP), at once under reduced motion.
- Neutral: no rank numbers, medals or ranking words.

Sort keys are computed, never typed: for each row and column, `build.py` takes the raw number from the axis chart that plots that figure (`axes.<axis>.charts[<chart>].views.run.rows[].value`) and multiplies it into one base unit by the chart's declared unit. The printed figure is parsed only to check that the raw number rounds to it. `test_sort_keys.py` checks the keys against hand-computed cases, the unit table, the single model, the reference rows (`ref_summary`) and the label rewrites.

### System pages

The violet band holds the name. Below it, one screen: the pie (200 px) in the middle with each property beside its own slice, slices 1 to 3 on its right and 4 to 6 on its left, top to bottom. Each property shows its name (a link to what its states mean), state and our short reason (left out when it only repeats Not stated); its question is read to screen readers. Pointing at a property lifts its slice; pointing at a slice marks its property. Beside the pie, the facts: kind, model, pinned repositories, licence, status (one form for every system: the state, then its last push and source when stored), adapter notes. Below 1240 px the facts move under the pie; on phones the pie sits on top with its left-hand and right-hand properties in two columns under it.

Then the figures (four plates with every label: spread, scope, grade, checked, workload, why, source; their rules line up across the plates) with more numbers in a table, and the tamper tests with the control test, run or documented and not yet run. The reference page uses the same layout for each reference, with one set of figures.

### Criteria page

`/criteria`: for each property, its name and question, then what Yes, Partly, No and Not stated mean for it, and what it does not cover, from `criteria.json`. The nav, the legend, the footer and every property name on a system page link to it.

### Preview cards

What a shared link shows (Open Graph and X `summary_large_image`): every page carries its title, description, canonical URL and a picture with its alt text, all from the data. The pictures are 1200 x 630 at 2x (2400 x 1260 PNG) and drawn in the site's own type and inks:

- `og/home.png` (the home, the reference and the criteria page): only what does not change with the systems benchmarked, since link previews stay cached in message apps for as long as the message lives: the six property names on the violet field, each beside its place in the pie, and the site's mark and name. No system, model or state.
- `og/<system>.png`: the system page's first screen: the name on the violet band with its model and pin, then its pie with each property's state beside its own slice.
- A system card says "Draft criteria, needs an RFC" (the data's label), since a picture travels without the page around it. Not stated slices get a heavier outline than on the pages, so they still read at preview size. The alt text says what the picture draws.
- `og/icon.svg` (the favicon) and `og/icon.png` (the 180 px touch icon, rendered from `og/icon.html`): the hex asterisk in ground ink on the violet field.

No figures are drawn: results are placeholders until a release exists, and a picture travels without its labels. `build.py` writes each picture's source (`og/<card>.html`); `og.mjs` renders it with the same Playwright as `shoot.mjs`, with the fonts from `fonts/` (no network), refuses a card whose fonts did not load, whose content spills past its edges or whose system name runs into the band's corner text, and records the sha256 of source and picture in `og/cards.json`. The pages name each picture with `?v=` and the first 12 hex of its hash, so a new picture is a new URL for link-preview caches. `test_cards.py` fails when a committed picture was not rendered from its committed source.

### 404

An unknown address answers the site's own page with status 404: the header and the violet band, "Not found". It is never shared (`noindex`, no preview card).

### Accessibility

axe passes on every page at 1440 and 390 px (WCAG 2.2 AA and axe's `best-practice` rules). Beyond it: no duplicate ids, row headings hold only the system's name (its six states follow as text for screen readers), arrows are not read aloud, page titles carry the site's name, the band's name keeps every letter under text-spacing overrides, nothing overflows at 320 px (400 % zoom), and under forced colours (Windows high contrast) the state squares keep their inks and Not stated stays empty.

## Inks and contrast (computed by `build.py`)

<!-- ladder -->
| Word | Ink | Luminance | Contrast on the ground `#0b0b0c` | Step from the state below |
|---|---|---|---|---|
| Not stated | none (empty, outline `#6f6a62`, 3.67:1) | 0.003 | 1.00:1 |  |
| No | `#e8332a` | 0.197 | 4.63:1 | 4.63:1 |
| Partly | `#e89400` | 0.383 | 8.12:1 | 1.76:1 |
| Yes | `#7cf29a` | 0.701 | 14.08:1 | 1.73:1 |

| Pair | Contrast |
|---|---|
| paper text on ground (`#f1efe9` on `#0b0b0c`) | 17.11:1 |
| muted text on ground (`#9b978e` on `#0b0b0c`) | 6.76:1 |
| black text on violet (`#0b0b0c` on `#c45cff`) | 5.92:1 |
| violet text on ground (`#c45cff` on `#0b0b0c`) | 5.92:1 |
| ground text on Yes (`#0b0b0c` on `#7cf29a`) | 14.08:1 |
| ground text on Partly (`#0b0b0c` on `#e89400`) | 8.12:1 |
| ground text on No (`#0b0b0c` on `#e8332a`) | 4.63:1 |
<!-- /ladder -->

## Files

- `build.py`: the pages, `vercel.json`, the card sources, the fonts block, the sort keys and the contrast table. `serve.py`: the local preview, run under `vercel.json`'s own rules.
- `test_sort_keys.py`: the sort keys, the single model, the reference rows and the label rewrites. `test_cards.py`: the preview cards, the share tags, the icon and the 404.
- `words.css`, `words.js`: style and behaviour, no data (the fonts block in `words.css` is written by the build).
- `fonts/`: the font files, `faces.json` and their licences.
- `shoot.mjs`: screenshots and checks: no sort control, toggle, tabs, quotes or placeholder marking; one table, Llama 4 Maverick, references after it; a static header; row hover without shift; sort order for every column and direction from the heads, also on rows that differ in every column with missing values among them, the hash round-trip, Back to the default and keyboard sorting; overflow at 320 to 1100 px on every page; `/system` redirects; a malformed hash breaks nothing; search (the shortcut, order, typos, the not-benchmarked badge and landing, Enter and arrows, the phone button); every local link and its #fragment resolve; CLS; the first system name on landing at 390 px and the model heading on a phone held sideways; on each system and reference page, a small pie with slices 1 to 3 described on its right and 4 to 6 on its left within the first screen; the styled 404 at any depth; no duplicate ids, no placeholder words, field names or bare rule codes; the cut sentences, ranking words, numbered property names, dead local links, console errors, and axe on every page at 1440 and 390 px.
- `search.json` (written by `build.py`) and `test_search.py`: the search index and its check.
- `og.mjs`, `og/`: the preview cards (sources, pictures, `cards.json`).
- `_data/`: `site.json`, `criteria.json` and `maverick_only.py`.
- `shots/`: screenshots and `checks.txt`.

## Open

- SASH's row on Llama 4 Maverick is a layout placeholder (see Models); the table needs a second real system on the model before sorting compares measured runs.
- The pie's states still come from reading each system's documentation (the criteria in `criteria.json`). Showing them as measured needs checks of our own per property; until then the reason line is ours and the quotes are left out.
- The direction words come from the data generator, which is not in this repository (`_data/site.json` is a frozen snapshot of its output), and mix two patterns ("small to large", "fewer positions first").
- The tamper tests print their tally and the control test; the per-attempt records are in the data but not listed, and SASH's records still describe its Llama 3.1 8B setup.
