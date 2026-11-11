"""The sites the web/ tests read, built once per session from this tree: one from the example
board file (`harness/tests/fixtures/board/v1.0-example.json`, invented values) and one with no
board, as the committed site is built while no Level 1 release has one.

Run from the repository root: `uv run pytest web -q`.
"""

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from iproofs.site import build, renderer
from iproofs.site.view import site_view

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
BOARD = ROOT / "harness/tests/fixtures/board/v1.0-example.json"


@pytest.fixture(scope="session")
def board_site(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """out: the site built from the example board; board: that file; build: the renderer, set
    up on the same view (for its number words)."""
    out = tmp_path_factory.mktemp("board-site")
    build(ROOT, out, BOARD)
    module: ModuleType = renderer(ROOT)
    module.setup(site_view(ROOT, BOARD), out)  # reads words.css and the fonts, writes nothing
    board: dict[str, Any] = json.loads(BOARD.read_text())
    return SimpleNamespace(out=out, board=board, build=module)


@pytest.fixture(scope="session")
def empty_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The site with no board: every rung of the level file not run yet."""
    out = tmp_path_factory.mktemp("empty-site")
    pages = build(ROOT, out) if not list(ROOT.glob("releases/v1.*/board.json")) else None
    if pages is None:
        pytest.skip("a Level 1 release has a board file; the committed site is built from it")
    return out
