"""RFC-0009 §Site: every page of the fixture release, byte for byte (S1 to S9 regressions)."""

import shutil
from pathlib import Path

import pytest

from fixtures.release_tree import build_rich
from iproofs import cli

GOLDEN = Path(__file__).resolve().parent / "site"


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The rich fixture release, frozen, then built into a site."""
    root = tmp_path_factory.mktemp("repo")
    build_rich(root)
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(root)
        assert cli.main(["release", "freeze", "v0.1"]) == 0
        assert cli.main(["site", "build", "--out", str(root / "out")]) == 0
    return root / "out"


def pages(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}  # fmt: skip


def test_site_matches_golden(site: Path, update_golden: bool) -> None:
    if update_golden:
        shutil.rmtree(GOLDEN, ignore_errors=True)
        shutil.copytree(site, GOLDEN)
    built, golden = pages(site), pages(GOLDEN)
    assert sorted(built) == sorted(golden)
    for rel in built:
        assert built[rel] == golden[rel], rel
    kinds = {"index.html", "v0.1/index.html", "v0.1/methodology.html",
             "v0.1/systems/fake.html", "v0.1/workloads/fake-tiny-ci.html"}  # fmt: skip
    assert kinds <= set(built)  # Home, Release, Methodology, System, Workload
