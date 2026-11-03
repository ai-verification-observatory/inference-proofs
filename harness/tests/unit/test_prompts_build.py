"""`iproofs prompts build` (RFC-0003 §Prompt generator corpus-window/1, CLI-3)."""

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry
from iproofs.workloads import load_tokenizer, load_workload, tokenizer_file

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


def build(tmp_path: Path, capsys: pytest.CaptureFixture[str], seed: str) -> dict[str, object]:
    assert cli.main(["prompts", "build", "fake-tiny-ci", "--seed", seed,
                     "--out", str(tmp_path / "prompts.jsonl")]) == 0  # fmt: skip
    out: dict[str, object] = json.loads(capsys.readouterr().out)
    return out


def test_prompts_build_cli_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The digest equals the prompt set a job with that seed records in its manifest."""
    monkeypatch.chdir(ROOT)
    result = build(tmp_path, capsys, "0x1f2e3d4c5b6a7988")
    env = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78"}
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=env)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, replay_seed=0x1F2E3D4C5B6A7988,
                    image="local/x@sha256:" + "0" * 64)  # fmt: skip
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path / "r"), "v0.1")
    manifest = json.loads((runner.run(spec) / "manifest.json").read_text())
    assert result["digest"] == manifest["workload"]["prompt_set_digest"]
    assert (result["count"], result["seed"]) == (6, "0x1f2e3d4c5b6a7988")
    assert len((tmp_path / "prompts.jsonl").read_text().splitlines()) == 6
    decimal = str(0x1F2E3D4C5B6A7988)
    assert build(tmp_path, capsys, decimal)["digest"] == result["digest"]


def test_prompts_build_missing_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real tokenizer file without the [prompts] extra: environment, exit 3."""
    monkeypatch.chdir(ROOT)
    monkeypatch.setitem(sys.modules, "tokenizers", None)  # the extra is not installed
    monkeypatch.setattr("iproofs.workloads.tokenizer_for", load_tokenizer)
    assert cli.main(["prompts", "build", "fake-tiny-ci", "--seed", "0",
                     "--out", str(tmp_path / "p.jsonl")]) == 3  # fmt: skip
    assert "[prompts] extra" in capsys.readouterr().err


def test_prompts_build_bad_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["prompts", "build", "fake-tiny-ci", "--seed", "abc"]) == 2
    assert cli.main(["prompts", "build", "fake-tiny-ci", "--seed", str(2**64)]) == 2


def test_hub_tokenizer_fetched_alone_and_verified(tmp_path: Path) -> None:
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    source = dataclasses.replace(wl.model.source, hub="huggingface", path=None, repo="org/toy")
    wl = dataclasses.replace(wl, model=dataclasses.replace(wl.model, source=source))
    calls: list[list[str]] = []

    def hub(repo: str, rev: str, files: list[str], into: Path, token: str | None) -> None:
        calls.append(files)
        for name in files:
            (into / name).write_bytes((ROOT / "systems/fake/model" / name).read_bytes())

    path = tokenizer_file(ROOT, wl, tmp_path, download=hub)
    assert calls == [["tokenizer.json"]]  # no weights
    assert tokenizer_file(ROOT, wl, tmp_path, download=hub) == path  # cached
    path.write_text("{}")
    with pytest.raises(IProofsError) as e:
        tokenizer_file(ROOT, wl, tmp_path, download=hub)
    assert e.value.kind is ErrorKind.INTEGRITY
