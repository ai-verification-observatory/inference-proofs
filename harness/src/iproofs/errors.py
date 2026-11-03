"""Error taxonomy: ErrorKind, IProofsError and failure records (RFC-0010 §Error taxonomy).

Verdicts (accept, reject, no_verdict, invalid_call) are results, never errors.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

MAX_MESSAGE_BYTES = 4096
MAX_LAST_LINES = 50


class ErrorKind(StrEnum):
    CONFIG = "config"
    ENVIRONMENT = "environment"
    INTEGRITY = "integrity"
    FETCH = "fetch"
    ADAPTER = "adapter"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    POLICY = "policy"
    INTERNAL = "internal"


class IProofsError(Exception):
    """The only exception type that crosses module boundaries."""

    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        step: str | None = None,
        exit_code: int | None = None,
        last_lines: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.step = step
        self.exit_code = exit_code
        self.last_lines = last_lines


# Where the error surfaced: `iproofs validate`, `iproofs run` before any job, or inside a job.
Phase = Literal["validate", "preflight", "job"]

_FIXED_EXIT = {
    ErrorKind.ENVIRONMENT: 3,
    ErrorKind.FETCH: 4,
    ErrorKind.ADAPTER: 4,
    ErrorKind.TIMEOUT: 4,
    ErrorKind.RESOURCE: 4,
    ErrorKind.INTERNAL: 5,
}


def exit_code(kind: ErrorKind, phase: Phase) -> int:
    """CLI exit code for an error kind, per the RFC-0010 §Error taxonomy table."""
    if kind in _FIXED_EXIT:
        return _FIXED_EXIT[kind]
    if phase == "validate":
        return 1  # config, integrity and policy found by a check
    if kind is ErrorKind.CONFIG:
        return 2  # bad input before any job starts
    return 4  # integrity or policy inside a run


def _cap_bytes(text: str, limit: int) -> str:
    raw = text.encode("utf-8")
    return text if len(raw) <= limit else raw[:limit].decode("utf-8", errors="ignore")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Failure:
    kind: ErrorKind
    step: str  # state name at which the failure occurred
    message: str  # <= 4096 bytes; redacted before writing (docs/spec/05 §Redaction)
    exit_code: int | None  # container or process exit code, if any
    last_lines: tuple[str, ...]  # last 50 lines of adapter stderr
    at: str  # RFC 3339 UTC timestamp

    @classmethod
    def from_error(cls, error: IProofsError, *, step: str, at: str | None = None) -> "Failure":
        return cls.build(
            error.kind,
            error.step or step,
            error.message,
            exit_code=error.exit_code,
            last_lines=error.last_lines,
            at=at,
        )

    @classmethod
    def build(
        cls,
        kind: ErrorKind,
        step: str,
        message: str,
        *,
        exit_code: int | None = None,
        last_lines: tuple[str, ...] | list[str] = (),
        at: str | None = None,
    ) -> "Failure":
        """Construct a failure with the RFC-0010 caps applied."""
        return cls(
            kind=kind,
            step=step,
            message=_cap_bytes(message, MAX_MESSAGE_BYTES),
            exit_code=exit_code,
            last_lines=tuple(last_lines)[-MAX_LAST_LINES:],
            at=at or utc_now(),
        )

    def to_json(self) -> dict[str, object]:
        """The `failure` object of run.json (RFC-0010 §Failure record)."""
        return {
            "kind": str(self.kind),
            "step": self.step,
            "message": self.message,
            "exit_code": self.exit_code,
            "last_lines": list(self.last_lines),
            "at": self.at,
        }
