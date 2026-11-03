"""JSON Lines logger, redaction hook and event catalogue (docs/spec/05-observability.md).

Layer 0: standard library only. INV-OBS-4: every line passes the redactor before it is written;
the redactor is `iproofs.log.redact.Redactor`, with patterns in `iproofs.log.patterns`.
"""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import TextIO

from iproofs.errors import ErrorKind, IProofsError


class Event(StrEnum):
    """Every event name of the docs/spec/05 catalogue; names are stable within a minor version."""

    RUNNER_START = "runner.start"
    RUNNER_RECOVERED = "runner.recovered"
    JOB_STATE = "job.state"
    JOB_FAILED = "job.failed"
    JOB_WRITTEN = "job.written"
    FETCH_ATTEMPT = "fetch.attempt"
    FETCH_FAILED = "fetch.failed"
    INTEGRITY_OK = "integrity.ok"
    INTEGRITY_MISMATCH = "integrity.mismatch"
    ENV_PROBE = "env.probe"
    ENV_GPU_BUSY = "env.gpu_busy"
    CPUSET_SELECTED = "cpuset.selected"
    STEP_START = "step.start"
    STEP_END = "step.end"
    STEP_TIMEOUT = "step.timeout"
    STEP_OOM = "step.oom"
    PROOF_RELEASED = "proof.released"
    PROOF_TMP_LEFT = "proof.tmp_left"
    SAMPLER_START = "sampler.start"
    SAMPLER_GAP = "sampler.gap"
    SAMPLER_CGROUP_UNAVAILABLE = "sampler.cgroup_unavailable"
    POLICY_WARNING = "policy.warning"
    VERIFY_RESULT = "verify.result"
    CONTROL_TRIAL = "control.trial"
    CONTROL_TWIN_MISMATCH = "control.twin_mismatch"
    CONTROL_DISCLOSURE_PENDING = "control.disclosure_pending"
    LOG_TRUNCATED = "log.truncated"
    VALIDATE_FAIL = "validate.fail"


LEVELS = ("debug", "info", "warning", "error")

# The catalogue's level per event; `log` uses it unless the caller overrides it.
DEFAULT_LEVEL = {
    **dict.fromkeys(Event, "info"),
    Event.RUNNER_RECOVERED: "warning",
    Event.JOB_FAILED: "error",
    Event.FETCH_FAILED: "error",
    Event.INTEGRITY_OK: "debug",
    Event.INTEGRITY_MISMATCH: "error",
    Event.ENV_GPU_BUSY: "error",
    Event.STEP_TIMEOUT: "error",
    Event.STEP_OOM: "error",
    Event.PROOF_RELEASED: "debug",
    Event.PROOF_TMP_LEFT: "warning",
    Event.POLICY_WARNING: "warning",
    Event.SAMPLER_START: "debug",
    Event.SAMPLER_GAP: "warning",
    Event.SAMPLER_CGROUP_UNAVAILABLE: "warning",
    Event.CONTROL_TWIN_MISMATCH: "warning",
    Event.CONTROL_DISCLOSURE_PENDING: "warning",
    Event.VALIDATE_FAIL: "error",
}

Redactor = Callable[[str], str]


def _identity(line: str) -> str:
    return line


def _utc_ms() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonlLogger:
    """Writes `logs/harness.jsonl`: one compact JSON object per line, UTF-8, LF."""

    def __init__(
        self,
        stream: TextIO,
        *,
        level: str = "info",
        redactor: Redactor = _identity,
        mono: Callable[[], int] = time.monotonic_ns,
        wall: Callable[[], str] = _utc_ms,
    ) -> None:
        if level not in LEVELS:
            raise IProofsError(ErrorKind.CONFIG, f"unknown log level {level!r}")
        self.stream = stream
        self.min_level = LEVELS.index(level)
        self.redactor = redactor
        self.mono = mono
        self.wall = wall

    def log(
        self,
        event: str,
        *,
        job: str | None = None,
        step: str | None = None,
        level: str | None = None,
        **fields: object,
    ) -> None:
        try:
            name = Event(event)
        except ValueError:
            raise IProofsError(ErrorKind.INTERNAL, f"unknown log event {event!r}") from None
        lvl = level or DEFAULT_LEVEL[name]
        if lvl not in LEVELS:
            raise IProofsError(ErrorKind.INTERNAL, f"unknown log level {lvl!r}")
        if LEVELS.index(lvl) < self.min_level:
            return
        record = {
            "ts": self.wall(),
            "mono_ns": self.mono(),
            "level": lvl,
            "event": str(name),
            "job": job,
            "step": step,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        self.stream.write(self.redactor(line) + "\n")
        self.stream.flush()
