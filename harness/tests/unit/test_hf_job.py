"""docs/runbooks/hf-job.sh, the job script of docs/runbooks/hf-jobs.md: it refuses a checkout
that is not the asked commit, stops when the harness install fails, and always writes its log
and tries the upload on exit, without a token in the log (AGENTS.md rule 7)."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "docs/runbooks/hf-job.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git"
)


def checkout(tmp_path: Path, files: dict[str, str] | None = None) -> tuple[Path, str]:
    """A one-commit repository laid out as the job clones it: <work>/inference-proofs."""
    repo = tmp_path / "work" / "inference-proofs"
    (repo / "docs/runbooks").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "docs/runbooks/hf-job.sh")
    for rel, text in (files or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}  # fmt: skip
    for argv in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *argv], check=True, env=env)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()  # fmt: skip
    return repo, head


def log_of(repo: Path, last: str) -> str:
    """job.log once its last line is written (tee may finish just after the script)."""
    path = repo.parent / "out/job.log"
    for _ in range(50):
        text = path.read_text() if path.is_file() else ""
        if last in text:
            return text
        time.sleep(0.1)
    return text


def job(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    base = {"PATH": os.environ["PATH"], "HOME": str(repo.parent), "HF_TOKEN": "hf_secret_x"}
    return subprocess.run(["bash", str(repo / "docs/runbooks/hf-job.sh"), *args],
                          check=False, capture_output=True, text=True, timeout=60,
                          env=base | env)  # fmt: skip


def test_wrong_commit_stops_and_logs(tmp_path: Path) -> None:
    repo, _ = checkout(tmp_path)
    done = job(repo, "probe", IPROOFS_COMMIT="0" * 40)
    assert done.returncode == 2
    log = log_of(repo, "upload: skipped")
    assert "is not IPROOFS_COMMIT; stopping" in log
    assert "upload: skipped" in log  # no IPROOFS_UPLOAD
    assert "hf_secret_x" not in log + done.stdout + done.stderr


def test_failed_install_stops_after_the_probe(tmp_path: Path) -> None:
    """With the right commit the probe step runs (here it is missing, and the job goes on) and
    the install fails: the fake checkout has no lockfile. The job stops, logged."""
    repo, head = checkout(tmp_path)
    done = job(repo, "run", "sash", IPROOFS_COMMIT=head, IPROOFS_JOB_BUDGET_S="120")
    assert done.returncode != 0
    log = log_of(repo, "upload: skipped")
    assert f"commit {head}" in log
    assert "probe exit" in log
    assert "bound GPU 0" in log  # no probe.json to read: the default, never an empty --gpu
    assert "stopping" in log
    assert "hf_secret_x" not in log


def test_the_install_names_every_extra_a_run_needs() -> None:
    """gpu (NVML), fetch (fetch-model) and prompts (tokenizers: every workload's prompts are
    materialised with its tokenizer.json); stage 1 imports all three."""
    text = SCRIPT.read_text()
    assert "uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts" in text
    assert "import huggingface_hub, pynvml, tokenizers" in text


def test_upload_to_a_mounted_bucket_prunes_a_stopped_run(tmp_path: Path) -> None:
    """A run stopped at the deadline leaves io/ (a weights copy), scratch directories and the
    commitment store (a prover key) in its staging directory: they never leave the job; its logs
    and lock do, with job.log and the probe, into a folder of the mounted bucket."""
    repo, _ = checkout(tmp_path)
    staging = repo.parent / "out/dev-results/v0.1/flashprove/.staging-r1"
    for part in ("io/fit", "prover-ro", "verify", "controls-io", "commitment/prover", "logs"):
        (staging / part).mkdir(parents=True)
    (staging / "io/fit/weights.bin").write_bytes(b"w" * 1024)
    (staging / "commitment/prover/isk.tar").write_bytes(b"k")
    (staging / "logs/harness.jsonl").write_text("{}\n")
    (staging / "job.lock").write_text("{}")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    done = job(repo, "probe", IPROOFS_COMMIT="0" * 40, IPROOFS_UPLOAD_DIR=str(bucket),
               IPROOFS_LABEL="probe-x")  # fmt: skip
    assert done.returncode == 2
    log = log_of(repo, "upload: done")
    assert "upload bucket" not in log  # the commit check comes first
    assert "prune: " in log
    assert ".staging-r1/commitment" in log
    (folder,) = (bucket / "runs").iterdir()
    assert folder.name.endswith("-probe-x")
    copied = folder / "dev-results/v0.1/flashprove/.staging-r1"
    assert (copied / "logs/harness.jsonl").is_file()
    assert (copied / "job.lock").is_file()
    for part in ("io", "prover-ro", "verify", "controls-io", "commitment"):
        assert not (copied / part).exists(), part
    assert (folder / "job.log").is_file()
    assert "hf_secret_x" not in (folder / "job.log").read_text() + log


def test_development_run_keeps_io(tmp_path: Path) -> None:
    """A development install's io holds the engine's responses and log, never weights (the
    adapter reads /models from the cache): a stopped run keeps it for the capture, and still
    drops the scratch directories and the commitment store."""
    repo, _ = checkout(tmp_path)
    staging = repo.parent / "out/dev-results/v0.1/ref-serve/.staging-r1"
    for part in ("io", "verify", "commitment"):
        (staging / part).mkdir(parents=True)
    (staging / "io/responses.jsonl").write_text("{}\n")
    weights = repo.parent / "out/dev-results/v0.1/other/.staging-r2/io"
    weights.mkdir(parents=True)
    (weights / "fit.gguf").write_bytes(b"w")  # another system's io with a weights file
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    done = job(repo, "probe", IPROOFS_COMMIT="0" * 40, IPROOFS_UPLOAD_DIR=str(bucket),
               IPROOFS_DEV_IMAGE=DEV_IMAGE)  # fmt: skip
    assert done.returncode == 2
    log = log_of(repo, "upload: done")
    assert ".staging-r1/io (development run)" in log
    assert "prune: io of a development run holds io/fit.gguf: not kept" in log
    (folder,) = (bucket / "runs").iterdir()
    copied = folder / "dev-results/v0.1/ref-serve/.staging-r1"
    assert (copied / "io/responses.jsonl").is_file()
    assert not (copied / "verify").exists()
    assert not (copied / "commitment").exists()
    assert not (folder / "dev-results/v0.1/other/.staging-r2/io").exists()


def test_development_run_installs_and_passes_the_engine_image() -> None:
    """IPROOFS_DEV_IMAGE: the system's dev_install.py from the checkout, then every run with
    `--image` (recorded as local/<image>) and `--keep-io`; uv from its pinned, checked release
    only for such a run."""
    text = SCRIPT.read_text()
    assert 'python3 "systems/$SYSTEM/dev_install.py" "$IPROOFS_DEV_IMAGE"' in text
    assert 'image_args=(--image "$IPROOFS_DEV_IMAGE" --keep-io)' in text
    assert '${image_args[@]+"${image_args[@]}"}' in text
    assert "sha256sum -c --quiet" in text
    assert "if ! command -v uv >/dev/null; then" in text


DEV_IMAGE = "docker.io/vllm/vllm-openai@sha256:" + "a" * 64

# Stand-ins for the tools hf-job.sh calls, each logging its arguments to $STUB_LOG: uv, the
# harness's python and iproofs, the system's dev_install.py, and huggingface_hub's HfApi.
STUB_UV = """#!/usr/bin/env bash
echo "uv $*" >> "$STUB_LOG"
"""
STUB_PYTHON = """#!/usr/bin/env bash
echo "python $*" >> "$STUB_LOG"
if [ "${1:-}" = - ] && [ $# -gt 1 ]; then cat > /dev/null; exit 0; fi  # the binding check
case "${2:-}" in
  *shm_gib_min*) echo "${STUB_SHM_NEED:-0}"; exit 0 ;;  # the profile's PC-SHM minimum
  *record_for*) echo "${STUB_RECORD:-}"; exit 0 ;;  # the serving record of a serve-role step
esac
exec "$STUB_REAL_PYTHON" "$@"  # the extras' import and the dataset upload, on stub modules
"""
STUB_IPROOFS = """#!/usr/bin/env bash
echo "iproofs $*" >> "$STUB_LOG"
[ "${1:-}" = machine-record ] && echo '{}'
exit 0
"""
STUB_DEV_INSTALL = """import os, sys
with open(os.environ["STUB_LOG"], "a") as f:
    f.write("dev_install " + " ".join(sys.argv[1:]) + "\\n")
rc = "STUB_TOK_RC" if sys.argv[1:2] == ["--tokenizer-check"] else "STUB_DEV_RC"
sys.exit(int(os.environ.get(rc, "0")))
"""
STUB_HF = """import json, os
class HfApi:
    def upload_folder(self, **kw):
        with open(os.environ["STUB_HF_LOG"], "a") as f:
            f.write(json.dumps(kw) + "\\n")
"""


def stubbed(tmp_path: Path) -> tuple[Path, str, dict[str, str]]:
    """A checkout with a stub dev_install.py for ref-serve, the stubs, and their env."""
    repo, head = checkout(tmp_path, {"systems/ref-serve/dev_install.py": STUB_DEV_INSTALL})
    bin_dir, venv, mods = tmp_path / "bin", repo / ".venv/bin", tmp_path / "mods"
    for path, text in ((bin_dir / "uv", STUB_UV), (venv / "python", STUB_PYTHON),
                       (venv / "iproofs", STUB_IPROOFS)):  # fmt: skip
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)
    for name, text in (("huggingface_hub", STUB_HF), ("pynvml", ""), ("tokenizers", "")):
        (mods / name).mkdir(parents=True)
        (mods / name / "__init__.py").write_text(text)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "PYTHONPATH": str(mods),
           "STUB_LOG": str(tmp_path / "stub.log"), "STUB_HF_LOG": str(tmp_path / "hf.log"),
           "STUB_REAL_PYTHON": sys.executable, "IPROOFS_DEV_IMAGE": DEV_IMAGE}  # fmt: skip
    return repo, head, env


def calls(tmp_path: Path) -> list[str]:
    path = tmp_path / "stub.log"
    return path.read_text().splitlines() if path.is_file() else []


def test_development_run_installs_then_runs_with_the_engine_image(tmp_path: Path) -> None:
    """IPROOFS_DEV_IMAGE: after the binding check, the system's dev_install.py with the image
    and the bound GPU (it checks the engine there), then fetch-model, then every run with
    `--image <image> --keep-io`; uv is not downloaded when the image has one."""
    repo, head, env = stubbed(tmp_path)
    done = job(repo, "run", "ref-serve", "fp-maverick-w1024-b1:1", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="5000", **env)  # fmt: skip
    log = log_of(repo, "upload: skipped")
    assert done.returncode == 0, log
    seen = calls(tmp_path)
    binding = seen.index("python - 0 prover-h200-hosted v0.1")
    install = seen.index(f"dev_install {DEV_IMAGE} 0")
    fetch = seen.index("iproofs fetch-model fp-maverick-w1024-b1")
    (run,) = [c for c in seen if c.startswith("iproofs run ")]
    assert binding < install < fetch < seen.index(run)
    assert run.endswith(f"--allow-nonconforming --results {repo.parent}/out/dev-results"
                        f" --image {DEV_IMAGE} --keep-io")  # fmt: skip
    assert "--system ref-serve --workload fp-maverick-w1024-b1" in run
    assert "uv: not in the image" not in log


def test_failed_development_install_stops_before_the_weights(tmp_path: Path) -> None:
    repo, head, env = stubbed(tmp_path)
    done = job(repo, "run", "ref-serve", "fp-maverick-w1024-b1:1", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="5000", STUB_DEV_RC="1", **env)  # fmt: skip
    assert done.returncode == 3
    log = log_of(repo, "upload: skipped")
    assert "engine check failed" in log
    assert f"dev_install {DEV_IMAGE} 0" in calls(tmp_path)
    assert not [c for c in calls(tmp_path) if c.startswith(("iproofs fetch-model", "iproofs run"))]


@pytest.mark.parametrize("dev", [True, False])
def test_dataset_upload_keeps_io_only_for_a_development_run(tmp_path: Path, dev: bool) -> None:
    """The fallback upload (a dataset) sends a development run's kept io/ as the bucket copy
    does; for any other run io/ never leaves the job."""
    repo, _, env = stubbed(tmp_path)
    if not dev:
        del env["IPROOFS_DEV_IMAGE"]
    staging = repo.parent / "out/dev-results/v0.1/ref-serve/.staging-r1"
    (staging / "io").mkdir(parents=True)
    (staging / "io/responses.jsonl").write_text("{}\n")
    done = job(repo, "probe", IPROOFS_COMMIT="0" * 40, IPROOFS_UPLOAD="ns/ds", **env)
    assert done.returncode == 2
    log_of(repo, "upload: done")
    first, runs = (json.loads(x) for x in (tmp_path / "hf.log").read_text().splitlines())
    assert first["allow_patterns"] == ["*.json", "job.log", "controls/**"]
    assert ("**/.staging-*/io/**" in runs["ignore_patterns"]) is not dev
    assert "**/.staging-*/commitment/**" in runs["ignore_patterns"]


def test_serving_profile_binds_every_gpu(tmp_path: Path) -> None:
    """RFC-0006 R6: IPROOFS_PROFILE=serving-h200x4-hosted binds GPUs 0 to 3 for the binding
    check, the self-test, the development install's engine check and every run (`--gpus`)."""
    repo, head, env = stubbed(tmp_path)
    done = job(repo, "run", "ref-serve", "fp-maverick-w1024-b24:1", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="5000", IPROOFS_PROFILE="serving-h200x4-hosted",
               **env)  # fmt: skip
    log = log_of(repo, "upload: skipped")
    assert done.returncode == 0, log
    seen = calls(tmp_path)
    assert "python - 0,1,2,3 serving-h200x4-hosted v0.1" in seen
    assert f"dev_install {DEV_IMAGE} 0,1,2,3" in seen
    (record,) = [c for c in seen if c.startswith("iproofs machine-record")]
    assert "--hosted --gpus 0,1,2,3 " in record
    (run,) = [c for c in seen if c.startswith("iproofs run ")]
    assert "--profile serving-h200x4-hosted --hosted --gpus 0,1,2,3 " in run
    assert "profile serving-h200x4-hosted; bound GPUs 0,1,2,3" in log


def test_step_fields_high_and_replay(tmp_path: Path) -> None:
    """A step's `:high` is a high-load production-serving job and `:from=DIR` replays the run
    DIR of the mounted bucket (RFC-0015 SRV-1, SRV-8); an unknown field stops the job."""
    repo, head, env = stubbed(tmp_path)
    step = "fp-maverick-w1024-b24:1:high:from=runs/t/dev-results/v0.1/flashprove/r1"
    done = job(repo, "run", "ref-serve", step, IPROOFS_COMMIT=head, IPROOFS_JOB_BUDGET_S="5000",
               IPROOFS_PROFILE="serving-h200x4-hosted", IPROOFS_GPUS="4,5,6,7", **env)  # fmt: skip
    assert done.returncode == 0, log_of(repo, "upload: skipped")
    (run,) = [c for c in calls(tmp_path) if c.startswith("iproofs run ")]
    assert "--gpus 4,5,6,7 " in run
    assert "--load high --prompts-from /upload/runs/t/dev-results/v0.1/flashprove/r1" in run
    repo2, head2, env2 = stubbed(tmp_path / "again")
    bad = job(repo2, "run", "ref-serve", "fp-maverick-w1024-b24:1:fast", IPROOFS_COMMIT=head2,
              IPROOFS_JOB_BUDGET_S="5000", **env2)  # fmt: skip
    assert bad.returncode == 2
    assert "unknown step field fast" in log_of(repo2, "upload: skipped")


def test_step_field_sizing_with_replay(tmp_path: Path) -> None:
    """A step's `:sizing=N` is a matched sizing capture of N batches (`--sizing-batches N`,
    RFC-0015 SRV-1), and it composes with `:from=DIR` (SRV-8)."""
    repo, head, env = stubbed(tmp_path)
    step = "sash-l31-8b-c1024:1:sizing=50:from=runs/t/dev-results/v0.1/sash/r1"
    done = job(repo, "run", "ref-serve", step, IPROOFS_COMMIT=head, IPROOFS_JOB_BUDGET_S="5000",
               IPROOFS_PROFILE="serving-h200x1-hosted", IPROOFS_GPUS="0", **env)  # fmt: skip
    assert done.returncode == 0, log_of(repo, "upload: skipped")
    (run,) = [c for c in calls(tmp_path) if c.startswith("iproofs run ")]
    assert "--workload sash-l31-8b-c1024 " in run
    assert "--sizing-batches 50 --prompts-from /upload/runs/t/dev-results/v0.1/sash/r1" in run
    assert "--load" not in run


def test_serving_shm_below_the_profile_stops_before_the_weights(tmp_path: Path) -> None:
    """RFC-0006 PC-SHM on a serving profile of several GPUs: /dev/shm below `shm_gib_min` (or
    unread) stops the job before any weights are fetched; a 1-GPU profile needs none."""
    repo, head, env = stubbed(tmp_path)
    done = job(repo, "run", "ref-serve", "fp-maverick-w1024-b24:1", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="5000", IPROOFS_PROFILE="serving-h200x4-hosted",
               STUB_SHM_NEED=str(10**18), **env)  # fmt: skip
    assert done.returncode == 3
    assert "stopping before any weights" in log_of(repo, "upload: skipped")
    assert not [c for c in calls(tmp_path) if c.startswith(("iproofs fetch-model", "iproofs run"))]


def test_serving_record_tokenizer_check_then_one_fetch(tmp_path: Path) -> None:
    """A serve-role step's record: its files without the weights and the engine's tokenizer
    load first, then the weights once; a later step on the same record fetches nothing (the
    run rehashes them). A failed tokenizer check fetches no weights."""
    repo, head, env = stubbed(tmp_path)
    steps = ("fp-maverick-w1024-b24:1", "fp-maverick-w1024-b24:1:high")
    done = job(repo, "run", "ref-serve", *steps, IPROOFS_COMMIT=head, IPROOFS_JOB_BUDGET_S="5000",
               IPROOFS_PROFILE="serving-h200x4-hosted", STUB_RECORD="rec", **env)  # fmt: skip
    log = log_of(repo, "upload: skipped")
    assert done.returncode == 0, log
    seen = calls(tmp_path)
    small = f"{repo.parent}/no-weights/rec"
    order = [seen.index(f"iproofs fetch-model --serving rec --no-weights {small}"),
             seen.index(f"dev_install --tokenizer-check {small}"),
             seen.index("iproofs fetch-model --serving rec")]  # fmt: skip
    assert order == sorted(order)
    assert [c for c in seen if c.startswith("iproofs fetch-model")] == [
        f"iproofs fetch-model --serving rec --no-weights {small}",
        "iproofs fetch-model --serving rec",
    ]
    assert len([c for c in seen if c.startswith("iproofs run ")]) == 2
    assert "done by an earlier step; the run rehashes it" in log
    repo2, head2, env2 = stubbed(tmp_path / "again")
    bad = job(repo2, "run", "ref-serve", steps[0], IPROOFS_COMMIT=head2,
              IPROOFS_JOB_BUDGET_S="5000", STUB_RECORD="rec", STUB_TOK_RC="1", **env2)  # fmt: skip
    assert bad.returncode == 1
    assert "the tokenizer check of rec failed" in log_of(repo2, "upload: skipped")
    seen = calls(tmp_path / "again")
    assert "iproofs fetch-model --serving rec" not in seen
    assert not [c for c in seen if c.startswith("iproofs run ")]


def test_keep_io_is_refused_for_flashprove_before_the_probe(tmp_path: Path) -> None:
    """keep-io uploads io/ and the commitment store; FlashProve's hold a weights copy and the
    prover's secret key, so the step is refused before anything is installed."""
    repo, head = checkout(tmp_path)
    done = job(repo, "run", "flashprove", "fp-maverick-w1024-b1:1:controls:keep-io",
               IPROOFS_COMMIT=head)  # fmt: skip
    assert done.returncode == 2
    log = log_of(repo, "upload: skipped")
    assert "keep-io is refused for flashprove" in log
    assert "probe exit" not in log


RUN_PATH = "runs/x/dev-results/v0.1/sash/r-1"


def stored(bucket: Path, *, done: bool = True, kept: bool = True, seed: bool = True) -> Path:
    """A run stored in the bucket by a keep-io job: run.json, manifest.json, io/proofs and
    commitment/, its folder's upload.done, and the split suite's seed record."""
    run = bucket / RUN_PATH
    for part in ("io/proofs", "commitment") if kept else ():
        (run / part).mkdir(parents=True)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run.json").write_text("{}")
    (run / "manifest.json").write_text("{}")
    if done:
        (bucket / "runs/x/upload.done").write_text("dev-results bytes 1\n")
    if seed:
        (run / "controls-seed.json").write_text('{"control_seed": "0x0000000000000001"}')
    return run


@pytest.mark.parametrize(
    ("mode", "args", "setup", "message"),
    [
        ("controls", ["sash", RUN_PATH], {}, "usage: hf-job.sh controls"),
        ("controls", ["sash", RUN_PATH, "C1"], None, "set IPROOFS_UPLOAD_DIR"),
        (
            "controls",
            ["sash", RUN_PATH.replace("sash", "flashprove"), "C1"],
            {},
            "RUN_PATH must be",
        ),
        ("controls", ["sash", "runs/y/dev-results/v0.1/sash/r-1", "C1"], {}, "no stored run at"),
        ("controls", ["sash", RUN_PATH, "C1"], {"done": False}, "did not finish (no upload.done)"),
        ("controls", ["sash", RUN_PATH, "C1"], {"kept": False}, "no kept run at"),
        ("controls", ["sash", RUN_PATH, "C1"], {"seed": False}, "draw it once with hf-job.sh seed"),
        ("controls", ["sash", RUN_PATH, "C1,C9"], {}, "unknown control id 'C9'"),
        ("controls", ["sash", RUN_PATH, "sash-unsound-x"], {}, "unknown control id"),
        ("seed", ["sash"], {}, "usage: hf-job.sh seed SYSTEM RUN_PATH"),
        ("seed", ["sash", RUN_PATH], {}, "already has controls-seed.json"),
        ("merge", ["sash", RUN_PATH], {"seed": False}, "no part can have run"),
    ],
)
def test_stored_run_modes_refuse_before_the_probe(
    tmp_path: Path, mode: str, args: list[str], setup: dict[str, bool] | None, message: str
) -> None:
    """seed, controls and merge read a run kept with keep-io from the mounted bucket; what they
    cannot use is refused before the probe, the install and any copy."""
    repo, head = checkout(tmp_path)
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    if setup is not None:
        stored(bucket, **setup)
    env = {"IPROOFS_UPLOAD_DIR": str(bucket)} if setup is not None else {}
    done = job(repo, mode, *args, IPROOFS_COMMIT=head, **env)
    assert done.returncode == 2
    log = log_of(repo, "upload:")
    assert message in log
    assert "probe exit" not in log
    assert "install the harness" not in log


def test_a_controlled_run_is_never_controlled_again(tmp_path: Path) -> None:
    repo, head = checkout(tmp_path)
    bucket = tmp_path / "bucket"
    (stored(bucket) / "controls.json").write_text("{}")
    for mode, args in (("controls", ["C1"]), ("seed", []), ("merge", [])):
        done = job(repo, mode, "sash", RUN_PATH, *args, IPROOFS_COMMIT=head,
                   IPROOFS_UPLOAD_DIR=str(bucket))  # fmt: skip
        assert done.returncode == 2
        assert "already has controls.json" in log_of(repo, "upload:")


def test_controls_knows_the_system_controls(tmp_path: Path) -> None:
    """The ids of systems/<system>/controls.yaml are accepted before the probe; the job then
    goes on to the probe (absent here) and the install, which fails in this checkout."""
    repo, head = checkout(tmp_path)
    (repo / "systems/sash").mkdir(parents=True)
    shutil.copy(ROOT / "systems/sash/controls.yaml", repo / "systems/sash/controls.yaml")
    bucket = tmp_path / "bucket"
    stored(bucket)
    done = job(repo, "controls", "sash", RUN_PATH, "C1,sash-unsound-skip-argmax",
               IPROOFS_COMMIT=head, IPROOFS_UPLOAD_DIR=str(bucket))  # fmt: skip
    assert done.returncode == 3
    log = log_of(repo, "upload:")
    assert "unknown control id" not in log
    assert "probe exit" in log


def test_controls_part_and_logs_are_uploaded(tmp_path: Path) -> None:
    """What a controls job leaves in out/controls (its part and the run's logs) goes to the
    bucket with the small files, before the run directories; a complete upload ends with
    upload.done."""
    repo, _ = checkout(tmp_path)
    part = repo.parent / "out/controls/controls-part-0000000000000001-abcdefabcdef.json"
    part.parent.mkdir(parents=True)
    part.write_text("{}")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    done = job(repo, "probe", IPROOFS_COMMIT="0" * 40, IPROOFS_UPLOAD_DIR=str(bucket))
    assert done.returncode == 2
    log_of(repo, "upload: done")
    (folder,) = (bucket / "runs").iterdir()
    assert (folder / "controls" / part.name).is_file()
    assert (folder / "upload.done").read_text().startswith("dev-results bytes ")


def test_keep_io_uploads_the_run_without_the_archive_copy(tmp_path: Path) -> None:
    """With keep-io, io/proofs holds the proof that .archive/ holds again as a tar: the upload
    leaves the tar out, logs its size, and copies the self-test record and the run."""
    repo, head = checkout(tmp_path)
    dev = repo.parent / "out/dev-results"
    (dev / ".archive/v0.1/sash").mkdir(parents=True)
    (dev / ".archive/v0.1/sash/r-1-p.tar").write_bytes(b"t" * 2048)
    (dev / "v0.1/sash/r-1/io/proofs/p").mkdir(parents=True)
    (dev / "v0.1/sash/r-1/io/proofs/p/part.bin").write_bytes(b"p" * 2048)
    (dev / ".selftest.json").write_text("{}")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    done = job(repo, "run", "sash", "sash-l31-8b-c1024:1:keep-io", IPROOFS_COMMIT=head,
               IPROOFS_UPLOAD_DIR=str(bucket))  # fmt: skip
    assert done.returncode == 3  # the install fails in this checkout; the upload still runs
    log = log_of(repo, "upload: done")
    assert "upload: .archive left out" in log
    (folder,) = (bucket / "runs").iterdir()
    assert (folder / "dev-results/v0.1/sash/r-1/io/proofs/p/part.bin").is_file()
    assert (folder / "dev-results/.selftest.json").is_file()
    assert not (folder / "dev-results/.archive").exists()
    assert (folder / "upload.done").is_file()


def test_the_controls_step_runs_one_part_in_this_container() -> None:
    text = SCRIPT.read_text()
    assert '"$IP" controls "$RUN" --hosted "${extra[@]}"' in text
    assert '--provider "$PROVIDER" --only "$IDS" --seed "$SEED"' in text
    assert 'SEED=$(record_seed "$READ_FROM/controls-seed.json")' in text  # never typed
    assert 'extra=(--gpu "$GPU")' in text  # prover-side ids bind the GPU; none: a verifier host
    assert "keep-io) extra+=(--keep-io) ;;" in text
    assert '"$IP" controls "$LOCAL" --draw-seed' in text
    assert '"$IP" controls "$LOCAL" --merge "${parts[@]}"' in text


@pytest.mark.parametrize("profile", ["prover-h200-hosted", "serving-h200x4-hosted"])
def test_every_job_uploads_through_the_bucket_api(tmp_path: Path, profile: str) -> None:
    """With HF_TOKEN and IPROOFS_UPLOAD_BUCKET, a production-serving job uploads as a prover
    job does: `hf buckets sync` twice (the records first), then the check file by file; the
    mounted bucket, still there for --prompts-from, gets no copy."""
    repo, head, env = stubbed(tmp_path)
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    done = job(repo, "run", "ref-serve", "fp-maverick-w1024-b24:1", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="2000", IPROOFS_PROFILE=profile,
               IPROOFS_UPLOAD_BUCKET="ns/b", IPROOFS_UPLOAD_DIR=str(bucket),
               IPROOFS_LABEL="serving-x", **env)  # fmt: skip
    log = log_of(repo, "upload: FAILED or incomplete")
    assert done.returncode == 0, log
    syncs = [c for c in calls(tmp_path) if " hf buckets sync " in c]
    assert len(syncs) == 2, syncs
    assert all(" hf://buckets/ns/b/runs/" in c and "-serving-x " in c for c in syncs)
    assert "--exclude */io/*" in syncs[0]
    assert [c for c in calls(tmp_path) if " hf buckets ls ns/b --recursive" in c]
    assert "upload: out/ through the bucket API" in log
    assert "upload: out/ to the mounted bucket" not in log
    assert not (bucket / "runs").exists() or not any((bucket / "runs").iterdir())
    assert "hf_secret_x" not in log


def test_runbook_helpers_upload_alike() -> None:
    """docs/runbooks/hf-jobs.md: the prover and the serving job helpers both pass the secrets
    file and IPROOFS_UPLOAD_BUCKET, so every job takes the checked API upload; S2 replays a b24
    run that records the batch-membership steady rule."""
    text = (ROOT / "docs/runbooks/hf-jobs.md").read_text()
    flags = ('--secrets-file "$HOME/.config/iproofs/hf-job.secrets" '
             '-e IPROOFS_UPLOAD_BUCKET="$NS/iproofs-dev-runs"')  # fmt: skip
    for helper in ("iproofs_job() {", "iproofs_serving_job() {"):
        body = text[text.index(helper) : text.index("\n}\n", text.index(helper))]
        assert flags in body, helper
    assert '"fp-maverick-w1024-b24:1:from=$FP_B24_RUN"' in text
    assert '"sash-l31-8b-c1024:1:from=$SASH_RUN"' in text
    assert '"sash-l31-8b-c1024:1:sizing=50:from=$SASH_RUN"' in text  # RFC-0015 SRV-1, Q10
    assert '"sash-l31-8b-c1024:3:from=$SASH_RUN"' in text
    assert '["workload"].get("steady_rule")' in text


def test_keep_io_sends_each_released_proof_and_retries_a_failed_upload(tmp_path: Path) -> None:
    """keep-io through the bucket API: a released proof (io/proofs/<id>) goes up on its own,
    under the run id, while one not yet released (.tmp-<id>) does not; a failed upload is tried
    again every IPROOFS_UPLOAD_RETRY_S until IPROOFS_UPLOAD_RETRY_STOP_S before the budget ends
    (10 min and 30 min in a job; seconds here)."""
    repo, head, env = stubbed(tmp_path)
    del env["IPROOFS_DEV_IMAGE"]
    staging = repo.parent / "out/dev-results/v0.1/sash/.staging-r-1/io/proofs"
    (staging / "req-0").mkdir(parents=True)
    (staging / "req-0/part.bin").write_bytes(b"p")
    (staging / ".tmp-req-1").mkdir()
    done = job(repo, "run", "sash", "sash-l31-8b-c1024:1:keep-io", IPROOFS_COMMIT=head,
               IPROOFS_JOB_BUDGET_S="4300", IPROOFS_UPLOAD_BUCKET="ns/b",
               IPROOFS_UPLOAD_RETRY_S="1", IPROOFS_UPLOAD_RETRY_STOP_S="4296",
               IPROOFS_LABEL="kept", **env)  # fmt: skip
    log = log_of(repo, "upload: FAILED or incomplete")
    assert done.returncode == 0, log
    syncs = [c for c in calls(tmp_path) if " hf buckets sync " in c]
    proof = [c for c in syncs if "/io/proofs/" in c]
    assert len(proof) == 1, proof
    assert proof[0].split()[-2].endswith("/dev-results/v0.1/sash/r-1/io/proofs/req-0")
    assert "-kept/dev-results/" in proof[0]
    assert "upload: proof r-1/req-0 sent" in log
    assert "upload: large files FAILED; next try in 1 s" in log  # the stub bucket lists nothing
    assert "upload: large files FAILED; no time left for another try" in log
