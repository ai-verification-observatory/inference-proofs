"""RFC-0018 on the runner side: level sessions, level control suites (CH-1 to CH-3), traced
verify calls (CH-4), the 512-token reply rule (AD-1), the optional `logprobs` subcommand (AD-2)
and the serving baseline's ladder run (CO-4). The fake systems run in process; every value is a
fixture value, not a result."""

import dataclasses
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs import cli
from iproofs.adapter import (
    STRACE_ARGS,
    TRACE_SH,
    DockerRunner,
    InProcessRunner,
    StepResult,
    check_requests,
    docker_create_argv,
)
from iproofs.controls import (
    C1_POSITIONS,
    HonestProof,
    Series,
    VerifyCall,
    VerifyResult,
    c1_at,
    level_control_record,
    seeded_index,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import NullCgroupReader, Sampler, parse_strace, reduce_strace
from iproofs.model import AdapterOut, ProofEntry, System, load
from iproofs.runner import CpuOnlyEnvironment, Job, JobSpec, LevelRun, Runner
from iproofs.schema import SchemaRegistry
from iproofs.workloads import load_workload, materialise_prompts, model_dir

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
IMAGE = "local/x@sha256:" + "0" * 64
SEED = "0x0123456789abcdef"
# The fake workload as a level would ask for it: 8 + 1 tokens, 6 requests a session.
LEVEL = LevelRun("L1", "sha256:" + "b" * 64, "fake-rung", 2, 3, 6, 8, 1)

# A captured-style `strace -f -o FILE` output: pid prefixes, a failed open, a call another thread
# interrupted and its resumed end, openat2's struct argument, an escaped path, a signal and an
# exit line.
SAMPLE = r"""4120  openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3
4120  openat(AT_FDCWD, "/usr/lib/libz.so.1", O_RDONLY) = -1 ENOENT (No such file or directory)
4121  openat(AT_FDCWD, "/io/proof/tag.bin", O_RDONLY <unfinished ...>
4120  open("/models/weights.bin", O_RDONLY) = -1 ENOENT (No such file or directory)
4121  <... openat resumed>) = 5
[pid  4122] openat2(AT_FDCWD, "/io/proof/body.bin", {flags=O_RDONLY|O_CLOEXEC, resolve=0}, 24) = 6
4122  openat(AT_FDCWD, "/io/d\303\251j\303\240 \"q\".txt", O_RDONLY) = 7
4122  openat(AT_FDCWD, "/dev/nvidia0", O_RDWR) = 8
4122  openat(AT_FDCWD, "/dev/nvidiactl", O_RDWR) = 9
4120  --- SIGCHLD {si_signo=SIGCHLD, si_code=CLD_EXITED} ---
4122  +++ exited with 0 +++
"""


def test_strace_lines_parse_with_pids_resumes_and_escapes() -> None:
    calls = [(c.path, c.ok) for c in parse_strace(SAMPLE)]
    assert calls == [
        ("/etc/ld.so.cache", True),
        ("/usr/lib/libz.so.1", False),
        ("/models/weights.bin", False),
        ("/io/proof/tag.bin", True),  # completed by its resumed line
        ("/io/proof/body.bin", True),
        ('/io/déjà "q".txt', True),
        ("/dev/nvidia0", True),
        ("/dev/nvidiactl", True),
    ]


def test_trace_reduction_names_model_files_by_path_dir_and_realpath() -> None:
    files = {"/models/weights.bin", "/cache/blobs/abc"}
    reduced = reduce_strace(SAMPLE, files, {"/models"})
    assert [(c.path, c.ok) for c in reduced.model_files] == [("/models/weights.bin", False)]
    assert reduced.opened[:2] == ("/etc/ld.so.cache", "/io/proof/tag.bin")
    assert reduced.failed == 2
    assert reduced.gpu_devices == ("/dev/nvidia0",)
    linked = '9  openat(AT_FDCWD, "/snap/w.bin", O_RDONLY) = 3\n'  # a symlink into the cache
    by_realpath = reduce_strace(linked, files, set(), lambda p: "/cache/blobs/abc")
    assert [c.path for c in by_realpath.model_files] == ["/snap/w.bin"]
    under = '9  openat(AT_FDCWD, "/models/sub/../extra.json", O_RDONLY) = 3\n'
    assert reduce_strace(under, set(), {"/models/"}).model_files[0].ok
    assert reduce_strace('9  openat(3, "weights.bin", O_RDONLY) = 4\n', files, {"/models"}) \
        .model_files == ()  # fmt: skip


def test_level_run_checks_512_reply_tokens_per_request() -> None:
    def out(*claims: tuple[int, int]) -> AdapterOut:
        proofs = tuple(
            ProofEntry(proof_id=f"p{i}", request_index=r, parts=(), claimed_output=(7,) * n)
            for i, (r, n) in enumerate(claims)
        )
        blank: dict[str, Any] = {f.name: None for f in dataclasses.fields(AdapterOut)}
        return AdapterOut(**(blank | {"proofs": proofs}))  # fmt: skip

    check_requests(out((0, 512), (1, 300), (1, 212)), 512)
    with pytest.raises(IProofsError, match=r"\{1: 511\}"):
        check_requests(out((0, 512), (1, 511)), 512)


# ---------------------------------------------------------------- level control records


def target(reply: int = 512) -> HonestProof:
    return HonestProof("p0", tuple(range(8)), tuple(range(reply)), "accept", 1, 0)


class Verifier:
    """Rejects every mutated call; the twin's verdicts come from `twins`, in order, then
    accept."""

    def __init__(self, twins: list[str] | None = None) -> None:
        self.twins = list(twins or [])
        self.calls: list[VerifyCall] = []

    def __call__(self, call: VerifyCall) -> VerifyResult:
        self.calls.append(call)
        if call.control_id == "twin":
            verdict = self.twins.pop(0) if self.twins else "accept"
            return VerifyResult(verdict, 0 if verdict == "accept" else 1, verdict, 0.1)
        return VerifyResult("reject", 1, "rejected", 0.2)


def twin_of(t: HonestProof) -> list[VerifyCall]:
    return [VerifyCall("twin", 0, "c", t.request, t.claimed_output, Path("p"), (), {})]


def c1_series(t: HonestProof, proof: Path) -> list[Series]:
    return [Series({"position": pos}, lambda k, pos=pos: [  # type: ignore[misc]
        c1_at(t, "c", proof, 1000, SEED, pos, k)]) for pos in C1_POSITIONS]  # fmt: skip


def test_c1_three_positions_three_trials_each_interior_seeded(tmp_path: Path) -> None:
    t = target()
    verify = Verifier()
    record = level_control_record("C1", c1_series(t, tmp_path), lambda: twin_of(t), verify)
    trials = record["trials"]
    assert isinstance(trials, list)
    assert [(x["detail"]["position"], x["seed_index"]) for x in trials] == [
        (p, k) for p in C1_POSITIONS for k in range(3)
    ]
    index = [x["mutation"]["index"] for x in trials]
    interior = [seeded_index(SEED, "C1-interior", k, 510) + 1 for k in range(3)]
    assert index == [0, 0, 0, 511, 511, 511, *interior]
    assert all(1 <= i <= 510 for i in interior)
    assert (record["outcome"], record["passed"], record["note"]) == ("rejected", True, None)
    assert sum(c.control_id == "twin" for c in verify.calls) == 9  # one twin per trial
    assert REGISTRY.errors("controls/1", {"schema": "controls/1", "run_id": "2026-11-10-a-b-c-1",
        "control_seed": SEED, "image": IMAGE, "verifier_profile": "ci-cpu",
        "perturbed_commitment": None, "controls": [record], "summary": {
            "run": 1, "passed": 1, "rejected": 1, "accepted": 0, "no_verdict": 0,
            "invalid_call": 0, "void": 0, "not_applicable": 0, "error": 0, "prover_failed": 0},
        "disclosure_pending": False}) == []  # fmt: skip


def test_void_trial_reruns_with_next_seed() -> None:
    t = target()
    verify = Verifier(twins=["reject", "accept", "reject"])
    mutation = {"commitment": "perturbed"}
    series = [Series({}, lambda k: [VerifyCall("C3", k, "w2", t.request, t.claimed_output,
                                               Path("p"), (), mutation)])]  # fmt: skip
    record = level_control_record("C3", series, lambda: twin_of(t), verify)
    trials = record["trials"]
    assert isinstance(trials, list)
    assert [(x["seed_index"], x["outcome"]) for x in trials] == [
        (0, "void"), (1, "rejected"), (2, "void"), (3, "rejected"), (4, "rejected")]  # fmt: skip
    assert trials[0]["detail"]["twin"] == {"verdict": "reject", "raw_exit_code": 1}
    assert (record["outcome"], record["passed"]) == ("rejected", True)


def test_ten_void_seeds_leave_the_control_void() -> None:
    t = target()
    verify = Verifier(twins=["reject"] * 10)
    series = [Series({}, lambda k: [VerifyCall("C2", k, "c", t.request, t.claimed_output,
                                               Path("p"), (), {})])]  # fmt: skip
    record = level_control_record("C2", series, lambda: twin_of(t), verify)
    assert len(record["trials"]) == 10  # type: ignore[arg-type]
    assert (record["outcome"], record["passed"]) == ("void", None)
    assert "0 of 3 trials counted in 10 seeds" in str(record["note"])


def test_one_accepted_trial_fails_the_control() -> None:
    t = target()
    answers = iter(["reject", "accept", "reject"])

    def verify(call: VerifyCall) -> VerifyResult:
        verdict = "accept" if call.control_id == "twin" else next(answers)
        return VerifyResult(verdict, 0, verdict, 0.1)

    series = [Series({}, lambda k: [VerifyCall("C2", k, "c", t.request, t.claimed_output,
                                               Path("p"), (), {})])]  # fmt: skip
    record = level_control_record("C2", series, lambda: twin_of(t), verify)
    assert (record["outcome"], record["passed"]) == ("accepted", False)


def test_failed_control_prove_counts_as_prover_failed() -> None:
    t = target()

    def prove(k: int) -> list[VerifyCall]:
        raise IProofsError(ErrorKind.ADAPTER, "prove exited 3", exit_code=3)

    record = level_control_record("P1", [Series({}, prove)], lambda: twin_of(t), Verifier(),
                                  side="prover")  # fmt: skip
    trials = record["trials"]
    assert isinstance(trials, list)
    assert [x["outcome"] for x in trials] == ["prover_failed"] * 3
    assert (record["outcome"], record["passed"]) == ("prover_failed", True)


# ---------------------------------------------------------------- level runs of the fakes


def fake_strace(directory: Path) -> Path:
    """A `strace` on PATH that writes a captured-style trace naming one model file, then runs
    the traced command."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "strace"
    script.write_text(
        f"#!{sys.executable}\n"
        + """import os, sys
args = sys.argv[1:]
out = args[args.index("-o") + 1]
command = args[args.index("-o") + 2:]
pid = os.getpid()
with open(out, "w") as f:
    f.write(f'{pid}  openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3\\n')
    f.write(f'{pid}  openat(AT_FDCWD, "/models/weights.bin", O_RDONLY) = -1 ENOENT (x)\\n')
os.execv(command[0], command)
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return directory


def level_runner(path: str, system: str = "fake", level: LevelRun = LEVEL) -> Runner:
    entry = ROOT / "systems" / system / "entrypoint"
    env = {**ENV, "PATH": path}
    if system == "fake-broken":
        env["IPROOFS_FAKE_UPSTREAM"] = "f7cf1d696bd15cf1601f48ea4c51ae20e57c9d82"
    return Runner(InProcessRunner(entry, REGISTRY, env=env), root=ROOT, registry=REGISTRY,
                  image=IMAGE, level=level, replay_seed=7)  # fmt: skip


def spec(results: Path, system: str = "fake", controls: bool = True) -> JobSpec:
    return JobSpec(system, "fake-tiny-ci", 1, "ci-cpu", 1, controls, str(results), "v0.1")


def read(run_dir: Path, name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((run_dir / name).read_text())
    return doc


@pytest.fixture(autouse=True)
def at_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_level_session_records_level_slot_traces_and_level_controls(tmp_path: Path) -> None:
    path = f"{fake_strace(tmp_path / 'bin')}{os.pathsep}{os.environ['PATH']}"
    run_dir = level_runner(path).run(spec(tmp_path / "results"))
    run, manifest = read(run_dir, "run.json"), read(run_dir, "manifest.json")
    assert run["status"] == "completed", run["failure"]
    assert "repetitions_below_minimum" not in run["warnings"]  # one run is one session
    assert manifest["level"] == {"id": "L1", "digest": LEVEL.digest}
    assert manifest["session"] == {"slot": 2, "rung": "fake-rung", "requests": 6, "beacon": None}
    assert REGISTRY.errors("manifest/1", manifest) == []
    # prove got slot 2: prompts [6, 12) of the seed's stream
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    stream = materialise_prompts(ROOT, wl, model_dir(ROOT, wl), 7, count=12)
    claimed = [p["request_index"] for p in run["proofs"]]
    assert claimed
    assert sorted(claimed) == list(range(6))
    prompts = materialise_prompts(ROOT, wl, model_dir(ROOT, wl), 7, slot=2)
    assert prompts == stream[6:12]
    # one verify-trace per counted verdict
    traces = sorted((run_dir / "verify-trace").glob("*.json"))
    assert [t.stem for t in traces] == sorted(p["proof_id"] for p in run["proofs"])
    trace = read(traces[0].parent, traces[0].name)
    assert REGISTRY.errors("verify-trace/1", trace) == []
    assert (trace["tool"], trace["mode"], trace["gpu_visible"]) == ("strace", "in-process", False)
    assert trace["model_files_opened"] == [{"path": "/models/weights.bin", "ok": False}]
    assert trace["opened"][0]["path"] == "/etc/ld.so.cache"
    assert trace["model_files_present"] is True  # in process, the repository's toy model
    # controls: C1 at the first and last of a 1-token reply, 3 trials each; C2 seeds 0 to 2
    controls = read(run_dir, "controls.json")
    assert REGISTRY.errors("controls/1", controls) == []
    by_id = {c["id"]: c for c in controls["controls"]}
    c1 = by_id["C1"]
    assert [t["detail"]["position"] for t in c1["trials"]] == ["first"] * 3 + ["last"] * 3
    assert all(t["outcome"] == "rejected" for t in c1["trials"])
    assert "interior: a reply of 1 token(s) has no interior position" in c1["note"]
    assert [t["seed_index"] for t in by_id["C2"]["trials"]] == [0, 1, 2]
    assert by_id["C2"]["passed"] is True
    assert len(by_id["C6"]["trials"]) == 5  # RFC-0008's own controls keep their counts
    assert by_id["P1"]["outcome"] == "not_applicable"  # no perturbed commitment


def test_level_session_without_strace_records_no_tool(tmp_path: Path) -> None:
    empty = tmp_path / "no-strace"
    empty.mkdir()
    run_dir = level_runner(str(empty)).run(spec(tmp_path / "results", controls=False))
    assert read(run_dir, "run.json")["status"] == "completed"
    for path in (run_dir / "verify-trace").glob("*.json"):
        trace = read(path.parent, path.name)
        assert (trace["tool"], trace["trace"], trace["opened"]) == (None, None, [])
        assert REGISTRY.errors("verify-trace/1", trace) == []


def test_level_suite_of_a_broken_verifier_accepts_c1(tmp_path: Path) -> None:
    empty = tmp_path / "no-strace"
    empty.mkdir()
    run_dir = level_runner(str(empty), "fake-broken").run(spec(tmp_path / "r", "fake-broken"))
    controls = read(run_dir, "controls.json")
    c1 = next(c for c in controls["controls"] if c["id"] == "C1")
    assert (c1["outcome"], c1["passed"]) == ("accepted", False)
    assert controls["disclosure_pending"] is True


def test_level_refuses_a_workload_off_the_request_before_any_step(tmp_path: Path) -> None:
    off = dataclasses.replace(LEVEL, output_tokens=512)
    run_dir = level_runner(os.environ["PATH"], level=off).run(spec(tmp_path / "r"))
    failure = read(run_dir, "run.json")["failure"]
    assert (failure["kind"], failure["step"]) == ("config", "resolved")
    assert "8 + 1" in failure["message"]


def test_level_run_takes_no_repetitions(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match="one session"):
        level_runner(os.environ["PATH"]).run_many(spec(tmp_path / "r"), 3)
    code = cli.main(["run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile",
                     "ci-cpu", "--results", str(tmp_path / "r"), "--in-process", "--level", "L1",
                     "--session", "1", "--repetitions", "2"])  # fmt: skip
    assert code != 0
    assert not (tmp_path / "r").exists()


# ---------------------------------------------------------------- weights away, docker trace


def test_hosted_level_run_removes_cached_weights_before_verify(tmp_path: Path) -> None:
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    source = dataclasses.replace(wl.model.source, hub="huggingface", path=None)
    wl = dataclasses.replace(wl, model=dataclasses.replace(wl.model, source=source))
    cache = tmp_path / "cache/models/x"
    shutil.copytree(model_dir(ROOT, load_workload("fake-tiny-ci", root=ROOT,
                                                  registry=REGISTRY)), cache)  # fmt: skip
    for p in [*cache.rglob("*"), cache]:
        p.chmod(stat.S_IMODE(p.stat().st_mode) & ~0o222)  # read-only, as ensure_model leaves it
    runner = Runner(InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY), root=ROOT,
                    registry=REGISTRY, image=IMAGE, hosted=True, level=LEVEL)  # fmt: skip
    job = Job(spec(tmp_path), "r", tmp_path, workload=wl, models=cache)
    runner._weights_away(job)
    assert job.models_removed
    assert not cache.exists()
    paths = job.model_paths
    assert paths is not None
    assert str(cache / "weights.bin") in paths.files
    assert "/models/weights.bin" in paths.files
    assert not any(p.exists() for p in paths.host_files)


def test_docker_verify_traced_inside_the_container(tmp_path: Path) -> None:
    argv = docker_create_argv(IMAGE, "verify", tmp_path / "io", models_dir=tmp_path / "m",
                              gpu=0, cpuset="1", mems="0", memory=None,
                              trace_dir=tmp_path / "t", entrypoint=["/opt/adapter"])  # fmt: skip
    assert "--gpus" not in argv
    assert not any(a.endswith(":/models:ro") for a in argv)
    assert f"{(tmp_path / 't').resolve()}:/trace:rw" in argv
    tail = argv[argv.index("--entrypoint") :]
    assert tail[:2] == ["--entrypoint", "/bin/sh"]
    assert tail[3:] == ["-c", TRACE_SH, "sh", "/opt/adapter", "verify", "/io/job.json",
                        "/io/out.json"]  # fmt: skip
    assert f"strace {' '.join(STRACE_ARGS)} /trace/strace.txt" in TRACE_SH
    seen: list[list[str]] = []

    def inspect(cmd: list[str]) -> str:
        seen.append(cmd)
        return '["python3","/opt/adapter/entrypoint"]\n'

    docker = DockerRunner(REGISTRY, inspect=inspect)
    assert docker.entrypoint(IMAGE) == ("python3", "/opt/adapter/entrypoint")
    assert docker.entrypoint(IMAGE) == ("python3", "/opt/adapter/entrypoint")
    assert len(seen) == 1  # once per image


# ---------------------------------------------------------------- logprobs (AD-2)


class LogprobsAdapter:
    """A container runner whose adapter answers `logprobs` with given files."""

    def __init__(self, sizes: list[int]) -> None:
        self.sizes = sizes

    def run(self, image: str, subcommand: str, io_dir: Path, **kw: Any) -> StepResult:
        job = json.loads((io_dir / "job.json").read_text())
        assert (job["subcommand"], job["texts_file"]) == ("logprobs", "/io/texts.jsonl")
        (io_dir / "logprobs").mkdir()
        names = []
        for i, n in enumerate(self.sizes):
            (io_dir / "logprobs" / f"{i}.f16").write_bytes(bytes(n))
            names.append(f"/io/logprobs/{i}.f16")
        blank: dict[str, Any] = {f.name: None for f in dataclasses.fields(AdapterOut)}
        out = AdapterOut(**(blank | {"schema": "adapter-out/1", "contract": "adapter/1",
                                     "subcommand": "logprobs", "phases": (), "warnings": (),
                                     "logprobs_files": tuple(names)}))  # fmt: skip
        return StepResult(subcommand, 0, 1, 0, out, ())


def logprobs_job(tmp_path: Path, supported: bool) -> Job:
    system = load(ROOT / "systems/fake/system.yaml", REGISTRY)
    assert isinstance(system, System)
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    blank: dict[str, Any] = {f.name: None for f in dataclasses.fields(AdapterOut)}
    commit = AdapterOut(**(blank | {"subcommand": "commit", "commitment_id": "c",
                                    "prover_files": ()}))  # fmt: skip
    (tmp_path / "logs").mkdir(parents=True)
    return Job(spec(tmp_path), "r", tmp_path, system=system, workload=wl, commit=commit,
               commitment_record={"commitment_id": "c", "verifier_files": [],
                                  "prover_files": []}, image=IMAGE,
               optional_subcommands=("logprobs",) if supported else ())  # fmt: skip


def test_logprobs_checks_full_distribution_sizes_or_answers_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-2: per text, (len - len//2 - 1) scored rows of `vocab` float16 values."""
    monkeypatch.setattr("iproofs.runner.Sampler", lambda gpu, readers: Sampler(None, readers))
    runner = Runner(LogprobsAdapter([2 * 1 * 3, 0]), root=ROOT, registry=REGISTRY, image=IMAGE,
                    env=CpuOnlyEnvironment())  # fmt: skip
    runner.readers = NullCgroupReader()
    paths = runner.logprobs(logprobs_job(tmp_path / "a", True), [[1, 2, 3, 4], [5]], vocab=3)
    assert paths is not None
    assert [p.stat().st_size for p in paths] == [6, 0]
    assert runner.logprobs(logprobs_job(tmp_path / "b", False), [[1, 2]], vocab=3) is None
    short = Runner(LogprobsAdapter([4]), root=ROOT, registry=REGISTRY, image=IMAGE)
    with pytest.raises(IProofsError, match="not 2 x 1 x 3"):
        short.logprobs(logprobs_job(tmp_path / "c", True), [[1, 2, 3, 4]], vocab=3)


# ---------------------------------------------------------------- ladder (CO-4)


@pytest.fixture
def ladder_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake systems and a serve-role `fake-ref` with a ladder entry on 2 fixture GPUs."""
    repo = tmp_path / "repo"
    for rel in ("schema", "systems/fake", "systems/fake-broken", "workloads/fake-tiny-ci.yaml",
                "reference",
                "harness/tests/fixtures/prompts", "uv.lock", "pyproject.toml"):  # fmt: skip
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    ref = repo / "systems/fake-ref"
    ref.mkdir()
    shutil.copy(ROOT / "systems/fake/entrypoint", ref / "entrypoint")
    entry = {"id": "fake-tiny-ci", "gpus": 2, "load_point": "ladder", "precision_used": "int8",
             "precision_substitution": None, "engine_args": []}  # fmt: skip
    system = {"schema": "system/1", "name": "fake-ref", "kind": "reference",
              "reference_role": "serve", "contract": "adapter/1",
              "engine": {"name": "fake", "version": "1", "image": IMAGE}, "workloads": [entry],
              "deterministic_proofs": True, "incremental_proofs": True,
              "forbidden_flags": []}  # fmt: skip
    (ref / "system.yaml").write_text(json.dumps(system))
    ci = repo / "reference/ci.yaml"
    doc = yaml.safe_load(ci.read_text())
    gpu = {"model": "CI fake GPU", "form_factor": "none", "memory_mib_min": 1, "count": 2}
    doc["profiles"]["ci-gpu"] = {**doc["profiles"]["ci-cpu"], "gpu": {**gpu, "count": 1}}
    doc["profiles"]["ci-serving-x2"] = {**doc["profiles"]["ci-cpu"], "kind": "serving",
                                        "gpu": gpu, "pairs_with": ["ci-gpu"]}  # fmt: skip
    ci.write_text(json.dumps(doc))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", "64168df9fd0706dfd955b6795fa6f535872dff78")
    monkeypatch.setattr("iproofs.runner.Sampler", lambda gpu, readers: Sampler(None, readers))
    monkeypatch.setattr("iproofs.runner.select_readers", lambda **_: NullCgroupReader())
    return repo


class TwoGpus(CpuOnlyEnvironment):
    def gpus(self) -> tuple[int, ...]:
        return (0, 1)


def test_ladder_run_serves_the_ladder_prompts_in_one_batch(ladder_repo: Path) -> None:
    lv = LevelRun("L1", "sha256:" + "b" * 64, "fake-rung", None, 3, 6, 8, 1, None, (1, 2), 1, 1, 4)
    containers = InProcessRunner(ladder_repo / "systems/fake-ref/entrypoint", REGISTRY,
                                 env={"IPROOFS_FAKE_NAME": "fake-ref"})  # fmt: skip
    runner = Runner(containers, root=ladder_repo, registry=REGISTRY, image=IMAGE, env=TwoGpus(),
                    load="ladder", level=lv, replay_seed=7, keep_io=True)  # fmt: skip
    run_dir = runner.run(JobSpec("fake-ref", "fake-tiny-ci", 1, "ci-serving-x2", 1, False,
                                 str(ladder_repo / "results"), "v0.1"))  # fmt: skip
    run, manifest = read(run_dir, "run.json"), read(run_dir, "manifest.json")
    assert run["status"] == "completed", run["failure"]
    assert manifest["workload"]["load_point"] == "ladder"
    assert (manifest["workload"]["batch_size_run"], manifest["workload"]["prompt_count_run"]) == (
        4, 4)  # fmt: skip
    assert manifest["session"] == {"slot": None, "rung": "fake-rung", "requests": 4,
                                   "beacon": None}  # fmt: skip
    assert REGISTRY.errors("manifest/1", manifest) == []
    job = read(run_dir / "io", "job.json")
    assert (job["ladder"], job["warmup_batches"], job["timed_batches"]) == ([1, 2], 1, 1)
    assert (job["batch_size"], job["batches"]) == (4, 1)


def test_controls_of_a_stored_level_run_are_the_level_suite(tmp_path: Path) -> None:
    """`iproofs controls RUN_DIR` on a kept level session reads `level` from its manifest."""
    from iproofs.runner import controls_for_run  # noqa: PLC0415

    empty = tmp_path / "no-strace"
    empty.mkdir()
    runner = level_runner(str(empty))
    runner.keep_io = True
    run_dir = runner.run(spec(tmp_path / "r", controls=False))
    plain = Runner(InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV),
                   root=ROOT, registry=REGISTRY, image=IMAGE)  # fmt: skip
    doc = read(run_dir, controls_for_run(plain, run_dir, seed=SEED).name)
    c2 = next(c for c in doc["controls"] if c["id"] == "C2")
    assert [t["seed_index"] for t in c2["trials"]] == [0, 1, 2]
    assert REGISTRY.errors("controls/1", doc) == []


# ---------------------------------------------------------------- round 2: AD-4 to AD-6


def l1_runner(path: str, system: str = "fake") -> Runner:
    runner = level_runner(path, system)
    assert isinstance(runner.containers, InProcessRunner)
    runner.containers.env["IPROOFS_FAKE_L1"] = "1"
    return runner


def spy_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object]]:
    """(subcommand, job.json `control`) of every adapter call."""
    seen: list[tuple[str, object]] = []
    original = Runner._call

    def call(self: Runner, job: Job, sub: str, extra: dict[str, object], *a: Any, **kw: Any) -> Any:
        seen.append((sub, kw.get("control", False)))
        return original(self, job, sub, extra, *a, **kw)

    monkeypatch.setattr(Runner, "_call", call)
    return seen


def test_generation_marks_are_timed_and_recorded(tmp_path: Path) -> None:
    empty = tmp_path / "no-strace"
    empty.mkdir()
    run_dir = l1_runner(str(empty)).run(spec(tmp_path / "r", controls=False))
    run = read(run_dir, "run.json")
    assert run["status"] == "completed", run["failure"]
    assert REGISTRY.errors("run/1", run) == []
    marks = {m["name"]: m["mono_ns"] for m in run["marks"]}
    assert list(marks) == ["generation.start", "generation.end"]
    events = {e["event"]: e["mono_ns"] for e in run["events"]}
    assert events["prove.start"] <= marks["generation.start"] <= marks["generation.end"]
    assert marks["generation.end"] <= events["prove.end"] + 50_000_000  # one observation lag
    plain = level_runner(str(empty)).run(spec(tmp_path / "p", controls=False))
    assert "marks" not in read(plain, "run.json")  # an adapter that writes none


def test_model_controls_use_the_adapters_perturb_and_name_the_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from iproofs.runner import prepare_perturbed  # noqa: PLC0415

    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "cache"))
    empty = tmp_path / "no-strace"
    empty.mkdir()
    seen = spy_calls(monkeypatch)
    results = tmp_path / "r"
    change = "byte 0 of weights.bin raised by one"
    path = prepare_perturbed(l1_runner(str(empty)), spec(results), tmp_path / "cache", change)
    record = read(path.parent, path.name)
    assert record["change"] == change
    assert (record["perturbation"]["old"] + 1) % 256 == record["perturbation"]["new"]
    assert REGISTRY.errors("perturbed-commitment/1", record) == []
    made = [(sub, c) for sub, c in seen if sub in ("perturb", "setup", "commit")]
    assert made[0] == ("perturb", True)
    assert made[1:] == [(s, {"id": "C3", "perturbation": record["perturbation"]})
                        for s in ("setup", "commit")]  # fmt: skip
    seen.clear()
    run_dir = l1_runner(str(empty)).run(spec(results))
    by_id = {c["id"]: c for c in read(run_dir, "controls.json")["controls"]}
    for cid in ("C3", "P1"):
        assert [t["outcome"] for t in by_id[cid]["trials"]] == ["rejected"] * 3, by_id[cid]
        assert by_id[cid]["passed"] is True
    p1 = [c for sub, c in seen if sub == "prove" and c is not True and c is not False]
    assert p1 == [{"id": "P1", "perturbation": record["perturbation"]}] * 3


def test_model_controls_without_perturb_are_not_applicable(tmp_path: Path) -> None:
    """A stored perturb_model commitment does not stand in for the adapter's perturb."""
    empty = tmp_path / "no-strace"
    empty.mkdir()
    run_dir = level_runner(str(empty)).run(spec(tmp_path / "r"))
    by_id = {c["id"]: c for c in read(run_dir, "controls.json")["controls"]}
    for cid in ("C3", "P1"):
        assert by_id[cid]["outcome"] == "not_applicable"
        assert "lists no perturb subcommand" in by_id[cid]["note"]


def test_c1_through_mutate_reply_verifies_the_honest_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "no-strace"
    empty.mkdir()
    seen = spy_calls(monkeypatch)
    run_dir = l1_runner(str(empty)).run(spec(tmp_path / "r"))
    c1 = next(c for c in read(run_dir, "controls.json")["controls"] if c["id"] == "C1")
    assert [t["outcome"] for t in c1["trials"]] == ["rejected"] * 6  # first and last
    assert c1["trials"][0]["mutation"]["mutated"] == {"parts": ["body.bin"],
                                                      "fields": ["reply[0]"]}  # fmt: skip
    assert sum(sub == "mutate_reply" for sub, _ in seen) == 6
    broken = l1_runner(str(empty), "fake-broken").run(spec(tmp_path / "b", "fake-broken"))
    c1 = next(c for c in read(broken, "controls.json")["controls"] if c["id"] == "C1")
    assert (c1["outcome"], c1["passed"]) == ("accepted", False)


def test_reject_made_by_adapter_code_is_void(tmp_path: Path) -> None:
    """AD-6: upstream's verifier exited 0 and the adapter's own comparison refused: void."""
    t = target()

    def verify(call: VerifyCall) -> VerifyResult:
        if call.control_id == "twin":
            return VerifyResult("accept", 0, "ok", 0.1)
        return VerifyResult("reject", 0, "claimed_output is not the ids the proof states", 0.1)

    series = [Series({"position": "first"}, lambda k: [VerifyCall("C1", k, "c", t.request,
                     t.claimed_output, tmp_path, (), {})], adapter_reject_void=True)]  # fmt: skip
    record = level_control_record("C1", series, lambda: twin_of(t), verify)
    trials = record["trials"]
    assert isinstance(trials, list)
    assert len(trials) == 10
    assert all(x["outcome"] == "void" and x["detail"]["decided_by"] == "adapter" for x in trials)
    assert (record["outcome"], record["passed"]) == ("void", None)


def test_c1_part_on_a_verifier_host_mutates_on_the_verifier_cpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-6: `mutate_reply` takes neither weights nor a GPU, so a verifier host (no prover
    CPUs) runs C1's split part; it once failed every trial with "binds no prover CPUs"."""
    from iproofs.provenance import Host  # noqa: PLC0415
    from iproofs.runner import VerifierEnvironment, controls_for_run, draw_seed  # noqa: PLC0415

    empty = tmp_path / "no-strace"
    empty.mkdir()
    kept = l1_runner(str(empty))
    kept.keep_io = True
    run_dir = kept.run(spec(tmp_path / "r", controls=False))
    draw_seed(REGISTRY, run_dir, control_seed=SEED)
    host = Host(ROOT / "harness/tests/fixtures/host", run=lambda _: None, hosted=True)
    verifier_host = l1_runner(str(empty))
    verifier_host.env = VerifierEnvironment(host, 3)
    seen = spy_calls(monkeypatch)
    part = read(run_dir, controls_for_run(verifier_host, run_dir, only=["C1"]).name)
    c1 = part["controls"][0]
    assert [t["outcome"] for t in c1["trials"]] == ["rejected"] * 6  # first and last
    assert sum(sub == "mutate_reply" for sub, _ in seen) == 6


def test_control_run_proves_one_batch_and_is_marked_control(tmp_path: Path) -> None:
    """RFC-0018 CH-1b: a control run proves the slot's first prompt at batch 1, records
    `control: true` in run.json and manifest.json, and runs the control suite."""
    path = f"{fake_strace(tmp_path / 'bin')}{os.pathsep}{os.environ['PATH']}"
    runner = level_runner(path)
    runner.control_run = True
    run_dir = runner.run(spec(tmp_path / "results"))
    run, manifest = read(run_dir, "run.json"), read(run_dir, "manifest.json")
    assert run["status"] == "completed", run["failure"]
    assert run["control"] is True
    assert manifest["control"] is True
    assert sorted({p["request_index"] for p in run["proofs"]}) == [0]
    assert (run_dir / "controls.json").is_file()


def test_control_prove_state_is_what_commit_left(tmp_path: Path) -> None:
    """A control prove's io/state holds the entries recorded after commit, not what the run's
    own prove wrote later (FlashProve's adapter refuses an existing work directory)."""
    from iproofs.runner import STATE_AFTER_COMMIT, copy_state_after_commit  # noqa: PLC0415

    src = tmp_path / "io"
    (src / "state/commit").mkdir(parents=True)
    (src / "state/commit/isk").write_text("k")
    (src / "state/key.tar").write_text("t")
    (src / STATE_AFTER_COMMIT).write_text(json.dumps(["commit", "key.tar"]))
    (src / "state/prove/home").mkdir(parents=True)  # the run's own prove, after commit
    dst = tmp_path / "prove-P1"
    copy_state_after_commit(src, dst)
    assert sorted(p.name for p in (dst / "state").iterdir()) == ["commit", "key.tar"]
    assert (dst / "state/commit/isk").read_text() == "k"
    (src / STATE_AFTER_COMMIT).unlink()  # a run kept before the record existed: all of it
    old = tmp_path / "prove-P1-old"
    copy_state_after_commit(src, old)
    assert (old / "state/prove/home").is_dir()


def test_reverify_of_a_kept_session_on_a_verifier_host(tmp_path: Path) -> None:
    """RFC-0018 CH-4a: `iproofs reverify` verifies every proof of a kept level session again on
    a verifier host, under the trace, into reverify/ (the session's own traces untouched), once;
    a GPU host is refused."""
    from iproofs.provenance import Host  # noqa: PLC0415
    from iproofs.runner import VerifierEnvironment, reverify_run  # noqa: PLC0415

    path = f"{fake_strace(tmp_path / 'bin')}{os.pathsep}{os.environ['PATH']}"
    kept = level_runner(path)
    kept.keep_io = True
    run_dir = kept.run(spec(tmp_path / "r", controls=False))
    own = sorted(p.name for p in (run_dir / "verify-trace").iterdir())
    with pytest.raises(IProofsError, match="verifier host"):
        reverify_run(level_runner(path), run_dir)
    host = Host(ROOT / "harness/tests/fixtures/host", run=lambda _: None, hosted=True)
    verifier_host = level_runner(path)
    verifier_host.env = VerifierEnvironment(host, 3)
    record = read(run_dir, str(reverify_run(verifier_host, run_dir).relative_to(run_dir)))
    assert REGISTRY.errors("reverify/1", record) == []
    proofs = read(run_dir, "run.json")["proofs"]
    assert [p["proof_id"] for p in record["proofs"]] == [p["proof_id"] for p in proofs]
    assert {p["verdict"] for p in record["proofs"]} == {"accept"}
    for p in record["proofs"]:
        trace = read(run_dir, p["trace"])
        assert trace["tool"] == "strace"
        assert trace["gpu_visible"] is False
        assert trace["model_files_present"] is False
    assert sorted(p.name for p in (run_dir / "verify-trace").iterdir()) == own
    with pytest.raises(IProofsError, match="re-verified once"):
        reverify_run(verifier_host, run_dir)
