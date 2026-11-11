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

The build writes the pages, 404.html, search.json, vercel.json, the card sources in og/, the fonts block in words.css and the contrast table below; `--out DIR` writes a complete site elsewhere (static assets copied). It never deletes a file: a page it no longer writes stops the build. `python3 -I serve.py` serves this folder at http://127.0.0.1:4440/ under `vercel.json`'s rules; `PLAYWRIGHT_MODULE=<path to playwright/index.mjs> node og.mjs` renders the card sources to og/*.png (then rebuild, so the pages name the new pictures).

## Deploy

Vercel serves this folder (Root Directory `web`) as committed: `buildCommand` copies the pages, `words.css`, `words.js`, `search.json`, the pictures and the fonts into `public/`. The build writes `vercel.json` (redirects, a Content-Security-Policy allowing the one inline script by its sha256, cache rules). `.github/workflows/site.yml` rebuilds the pages on every change to an input and fails if any file under `web/` differs from what the build writes.

## Data

`iproofs site build` reads `levels/L1.yaml`, the newest Level 1 release's `releases/<release>/board.json` (schema `board/1`; or the file `--board` names), the claim cards `systems/<system>/claim.yaml` and `_data/facts.json` (schema `site-facts/1`: names, licences, and each system's one fixed reason when it has no row, SI-4). With no Level 1 board, every rung of the level file is drawn as not run yet. `iproofs.site` turns these into one view with no git call and no clock; the renderer (`build.py` and `draw/`) draws that view and opens no data file. Every printed figure is a `quantity/1` value of the board file, printed at four significant digits in a reading unit, with its scope and n under it and its labels and record (the board file and JSON Pointer) in its title (AGENTS.md rule 2). The renderer types no number. `_data/criteria.json` (RFC-0016) no longer drives the site; no figure of v0.1 is printed (SI-5).

## Design

Dark ground, paper text, violet for the frame (the band, page titles), never a value or a state. The glyph is the hex asterisk: six triangles in a point-top hexagon, one per check in RFC-0018's order, clockwise from twelve (Run, Model, Prompt, Reply, No weight file, Fidelity). Green is held, red is failed, an outline only is undecided (CH-7). It never carries a state word or a number; on a system page it is drawn once, large, each check's name in its triangle. In one colour it is the logo and the icon.

- Overview: the frontier headline on the violet band (the largest model a system passed on, the system, its multiple, its position among the systems run on that model), then one section per model, largest first: its head (publisher, total parameters, the request, the serving baseline), then its rows in the board's order (position and count, glyph, name, multiple of serving, session cost per reply, check time per reply, KL). Nothing re-sorts. Under the first model, SI-2's line. Then the systems not run, A to Z, each with its reason.
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
| black text on violet (`#0b0b0c` on `#c45cff`) | 5.92:1 |
| violet text on ground (`#c45cff` on `#0b0b0c`) | 5.92:1 |
| ground text on red (`#0b0b0c` on `#e03c44`) | 4.59:1 |
| ground text on amber (`#0b0b0c` on `#e49921`) | 8.32:1 |
| ground text on green (`#0b0b0c` on `#6ffeb7`) | 15.49:1 |
<!-- /ladder -->

## Files

- `build.py`: the renderer's entry point (`setup`, `check_stale`, `render`); it loads `draw/` afresh for every build. `serve.py`: the local preview.
- `draw/`: `state.py` (what `setup` reads), `words.py` (fixed words for stored ids, numbers in reading units, the checks' definitions), `inks.py` (contrast checks), `hexagon.py` (the glyph), `chrome.py` (header, search field, footer, page frame, share tags), `overview.py` (the ladder), `pages.py` (system pages, checks, 404), `outputs.py` (search.json, vercel.json, og/ sources, the fonts block, the table below).
- `conftest.py`, `test_site.py`: the site built from `harness/tests/fixtures/board/v1.0-example.json` (invented values) and with no board.
- `words.css`, `words.js`: style and behaviour (the band, search), no data. `fonts/`: the font files and licences. `og/`: the card sources and pictures. `_data/`: `facts.json` and `criteria.json`.
