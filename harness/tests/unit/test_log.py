import io
import json
import re
from pathlib import Path

import pytest

from iproofs.errors import IProofsError
from iproofs.log import DEFAULT_LEVEL, Event, JsonlLogger

ROOT = Path(__file__).resolve().parents[3]
REQUIRED = {"ts", "mono_ns", "level", "event", "job", "step"}


def catalogue() -> dict[str, str]:
    """Event name -> level, parsed from the docs/spec/05 events catalogue table."""
    text = (ROOT / "docs/spec/05-observability.md").read_text()
    table = text.split("## Events catalogue", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([a-z_.]+)` \| (\w+) \|", table, flags=re.M)
    return dict(rows)


def test_every_catalogue_event_is_a_constant() -> None:
    assert catalogue() == {str(e): DEFAULT_LEVEL[e] for e in Event}


def test_log_event_format() -> None:
    out = io.StringIO()
    logger = JsonlLogger(out, level="debug")
    logger.log(
        Event.STEP_END,
        job="2026-11-03-fake-fake-tiny-ci-ci-cpu-1",
        step="prove",
        exit_code=0,
        seconds=4.812,
    )
    logger.log(Event.RUNNER_START, harness_version="0.1.0", argv=["iproofs", "run"])
    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert set(record) >= REQUIRED
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", record["ts"])
        assert "\n" not in line
    first = json.loads(lines[0])
    assert (first["event"], first["level"], first["step"], first["exit_code"]) == (
        "step.end",
        "info",
        "prove",
        0,
    )


def test_unknown_event_rejected() -> None:
    with pytest.raises(IProofsError, match="unknown log event"):
        JsonlLogger(io.StringIO()).log("step.started")


def test_every_line_passes_redactor() -> None:
    seen: list[str] = []

    def redactor(line: str) -> str:
        seen.append(line)
        return line.replace("SECRET", "[redacted]")

    out = io.StringIO()
    logger = JsonlLogger(out, redactor=redactor)
    logger.log(Event.JOB_FAILED, kind="adapter", message="token SECRET leaked", exit_code=1)
    assert len(seen) == 1
    assert "SECRET" in seen[0]
    assert "SECRET" not in out.getvalue()
    assert "[redacted]" in out.getvalue()


def test_mono_ns_monotonic() -> None:
    out = io.StringIO()
    logger = JsonlLogger(out)
    for _ in range(50):
        logger.log(Event.JOB_STATE, **{"from": "a", "to": "b"})
    stamps = [json.loads(line)["mono_ns"] for line in out.getvalue().splitlines()]
    assert stamps == sorted(stamps)


def test_level_filter() -> None:
    out = io.StringIO()
    logger = JsonlLogger(out, level="warning")
    logger.log(Event.PROOF_RELEASED, proof_id="p", release_mono_ns=1)  # debug
    logger.log(Event.STEP_START, subcommand="prove", image="x", timeout_s=1)  # info
    logger.log(Event.SAMPLER_GAP, kind="nvml", gap_ms=200)  # warning
    assert [json.loads(line)["event"] for line in out.getvalue().splitlines()] == ["sampler.gap"]


def test_bad_level_rejected() -> None:
    with pytest.raises(IProofsError, match="unknown log level"):
        JsonlLogger(io.StringIO(), level="trace")
