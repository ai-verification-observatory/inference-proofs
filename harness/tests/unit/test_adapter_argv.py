import json
import re
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner, StepResult, check_image, docker_create_argv
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import AdapterOut
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64
FAKE = ROOT / "systems/fake"
JOB = {
    "schema": "adapter-job/1",
    "contract": "adapter/1",
    "run_id": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
    "workload": {"id": "fake-tiny-ci", "version": 1},
    "shape": {
        "prompt_tokens": 8,
        "output_tokens": 1,
        "batch_size": 2,
        "batches_per_session": 3,
        "context_window": 8,
    },
    "control": False,
}


def argv(subcommand: str, **kw: object) -> list[str]:
    args: dict[str, object] = {
        "models_dir": Path("/srv/models"),
        "gpu": 0,
        "cpuset": "0-23",
        "mems": "0",
        "memory": None,
        **kw,
    }
    return docker_create_argv(IMAGE, subcommand, Path("/srv/io"), **args)  # type: ignore[arg-type]


def test_docker_argv_isolation_flags() -> None:
    a = " ".join(argv("prove"))
    for flag in [
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--pids-limit 4096",
        "--user 10001:10001",
        "--cpuset-cpus 0-23",
        "--cpuset-mems 0",
        "--tmpfs /tmp:rw,",
        "-v /srv/io:/io:rw",
        "-v /srv/models:/models:ro",
        "--gpus device=0",
    ]:
        assert flag in a, flag
    assert a.endswith(f"{IMAGE} prove /io/job.json /io/out.json")
    verify = " ".join(argv("verify"))
    assert "--gpus" not in verify
    assert "/models" not in verify  # a verifier never sees the weights
    assert "--memory 32g" in verify


def test_mounts_are_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative path after -v is a named volume to docker, not a host directory."""
    monkeypatch.chdir(tmp_path)
    a = docker_create_argv(
        IMAGE,
        "prove",
        Path("results/io"),
        models_dir=Path("m"),
        gpu=None,
        cpuset="0",
        mems="0",
        memory=None,
    )
    mounts = [a[i + 1] for i, x in enumerate(a) if x == "-v"]
    assert mounts == [
        f"{tmp_path.resolve()}/results/io:/io:rw",
        f"{tmp_path.resolve()}/m:/models:ro",
    ]


def test_local_image_goes_to_docker_by_id() -> None:
    image_id = "sha256:" + "b" * 64
    a = docker_create_argv(
        f"local/fake@{image_id}",
        "info",
        Path("/srv/io"),
        models_dir=None,
        gpu=None,
        cpuset="0",
        mems="0",
        memory=None,
    )
    assert a[-4:] == [image_id, "info", "/io/job.json", "/io/out.json"]


def test_no_gpu_without_index() -> None:
    assert "--gpus" not in argv("commit", gpu=None)


def test_tag_only_image_rejected() -> None:
    for bad in ["ghcr.io/example/iproofs-fake:latest", "iproofs-fake", "x@sha256:abc"]:
        with pytest.raises(IProofsError) as e:
            check_image(bad)
        assert e.value.kind is ErrorKind.CONFIG


def run_fake(
    tmp_path: Path, entrypoint: Path, subcommand: str, job: dict[str, object]
) -> StepResult:
    (tmp_path / "job.json").write_text(json.dumps({**JOB, "subcommand": subcommand, **job}))
    runner = InProcessRunner(entrypoint, REGISTRY, env={"IPROOFS_FAKE_DELAY_S": "0"})
    return runner.run(
        IMAGE,
        subcommand,
        tmp_path,
        models_dir=FAKE / "model",
        gpu=None,
        cpuset="0",
        mems="0",
        memory=None,
        timeout_s=30,
    )


def test_inprocess_runner_same_contract(tmp_path: Path) -> None:
    result = run_fake(tmp_path, FAKE / "entrypoint", "commit", {"model_dir": "/models"})
    assert result.exit_code == 0
    out = result.out
    assert isinstance(out, AdapterOut)
    assert re.fullmatch(r"[0-9a-f]{64}", str(out.commitment_id))
    assert result.ended_mono_ns >= result.started_mono_ns


def fake_writing(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "bad-entrypoint"
    script.write_text(
        f"import os, sys\nopen(os.environ['IPROOFS_IO'] + '/out.json', 'w').write({body})\n"
    )
    return script


def test_out_json_over_16_mib_is_adapter_error(tmp_path: Path) -> None:
    script = fake_writing(tmp_path, "'x' * (16 * 1024 * 1024 + 1)")
    with pytest.raises(IProofsError) as e:
        run_fake(tmp_path, script, "setup", {})
    assert e.value.kind is ErrorKind.ADAPTER
    assert "larger than" in e.value.message


def test_invalid_out_json_is_adapter_error(tmp_path: Path) -> None:
    script = fake_writing(tmp_path, '\'{"schema": "adapter-out/1", "subcommand": "setup"}\'')
    with pytest.raises(IProofsError) as e:
        run_fake(tmp_path, script, "setup", {})
    assert e.value.kind is ErrorKind.ADAPTER
    assert "invalid" in e.value.message


def test_nonzero_exit_has_no_out(tmp_path: Path) -> None:
    script = tmp_path / "failing"
    script.write_text("import sys\nprint('upstream crashed', file=sys.stderr)\nsys.exit(3)\n")
    result = run_fake(tmp_path, script, "setup", {})
    assert (result.exit_code, result.out) == (3, None)
    assert result.stderr_tail == ("upstream crashed",)


def test_only_adapter_and_measure_touch_docker() -> None:
    # INV-ARCH-3: adapter builds the argv, measure.timed_call runs it
    offenders = [
        p.name
        for p in (ROOT / "harness/src/iproofs").rglob("*.py")
        if '"docker"' in p.read_text() and p.name not in {"adapter.py", "measure.py"}
    ]
    assert offenders == []
