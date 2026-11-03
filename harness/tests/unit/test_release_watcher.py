import itertools
import os
import sys
import time
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import ReleaseWatcher

LINUX = sys.platform.startswith("linux")


def release(proofs: Path, proof_id: str, data: bytes = b"part") -> None:
    tmp = proofs / f".tmp-{proof_id}"
    tmp.mkdir()
    (tmp / "body.bin").write_bytes(data)
    os.rename(tmp, proofs / proof_id)


def spaced_releases(watcher: ReleaseWatcher, proofs: Path, n: int = 3, gap_s: float = 0.05) -> None:
    watcher.start()
    for i in range(n):
        time.sleep(gap_s)
        release(proofs, f"req-{i}")
    time.sleep(gap_s)


def test_watch_poll(tmp_path: Path) -> None:
    """TC-WATCH-POLL: polling timestamps each release in order, apart by about the gap."""
    w = ReleaseWatcher(tmp_path, force_poll=True)
    spaced_releases(w, tmp_path)
    releases = w.stop()
    assert w.mechanism == "poll"
    assert [r.proof_id for r in releases] == ["req-0", "req-1", "req-2"]
    gaps = [(b.mono_ns - a.mono_ns) / 1e9 for a, b in itertools.pairwise(releases)]
    assert all(0.02 < g < 1.0 for g in gaps), gaps
    assert w.observable


@pytest.mark.skipif(not LINUX, reason="inotify is Linux only")
def test_watch_inotify(tmp_path: Path) -> None:
    """TC-WATCH-INOTIFY."""
    w = ReleaseWatcher(tmp_path)
    spaced_releases(w, tmp_path)
    releases = w.stop()
    assert w.mechanism == "inotify"
    assert [r.proof_id for r in releases] == ["req-0", "req-1", "req-2"]
    assert w.observable
    assert w.nonatomic == []


def test_watch_burst(tmp_path: Path) -> None:
    """TC-WATCH-BURST: every release in one observation is not observable (W-4)."""
    w = ReleaseWatcher(tmp_path, poll_interval_s=5.0, force_poll=True)
    w.start()  # the first scan sees an empty directory, then the poller sleeps
    for i in range(3):
        release(tmp_path, f"req-{i}")
    releases = w.stop()  # the final scan sees all three at once
    assert len(releases) == 3
    assert not w.observable


def test_watch_declared(tmp_path: Path) -> None:
    """TC-WATCH-DECLARED: incremental_proofs false is never observable."""
    w = ReleaseWatcher(tmp_path, incremental_proofs=False, force_poll=True)
    spaced_releases(w, tmp_path)
    w.stop()
    assert not w.observable


@pytest.mark.skipif(not LINUX, reason="direct creation is told apart from a rename by inotify")
def test_watch_nonatomic(tmp_path: Path) -> None:
    """TC-WATCH-NONATOMIC: a directory created without a .tmp- stage is accepted and noted."""
    w = ReleaseWatcher(tmp_path)
    w.start()
    time.sleep(0.05)
    (tmp_path / "req-0").mkdir()
    time.sleep(0.05)
    assert [r.proof_id for r in w.stop()] == ["req-0"]
    assert w.nonatomic == ["req-0"]


def test_watch_mutated(tmp_path: Path) -> None:
    """TC-WATCH-MUTATED: a part that changes after release fails with kind adapter."""
    w = ReleaseWatcher(tmp_path, force_poll=True)
    spaced_releases(w, tmp_path, n=1)
    w.stop()
    w.check_unchanged()
    with (tmp_path / "req-0/body.bin").open("ab") as f:
        f.write(b"more")
    with pytest.raises(IProofsError) as e:
        w.check_unchanged()
    assert e.value.kind is ErrorKind.ADAPTER


def test_release_after_call_exit_is_adapter_error(tmp_path: Path) -> None:
    """W-5."""
    w = ReleaseWatcher(tmp_path, force_poll=True)
    w.start()
    call_end = time.monotonic_ns()
    time.sleep(0.2)  # well beyond the observation lag allowed for polling
    release(tmp_path, "late")
    time.sleep(0.03)
    with pytest.raises(IProofsError, match="W-5") as e:
        w.stop(call_end_ns=call_end)
    assert e.value.kind is ErrorKind.ADAPTER


def test_tmp_left_listed(tmp_path: Path) -> None:
    w = ReleaseWatcher(tmp_path, force_poll=True)
    w.start()
    (tmp_path / ".tmp-req-9").mkdir()
    w.stop()
    assert w.tmp_left() == [".tmp-req-9"]


def test_release_seen_just_after_exit_is_not_late(tmp_path: Path) -> None:
    """A fast adapter's proofs may first be observed just after it exits (poll lag)."""
    w = ReleaseWatcher(tmp_path, poll_interval_s=5.0, force_poll=True)
    w.start()
    release(tmp_path, "req-0")
    call_end = time.monotonic_ns()
    assert [r.proof_id for r in w.stop(call_end_ns=call_end)] == ["req-0"]
