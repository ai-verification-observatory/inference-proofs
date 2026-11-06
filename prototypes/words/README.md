# Made of words (prototype site)

A static prototype of the public site. Draft criteria, prototype only, needs an RFC (RFC-0001). Every run-here value and every benchmark result here is invented for layout and marked MOCK. Quotes, model sizes and each system's published figures come from the data and are real.

Four static pages built from two data files: `index.html` (the overview), `flashprove.html` and `sash.html` (one page per benchmarked system), `reference.html` (the reference rows), and `system.html` (a redirect to the first system page).

## Build and check

From this folder:

```
python3 -I build.py                      # writes the five HTML files and the contrast table below
python3 test_sort_keys.py                # or: python3 -m pytest test_sort_keys.py
python3 -m http.server 4421 --bind 127.0.0.1 --directory .
PLAYWRIGHT_MODULE=<path to playwright/index.mjs> \
AXE_MODULE=<path to @axe-core/playwright/dist/index.mjs> \
BASE=http://127.0.0.1:4421/ node shoot.mjs    # screenshots and checks into shots/ (shots/checks.txt)
```

`PLAYWRIGHT_MODULE` and `AXE_MODULE` default to the package names `playwright` and `@axe-core/playwright`, so with both installed next to the scripts the two variables can be left out. `node peek.mjs <page> <width> <height> <out.png> [1 for full page] [script]` takes one screenshot. `shoot.mjs` exits non-zero when any check fails.

## Data

`build.py` reads only `_data/site.json` and `_data/criteria.json`, found relative to its own file. It stops if `criteria.json` changed since `site.json` was built, if a pie's states differ from `criteria.json`, if a state ink steps less than 1.7:1 from the one below, if a text pair falls under 4.5:1, or if a home figure's sort key disagrees with the number the figure prints. Every value, label, quote, pin, hash and data sentence on the pages comes from the data. The build computes only pie geometry, sort keys and the contrast table. `words.js` and `words.css` hold no data.

Three data sentences are not printed: "These tests show only what happened to these attempts, nothing more." (tamper tests), "Printed as text." (inside one of our notes) and "Run-here values are MOCK: never set them against a published figure." (every run-here value carries its own MOCK chip, and the sentence made the table jump when the view changed). "Native workloads differ: rows are not a head-to-head comparison." is printed only where rows sit side by side: the Benchmarked table and the reference page.

## Design

Dark ground, paper text. Violet is the benchmark's own frame: the six properties and page titles, never a value or a state. Green, amber, red and empty mean Yes, Partly, No and Not stated, and appear only in pie slices and state squares. The paper chip is MOCK. Archivo for display, IBM Plex Mono for data and quotes. No cards, shadows or double rules; no helper sentences, taglines or captions.

Each system is a flat pie of six slices, one per property, clockwise from twelve: Weights hidden, Model bound, Whole output proved, Formally verified, Security level, No trusted party. The properties carry no numbers anywhere, visible or spoken, so they do not read as a sequence.

### Overview header

A plain legend on the violet field: six small key pies (each with its own slice filled in paper), the property name and its question, the states key and the draft-criteria link. Nothing in it reacts to the pointer: no buttons, no hover or pressed states, no script. 276 px tall at 1440 px wide; the six questions share one top line. Below 560 px it is one compact line per property (22 px key pie, name, question), so the first system's name shows on a 390 x 844 screen without scrolling.

### Overview rows

Each row: the pie, the system name (both link to the system page), the model and pinned commit, then the four figures with their label lines. Each figure links to its plate on the system page, and its full label line is in its `title`. A figure with a stored spread always shows its sample size (with failed runs) and range first, e.g. SASH run here: "n = 3 runs, n_failed = 1", "119.8 s to 122.6 s". Pointing at a slice with a mouse lifts that slice (the others keep their ink) and shows the property's name and state in a small positioned label under the pie, so nothing moves. Touch screens show no label. There is no per-row readout block.

### Sorting

The Benchmarked table sorts on System (A to Z, Z to A) and on each figure column: One proof covers, Proof size, Check time, Overhead.

- Every column head is a button with a glyph: ↕ when idle, ↑ or ↓ when it sorts the table. The sorting head is in paper with a rule under it, and its header cell has `aria-sort`. A second press reverses the order.
- The Sort control (a native select) above the table names the order in words, from the data's own direction words: "Proof size, small to large", "Overhead, closer to plain serving first", and so on. Below 920 px the heads are hidden, the control stays, and each row's sorted figure label turns paper and carries the glyph.
- The order is kept in the hash, with the view when it is Run here: `#sort=proof_size-desc`, `#sort=check_time-desc&view=run`. The default (System, A to Z, published values) has no hash. An unknown order in a link falls back to the default and the hash is rewritten to match. The draft-criteria link scrolls to the footer without replacing the hash, so a sorted link survives it.
- Sorting uses the values of the current view. Switching between Published by each system and Run here (MOCK) re-sorts.
- A figure with no number (Not published, No value) goes last in both directions. Ties fall back to the name.
- Rows move to their new place in 200 ms (FLIP), and at once under reduced motion.
- Neutral: no rank numbers, no medals, no ranking words. "Native workloads differ: rows are not a head-to-head comparison." stays directly above the sorted table, beside the Sort control.

Sort keys are computed, never typed. For each prover row, view and column, `build.py` takes the raw number from the axis chart that plots that figure (`axes.<axis>.charts[<chart>].views.<view>.rows[].value` in `site.json`) and multiplies it into one base unit by the chart's declared unit (bytes for proof size, seconds for check time, positions for coverage, a plain ratio for overhead). The keys go on each row as `data-k`. The build also parses each printed figure ("18.78 MB", "1,583×") only to check that the raw number rounds to it; the printed text is never a key. `test_sort_keys.py` checks the keys against hand-computed cases (18.78 MB < 19.83 GB, 16.84 s < 119.1 s, missing overheads), the unit table, and the data's own precomputed sort orders.

Not sortable, by design: the Reference table. Its cells have no raw number in the data ("same as above", "No proof", "Does not apply", "1× by definition"), so it keeps the data's order. The Not benchmarked yet tab has no figures.

### System pages

The large pie with quotes inside is gone. The page opens on the violet field with the system name, the pinned repository and in-page links (Properties, Figures, Tamper tests, Sources). Then the system's own quote with its source, beside its facts (kind, model, repository, licence, status).

What one proof establishes is one view, with everything visible at once: a 168 px pie, sticky beside six lines. Each line has a small key pie drawn like the header legend (its slice in paper), the property name and question, the state and our short reason, and the decisive verbatim quote with its source link (or what was read, when silent). When a property is Not stated, the generic reason ("Not stated in the pinned repositories.") is left out: the state word and "Silent in the N sources read" already say it. Further quotes, our notes and the system's own notes outside the pin go into one `details` per line. The summary names what is inside, with the data's own outside-pin line in muted text and no state colour ("Outside the pin, SASH's own note says: Partly (not counted)"); the coloured state and its reason appear only inside. Pointing at a line lifts its slice on the pie (CSS only).

Figures follow: the published or run-here view, four plates with every label (spread, as published, scope, grade, checked, workload, source and caveats), more numbers, tamper tests (MOCK) with the control test, and sources and pins. The reference page uses the same property view and plates for each reference system.

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

- `build.py`: the pages, the sort keys and the contrast table. `test_sort_keys.py`: the sort-key test, and the spread shown on every home figure that stores one.
- `words.css`, `words.js`: style and behaviour, no data.
- `shoot.mjs`: screenshots and checks: horizontal overflow at 360 and 390 px (every page and tab) and 768 to 1100 px, clipped figures, CLS on load and after sorting, a static header, row hover without shift, sort order for every column, direction and view (missing values last), hash round-trip (unknown order and the draft link included), a table that stays put when the view changes, sample size and range on every run figure that has them, the first system name on landing at 390 px, keyboard sorting, the cut sentences, ranking words in the site's controls, numbered property names, dead local links, console errors, and axe on every page (1440 and 390 px, home tabs and sorted run view). `peek.mjs`: one screenshot.
- `_data/`: `site.json` and `criteria.json`, a frozen snapshot from the prototype data pipeline (MOCK benchmark fixtures; quotes and published figures at their pins). The generator is not part of this folder.
- `shots/`: screenshots and `checks.txt`.

## Open

- The reference table cannot be sorted until the data stores raw numbers for its cells.
- The Sort select is as wide as its longest option ("Overhead, further from plain serving first"), so it does not change width as the order changes. The direction words come from the data (`overview.sort_keys[].dir_words` in `site.json`); making them one pattern ("low to high", "few to many") is a change to the data generator, not to this folder.
- The phone system page puts the pie above the six lines rather than beside them.

## Critique

- Sorting is visible in three places at 1440 px: the Sort select, the column-head glyphs and the paper rule under the active head. That is one control too many for two rows; it earns its place once more systems are benchmarked.
- The desktop table shows the sorted column only in its 12 px head. Phones mark each row's figure label instead, because they have no heads.
- The phone header is still about 400 px tall. The first system's name shows on landing at 390 x 844, its pie only in part.
- The option words mix two patterns ("small to large", "fewer positions first") and "plain serving" is named on the Reference tab, not on the Benchmarked one. Both come from the data generator.
- The property view's 26 px key pie is quiet at 1x; the state square beside it carries the state.
- With two benchmarked systems, the sort changes little on screen. The checks run every column, direction and view, but the design has not been seen with ten rows.
