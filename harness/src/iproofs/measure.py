"""Clock events, container-call timing, release watcher, sampling, proof sizes (RFC-0011).

INV-ARCH-4: durations are read here, from the monotonic clock only (C-1).
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from iproofs.derive import span_seconds
from iproofs.errors import ErrorKind, IProofsError

__all__ = ["CallTiming", "EventLog", "pin_harness_cpu", "span_seconds", "timed_call"]


@dataclass(frozen=True, slots=True)
class CallTiming:
    start_ns: int  # read after `docker create` returned, before `docker start` is spawned
    end_ns: int  # read after the `docker start --attach` process is reaped
    exit_code: int
    container_id: str  # T-3: kept in memory only; never logged or written
    stdout: str
    stderr: str


def timed_call(
    argv_create: Sequence[str],
    timeout_s: float,
    on_started: Callable[[str], None] = lambda cid: None,
    clock: Callable[[], int] = time.monotonic_ns,
) -> CallTiming:
    """Time one adapter call: `docker create` untimed, `docker start --attach` timed (T-1)."""
    created = subprocess.run(list(argv_create), capture_output=True, text=True, check=False)
    if created.returncode != 0:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"docker create failed: {created.stderr.strip()}",
            exit_code=created.returncode,
        )
    cid = created.stdout.strip()
    start = clock()
    proc = subprocess.Popen(
        ["docker", "start", "--attach", cid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        on_started(cid)  # samplers attach to the container's cgroup here (RFC-0011)
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        subprocess.run(["docker", "kill", cid], capture_output=True, check=False)
        stdout, stderr = proc.communicate()
        raise IProofsError(
            ErrorKind.TIMEOUT,
            f"step exceeded {timeout_s} s",
            last_lines=tuple(stderr.splitlines()[-50:]),
        ) from e
    finally:
        end = clock()
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)
    return CallTiming(start, end, proc.returncode, cid, stdout, stderr)


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
