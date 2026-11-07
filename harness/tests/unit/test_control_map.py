"""RFC-0016 OVR-2 control map and OVR-5 run selection (`iproofs.controls`)."""

import json
import re
from pathlib import Path

import pytest

from iproofs.controls import CONTROL_PROPERTY, EXPECTED, runs_read
from iproofs.errors import ErrorKind, IProofsError

ROOT = Path(__file__).resolve().parents[3]
RFC = ROOT / "rfcs/0016-glyph-properties-and-states.md"


def rfc_control_map(text: str = RFC.read_text()) -> dict[str, str | None]:
    """Control id -> property id, parsed from the OVR-2 table and the property headings."""
    ids = dict(re.findall(r"^#### (.+?) \(`(\w+)`\)$", text, re.M))
    section = text.split("### Negative control override", 1)[1].split("\n- OVR-3.", 1)[0]
    rows = re.findall(r"^\| ([CP]\d) \| [^|]+ \| ([^|]+) \|", section, re.M)
    return {c: None if p.strip() == "none" else ids[p.strip()] for c, p in rows}


def test_control_map_matches_rfc() -> None:
    """OVR-2: the code's map equals the RFC table, and covers every shared control."""
    parsed = rfc_control_map()
    assert dict(CONTROL_PROPERTY) == parsed
    assert set(parsed) == set(EXPECTED)
    assert set(parsed.values()) == {"whole_output", "model_bound", None}


def test_control_map_is_read_only() -> None:
    with pytest.raises(TypeError):
        CONTROL_PROPERTY["C5"] = "model_bound"  # type: ignore[index]


# ---------------------------------------------------------------- OVR-5

SYSTEM, CONFIG = "fake", "default"


def release(root: Path, rid: str, freeze: str, runs: list[str], superseded: list[str]) -> None:
    path = root / "releases" / rid / "release.yaml"
    path.parent.mkdir(parents=True)
    lines = [f'release: "{rid}"', f'freeze_date: "{freeze}"', "runs:"]
    lines += [f'  - "{r}"' for r in runs] or ["  []"]
    if superseded:
        lines += ["superseded_runs:"]
        lines += [f'  - {{run_id: "{s}", reason: "fixture"}}' for s in superseded]
    path.write_text("\n".join(lines).replace("runs:\n  []", "runs: []") + "\n")


def run(root: Path, rel: str, *, claim: object = None, replaces: str | None = None) -> str:
    rid = rel.rsplit("/", 1)[1]
    doc = {
        "run_id": rid,
        "claim": {"system": SYSTEM, "configuration": CONFIG} if claim is None else claim,
        "replaces": None if replaces is None else {"run_id": replaces, "reason": "fixture"},
    }
    (root / rel).mkdir(parents=True)
    (root / rel / "run.json").write_text(json.dumps(doc))
    return rel


DATES = {"v0.1": "2026-11-20", "v0.2": "2026-12-20", "v0.3": "2027-01-20"}


def r(n: int, release_id: str = "v0.1") -> str:
    return f"results/{release_id}/fake/{rid(n, release_id)}"


def rid(n: int, release_id: str = "v0.1") -> str:
    return f"{DATES[release_id]}-fake-fake-tiny-ci-ci-cpu-{n}"


def test_runs_read_ovr5(tmp_path: Path) -> None:
    """OVR-5: earlier releases read, later not; superseded, replaced and other claims left out."""
    root = tmp_path
    early = [run(root, r(1)), run(root, r(2)), run(root, r(3), claim=None)]
    other = run(root, r(4), claim={"system": SYSTEM, "configuration": "other"})
    no_claim = run(root, r(5), claim={})
    release(root, "v0.1", "2027-01-10", [*early, other, no_claim], superseded=["2026-11-20-x"])
    fix = run(root, r(1, "v0.2"), replaces=rid(2))
    dropped = run(root, r(2, "v0.2"))
    release(root, "v0.2", "2027-03-10", [fix, dropped, early[0]], superseded=[rid(2, "v0.2")])
    later = run(root, r(1, "v0.3"))
    release(root, "v0.3", "2027-05-10", [later], superseded=[rid(1)])

    assert runs_read(root, "v0.2", SYSTEM, CONFIG) == [early[0], early[2], fix]
    assert runs_read(root, "v0.1", SYSTEM, CONFIG) == early
    assert runs_read(root, "v0.1", SYSTEM, "other") == [other]
    assert runs_read(root, "v0.3", SYSTEM, CONFIG) == [early[2], fix, later]
    assert runs_read(root, None, SYSTEM, CONFIG) == []


def test_runs_read_no_runs_listed(tmp_path: Path) -> None:
    release(tmp_path, "v0.1", "2027-01-10", [], superseded=[])
    assert runs_read(tmp_path, "v0.1", SYSTEM, CONFIG) == []


def test_runs_read_unknown_release(tmp_path: Path) -> None:
    with pytest.raises(IProofsError) as e:
        runs_read(tmp_path, "v9.9", SYSTEM, CONFIG)
    assert e.value.kind is ErrorKind.INTEGRITY


def test_runs_read_unreadable_run_is_environment(tmp_path: Path) -> None:
    """CRIT-13: a listed run directory that cannot be read is an error, never a pass."""
    release(tmp_path, "v0.1", "2027-01-10", [r(1)], superseded=[])
    with pytest.raises(IProofsError) as e:
        runs_read(tmp_path, "v0.1", SYSTEM, CONFIG)
    assert e.value.kind is ErrorKind.ENVIRONMENT
