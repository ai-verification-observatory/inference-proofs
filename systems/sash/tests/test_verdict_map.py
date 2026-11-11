"""RFC-0005 §Verdict normalisation for SASH: `boundary-grid --verify`'s exit status and JSON
(prover/src/boundary.rs at the pin) onto the four verdicts. The JSON documents below are built
by hand from the fields that source names; none is a captured upstream output."""

import json
from pathlib import Path
from types import ModuleType

import pytest
from sash_fixtures import load


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load(tmp_path, monkeypatch)


def grid(*, run: int = 290, accepted: int = 290, chain: bool = True, ids: bool = True) -> str:
    failures = [] if chain else ["B3L7 -> B3L8: residual root differs"]
    tokens = {"all": ids, "mismatches": [] if ids else [{"position": 4100}], "unbacked": []}
    verified = {"run": run, "accepted": accepted, "all": accepted == run}
    return json.dumps({"result": {"all_chain": chain, "failures": failures,
                                  "verified": verified, "tokens": tokens}})  # fmt: skip


def test_all_segments_accepted_and_grid_passed_is_accept(adapter: ModuleType) -> None:
    assert adapter.verdict_of(0, grid(), "grid: done\n") == ("accept", "grid: done")


def test_one_segment_rejected_is_reject(adapter: ModuleType) -> None:
    verdict, line = adapter.verdict_of(1, grid(accepted=289), "B4L9: rejected\n")
    assert (verdict, line) == ("reject", "B4L9: rejected")


@pytest.mark.parametrize("doc", [grid(chain=False), grid(ids=False)])
def test_grid_failure_is_reject(adapter: ModuleType, doc: str) -> None:
    assert adapter.verdict_of(1, doc, "")[0] == "reject"


@pytest.mark.parametrize(
    ("code", "stdout", "stderr"),
    [
        (101, "", "thread 'main' panicked at boundary.rs: --dir: No such file\n"),
        (1, "", "grid: --verify needs --prompt <file>\n"),
        (0, grid(accepted=289), "inconsistent\n"),  # exit 0 with a rejected segment
        (1, grid(), "counts not met\n"),  # exit 1 with nothing failed
        (0, grid(run=0, accepted=0), "nothing verified\n"),
        (0, "not json", "garbled\n"),
    ],
)
def test_any_other_outcome_is_no_verdict_with_the_raw_line(
    adapter: ModuleType, code: int, stdout: str, stderr: str
) -> None:
    verdict, line = adapter.verdict_of(code, stdout, stderr)
    assert verdict == "no_verdict"
    assert line == stderr.strip()


def test_raw_line_is_capped(adapter: ModuleType) -> None:
    assert len(adapter.verdict_of(101, "", "x" * 5000)[1]) == 4096
