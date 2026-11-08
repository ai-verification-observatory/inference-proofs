"""The site the web/ tests read: the placeholder release, frozen and built once per session.

Run from the repository root: `uv run pytest web -q` (pyproject's pytest `pythonpath` makes
`harness/tests/fixtures` importable). Until #146 the deployed pages come from this placeholder
release (`python -m fixtures.placeholder_release --site web`); the tests compare the committed
files in web/ with a fresh build and check the build against hand-computed cases.
"""

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from fixtures.builds import SiteBuild, placeholder_build  # noqa: F401 (a session fixture)
from iproofs.site import renderer
from iproofs.site.view import site_view

WEB = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def site(placeholder_build: SiteBuild) -> SimpleNamespace:  # noqa: F811 (the fixture above)
    """out: a fresh build (the shared, read-only deployed build of fixtures/builds); web: the
    committed pages; view: what the build printed from; build: the renderer, set up on that
    view (for its words and helpers)."""
    out = placeholder_build.out
    view = site_view(placeholder_build.repo)
    build: ModuleType = renderer(placeholder_build.repo)
    build.setup(view, out)
    return SimpleNamespace(out=out, web=WEB, view=view, build=build)
