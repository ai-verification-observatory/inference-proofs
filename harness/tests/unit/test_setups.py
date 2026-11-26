"""A setup made once and reused (iproofs.setups): a setup run keeps the state commit left and its
record, with no prompt; a session restores it, commit makes nothing again, and run.json names
the setup; a setup that is not this session's, or whose archive or commitment differs, stops
the session at commit."""

import io as io_
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

import pytest

from iproofs import cli
from iproofs.adapter import ContainerRunner, InProcessRunner, StepResult
from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import file_digest
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry
from iproofs.setups import (
    ARCHIVE,
    SETUP_RECORD,
    Setup,
    archive_state,
    load_setup,
    record_problems,
    restore_state,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
UPSTREAM = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0.0",
}
IMAGE = "local/in-process@sha256:" + "0" * 64


class Recording:
    """The fake in process, keeping each call's job.json and the names under io/ at its start."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=UPSTREAM | (env or {}))
        self.calls: list[tuple[str, dict[str, Any], list[str]]] = []

    def run(self, image: str, subcommand: str, io_dir: Path, **kw: Any) -> StepResult:
        job = json.loads((io_dir / "job.json").read_text())
        names = sorted(p.relative_to(io_dir).as_posix() for p in io_dir.rglob("*"))
        self.calls.append((subcommand, job, names))
        return self.inner.run(image, subcommand, io_dir, **kw)

    def subcommands(self) -> list[str]:
        return [sub for sub, _, _ in self.calls]


def spec(results: Path) -> JobSpec:
    return JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(results), "v0.1")


def runner(containers: ContainerRunner, setup: Setup | None = None) -> Runner:
    return Runner(containers, root=ROOT, registry=REGISTRY, image=IMAGE, setup=setup)


def make(tmp_path: Path) -> Path:
    return runner(Recording()).make_setup(spec(tmp_path / "setups"))


def record(setup_dir: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((setup_dir / SETUP_RECORD).read_text())
    return doc


def edit(setup_dir: Path, change: Any) -> None:
    doc = record(setup_dir)
    change(doc)
    (setup_dir / SETUP_RECORD).write_text(json.dumps(doc))


def session(tmp_path: Path, setup_dir: Path, **env: str) -> tuple[dict[str, Any], Recording]:
    containers = Recording(env)
    run_dir = runner(containers, load_setup(setup_dir, REGISTRY)).run(spec(tmp_path / "results"))
    doc: dict[str, Any] = json.loads((run_dir / "run.json").read_text())
    assert REGISTRY.errors("run/1", doc) == []
    return doc, containers


def test_a_setup_run_saves_a_setup_directory(tmp_path: Path) -> None:
    made = make(tmp_path)
    doc = record(made)
    assert REGISTRY.errors("setup/1", doc) == []
    assert record_problems(doc) == []
    assert doc["status"] == "completed"
    assert doc["failure"] is None
    assert made.name == doc["setup_id"]
    assert made.parent.name == "_setups"
    assert {"setup.json", "state.tar", "logs", "digests.txt"} <= {p.name for p in made.iterdir()}
    assert doc["archive"]["digest"] == file_digest(made / ARCHIVE)
    with tarfile.open(made / ARCHIVE) as tar:
        kept = tar.extractfile("state/commitment.txt")
        assert kept is not None
        assert kept.read().decode().strip() == doc["commitment"]["commitment_id"]
    assert set(doc["jobs"]) == {"info", "setup", "commit"}
    assert doc["jobs"]["commit"]["model_dir"] == "/models"
    assert doc["workload"]["shape"] == doc["jobs"]["commit"]["shape"]
    assert doc["system"]["upstream"]["commit"] == UPSTREAM["IPROOFS_FAKE_UPSTREAM"]
    assert doc["system"]["image"]["ref"] == IMAGE
    assert set(doc["steps"]) == {"info", "setup", "commit"}
    assert doc["total_seconds"]["value"] >= sum(s["value"] for s in doc["steps"].values())
    # ci-cpu binds no GPU: no GPU time, said so
    assert (doc["gpu_count"]["value"], doc["gpu_seconds"]["value"]) == (None, None)
    assert doc["gpu_seconds"]["null_reason"] == "not_applicable"


def test_a_setup_run_never_writes_or_passes_a_prompts_file(tmp_path: Path) -> None:
    containers = Recording()
    made = runner(containers).make_setup(spec(tmp_path))
    assert containers.subcommands() == ["info", "setup", "commit"]
    for _, job, names in containers.calls:
        assert "prompts_file" not in job
        assert not [n for n in names if "prompt" in n]
    doc = record(made)
    assert doc["prompts_file"] is None
    assert all("prompts_file" not in job for job in doc["jobs"].values())
    with tarfile.open(made / ARCHIVE) as tar:
        assert not [n for n in tar.getnames() if "prompt" in n]
    assert not [p for p in made.rglob("*") if "prompt" in p.name]


def test_gpu_seconds_are_recomputed_from_the_record() -> None:
    """2 GPUs held for 1,500.25 s are 3,000.5 GPU-seconds; another value is refused."""
    doc: dict[str, Any] = {"gpu_count": {"value": 2}, "total_seconds": {"value": 1500.25},
                           "gpu_seconds": {"value": 3000.5}}  # fmt: skip
    assert record_problems(doc) == []
    doc["gpu_seconds"]["value"] = 3000.0
    assert record_problems(doc) != []


def test_a_session_with_a_setup_restores_it_and_makes_nothing(tmp_path: Path) -> None:
    made = make(tmp_path)
    setup = load_setup(made, REGISTRY)
    doc, containers = session(tmp_path, made)
    assert doc["status"] == "completed", doc["failure"]
    assert containers.subcommands().count("commit") == 1
    commit = next(job for sub, job, _ in containers.calls if sub == "commit")
    assert commit["setup_state"] == {"commitment_id": setup.commitment_id}  # from the record
    assert list(doc["adapter_phases"]["commit"]) == ["setup_check"]  # the check, nothing made
    named = doc["setup"]
    assert named["setup_id"] == setup.setup_id
    assert named["record_digest"] == file_digest(made / SETUP_RECORD)
    assert named["archive_digest"] == file_digest(made / ARCHIVE)
    assert named["commitment_id"] == setup.commitment_id
    restore = named["restore_seconds"]
    assert (restore["unit"], restore["grade"], restore["source"]["kind"]) == ("s", "measured",
                                                                             "harness")  # fmt: skip
    assert restore["value"] > 0
    assert doc["metrics"]["verdicts_accept_count"]["value"] == 6  # the reused commitment verifies
    # commit only checked the setup's state: no commit or whole-wall time is given for it
    for name, scope in (("commit_seconds", "commit"), ("whole_wall_seconds", "whole_wall")):
        q = doc["metrics"][name]
        assert (q["value"], q["null_reason"], q["scope"]) == (None, "setup_reused", scope)
        assert q["source"]["ref"].endswith("run.json#/setup")
    assert doc["metrics"]["prove_session_seconds"]["value"] > 0
    assert named["build_key"] is None  # the fake compiles no kernels
    assert "kernels" not in doc


def test_a_session_without_a_setup_times_its_commit(tmp_path: Path) -> None:
    run_dir = runner(Recording()).run(spec(tmp_path))
    metrics = json.loads((run_dir / "run.json").read_text())["metrics"]
    assert metrics["commit_seconds"]["value"] >= 0
    assert metrics["whole_wall_seconds"]["value"] > 0


def test_run_json_keeps_each_steps_kernel_store(tmp_path: Path) -> None:
    made = runner(Recording({"IPROOFS_FAKE_KERNELS": "1"})).make_setup(spec(tmp_path / "s"))
    doc, _ = session(tmp_path, made, IPROOFS_FAKE_KERNELS="1")
    assert doc["setup"]["build_key"] == "sha256:" + "a" * 64
    kernels = doc["kernels"]
    assert kernels["commit"]["build_key"] == doc["setup"]["build_key"]
    assert kernels["prove"]["replies_built"] == 1
    assert (kernels["prove"]["constraint_kernels"], kernels["prove"]["generation_shapes"]) == (1, 1)


def test_a_session_without_a_setup_names_none(tmp_path: Path) -> None:
    run_dir = runner(Recording()).run(spec(tmp_path))
    doc = json.loads((run_dir / "run.json").read_text())
    assert "setup" not in doc
    assert doc["adapter_phases"] == {}  # the fake's commit reports no phase


def failed_at_commit(doc: dict[str, Any], containers: Recording, kind: str, called: bool) -> str:
    assert doc["status"] == "failed"
    failure = doc["failure"]
    assert (failure["kind"], failure["step"]) == (kind, "commit")
    assert ("commit" in containers.subcommands()) is called
    assert "prove" not in containers.subcommands()
    return str(failure["message"])


def test_a_wrong_archive_digest_stops_the_run(tmp_path: Path) -> None:
    made = make(tmp_path)
    with (made / ARCHIVE).open("ab") as f:
        f.write(b"\0" * 512)
    doc, containers = session(tmp_path, made)
    message = failed_at_commit(doc, containers, "integrity", called=False)
    assert "setup record names" in message
    assert doc["setup"]["restore_seconds"]["value"] is None


@pytest.mark.parametrize(
    ("what", "change"),
    [
        ("upstream_commit", lambda d: d["system"]["upstream"].update(commit="1" * 40)),
        ("image", lambda d: d["system"]["image"].update(ref="local/other@sha256:" + "1" * 64)),
        ("adapter_commit", lambda d: d["system"].update(adapter_commit="2" * 40)),
        ("adapter_dirty", lambda d: d["system"].update(adapter_dirty=not d["system"][
            "adapter_dirty"])),
        ("model_digest", lambda d: d["workload"]["model"].update(digest="sha256:" + "3" * 64)),
        ("shape", lambda d: d["workload"]["shape"].update(batch_size=3)),
    ],
)  # fmt: skip
def test_a_setup_made_for_another_session_stops_the_run(
    tmp_path: Path, what: str, change: Any
) -> None:
    made = make(tmp_path)
    edit(made, change)
    doc, containers = session(tmp_path, made)
    message = failed_at_commit(doc, containers, "config", called=False)
    assert f"{what}: the setup has" in message


def test_a_differing_commitment_id_stops_the_run(tmp_path: Path) -> None:
    made = make(tmp_path)
    doc, containers = session(tmp_path, made, IPROOFS_FAKE_FAULT="setup-id")
    message = failed_at_commit(doc, containers, "integrity", called=True)
    assert "the setup record names" in message
    assert "commit" not in doc["adapter_phases"]  # an output the harness refused records none


def test_restored_state_that_fails_the_adapters_check_stops_the_run(tmp_path: Path) -> None:
    """The record and archive agree, but the state commits other weights than the record
    names: the adapter's own check refuses it, and nothing is made again."""
    made = make(tmp_path)
    work = tmp_path / "work"
    with tarfile.open(made / ARCHIVE) as tar:
        tar.extractall(work, filter="tar")
    (work / "state/commitment.txt").write_text("0" * 64 + "\n")
    archive_state(work / "state", made / ARCHIVE)
    edit(made, lambda d: d["archive"].update(digest=file_digest(made / ARCHIVE)))
    doc, containers = session(tmp_path, made)
    failed_at_commit(doc, containers, "adapter", called=True)


def test_a_failed_setup_is_recorded_and_never_reused(tmp_path: Path) -> None:
    class FailCommit(Recording):
        def run(self, image: str, subcommand: str, io_dir: Path, **kw: Any) -> StepResult:
            result = super().run(image, subcommand, io_dir, **kw)
            if subcommand != "commit":
                return result
            return StepResult(subcommand, result.started_mono_ns, result.ended_mono_ns, 7, None,
                              ("upstream failed",))  # fmt: skip

    made = runner(FailCommit()).make_setup(spec(tmp_path))
    doc = record(made)
    assert REGISTRY.errors("setup/1", doc) == []
    failure = doc["failure"]
    assert (doc["status"], failure["step"], failure["exit_code"]) == ("failed", "commit", 7)
    assert doc["archive"] is None
    assert not (made / ARCHIVE).exists()
    with pytest.raises(IProofsError) as e:
        load_setup(made, REGISTRY)
    assert e.value.kind is ErrorKind.CONFIG


def test_restore_refuses_a_state_already_there_and_entries_outside_state(tmp_path: Path) -> None:
    state = tmp_path / "made/state"
    (state / "build").mkdir(parents=True)
    (state / "build/kernels.done").write_text("k")
    (state / "build/registry").symlink_to("/opt/cargo/registry")
    archive_state(state, tmp_path / ARCHIVE)
    digest = file_digest(tmp_path / ARCHIVE)
    io = tmp_path / "io"
    restore_state(tmp_path / ARCHIVE, digest, io)
    assert (io / "state/build/registry").is_symlink()  # an absolute link stays a link
    assert (io / "state/build/kernels.done").read_text() == "k"
    with pytest.raises(IProofsError, match="holds files before"):
        restore_state(tmp_path / ARCHIVE, digest, io)
    stray = tmp_path / "stray.tar"
    with tarfile.open(stray, "w") as tar:
        tar.add(state, arcname="other")
    shutil.rmtree(io)
    with pytest.raises(IProofsError, match="outside state/"):
        restore_state(stray, file_digest(stray), io)


def crafted(tmp_path: Path, *members: tarfile.TarInfo) -> Path:
    archive = tmp_path / "crafted.tar"
    with tarfile.open(archive, "w") as tar:
        root = tarfile.TarInfo("state")
        root.type, root.mode = tarfile.DIRTYPE, 0o755
        tar.addfile(root)
        for m in members:
            tar.addfile(m, io_.BytesIO(b"REPLACED\n") if m.isfile() else None)
    return archive


def member(name: str, kind: bytes = tarfile.REGTYPE, link: str = "") -> tarfile.TarInfo:
    m = tarfile.TarInfo(name)
    m.type, m.linkname, m.mode = kind, link, 0o644
    m.size = len(b"REPLACED\n") if kind == tarfile.REGTYPE else 0
    return m


@pytest.mark.parametrize("members", [
    [member("state/../prompts.jsonl")],  # a name that leaves state/ once normalised
    [member("state/up", tarfile.SYMTYPE, "../prompts.jsonl")],  # a link out of state/
    [member("state/up", tarfile.SYMTYPE, ".."), member("state/up/prompts.jsonl")],  # through one
    [member("state/hard", tarfile.LNKTYPE, "prompts.jsonl")],  # a hard link to an io file
])  # fmt: skip
def test_restore_writes_nothing_outside_io_state(
    tmp_path: Path, members: list[tarfile.TarInfo]
) -> None:
    io = tmp_path / "io"
    io.mkdir()
    (io / "prompts.jsonl").write_text("ORIGINAL\n")
    archive = crafted(tmp_path, *members)
    with pytest.raises(IProofsError) as e:
        restore_state(archive, file_digest(archive), io)
    assert e.value.kind is ErrorKind.INTEGRITY
    assert (io / "prompts.jsonl").read_text() == "ORIGINAL\n"


def test_cli_makes_a_setup_and_a_session_reuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    for key, value in UPSTREAM.items():
        monkeypatch.setenv(key, value)
    base = ["--quiet", "run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile",
            "ci-cpu", "--in-process", "--results", str(tmp_path)]  # fmt: skip
    assert cli.main([*base, "--make-setup"]) == 0
    made = Path(capsys.readouterr().out.strip().splitlines()[-1])
    assert (made / SETUP_RECORD).is_file()
    assert cli.main([*base, "--repetitions", "1", "--setup", str(made)]) == 0
    run_dir = Path(capsys.readouterr().out.strip().splitlines()[-1])
    assert json.loads((run_dir / "run.json").read_text())["setup"]["setup_id"] == made.name


@pytest.mark.parametrize("extra", [["--session", "1"], ["--control-suite"], ["--keep-io"],
                                   ["--repetitions", "1"], ["--setup", "x"]])  # fmt: skip
def test_a_setup_run_refuses_session_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: list[str]
) -> None:
    monkeypatch.chdir(ROOT)
    argv = ["--quiet", "run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile",
            "ci-cpu", "--in-process", "--results", str(tmp_path), "--make-setup",
            *extra]  # fmt: skip
    assert cli.main(argv) == 2
    assert not (tmp_path / "v0.1").exists()
