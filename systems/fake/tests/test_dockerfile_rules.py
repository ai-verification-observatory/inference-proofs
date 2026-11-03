"""RFC-0014 §Adapter image build, B1 to B3, on the fake systems and a known-bad Dockerfile."""

from pathlib import Path

from iproofs.provenance import dockerfile_problems

SYSTEMS = Path(__file__).resolve().parents[2]
BAD = SYSTEMS.parent / "harness/tests/fixtures/gates/G1/Dockerfile-networked-run"
LOCK = "https://example.org/src.tar.gz"


def test_fake_dockerfile_follows_the_build_rules() -> None:
    lock = (SYSTEMS / "fake/inputs.lock").read_text()
    assert dockerfile_problems((SYSTEMS / "fake/Dockerfile").read_text(), lock) == []
    assert dockerfile_problems((SYSTEMS / "fake-broken/Dockerfile").read_text(), lock) == []


def test_networked_run_fails() -> None:
    lock = f"src\t{LOCK}\tsha256:{'0' * 64}\n"
    assert dockerfile_problems(BAD.read_text(), lock) == [
        "5: B3 RUN outside the fetch stage without --network=none"
    ]


def test_inputs_lock_covers_every_download() -> None:
    assert dockerfile_problems(BAD.read_text(), "") == [
        f"3: B2 {LOCK} is not in inputs.lock",
        "5: B3 RUN outside the fetch stage without --network=none",
    ]
    other = f"src\t{LOCK}\tsha256:{'1' * 64}\n"
    assert dockerfile_problems(BAD.read_text(), other)[0] == (
        f"3: B2 {LOCK} checksum differs from inputs.lock"
    )
    outside = "FROM a@sha256:" + "0" * 64 + f"\nADD {LOCK} /src\n"
    assert dockerfile_problems(outside) == [f"2: B2 {LOCK} downloaded outside the fetch stage"]
    assert dockerfile_problems("FROM python:3.12\n") == ["1: B1 FROM python:3.12 has no digest"]


def test_info_reports_the_build_record(tmp_path: Path) -> None:
    """B5 and B6: `info` returns image_inputs and the adapter commit and dirty flag baked in."""
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    io = tmp_path / "io"
    io.mkdir()
    (io / "job.json").write_text(json.dumps({"subcommand": "info"}))
    env = {**os.environ, "IPROOFS_IO": str(io), "IPROOFS_ADAPTER_COMMIT": "a" * 40,
           "IPROOFS_ADAPTER_DIRTY": "false"}  # fmt: skip
    entry = SYSTEMS / "fake/entrypoint"
    subprocess.run([sys.executable, str(entry), "info", "/io/job.json", "/io/out.json"], env=env,
                   check=True)  # fmt: skip
    out = json.loads((io / "out.json").read_text())
    assert (out["adapter_commit"], out["adapter_dirty"], out["image_inputs"]) == (
        "a" * 40,
        False,
        [],
    )
