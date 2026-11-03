"""RFC-0011 §Cgroup accounting: TC-CGROUP-PARSE, the OOM-kill delta, stale hold units."""

import shutil
from pathlib import Path

import pytest

from iproofs.adapter import docker_create_argv
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import CgroupSlice, SliceCgroupReader, job_hash, stop_stale_holds

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/cgroup/iproofs.slice"
RUN_ID = "2026-11-20-sash-sash-l31-8b-c4096-prover-h100-1"


def test_cgroup_parse() -> None:
    """TC-CGROUP-PARSE: the fixture counters read to exact integers."""
    r = SliceCgroupReader(FIXTURE)
    assert r.memory_peak() == 8589934592
    assert r.memory_anon() == 1073741824
    assert r.cpu_usage_usec() == 4200000
    assert r.oom_kills() == 0


class Host:
    """systemctl and systemd-run stand-ins over a copy of the fixture slice."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[list[str]] = []
        self.units = ""

    def run(self, argv: list[str]) -> str:
        self.calls.append(argv)
        if argv[:2] == ["systemctl", "show"]:
            return "/iproofs.slice/" + argv[-1] + "\n"
        if argv[:2] == ["systemctl", "list-units"]:
            return self.units
        return ""

    def slice(self, step: str) -> CgroupSlice:
        s = CgroupSlice(RUN_ID, step, cgroup_root=self.root, run=self.run,
                        popen=self.calls.append)  # fmt: skip
        shutil.copytree(FIXTURE, self.root / "iproofs.slice" / s.name)
        return s


def test_slice_names_and_counters(tmp_path: Path) -> None:
    host = Host(tmp_path)
    s = host.slice("prove")
    h = job_hash(RUN_ID)
    assert (s.name, s.unit) == (f"iproofs-{h}-prove.slice", f"iproofs-{h}-prove-hold")
    assert len(h) == 12
    reader = s.start()
    assert host.calls[0] == ["systemd-run", "--scope", f"--slice={s.name}", f"--unit={s.unit}",
                             "sleep", "infinity"]  # fmt: skip
    (reader.path / "memory.peak").write_text("9663676416\n")
    (reader.path / "cpu.stat").write_text("usage_usec 6700000\n")
    peak, cpu = s.finish()
    assert (peak, cpu, s.baseline_bytes) == (9663676416, 2.5, 8589934592)
    assert host.calls[-1] == ["systemctl", "stop", f"{s.unit}.scope"]
    argv = docker_create_argv("x/y@sha256:" + "a" * 64, "prove", Path("/srv/io"),
                              models_dir=None, gpu=0, cpuset="0", mems="0", memory=None,
                              cgroup_parent=s.name)  # fmt: skip
    assert argv[argv.index("--cgroup-parent") + 1] == s.name  # G-2


def test_oom_kill_delta_is_resource(tmp_path: Path) -> None:
    host = Host(tmp_path)
    s = host.slice("commit")
    reader = s.start()
    (reader.path / "memory.events").write_text("oom 1\noom_kill 1\n")
    with pytest.raises(IProofsError) as e:
        s.finish()
    assert e.value.kind is ErrorKind.RESOURCE
    assert host.calls[-1] == ["systemctl", "stop", f"{s.unit}.scope"]  # stopped anyway


def test_missing_slice_fails_before_timing(tmp_path: Path) -> None:
    s = CgroupSlice(RUN_ID, "prove", cgroup_root=tmp_path, run=lambda argv: "",
                    popen=lambda argv: None)  # fmt: skip
    with pytest.raises(IProofsError) as e:
        s.start()
    assert e.value.kind is ErrorKind.ENVIRONMENT
    assert "G-7" in e.value.message


def test_stale_hold_units_stopped(tmp_path: Path) -> None:
    host = Host(tmp_path)
    host.units = "iproofs-aaaaaaaaaaaa-prove-hold.scope loaded active running sleep\n"
    assert stop_stale_holds(host.run) == ["iproofs-aaaaaaaaaaaa-prove-hold.scope"]
    assert ["systemctl", "stop", "iproofs-aaaaaaaaaaaa-prove-hold.scope"] in host.calls
