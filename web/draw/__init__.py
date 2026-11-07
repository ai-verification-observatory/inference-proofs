"""The parts of the site's renderer, one module per job; `build.py` beside this folder is the
entry point. `build.py` loads this package afresh for every build, under the name `_web_draw`,
and removes it from sys.modules once loaded, so its modules import one another only relatively
and never through sys.path.
"""
