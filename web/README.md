# The public site

The public site at www.inferenceproofs.ai, its design named "Made of words", served with `noindex`. The rules it follows are RFC-0018 §Site (SI-1 to SI-6).

Pages, written by `iproofs site build` and served at clean addresses: `/` (the ladder), one page per row of the board (`/<system>`, or `/<system>-<model>` for a system on more than one model), `/checks` (the six checks, the order rule, what is not tested) and the 404 page. Addresses of the earlier site (`/criteria`, `/reference`, `/release`, a level system with no page yet) redirect.

## Build and check

From the repository root:

```
uv run iproofs site build                                   # into web/, from the newest releases/v1.*/board.json, or the level file alone
uv run iproofs site build --board PATH --out DIR            # a preview from a given board file
uv run pytest web -q                                        # figures, states and order against the board file
```

The build writes the pages, 404.html, search.json, vercel.json, the card sources in og/, the fonts block in words.css and the contrast table below; `--out DIR` writes a complete site elsewhere (static assets copied). It never deletes a file: a page it no longer writes stops the build. `python3 -I serve.py` serves this folder at http://127.0.0.1:4440/ under `vercel.json`'s rules; `PLAYWRIGHT_MODULE=<path to playwright/index.mjs> node og.mjs` renders the card sources to og/*.png (`OG_CHANNEL=chrome` runs an installed Chrome instead of Playwright's own browser; then rebuild, so the pages name the new pictures). When the display font file changes, `<python with fonttools and uharfbuzz> -I wordmark.py` redraws the wordmark's outlines from it (`fonts/wordmark.json`); the build stops while they name another file.

## Deploy

Vercel serves this folder (Root Directory `web`) as committed: `buildCommand` copies the pages, `words.css`, `words.js`, `search.json`, the pictures and the fonts into `public/`. The build writes `vercel.json` (redirects, a Content-Security-Policy allowing the one inline script by its sha256, cache rules). `.github/workflows/site.yml` rebuilds the pages on every change to an input and fails if any file under `web/` differs from what the build writes.

## Data

`iproofs site build` reads `levels/L1.yaml`, the newest Level 1 release's `releases/<release>/board.json` (schema `board/1`; or the file `--board` names), the claim cards `systems/<system>/claim.yaml` and `_data/facts.json` (schema `site-facts/1`: names, licences, and each system's one fixed reason when it has no row, SI-4). With no Level 1 board, every rung of the level file is drawn as not run yet. `iproofs.site` turns these into one view with no git call and no clock; the renderer (`build.py` and `draw/`) draws that view and opens no data file. Every printed figure is a `quantity/1` value of the board file, printed at four significant digits in a reading unit, with its scope and n under it and its labels and record (the board file and JSON Pointer) in its title (AGENTS.md rule 2). The renderer types no number. `_data/criteria.json` (RFC-0016) no longer drives the site; no figure of v0.1 is printed (SI-5).

## Design

The name is set as a formula, INFERENCE ⊢ PROOFS: capitals in Big Shoulders Display 900 (in outline, `fonts/wordmark.json`), the mark between the two words at cap height. The mark is the turnstile ⊢ on a grid of 20 by 15 units (1 unit = cap height / 15): a solid stem 3 units wide, and on its centre line three square cells of 5 units with gaps of 1, the first joined to the stem. In the lockup it stands 4 units after the E and 3 before the P. Below 32 px it is redrawn on whole pixels (13 by 9 px at 16, doubled at 32). It is the header's logo, the icon (`og/icon.svg`, the touch icon and the 32 px PNG: the mark in ground ink on cobalt) and a page's mark in search results. `draw/mark.py` draws all of it.

Dark ground `#0b0b0c`, paper text `#f1efe9`, muted `#9b978e`, rules `#6f6a62`, and one flat cobalt `#5b7bff` for the benchmark's own frame: the band (black type on it), the mark, the stems, focus and the current page; never a value or a state. No gradient, glow or shadow. Names and titles are set in Big Shoulders Display (800, 900); every label and figure in Martian Mono (400 to 600, width 87.5). Both are served from `fonts/` with their licences (`OFL-BigShoulders.txt`, `OFL-MartianMono.txt`).

The stem is a cobalt bar at the left edge from which rows come off. On the overview one stem runs down from the band, carrying the rungs; every row's rule starts at it. Each section of rows on the other pages has its own, and each column of the systems not run. A band with a title only has none.

The glyph is a row's state: five petals in a point-top pentagon, clockwise from twelve (RFC-0018 §The glyph), green, amber or red filled, hollow an outline only. It never carries a state word or a number; on a system page it is drawn once, large, each petal's name in its triangle, and on the checks page as the key, in cobalt.

- Overview: the frontier headline on the cobalt band (the largest model a system passed on, the system, its multiple, its position among the systems run on that model), then one section per model, largest first: its head (publisher, total parameters, the request, the serving baseline), then its rows in the board's order (position and count, glyph, name, multiple of serving, session cost per reply, check time per reply, KL). Nothing re-sorts. Under the first model, SI-2's line. Then the systems not run, A to Z, each with its reason.
- System page: the glyph and a ruled table of the six checks (state, cause, evidence), the sessions (each counted session's steady m and session value; incomplete sessions with exit code and last line), the cost parts, fidelity beside the model's controls (the bar marked), and the publisher's statements quoted from its claim card at the pin, labelled as its words.
- Checks page: what holds and fails each check, the undecided causes, the order rule and what is not tested, from RFC-0018.

## Inks and contrast (computed by the build, `draw/inks.py`)

<!-- ladder -->
| State | Ink | Luminance | Contrast on the ground `#0b0b0c` | Step from the state below |
|---|---|---|---|---|
| red | `#e03c44` | 0.195 | 4.59:1 | 4.59:1 |
| amber | `#e49921` | 0.394 | 8.32:1 | 1.81:1 |
| green | `#6ffeb7` | 0.777 | 15.49:1 | 1.86:1 |

| Pair | Contrast |
|---|---|
| paper text on ground (`#f1efe9` on `#0b0b0c`) | 17.11:1 |
| muted text on ground (`#9b978e` on `#0b0b0c`) | 6.76:1 |
| black text on cobalt (`#0b0b0c` on `#5b7bff`) | 5.36:1 |
| cobalt text on ground (`#5b7bff` on `#0b0b0c`) | 5.36:1 |
| ground text on red (`#0b0b0c` on `#e03c44`) | 4.59:1 |
| ground text on amber (`#0b0b0c` on `#e49921`) | 8.32:1 |
| ground text on green (`#0b0b0c` on `#6ffeb7`) | 15.49:1 |
<!-- /ladder -->

## Files

- `build.py`: the renderer's entry point (`setup`, `check_stale`, `render`); it loads `draw/` afresh for every build. `serve.py`: the local preview.
- `draw/`: `state.py` (what `setup` reads), `words.py` (fixed words for stored ids, numbers in reading units, the checks' definitions), `inks.py` (contrast checks), `hexagon.py` (the glyph), `mark.py` (the turnstile, the lockup), `chrome.py` (header, search field, footer, page frame, share tags), `overview.py` (the ladder), `pages.py` (system pages, checks, 404), `outputs.py` (search.json, vercel.json, og/ sources, the fonts block, the table below).
- `conftest.py`, `test_site.py`: the site built from `harness/tests/fixtures/board/v1.0-example.json` (invented values) and with no board.
- `words.css`, `words.js`: style and behaviour (search), no data. `fonts/`: the font files, their licences, `faces.json` and the wordmark's outlines. `wordmark.py`: writes those outlines. `og/`: the card sources and pictures. `_data/`: `facts.json` and `criteria.json`.
