"""The renderer's loader: build.py loads draw/ afresh for every build and leaves nothing behind.

Run from the repository root: uv run pytest web -q
"""

import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

import iproofs.site.view
from iproofs.errors import ErrorKind, IProofsError
from iproofs.site import build, renderer

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent


def test_each_load_is_fresh(site):
    one, two = renderer(ROOT), renderer(ROOT)
    assert one.draw is not two.draw
    assert one.S is not two.S
    for part in one.PARTS:
        assert getattr(one.draw, part) is not getattr(two.draw, part)
    # the session's build ran setup; a new load starts from the empty state
    assert site.build.S.V
    assert one.S.V == {}
    assert not [k for k in sys.modules if k == "_web_draw" or k.startswith("_web_draw.")]


def test_names_of_the_parts_read_through_build():
    loaded = renderer(ROOT)
    assert "SITE_URL" not in vars(loaded)
    assert loaded.SITE_URL is loaded.draw.chrome.SITE_URL
    # a name build.py does not define reads from the first part in PARTS that holds it
    parts = [vars(getattr(loaded.draw, p)) for p in loaded.PARTS]
    names = {n for found in parts for n in found if not n.startswith("__")} - set(vars(loaded))
    for name in names:
        value = next(found[name] for found in parts if name in found)
        if not isinstance(value, ModuleType):
            assert getattr(loaded, name) is value, name
    with pytest.raises(AttributeError):
        _ = loaded.no_such_name


def test_missing_draw_is_a_config_error(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    shutil.copyfile(WEB / "build.py", tmp_path / "web" / "build.py")
    with pytest.raises(RuntimeError, match="no renderer package at"):
        renderer(tmp_path)
    # iproofs site build reports it as a config error, not a traceback
    monkeypatch.setattr(iproofs.site.view, "site_view", lambda root: {})
    with pytest.raises(IProofsError, match="site: no renderer package at") as e:
        build(tmp_path, tmp_path / "out")
    assert e.value.kind is ErrorKind.CONFIG
