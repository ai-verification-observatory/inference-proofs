"""Redaction of secrets and host identifiers (docs/spec/05-observability.md §Redaction)."""

import functools
import os
import re
import socket
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path

from iproofs.errors import Failure
from iproofs.log.patterns import IPV4_ALLOWED, PATTERNS, Pattern, is_ipv6

SECRET_NAME = re.compile(r"(?i)(token|key|secret|password|credential)")
MIN_SECRET_LENGTH = 8


def marker(kind: str) -> str:
    return f"<redacted:{kind}>"


class Redactor:
    """Replaces known literals (env secrets, host name, GPU serials) and every shared pattern."""

    patterns: tuple[Pattern, ...] = PATTERNS

    def __init__(self, literals: Mapping[str, Iterable[str]], home: str | None = None) -> None:
        pairs = [(value, kind) for kind, values in literals.items() for value in values if value]
        # longest first, so a value that contains another is replaced whole
        self.literals = sorted(set(pairs), key=lambda p: (-len(p[0]), p[0]))
        self.home = home.rstrip("/") if home else None

    @classmethod
    def from_host(
        cls,
        env: Mapping[str, str] | None = None,
        hostname: str | None = None,
        home: str | None = None,
        gpu_serials: Iterable[str] = (),
    ) -> "Redactor":
        env = os.environ if env is None else env
        host = socket.gethostname() if hostname is None else hostname
        secrets = [
            v
            for k, v in env.items()
            if (SECRET_NAME.search(k) or k == "HF_TOKEN") and len(v) >= MIN_SECRET_LENGTH
        ]
        hosts = [h for h in {host, host.split(".")[0]} if h and h != "localhost"]
        return cls(
            {"env_secret": secrets, "hostname": hosts, "gpu_serial": list(gpu_serials)},
            home=str(Path.home()) if home is None else home,
        )

    def __call__(self, text: str) -> str:
        for value, kind in self.literals:
            text = text.replace(value, marker(kind))
        if self.home:
            text = re.sub(re.escape(self.home) + r"(?=/|\b)", "~", text)
        for p in self.patterns:
            text = p.regex.sub(functools.partial(self._replace, p), text)
        return text

    @staticmethod
    def _replace(p: Pattern, m: re.Match[str]) -> str:
        found = m.group(0)
        if p.rule == "SEC-5" and found in IPV4_ALLOWED:
            return found
        if p.rule == "SEC-6" and not is_ipv6(found):
            return found
        if p.rule == "SEC-10":
            return "~/"
        if p.rule in {"SEC-11", "SEC-9"}:
            return m.group(1) + marker(p.kind)  # keep the key, drop the value
        return marker(p.kind)

    def failure(self, f: Failure) -> Failure:
        """A failure record with its message and stderr lines redacted before writing."""
        return replace(f, message=self(f.message), last_lines=tuple(self(x) for x in f.last_lines))
