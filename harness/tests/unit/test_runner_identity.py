"""The declared runner in every manifest."""

import json
from pathlib import Path

import pytest

from iproofs import cli

ROOT = Path(__file__).resolve().parents[3]


def run(tmp_path: Path, *extra: str) -> int:
    argv = ["run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile", "ci-cpu"]
    argv += ["--repetitions", "1", "--results", str(tmp_path), "--in-process", *extra]
    return cli.main(argv)


def test_runner_recorded_in_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    extra = ["--runner", "rr", "--runner-org", "Lab R", "--affiliated", "fake-broken"]
    assert run(tmp_path, *extra, "--affiliated", "fake-broken") == 0
    (manifest,) = tmp_path.glob("*/fake/*/manifest.json")
    runner = json.loads(manifest.read_text())["runner"]
    assert runner == {
        "handle": "rr",
        "organisation": "Lab R",
        "affiliated_systems": ["fake-broken"],
    }


def test_environment_is_the_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_RUNNER", "env-handle")
    monkeypatch.setenv("IPROOFS_RUNNER_ORG", "Env Org")
    monkeypatch.setenv("IPROOFS_RUNNER_SYSTEMS", "fake")
    assert run(tmp_path, "--runner-org", "Flag Org") == 0
    (manifest,) = tmp_path.glob("*/fake/*/manifest.json")
    runner = json.loads(manifest.read_text())["runner"]
    assert runner == {
        "handle": "env-handle",
        "organisation": "Flag Org",
        "affiliated_systems": ["fake"],
    }


def test_unknown_affiliated_system_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    assert run(tmp_path, "--affiliated", "no-such-system") != 0
    assert not list(tmp_path.rglob("run.json"))  # refused before any job starts
