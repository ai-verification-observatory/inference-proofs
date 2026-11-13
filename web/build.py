"""MADE OF WORDS: the renderer of the public site (RFC-0018 §Site).

`iproofs site build` computes every value the pages print into a view
(`iproofs.site.view.site_view`, from the level file, the newest Level 1 release's board file or
one given for a preview, the claim cards and `_data/facts.json`) and calls
`render(view, out, write_json=..., write_text=...)`. The renderer opens no data file and types no
number: every value, label, pin and hash comes from the view. It holds the drawing and the fixed
words the pages print for stored ids (checks, states, causes, scopes, grades, tiers, null
reasons, units). Standard library only.

`render` writes into `out`: the pages (the overview, one per row of the board, the checks page,
the mandate, the scale page, the Learn pages, 404), search.json, the preview-card sources and icon in og/, the @font-face block in words.css,
vercel.json (headers with the inline script's hash, redirects, cache rules) and the contrast
table in README.md when `out` holds one. The static assets (words.css, words.js, fonts/,
og/*.png, og/cards.json) are in `out` before it runs.

This module is the entry point: it reads the view into the build's state (`setup`), checks that
`out` holds no page or card source the build no longer writes (`check_stale`) and writes the
files (`render`). The drawing is in the package draw/ beside it, in this order of imports:
state (what `setup` reads), words (fixed words, numbers as shown), inks (contrast checks), hexagon
(the glyph's geometry), mark (the turnstile, the lockup, the token cells), plots (a system
page's bars and fidelity tracks), chrome (header, footer, page frame, fonts, share tags), overview (the
ladder), pages (system pages, checks, 404), scale (every row on a decade axis), figures and learn (the Learn pages: what they draw,
then their text) and outputs (search.json, vercel.json, og/ sources, the fonts block, the README
table). Every name of those modules reads as `build.<name>` too.
"""

import importlib
import importlib.util
import pathlib
import sys
import types

PARTS = ("state", "words", "inks", "hexagon", "mark", "plots", "chrome", "overview", "pages",
         "scale", "figures", "learn", "outputs")  # fmt: skip


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
    S.REPO_URL, S.LINK_REF = view["repository"], view["link_ref"]
    S.ROWS = [row for rung in view["rungs"] for row in rung["rows"]]
    S.PAGE = {row["page"]: row for row in S.ROWS}
    assert len(S.PAGE) == len(S.ROWS), "two rows share a page"
    learn = draw.learn.slugs()
    assert set(S.PAGE).isdisjoint({"index", "checks", "mandate", "scale", "404", *learn}), (
        "a row's page is a site page"
    )
    # a Learn page must not take the address of a site page, of a redirect or of a system
    taken = {"index", "checks", "mandate", "scale", "404", "system", "criteria", "reference", "release",
             "targets", *S.PAGE, *view["planned"]}  # fmt: skip
    clash = sorted(set(learn) & taken) + sorted({s for s in learn if learn.count(s) > 1})
    if clash:
        raise RuntimeError(
            f"web/learn/index.yaml: the address {clash[0]!r} is taken by another page"
        )
    draw.inks.check_inks()
    draw.chrome.load_faces()
    draw.mark.load_wordmark()


def check_stale():
    """The build's pages and card sources are the only ones in `out`: a page it no longer writes
    would still be deployed (vercel.json copies *.html). Checked before anything is written;
    RuntimeError, which `iproofs site build` reports as a config error (not an assert, which
    `python -O` drops)."""
    c = draw.chrome
    pages = {c.file_of("/"), *(c.file_of(f"/{p}") for p in S.PAGE), c.file_of(c.CHECKS_PAGE),
             c.file_of(c.MANDATE_PAGE), c.file_of(c.SCALE_PAGE), *(c.file_of(f"/{p}") for p in draw.learn.slugs()),
             S.HERE / "404.html"}  # fmt: skip
    stale = sorted(q.name for q in set(S.HERE.glob("*.html")) - pages)
    if stale:
        raise RuntimeError(f"pages the build no longer writes: {stale}")
    cards = sorted({q.stem for q in S.OG.glob("*.html")} - {"icon", "icon-32", "home", *S.PAGE})
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
    for pid in S.PAGE:
        pages[file_of(f"/{pid}")] = draw.pages.build_system(pid)
    pages[file_of(draw.chrome.CHECKS_PAGE)] = draw.pages.build_checks()
    pages[file_of(draw.chrome.MANDATE_PAGE)] = draw.pages.build_mandate()
    pages[file_of(draw.chrome.SCALE_PAGE)] = draw.scale.build_scale()
    for address, text in draw.learn.build_all().items():
        pages[file_of(address)] = text
    pages[S.HERE / "404.html"] = draw.pages.build_404()
    if set(pages) != expected:
        raise RuntimeError(f"check_stale lists {sorted(q.name for q in expected)}, the build "
                           f"writes {sorted(q.name for q in pages)}")  # fmt: skip
    for path, text in pages.items():
        write_text(path, text)
    write_json(S.HERE / "vercel.json", draw.outputs.vercel_json())
    draw.outputs.write_readme()
    return sorted(pages)
