"""The site the web/ tests read: the placeholder release, frozen and built once per session.

Run from the repository root: `uv run pytest web -q` (pyproject's pytest `pythonpath` makes
`harness/tests/fixtures` importable). Until #146 the deployed pages come from this placeholder
release (`python -m fixtures.placeholder_release --site web`); the tests compare the committed
files in web/ with a fresh build and check the build against hand-computed cases.
"""

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from fixtures.placeholder_release import build_site
from iproofs.site import renderer
from iproofs.site.view import site_view

WEB = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def site(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """out: a fresh build; web: the committed pages; view: what the build printed from;
    build: the renderer, set up on that view (for its words and helpers)."""
    root = tmp_path_factory.mktemp("site")
    out = build_site(root / "repo", root / "out")
    view = site_view(root / "repo")
    build: ModuleType = renderer(root / "repo")
    build.setup(view, out)
    return SimpleNamespace(out=out, web=WEB, view=view, build=build)
