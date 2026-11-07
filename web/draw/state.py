"""The build's state: the output folder, the view and what `build.setup` reads from it.

Every other module reads these as `S.<name>` (`from . import state as S`), so they see the values
`setup` and `render` set. `build.py` loads this package afresh for every build, so the state of
one build never reaches the next.
"""

import pathlib

# Set by build.setup and build.render (INK, ladder and pairs by inks.check_inks, FACES by
# chrome.load_faces). Nothing is read when the module is imported.
HERE = OG = pathlib.Path()
V: dict = {}
CRIT: dict = {}
PROPS: list = []
CONFIGS: list = []
PROVERS: list = []
PAGE: dict = {}
MODELS: list = []
MODEL_NAME: dict = {}
INK: dict = {}
FACES: list = []
RFC_FILES: dict = {}
REPO_URL = LINK_REF = RFC_REF = crit_sha = ""
ladder: list = []
pairs: list = []
WRITE_TEXT = WRITE_JSON = None
