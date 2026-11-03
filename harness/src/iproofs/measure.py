"""Clock events, container-call timing, release watcher, sampling, proof sizes (RFC-0011).

INV-ARCH-4: durations are read here, from the monotonic clock only (C-1).
"""

import ctypes
import ctypes.util
import hashlib
import os
import select
import stat
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal

from iproofs.derive import span_seconds
from iproofs.errors import ErrorKind, IProofsError

KILL_WAIT_S = 30  # RFC-0010 §Timeouts: wait for the killed container to exit

__all__ = [
    "LOG_HEAD_BYTES",
    "LOG_TAIL_BYTES",
    "CallTiming",
    "Capture",
    "EventLog",
    "Release",
    "ReleaseWatcher",
    "cap_text",
    "drain",
    "pin_harness_cpu",
    "span_seconds",
    "timed_call",
]


@dataclass(frozen=True, slots=True)
class CallTiming:
    start_ns: int  # read after `docker create` returned, before `docker start` is spawned
    end_ns: int  # read after the `docker start --attach` process is reaped
    exit_code: int
    container_id: str  # T-3: kept in memory only; never logged or written
    stdout: str
    stderr: str


# ---------------------------------------------------------------- bounded output capture

LOG_HEAD_BYTES = 256 * 1024  # RFC-0009 §Storage: per log file, first 256 KiB ...
LOG_TAIL_BYTES = 768 * 1024  # ... and last 768 KiB
CHUNK = 64 * 1024


def omitted_marker(k: int) -> bytes:
    return f"[iproofs: {k} bytes omitted, full digest in digests.txt]\n".encode()


class Capture:
    """One output stream kept as its first and last bytes, with the sha256 and length of all
    of it, so a runaway adapter cannot fill memory or disk (docs/spec/06-security.md)."""

    def __init__(self, head: int = LOG_HEAD_BYTES, tail: int = LOG_TAIL_BYTES) -> None:
        self.head_limit, self.tail_limit = head, tail
        self.head, self.tail = bytearray(), bytearray()
        self.total = 0
        self._sha = hashlib.sha256()
        self._lock = threading.Lock()

    def feed(self, chunk: bytes) -> None:
        with self._lock:
            self.total += len(chunk)
            self._sha.update(chunk)
            room = self.head_limit - len(self.head)
            if room > 0:
                self.head += chunk[:room]
                chunk = chunk[room:]
            self.tail += chunk
            if len(self.tail) > self.tail_limit:
                del self.tail[: len(self.tail) - self.tail_limit]

    @property
    def digest(self) -> str:
        return "sha256:" + self._sha.hexdigest()

    @property
    def elided(self) -> int:
        return self.total - len(self.head) - len(self.tail)

    def kept(self) -> bytes:
        middle = omitted_marker(self.elided) if self.elided else b""
        return bytes(self.head) + middle + bytes(self.tail)

    def text(self) -> str:
        return self.kept().decode("utf-8", errors="replace")


def _pump(stream: IO[bytes], sinks: Sequence[Capture]) -> None:
    while chunk := stream.read1(CHUNK) if hasattr(stream, "read1") else stream.read(CHUNK):
        for sink in sinks:
            sink.feed(chunk)


def drain(
    proc: "subprocess.Popen[bytes]", out: Sequence[Capture], err: Sequence[Capture]
) -> list[threading.Thread]:
    """Read both pipes on threads into bounded captures; join the threads after the wait."""
    threads = [
        threading.Thread(target=_pump, args=(pipe, sinks), daemon=True)
        for pipe, sinks in ((proc.stdout, out), (proc.stderr, err))
        if pipe is not None
    ]
    for t in threads:
        t.start()
    return threads


def cap_text(data: bytes, head: int, tail: int) -> tuple[bytes, int]:
    """The first `head` and last `tail` bytes joined by the omitted marker, and the count."""
    elided = len(data) - head - tail
    if elided <= 0:
        return data, 0
    return data[:head] + omitted_marker(elided) + data[len(data) - tail :], elided


def timed_call(
    argv_create: Sequence[str],
    timeout_s: float,
    on_started: Callable[[str], None] = lambda cid: None,
    clock: Callable[[], int] = time.monotonic_ns,
    sinks: Sequence[Capture] = (),
) -> CallTiming:
    """Time one adapter call: `docker create` untimed, `docker start --attach` timed (T-1).
    `sinks` (stdout, stderr) also receive the output: the run's per-file log captures."""
    created = subprocess.run(list(argv_create), capture_output=True, text=True, check=False)
    if created.returncode != 0:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"docker create failed: {created.stderr.strip()}",
            exit_code=created.returncode,
        )
    cid = created.stdout.strip()
    out, err = Capture(), Capture()
    start = clock()
    proc = subprocess.Popen(
        ["docker", "start", "--attach", cid], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    threads = drain(proc, [out, *sinks[:1]], [err, *sinks[1:2]])
    try:
        on_started(cid)  # samplers attach to the container's cgroup here (RFC-0011)
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        subprocess.run(
            ["docker", "kill", "--signal", "KILL", cid], capture_output=True, check=False
        )
        try:
            proc.wait(timeout=KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        for t in threads:
            t.join()
        _remove(cid)
        raise IProofsError(
            ErrorKind.TIMEOUT,
            f"step exceeded {timeout_s} s",
            last_lines=tuple(err.text().splitlines()[-50:]),
        ) from e
    end = clock()
    for t in threads:
        t.join()
    stdout, stderr = out.text(), err.text()
    oom = proc.returncode != 0 and _oom_killed(cid)
    _remove(cid)
    if oom:
        raise IProofsError(
            ErrorKind.RESOURCE,
            "container killed: out of memory",
            exit_code=proc.returncode,
            last_lines=tuple(stderr.splitlines()[-50:]),
        )
    return CallTiming(start, end, proc.returncode, cid, stdout, stderr)


def _remove(cid: str) -> None:
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)


def _oom_killed(cid: str) -> bool:
    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.OOMKilled}}", cid],
        capture_output=True,
        text=True,
        check=False,
    )
    return inspect.stdout.strip() == "true"


@dataclass(slots=True)
class EventLog:
    """Lifecycle events stored in run.json `events` as {event, mono_ns} (RFC-0011 C-2)."""

    clock: Callable[[], int] = time.monotonic_ns
    events: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, mono_ns: int | None = None) -> int:
        stamp = self.clock() if mono_ns is None else mono_ns
        self.events.append({"event": name, "mono_ns": stamp})
        return stamp

    def first(self) -> dict[str, int]:
        """Event name -> first timestamp, the input of `iproofs.derive.scope_seconds`."""
        out: dict[str, int] = {}
        for e in self.events:
            out.setdefault(str(e["event"]), int(str(e["mono_ns"])))
        return out

    def releases(self) -> list[int]:
        return [int(str(e["mono_ns"])) for e in self.events if e["event"] == "proof.released"]


def pin_harness_cpu(job_cpus: Iterable[int]) -> int | None:
    """C-3: pin the harness to one logical CPU outside the job's cpusets (Linux only)."""
    if not sys.platform.startswith("linux"):
        return None
    taken = set(job_cpus)
    free = sorted(set(os.sched_getaffinity(0)) - taken)
    if not free:
        raise IProofsError(ErrorKind.ENVIRONMENT, "no CPU left for the harness outside the job")
    os.sched_setaffinity(0, {free[-1]})
    return free[-1]


# ---------------------------------------------------------------- proof release watcher

IN_CREATE = 0x00000100
IN_MOVED_TO = 0x00000080
IN_ONLYDIR = 0x01000000
IN_ISDIR = 0x40000000
_IN_NONBLOCK = 0o4000
_IN_CLOEXEC = 0o2000000
_EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, len


@dataclass(frozen=True, slots=True)
class Release:
    proof_id: str
    mono_ns: int


class ReleaseWatcher:
    """Timestamps each proof directory as it appears under /io/proofs (RFC-0011 W-1 to W-5).

    Adapters rename `.tmp-<id>` to `<id>`; on Linux the rename is read from inotify in a
    thread, elsewhere `os.scandir` polls every `poll_interval_s`.
    """

    def __init__(
        self,
        proofs_dir: Path,
        poll_interval_s: float = 0.010,
        *,
        incremental_proofs: bool = True,
        force_poll: bool = False,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.dir = proofs_dir
        self.interval = poll_interval_s
        self.incremental = incremental_proofs
        self.clock = clock
        self._mechanism: Literal["inotify", "poll"] = "poll"
        self._libc = None if force_poll or not sys.platform.startswith("linux") else _libc()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._releases: dict[str, tuple[int, int]] = {}  # proof id -> (mono_ns, batch)
        self._sizes: dict[str, dict[str, int]] = {}
        self.nonatomic: list[str] = []  # W-3: logged as release.nonatomic

    @property
    def mechanism(self) -> Literal["inotify", "poll"]:
        return self._mechanism

    @property
    def observable(self) -> bool:
        """W-4: false for non-incremental systems or when every release came in one batch."""
        batches = {batch for _, batch in self._releases.values()}
        return self.incremental and len(batches) > 1

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd = self._inotify() if self._libc is not None else None
        self._mechanism = "inotify" if fd is not None else "poll"
        target = self._run_inotify if fd is not None else self._run_poll
        self._thread = threading.Thread(
            target=target, args=(fd,) if fd is not None else (), name="release-watcher", daemon=True
        )
        self._thread.start()

    def stop(self, call_end_ns: int | None = None) -> list[Release]:
        """Stop after the prove call; W-5: a release after `call_end_ns` is an adapter error."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._scan(batch=-1)  # anything the reader had not yet seen
        releases = sorted(
            (Release(pid, ns) for pid, (ns, _) in self._releases.items()),
            key=lambda r: (r.mono_ns, r.proof_id),
        )
        # A release is observed up to one poll interval (or one inotify read) after it happens,
        # so only observations clearly after the call ended count as W-5 violations.
        lag_ns = int(max(2 * self.interval, 0.05) * 1e9)
        late = [
            r.proof_id
            for r in releases
            if call_end_ns is not None and r.mono_ns > call_end_ns + lag_ns
        ]
        if late:
            raise IProofsError(
                ErrorKind.ADAPTER, f"W-5: proofs released after prove exited: {late}", step="prove"
            )
        return releases

    def tmp_left(self) -> list[str]:
        """`.tmp-*` directories still present: logged as proof.tmp_left."""
        return sorted(p.name for p in self.dir.iterdir() if p.name.startswith(".tmp-"))

    def check_unchanged(self) -> None:
        """W-3: parts that change size after release fail the job with kind adapter."""
        for pid, sizes in sorted(self._sizes.items()):
            now = _part_sizes(self.dir / pid)
            if now != sizes:
                raise IProofsError(
                    ErrorKind.ADAPTER, f"W-3: proof {pid} changed after release", step="prove"
                )

    def _release(self, name: str, batch: int, atomic: bool) -> None:
        if name.startswith(".tmp-") or name in self._releases:
            return
        self._releases[name] = (self.clock(), batch)
        self._sizes[name] = _part_sizes(self.dir / name)
        if not atomic:
            self.nonatomic.append(name)

    def _scan(self, batch: int) -> None:
        with os.scandir(self.dir) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    self._release(entry.name, batch, atomic=True)

    def _run_poll(self) -> None:
        batch = 0
        while not self._stop.is_set():
            self._scan(batch)
            batch += 1
            self._stop.wait(self.interval)

    def _inotify(self) -> int | None:
        assert self._libc is not None
        fd = int(self._libc.inotify_init1(_IN_NONBLOCK | _IN_CLOEXEC))
        if fd < 0:
            return None
        wd = self._libc.inotify_add_watch(
            fd, os.fsencode(self.dir), IN_MOVED_TO | IN_CREATE | IN_ONLYDIR
        )
        if wd < 0:
            os.close(fd)
            return None
        return fd

    def _run_inotify(self, fd: int) -> None:
        batch = 0
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([fd], [], [], self.interval)
                if not ready:
                    continue
                data = os.read(fd, 1 << 16)
                offset = 0
                while offset < len(data):
                    _, mask, _, length = _EVENT_HEADER.unpack_from(data, offset)
                    name_bytes = data[
                        offset + _EVENT_HEADER.size : offset + _EVENT_HEADER.size + length
                    ]
                    offset += _EVENT_HEADER.size + length
                    name = name_bytes.rstrip(b"\0").decode(errors="replace")
                    if mask & IN_MOVED_TO:
                        self._release(name, batch, atomic=True)
                    elif mask & IN_CREATE and mask & IN_ISDIR:
                        self._release(name, batch, atomic=False)  # created without a .tmp- stage
                batch += 1
        finally:
            os.close(fd)


def _part_sizes(proof: Path) -> dict[str, int]:
    try:
        return {p.name: p.stat().st_size for p in proof.iterdir() if p.is_file()}
    except FileNotFoundError:
        return {}


def _libc() -> ctypes.CDLL | None:
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    except OSError:
        return None
    return libc if hasattr(libc, "inotify_init1") else None


# ---------------------------------------------------------------- proof sizes (RFC-0011 Z-1 to Z-3)


@dataclass(frozen=True, slots=True)
class ProofSize:
    bytes: int
    digest: str  # the RFC-0012 proof digest, computed in the same pass
    parts: tuple[tuple[str, int, str], ...]  # (name, bytes, sha256 digest) per part


def _regular_inside(path: Path, io_root: Path, what: str) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise IProofsError(ErrorKind.ADAPTER, f"Z-1: {what} is not a regular file", step="prove")
    if not path.resolve().is_relative_to(io_root.resolve()):
        raise IProofsError(ErrorKind.ADAPTER, f"Z-1: {what} resolves outside /io", step="prove")


def proof_size(proof_dir: Path, io_root: Path) -> ProofSize:
    """Bytes as stored of every part of one proof, with per-part sha256 and the proof digest."""
    parts = []
    lines = []
    for part in sorted(proof_dir.iterdir(), key=lambda p: p.name.encode()):
        _regular_inside(part, io_root, f"/io/proofs/{proof_dir.name}/{part.name}")
        h = hashlib.sha256()
        size = 0
        with part.open("rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
                size += len(chunk)
        parts.append((part.name, size, "sha256:" + h.hexdigest()))
        lines.append(f"{part.name}\t{h.hexdigest()}\n")
    digest = "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest()
    return ProofSize(sum(size for _, size, _ in parts), digest, tuple(parts))


def proof_bytes(proof_dir: Path, io_root: Path) -> int:
    return proof_size(proof_dir, io_root).bytes


def files_bytes(paths: Sequence[str], io_root: Path) -> int:
    """Total bytes of adapter files named by container path (verifier or prover files, Z-2)."""
    total = 0
    for container_path in paths:
        rel = container_path.removeprefix("/io/")
        if rel == container_path or ".." in Path(rel).parts:
            raise IProofsError(
                ErrorKind.ADAPTER, f"Z-1: {container_path} is outside /io", step="commit"
            )
        host = io_root / rel
        _regular_inside(host, io_root, container_path)
        total += host.stat().st_size
    return total
