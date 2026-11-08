"""docs/runbooks/hf-job.sh, the job script of docs/runbooks/hf-jobs.md: it refuses a checkout
that is not the asked commit, stops when the harness install fails, and always writes its log
and tries the upload on exit, without a token in the log (AGENTS.md rule 7)."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "docs/runbooks/hf-job.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git"
)


def checkout(tmp_path: Path) -> tuple[Path, str]:
    """A one-commit repository laid out as the job clones it: <work>/inference-proofs."""
    repo = tmp_path / "work" / "inference-proofs"
    (repo / "docs/runbooks").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "docs/runbooks/hf-job.sh")
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


@pytest.mark.parametrize(
    ("args", "bucket", "message"),
    [
        (["sash", RUN_PATH, "0x1"], True, "usage: hf-job.sh controls"),
        (["sash", RUN_PATH, "0x1", "C1"], False, "set IPROOFS_UPLOAD_DIR"),
        (["sash", RUN_PATH.replace("sash", "flashprove"), "0x1", "C1"], True, "RUN_PATH must be"),
        (["sash", RUN_PATH, "0x1", "C1"], True, "no kept run at"),
    ],
)
def test_controls_refuses_before_the_probe(
    tmp_path: Path, args: list[str], bucket: bool, message: str
) -> None:
    """A controls job reads a run kept with keep-io from the mounted bucket; what it cannot
    run is refused before the probe, the install and any copy."""
    repo, head = checkout(tmp_path)
    (tmp_path / "bucket").mkdir()
    env = {"IPROOFS_UPLOAD_DIR": str(tmp_path / "bucket")} if bucket else {}
    done = job(repo, "controls", *args, IPROOFS_COMMIT=head, **env)
    assert done.returncode == 2
    log = log_of(repo, "upload:")
    assert message in log
    assert "probe exit" not in log


def test_controls_part_and_logs_are_uploaded(tmp_path: Path) -> None:
    """What a controls job leaves in out/controls (its part and the run's logs) goes to the
    bucket with the small files, before the run directories."""
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


def test_the_controls_step_runs_one_part_in_this_container() -> None:
    text = SCRIPT.read_text()
    assert '"$IP" controls "$RUN" --hosted "${extra[@]}"' in text
    assert '--only "$IDS" --seed "$SEED"' in text
    assert 'extra=(--gpu "$GPU")' in text  # prover-side ids bind the GPU; none: a verifier host
    assert 'has_opt "${opts:-}" keep-io && extra+=(--keep-io)' in text
