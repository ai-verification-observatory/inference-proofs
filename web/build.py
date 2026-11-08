"""MADE OF WORDS: the renderer of the public site (RFC-0009 §Site).

`iproofs site build` computes every value the pages print into a view
(`iproofs.site.view.site_view`, from the newest frozen release, the claim cards, the criteria
file and `_data/facts.json`) and calls `render(view, out, write_json=..., write_text=...)`. The
renderer opens no data file and types no number: every value, label, pin and hash comes from the
view. It holds the drawing and the fixed words the pages print for stored values (scope, grade,
tier, null reasons, units, states, families), as RFC-0009 S2 allows. Standard library only.

`render` writes into `out`: the pages (index, one per system, reference, criteria, release,
sponsors and conflicts, targets when the release evaluates one, 404),
search.json, the preview-card sources and icon in og/, the @font-face block in words.css,
vercel.json (headers with the inline script's hash, redirects, cache rules) and the contrast
table in README.md when `out` holds one. The static assets (words.css, words.js, fonts/,
og/*.png, og/cards.json) are in `out` before it runs. It computes pie geometry, the contrast of
each ink and the content hashes that version words.css, words.js and the pictures.

This module is the entry point: it reads the view into the build's state (`setup`), checks that
`out` holds no page or card source the build no longer writes (`check_stale`) and writes the
files (`render`). The drawing is in the package draw/ beside it, in this order of imports:
state (what `setup` reads), words (fixed words, numbers as shown), inks (contrast checks), hexagon
(the glyph's geometry), plates (criteria rows, text helpers, one configuration's figures), claims
(a card's validated claims, the card in full, its quality gap and the agreement rate), chrome
(header, footer, page frame, fonts, share tags), overview (index.html), pages (system, reference,
criteria and 404 pages), release (the release, sponsors and conflicts, and targets pages) and outputs (search.json, vercel.json, og/ sources, the fonts block, the
README table). Every name of those modules reads as `build.<name>` too.
"""

import importlib
import importlib.util
import json
import pathlib
import re
import sys
import types

PARTS = (
    "state",
    "words",
    "inks",
    "hexagon",
    "plates",
    "claims",
    "chrome",
    "overview",
    "pages",
    "release",
    "outputs",
)


def _load_draw():
    """The package draw/, loaded afresh under the name `_web_draw` and removed from sys.modules
    once its modules are in. Nothing is looked up on sys.path, so the build runs its own tree's
    code (under `python -I` as well, where a script's folder is not on sys.path), and the state
    of the parts is new for every load of this module, as `iproofs.site.renderer` loads one per
    build. Loads run one after another: two at once (threads) would share `_web_draw`. A missing
    draw/ raises RuntimeError, which `iproofs site build` reports as a config error."""
    folder = pathlib.Path(__file__).resolve().with_name("draw")
    if not (folder / "__init__.py").is_file():
        raise RuntimeError(f"no renderer package at {folder}")
    name = "_web_draw"
    spec = importlib.util.spec_from_file_location(
        name, folder / "__init__.py", submodule_search_locations=[str(folder)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no renderer package at {folder}")
    try:
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
        for part in PARTS:
            importlib.import_module(f"{name}.{part}")
        return package
    finally:
        for k in [k for k in sys.modules if k == name or k.startswith(f"{name}.")]:
            del sys.modules[k]


draw = _load_draw()
S = draw.state


def __getattr__(name: str) -> object:
    """A name of the parts as `build.<name>` (the web tests read them so); the state first, so a
    value `setup` set is the one returned."""
    if not name.startswith("__"):
        for part in PARTS:
            found = vars(getattr(draw, part))
            if name in found and not isinstance(found[name], types.ModuleType):
                return found[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ------------------------------------------------------------------ render


def setup(view, out):
    """Read the view into the build's state (draw/state.py) and run the checks the drawing rests on."""
    S.HERE = pathlib.Path(out)
    S.OG = S.HERE / "og"
    S.V = view
    S.CRIT = view["criteria"]
    S.PROPS = [p for pid in S.CRIT["order"] for p in S.CRIT["properties"] if p["id"] == pid]
    S.CONFIGS = view["configurations"]
    S.PROVERS = [c for c in S.CONFIGS if c["kind"] == "prover"]
    S.PAGE = {sid: f"/{sid}" for sid in view["orders"]["benchmarked"]}
    S.REPO_URL, S.LINK_REF = view["repository"], view["link_ref"]
    S.RFC_REF = view["release"]["rfc_commit"]  # the methodology the release was frozen under
    S.RFC_FILES = {f[:4]: f for f in view["rfcs"] if re.match(r"\d{4}-", f)}
    S.crit_sha = S.CRIT["sha256"].removeprefix("sha256:")
    S.MODEL_NAME = {d: view["facts"]["models"][d]["name"]
                    for d in {c["workload"]["model"]["digest"] for c in S.CONFIGS}}  # fmt: skip
    assert len(set(S.MODEL_NAME.values())) == len(S.MODEL_NAME), "two models share a name"
    S.MODELS = draw.overview.models_by_size(S.PROVERS, S.MODEL_NAME)
    text = json.dumps(S.CRIT, ensure_ascii=False) + json.dumps(view["facts"], ensure_ascii=False)
    for k in draw.plates.PHRASES:
        assert k in text, f"PHRASES: {k!r} no longer in the criteria or facts file"
    # one state vocabulary (RFC-0016 §States): the words the pages print are the file's
    words = {k: v["word"] for k, v in S.CRIT["states"].items()}
    assert words == draw.words.STATE_WORD, f"state words {words} differ from the pages'"
    for rid, row in S.CRIT["rows"].items():
        assert row["family"] in draw.words.FAMILY_WORD, (
            f"{rid}: no words for family {row['family']!r}"
        )
    draw.inks.check_inks()
    draw.hexagon.check_lifts()
    draw.chrome.load_faces()


def check_stale():
    """The build's pages and card sources are the only ones in `out`: a page it no longer writes
    would still be deployed (vercel.json copies *.html). Checked before anything is written;
    RuntimeError, which `iproofs site build` reports as a config error (not an assert, which
    `python -O` drops)."""
    c = draw.chrome
    pages = {c.file_of("/"), *(c.file_of(p) for p in S.PAGE.values()), c.file_of(c.REF_PAGE),
             c.file_of(c.CRIT_PAGE), c.file_of(c.RELEASE_PAGE), c.file_of(c.SPONSORS_PAGE),
             S.HERE / "404.html"}  # fmt: skip
    if c.has_targets():
        pages.add(c.file_of(c.TARGETS_PAGE))
    stale = sorted(q.name for q in set(S.HERE.glob("*.html")) - pages)
    if stale:
        raise RuntimeError(f"pages the build no longer writes: {stale}")
    cards = sorted({q.stem for q in S.OG.glob("*.html")} - {"icon", "home", *S.PAGE})
    if cards:
        raise RuntimeError(f"card sources the build no longer writes, in og/: {cards}")
    return pages


def render(view, out, *, write_json, write_text):
    """Write the site for `view` into `out` (module docstring); returns the pages written."""
    S.WRITE_TEXT, S.WRITE_JSON = write_text, write_json
    setup(view, out)
    expected = check_stale()
    draw.outputs.write_font_faces()
    draw.outputs.write_cards()
    # before the pages: they link it by its hash
    write_json(S.HERE / "search.json", {"entries": draw.outputs.search_entries()})
    file_of = draw.chrome.file_of
    pages = {file_of("/"): draw.overview.build_index()}
    for sid, path in S.PAGE.items():
        pages[file_of(path)] = draw.pages.build_system(sid)
    pages[file_of(draw.chrome.REF_PAGE)] = draw.pages.build_reference()
    pages[file_of(draw.chrome.CRIT_PAGE)] = draw.pages.build_criteria()
    pages[file_of(draw.chrome.RELEASE_PAGE)] = draw.release.build_release()
    pages[file_of(draw.chrome.SPONSORS_PAGE)] = draw.release.build_sponsors()
    if draw.chrome.has_targets():
        pages[file_of(draw.chrome.TARGETS_PAGE)] = draw.release.build_targets()
    pages[S.HERE / "404.html"] = draw.pages.build_404()
    if set(pages) != expected:
        raise RuntimeError(f"check_stale lists {sorted(q.name for q in expected)}, the build "
                           f"writes {sorted(q.name for q in pages)}")  # fmt: skip
    for path, text in pages.items():
        write_text(path, text)
    write_json(S.HERE / "vercel.json", draw.outputs.vercel_json())
    draw.outputs.write_readme()
    return sorted(pages)
