"""docs/spec/05 §Progress output: stderr lines derived from the records harness.jsonl holds."""

import io
import json
import re
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import InProcessRunner
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}
SHOWN = {"job.state", "proof.released", "verify.result", "job.failed", "job.written"}


def test_progress_lines_match_events(tmp_path: Path) -> None:
    out = io.StringIO()
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64,
                    progress=out, log_level="debug")  # fmt: skip
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    (run_dir,) = runner.run_many(spec, 1)
    records = [json.loads(line) for line in (run_dir / "logs/harness.jsonl").open()]
    shown = [r for r in records if r["event"] in SHOWN]
    lines = out.getvalue().splitlines()
    assert len(lines) == len(shown)  # one line per record, none without a record
    assert all(line.startswith("[rep 1/1] ") for line in lines)
    assert "[rep 1/1] prove    running   00:00:00  proofs 6/6" in lines
    assert "[rep 1/1] verify   proof 6/6 accept" in lines
    assert lines[-1].startswith("[rep 1/1] written  completed")
    released = [r for r in records if r["event"] == "proof.released"]
    assert [r["index"] for r in released] == [1, 2, 3, 4, 5, 6]


def run(tmp_path: Path, *extra: str) -> int:
    argv = ["run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile", "ci-cpu"]
    return cli.main(
        [*extra, *argv, "--repetitions", "1", "--results", str(tmp_path), "--in-process"]
    )


def test_quiet_suppresses_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    assert run(tmp_path / "loud") == 0
    assert "[rep 1/1] verify   proof" in capsys.readouterr().err
    assert run(tmp_path / "quiet", "--quiet") == 0
    assert "[rep" not in capsys.readouterr().err


def test_stdout_unchanged_by_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    outs = []
    for name, extra in (("a", ()), ("b", ("--quiet",))):
        assert run(tmp_path / name, *extra) == 0
        outs.append(re.sub(re.escape(str(tmp_path / name)), "<results>", capsys.readouterr().out))
    assert outs[0] == outs[1]
    assert outs[0].strip().startswith("<results>/v0.1/fake/")
