"""The build's state: the output folder, the view and what `build.setup` reads from it.

Every other module reads these as `S.<name>` (`from . import state as S`), so they see the values
`setup` and `render` set. `build.py` loads this package afresh for every build, so the state of
one build never reaches the next.
"""

import pathlib

# Set by build.setup and build.render (INK, ladder and pairs by inks.check_inks, FACES by
# chrome.load_faces, WORDMARK by mark.load_wordmark). Nothing is read when the module is imported.
HERE = OG = pathlib.Path()
V: dict = {}
ROWS: list = []  # every row of the board, rung by rung (largest model first), in board order
PAGE: dict = {}  # page id -> its row
INK: dict = {}
FACES: list = []
WORDMARK: dict = {}
REPO_URL = LINK_REF = ""
ladder: list = []
pairs: list = []
WRITE_TEXT = WRITE_JSON = None
