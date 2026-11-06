# The public site

The public site at www.inferenceproofs.ai, its design named "Made of words". Draft criteria, needs an RFC (RFC-0001). The site shows only the benchmark's own runs. **Every benchmark result in this prototype is a placeholder** from the data fixture; the pages do not mark them, because the published site will only ever show real runs. Model sizes, pins and workloads come from the data and are real.

Four static pages built from two data files: `index.html` (the overview), `flashprove.html` and `sash.html` (one page per benchmarked system), `reference.html` (the two references) and `system.html` (a redirect to the first system page).

## Build and check

From this folder:

```
python3 -I build.py                      # writes the five HTML files and the contrast table below
python3 test_sort_keys.py                # or: python3 -m pytest test_sort_keys.py
python3 -m http.server 4440 --bind 127.0.0.1 --directory .
PLAYWRIGHT_MODULE=<path to playwright/index.mjs> \
AXE_MODULE=<path to @axe-core/playwright/dist/index.mjs> \
BASE=http://127.0.0.1:4440/ node shoot.mjs    # screenshots and checks into shots/ (shots/checks.txt)
```

`PLAYWRIGHT_MODULE` and `AXE_MODULE` default to the package names `playwright` and `@axe-core/playwright`. Locally they can be installed under `web/.tools/` (ignored by git): `npm i --prefix .tools playwright @axe-core/playwright`. `node peek.mjs <page> <width> <height> <out.png> [1 for full page] [script]` takes one screenshot. `shoot.mjs` exits non-zero when any check fails.

## Deploy

www.inferenceproofs.ai serves this folder from Vercel's Git integration (the Vercel project's Root Directory is `web`). `vercel.json` here does the rest:

- `ignoreCommand`: `git diff --quiet HEAD^ HEAD -- .` skips a deployment when the commit (on main, the merge commit against its first parent) does not change this folder.
- `buildCommand`: no build on Vercel; it copies the committed pages, `words.css` and `words.js` into `public/`, the only folder served. The data, scripts, screenshots and README are not.
- `cleanUrls`, and the headers of the previous site, `noindex` included while the results are placeholders.

The pages are served as committed, so `.github/workflows/site.yml` holds them to the build: on every pull request that touches this folder it runs `build.py` and `test_sort_keys.py` and fails if the committed files differ from what the build writes.

## Data

`build.py` reads only `_data/site.json` and `_data/criteria.json`, found relative to its own file. It stops if a pie's states differ from `criteria.json`, if a state ink steps less than 1.7:1 from the one below, if a text pair falls under 4.5:1, if a home figure's sort key disagrees with the number the figure prints, or if the default model does not name exactly one workload. Every value, label, pin and hash on the pages comes from the data. The build computes only pie geometry, sort keys and the contrast table. `words.js` and `words.css` hold no data.

What the pages leave out of the data, on purpose:

- The systems' own published figures and every quote. The benchmark measures; who said what is not shown. The pie's states and our short reasons stay.
- Every placeholder marking: MOCK chips, the placeholder banner, and the parts of the data's label text that speak of mock values (a " · "-separated segment, or a clause of a sentence, that says mock; `clean` and `clean_prose` in `build.py`). A label left empty by that is not printed.
- The references' rows per model. Each reference is one row (`ref_summary` in `build.py`): a figure the models share is printed once; where they differ, the one that holds a value (plain serving's overhead is 1× by definition, run or not); what one proof covers, stored as "same as above", reads "Same as the system" with its rule (RFC-0015 REF-3).
- Two data sentences: "These tests show only what happened to these attempts, nothing more." and "Printed as text.".

## Models

Each system is shown on the biggest model it runs, by total parameters in its workload records (`biggest_workload` in `build.py`; the build stops if a system's home row runs a smaller one). Rows are set side by side only within one model, and the models follow each other, biggest first: Llama 4 Maverick (FlashProve), then Llama 3.1 8B (SASH).

## Design

Dark ground, paper text. Violet is the benchmark's own frame: the six properties and page titles, never a value or a state. Green, amber, red and empty mean Yes, Partly, No and Not stated, and appear only in pie slices and state squares. Archivo for display, IBM Plex Mono for data. No cards, shadows or double rules; no helper sentences, taglines or captions.

Each system is a flat pie of six slices, one per property, clockwise from twelve: Weights hidden, Model bound, Whole output proved, Formally verified, Security level, No trusted party. The properties carry no numbers anywhere.

### Overview

1. A plain legend on the violet field: six small key pies, each property's name and question, the states key and the draft-criteria link. Nothing in it reacts to the pointer.
2. One section per model, biggest first: the model's name, its workload in one line, and a sortable table of the systems on it (pie, name, model and pin, then One proof covers, Proof size, Check time, Overhead). Each figure links to its plate on the system page and shows its sample size and range when it has them.
3. **References**, after the models: two rows, plain serving and a rerun by a weights holder, on the same columns. Not sorted.
4. **Not benchmarked yet**: a compact grid, A to Z, of pie, name, models and status.

Pointing at a row's slice with a mouse lifts it (the others keep their ink) and shows its name and state under the pie.

### Sorting

The column heads are the only sort control, and one order applies to every model's table. Each head is a button with a glyph: ↕ idle, ↑ or ↓ when it sorts, a second press reverses. The sorting head is in paper with a rule under it and its cell has `aria-sort`; the order is also named for screen readers ("Proof size, large to small", from the data's direction words). Below 920 px the heads wrap into a strip of the same buttons above the rows.

- The order is kept in the hash: `#sort=proof_size-desc`. The default (System, A to Z) has no hash; an unknown order falls back to it.
- A figure with no number goes last in both directions. Ties fall back to the name.
- Rows move in 200 ms (FLIP), at once under reduced motion.
- Neutral: no rank numbers, medals or ranking words.

Sort keys are computed, never typed: for each row and column, `build.py` takes the raw number from the axis chart that plots that figure (`axes.<axis>.charts[<chart>].views.run.rows[].value`) and multiplies it into one base unit by the chart's declared unit. The printed figure is parsed only to check that the raw number rounds to it. `test_sort_keys.py` checks the keys against hand-computed cases, the unit table, the data's own sorted orders, the model order and the reference figure.

### System pages

The violet band holds the name. Below it, one screen: the pie (200 px) in the middle with each property beside its own slice, slices 1 to 3 on its right and 4 to 6 on its left, top to bottom. Each property shows its name, state and our short reason (left out when it only repeats Not stated). Pointing at a property lifts its slice; pointing at a slice marks its property. Beside the pie, the facts: kind, model, pinned repositories, licence, status, adapter notes. Below 1240 px the facts move under the pie; on phones the pie sits on top with its left-hand and right-hand properties in two columns under it.

Then the figures (four plates with every label: spread, scope, grade, checked, workload, source and caveats; more numbers in a table) and the tamper tests with the control test. The reference page uses the same layout for each reference, with one set of figures.

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

- `build.py`: the pages, the sort keys and the contrast table. `test_sort_keys.py`: the sort keys, the model order, the reference figure and the spread shown on every home figure that stores one.
- `words.css`, `words.js`: style and behaviour, no data.
- `shoot.mjs`: screenshots and checks: no sort control, toggle, tabs, quotes or placeholder marking; one table per model, biggest first, references after them; a static header; row hover without shift; sort order for every column and direction from the heads (missing values last), the hash round-trip and keyboard sorting; overflow at 360 to 1100 px on every page; CLS; the first system name on landing at 390 px; on each system and reference page, a small pie with slices 1 to 3 described on its right and 4 to 6 on its left within the first screen; the cut sentences, ranking words, numbered property names, dead local links, console errors, and axe on every page at 1440 and 390 px.
- `_data/`: `site.json` and `criteria.json`.
- `shots/`: screenshots and `checks.txt`.

## Open

- Each model's table has one row today; sorting shows its value once two systems run the same model.
- The pie's states still come from reading each system's documentation (the criteria in `criteria.json`). Showing them as measured needs checks of our own per property; until then the reason line is ours and the quotes are left out.
- The direction words come from the data generator, which is not in this repository (`_data/site.json` is a frozen snapshot of its output), and mix two patterns ("small to large", "fewer positions first").
