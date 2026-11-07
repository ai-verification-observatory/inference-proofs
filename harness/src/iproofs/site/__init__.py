"""`iproofs site build`: the public site from the newest frozen release (RFC-0009 §Site).

One generator (#320). `view.site_view` computes every value the pages print from the release
index, `release.yaml`, the claim cards, the run records, the criteria file and
`web/_data/facts.json` (`inputs` reads them; no git call, no clock). `build` hands that view to
the renderer in the tree's `web/build.py`, which draws the pages, search index, preview-card
sources and `vercel.json`, and writes them with the canonical writers of `iproofs.serialize`.
"""

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

from iproofs.errors import ErrorKind, IProofsError
from iproofs.serialize import write_json, write_text
from iproofs.site.inputs import REPOSITORY, maintainer_rows
from iproofs.site.reply import reply_html

__all__ = ["ASSETS", "REPOSITORY", "build", "maintainer_rows", "renderer", "reply_html"]

RENDERER = "web/build.py"
# What the renderer reads from its output folder and does not write: copied there first when the
# site is written anywhere other than the tree's own web/.
ASSETS = ("words.css", "words.js", "fonts", "og/cards.json", "og/*.png")


def renderer(root: Path) -> ModuleType:
    """The tree's `web/build.py`, loaded as a module of its own (no `sys.path` change)."""
    path = root / RENDERER
    spec = importlib.util.spec_from_file_location("iproofs_site_renderer", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"site: no renderer at {RENDERER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_assets(web: Path, out: Path) -> None:
    for pattern in ASSETS:
        for src in sorted(web.glob(pattern)):
            dst = out / src.relative_to(web)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copyfile(src, dst)


def build(root: Path, out: Path) -> list[Path]:
    """Write the site of the newest frozen release under `root` into `out`; returns the pages
    written, sorted. Never removes `out` or a file in it: the renderer fails on a page it no
    longer writes, so a stale page stops the build instead of being deployed."""
    from iproofs.site.view import site_view  # noqa: PLC0415 (view reads the release tree)

    view = site_view(root)
    out.mkdir(parents=True, exist_ok=True)
    if out.resolve() != (root / "web").resolve():
        copy_assets(root / "web", out)
    pages: list[Path] = renderer(root).render(view, out, write_json=write_json,
                                              write_text=write_text)  # fmt: skip
    return pages
