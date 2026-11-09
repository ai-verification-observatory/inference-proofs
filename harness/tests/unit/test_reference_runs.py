"""RFC-0015 §Steps per job: TC-REF-SKIP, TC-REF-TOKENS, TC-PROMPTS-FROM."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs import cli

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "ghcr.io/example/fake@sha256:" + "a" * 64


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake systems plus `fake-ref` and `fake-recompute`, the fake entrypoint declared as
    a serving and a recompute reference system."""
    repo = tmp_path / "repo"
    copied = [
        "schema",
        "systems/fake",
        "systems/fake-broken",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
        "uv.lock",
        "pyproject.toml",
    ]
    for rel in copied:
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    for name, role in (("fake-ref", "serve"), ("fake-recompute", "recompute")):
        reference_system(repo, name, role)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0.02")  # releases apart, so steady is observable
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", "64168df9fd0706dfd955b6795fa6f535872dff78")
    return repo


def reference_system(repo: Path, name: str, role: str) -> None:
    ref = repo / "systems" / name
    ref.mkdir()
    shutil.copy(ROOT / "systems/fake/entrypoint", ref / "entrypoint")
    system = {
        "schema": "system/1",
        "name": name,
        "kind": "reference",
        "reference_role": role,
        "contract": "adapter/1",
        "engine": {"name": "fake", "version": "1", "image": IMAGE},
        "workloads": [
            {"id": "fake-tiny-ci", "precision_used": "int8", "precision_substitution": None,
             "engine_args": []} | ({"load_point": "matched", "gpus": 1} if role == "serve" else {})
        ],
        "deterministic_proofs": True,
        "incremental_proofs": True,
        "forbidden_flags": [],
    }  # fmt: skip
    (ref / "system.yaml").write_text(yaml.safe_dump(system))


def run(system: str, results: Path, *extra: str) -> int:
    argv = ["--quiet", "run", "--system", system, "--workload", "fake-tiny-ci"]
    argv += ["--profile", "ci-cpu", "--repetitions", "1", "--results", str(results)]
    return cli.main([*argv, "--in-process", *extra])


def only_run(results: Path, system: str) -> Path:
    (d,) = (results / "v0.1" / system).iterdir()
    return d


def test_reference_skips_commit_and_verify(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-REF-SKIP and TC-REF-TOKENS."""
    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    # a reference system is held to its profile; this host is not ci-cpu, so allow it here
    assert run("fake-ref", repo / "results", "--allow-nonconforming") == 0
    d = only_run(repo / "results", "fake-ref")
    doc = json.loads((d / "run.json").read_text())
    manifest = json.loads((d / "manifest.json").read_text())
    assert doc["status"] == "completed", doc["failure"]
    assert doc["system_kind"] == "reference"
    events = [json.loads(line) for line in (d / "logs/harness.jsonl").open()]
    skipped = [e["to"] for e in events if e["event"] == "job.state" and e.get("skipped")]
    assert skipped == ["commit", "verify"]
    m = doc["metrics"]
    for metric in ("commit_seconds", "whole_wall_seconds"):
        assert (m[metric]["value"], m[metric]["null_reason"]) == (None, "not_applicable")
    assert m["prove_session_seconds"]["value"] > 0
    assert m["prove_steady_seconds"]["value"] > 0
    assert "proof_bytes" not in m  # outputs, not proofs
    assert "verify_seconds" not in m
    assert m["tokens_covered_total"]["value"] == 48  # fake's window rule: 8 per release, 6
    assert manifest["commitment"] is None
    assert not (d / "controls.json").exists()


def test_prompts_from_replays_the_source_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-PROMPTS-FROM: the same prompt digest as the source run; the source is recorded."""
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    assert run("fake", repo / "replay", "--prompts-from", str(source)) == 0
    replay = only_run(repo / "replay", "fake")
    a, b = (json.loads((x / "manifest.json").read_text()) for x in (source, replay))
    assert a["workload"]["prompt_set_digest"] == b["workload"]["prompt_set_digest"]
    assert (a["prompts_from"], b["prompts_from"]) == (None, source.name)


def test_prompts_from_refuses_another_version_or_a_failed_run(repo: Path, tmp_path: Path) -> None:
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    other = tmp_path / "other"
    shutil.copytree(source, other)
    manifest = json.loads((other / "manifest.json").read_text())
    manifest["workload"]["version"] = 2
    (other / "manifest.json").write_text(json.dumps(manifest))
    assert run("fake", repo / "x", "--prompts-from", str(other)) == 2  # config
    failed = tmp_path / "failed"
    shutil.copytree(source, failed)
    doc = json.loads((failed / "run.json").read_text())
    (failed / "run.json").write_text(json.dumps({**doc, "status": "failed"}))
    assert run("fake", repo / "y", "--prompts-from", str(failed)) == 2


def _in_process_any(  # type: ignore[no-untyped-def]
    system_file: Path, in_process: bool, image_id: str | None = None, *, hosted: bool = False
):
    """The CLI runs only test systems in process; this test runs the reference fixture so."""
    from iproofs.adapter import InProcessRunner  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415

    registry = SchemaRegistry.from_tree(system_file.parents[2] / "schema")
    runner = InProcessRunner(system_file.parent / "entrypoint", registry,
                             env={"IPROOFS_FAKE_NAME": system_file.parent.name})  # fmt: skip
    return runner, "local/in-process@sha256:" + "0" * 64, registry


def test_recompute_agreement(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RC-1, RC-3 and RC-5: the source run's claims reach the recompute job, every position is
    compared, and the counts are run metrics. The fake recomputes the same function, so all
    agree until a claim is changed."""
    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    claims = [p["claimed_output"] for p in json.loads((source / "run.json").read_text())["proofs"]]
    assert len(claims) == 6
    args = ("--prompts-from", str(source), "--allow-nonconforming")
    assert run("fake-recompute", repo / "same", *args) == 0
    doc = json.loads((only_run(repo / "same", "fake-recompute") / "run.json").read_text())
    m = doc["metrics"]
    assert (m["agreement_positions"]["value"], m["disagreement_positions"]["value"]) == (6, 0)
    assert doc["proofs"][0]["agreement"] == {"agree": 1, "disagree": 0, "first_disagreement": None}
    changed = json.loads((source / "run.json").read_text())
    changed["proofs"][2]["claimed_output"] = [changed["proofs"][2]["claimed_output"][0] + 1]
    (source / "run.json").write_text(json.dumps(changed))
    assert run("fake-recompute", repo / "other", *args) == 0
    doc = json.loads((only_run(repo / "other", "fake-recompute") / "run.json").read_text())
    m = doc["metrics"]
    assert (m["agreement_positions"]["value"], m["disagreement_positions"]["value"]) == (5, 1)
    by_request = {p["request_index"]: p["agreement"] for p in doc["proofs"]}
    assert by_request[2] == {"agree": 0, "disagree": 1, "first_disagreement": 0}


def test_recompute_needs_claims(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RFC-0015 §Failure modes: no source run, or one without claims, is a config error."""
    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    assert run("fake-recompute", repo / "none", "--allow-nonconforming") == 2
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    doc = json.loads((source / "run.json").read_text())
    for proof in doc["proofs"]:
        del proof["claimed_output"]
    (source / "run.json").write_text(json.dumps(doc))
    assert run("fake-recompute", repo / "x", "--prompts-from", str(source)) == 2


def test_agreement_positions() -> None:
    """RC-7: positions after the first disagreement are still compared; lengths must match."""
    from iproofs.errors import IProofsError  # noqa: PLC0415
    from iproofs.runner import agreement  # noqa: PLC0415

    got = agreement([1, 9, 3, 9], [1, 2, 3, 4], "req-0")
    assert got == {"agree": 2, "disagree": 2, "first_disagreement": 1}
    with pytest.raises(IProofsError, match="3 argmax positions for 4 claimed tokens"):
        agreement([1, 2, 3], [1, 2, 3, 4], "req-0")


def test_reference_without_a_served_system_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RFC-0015 REF-3: a reference row counts tokens by the rule of the proving system the
    workload lists; without one the job stops at resolve with a config failure."""
    from iproofs.runner import Runner  # noqa: PLC0415

    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    monkeypatch.setattr(Runner, "_coverage", lambda self, job: None)
    assert run("fake-ref", repo / "results", "--allow-nonconforming") == 4
    doc = json.loads((only_run(repo / "results", "fake-ref") / "run.json").read_text())
    assert doc["failure"]["kind"] == "config"
    assert "REF-3" in doc["failure"]["message"]


def test_engine_command_must_end_with_the_commits_engine_args(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RFC-0015 SRV-3: system.yaml at the run's commit lists other options than the adapter
    ran with (an image built from another system.yaml): the run fails with kind config, not as
    a run of the committed configuration. The fake's engine command is `fake-prover prove`."""
    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    path = repo / "systems/fake-ref/system.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["workloads"][0]["engine_args"] = ["--max-num-seqs", "24"]
    path.write_text(yaml.safe_dump(doc))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "commit", "-qam", "24 sequences", "--no-gpg-sign"], check=True)
    assert run("fake-ref", repo / "results", "--allow-nonconforming") != 0
    failed = json.loads((only_run(repo / "results", "fake-ref") / "run.json").read_text())
    assert failed["status"] == "failed"
    assert failed["failure"]["kind"] == "config"
    assert "does not end with system.yaml's engine_args ['--max-num-seqs', '24']" in str(
        failed["failure"]
    )


def test_engine_command_problem(tmp_path: Path) -> None:
    """The check on its own: the recorded argv's tail against engine_args, verbatim."""
    from iproofs.runner import engine_command_problem  # noqa: PLC0415

    args = ["--tensor-parallel-size", "4", "--max-model-len", "1025", "--max-num-seqs", "24"]
    assert engine_command_problem(tmp_path, [], required=True) is None  # nothing to compare
    assert engine_command_problem(tmp_path, args, required=False) is None  # failed before it
    assert "no engine command" in str(engine_command_problem(tmp_path, args, required=True))
    served = ["vllm", "serve", "/models"]
    lines = [{"argv": [*served, *args], "cwd": "/io", "started_mono_ns": 1, "exit_code": 0}]
    (tmp_path / "commands.jsonl").write_text("not json\n" + json.dumps(lines[0]) + "\n")
    assert engine_command_problem(tmp_path, args, required=True) is None
    stale = [*args[:3], "24", *args[4:]]
    assert "recorded: " in str(engine_command_problem(tmp_path, stale, required=False))
    assert engine_command_problem(tmp_path, ["x", *args], required=True) is not None
