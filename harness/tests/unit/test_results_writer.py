"""RFC-0009 §Storage log caps and docs/spec/05 §Log files (INV-OBS-1)."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from iproofs.adapter import InProcessRunner
from iproofs.measure import LOG_HEAD_BYTES, LOG_TAIL_BYTES, Capture, cap_text
from iproofs.runner import RUN_DIR_CAP_BYTES, Job, JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake/entrypoint"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}
MIB = 1024 * 1024
SPEC = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, "", "v0.1")


def test_log_truncation_keeps_head_and_tail() -> None:
    data = bytes(i % 251 for i in range(3 * MIB))
    capture = Capture()
    for i in range(0, len(data), 10_000):  # chunk boundaries never align with the caps
        capture.feed(data[i : i + 10_000])
    elided = len(data) - LOG_HEAD_BYTES - LOG_TAIL_BYTES
    marker = f"[iproofs: {elided} bytes omitted, full digest in digests.txt]\n".encode()
    assert capture.kept() == data[:LOG_HEAD_BYTES] + marker + data[-LOG_TAIL_BYTES:]
    assert cap_text(data, LOG_HEAD_BYTES, LOG_TAIL_BYTES) == (capture.kept(), elided)
    assert capture.digest == "sha256:" + hashlib.sha256(data).hexdigest()
    small = Capture()
    small.feed(b"short\n")
    assert (small.kept(), small.elided) == (b"short\n", 0)


def noisy(tmp_path: Path) -> Path:
    """The fake adapter, writing 5 MiB to stderr during prove."""
    script = tmp_path / "noisy"
    script.write_text(
        "import runpy, sys\n"
        "if sys.argv[1] == 'prove':\n"
        "    sys.stderr.write(('x' * 1023 + '\\n') * 5 * 1024)\n"
        f"runpy.run_path({str(FAKE)!r}, run_name='__main__')\n"
    )
    return script


def test_untruncated_digest_recorded(tmp_path: Path) -> None:
    containers = InProcessRunner(noisy(tmp_path), REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    run_dir = runner.run(replace(SPEC, results_root=str(tmp_path / "results")))
    log = run_dir / "logs/prove.stderr"
    full = ("x" * 1023 + "\n").encode() * 5 * 1024
    assert log.stat().st_size <= MIB + 100  # 1 MiB kept plus the marker line
    assert b"bytes omitted, full digest in digests.txt]" in log.read_bytes()
    digests = dict(line.split("\t") for line in (run_dir / "digests.txt").read_text().splitlines())
    assert digests["logs/prove.stderr"] == "sha256:" + hashlib.sha256(full).hexdigest()
    events = [json.loads(line) for line in (run_dir / "logs/harness.jsonl").open()]
    cut = [e for e in events if e["event"] == "log.truncated"]
    assert [(e["file"], e["elided_bytes"]) for e in cut] == [("logs/prove.stderr", 4 * MIB)]


def test_run_dir_cap_enforced(tmp_path: Path) -> None:
    staging = tmp_path / ".staging-x"
    (staging / "logs").mkdir(parents=True)
    for i in range(12):  # 12 adapter logs of 1 MiB: under the per-file cap, over 10 MiB in all
        (staging / f"logs/s{i:02d}.stderr").write_bytes(bytes([65 + i]) * MIB)
    (staging / "logs/harness.jsonl").write_text('{"event":"runner.start"}\n')
    runner = Runner(InProcessRunner(FAKE, REGISTRY), root=ROOT, registry=REGISTRY)
    runner._cap_run_dir(Job(SPEC, "2026-11-03-fake-fake-tiny-ci-ci-cpu-1", staging))
    total = sum(p.stat().st_size for p in staging.rglob("*") if p.is_file())
    assert total <= RUN_DIR_CAP_BYTES
    cut = sorted(p.name for p in (staging / "logs").glob("*.stderr") if p.stat().st_size < MIB)
    assert cut == [f"s{i:02d}.stderr" for i in range(3)]  # largest first; ties in name order
    digests = (staging / "digests.txt").read_text()
    assert f"logs/s00.stderr\tsha256:{hashlib.sha256(b'A' * MIB).hexdigest()}" in digests
    events = [json.loads(line) for line in (staging / "logs/harness.jsonl").open()]
    assert [e["file"] for e in events if e["event"] == "log.truncated"] == [
        f"logs/s{i:02d}.stderr" for i in range(3)
    ]
