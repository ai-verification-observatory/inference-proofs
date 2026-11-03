"""Secret and host-identifier patterns shared by the redactor and gate G9 (RFC-0013 §G9).

Layer 0, standard library only, so both iproofs.log and iproofs.validate can import it and
what the redactor removes is exactly what the scanner looks for.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pattern:
    rule: str  # RFC-0013 rule id
    kind: str  # class named in the replacement marker, <redacted:kind>
    regex: re.Pattern[str]


_IPV4 = r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"
# IPv6 candidates; `is_ipv6` keeps only those with "::" or at least three colons, so clock
# times such as 10:15:02 never match.
_IPV6 = r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])"

# Order matters: MAC addresses are removed before IPv6 candidates are considered.
PATTERNS: tuple[Pattern, ...] = (
    Pattern("SEC-4", "private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    Pattern("SEC-1", "token", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    Pattern("SEC-2", "token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    Pattern("SEC-3", "token", re.compile(r"AKIA[0-9A-Z]{16}")),
    Pattern(
        "SEC-11",
        "secret",
        re.compile(
            r"(?i)((?:token|secret|password|api[_-]?key|credential)\s*[:=]\s*['\"]?)"
            r"[A-Za-z0-9/+_\-]{16,}"
        ),
    ),
    Pattern("SEC-9", "ssh", re.compile(r"(?m)^(\s*(?:Host|HostName|IdentityFile)\s+)\S+")),
    Pattern(
        "SEC-8",
        "gpu_uuid",
        re.compile(r"GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
    ),
    Pattern("SEC-7", "mac", re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")),
    Pattern("SEC-5", "ip", re.compile(_IPV4)),
    Pattern("SEC-6", "ip", re.compile(_IPV6)),
    Pattern("SEC-10", "home", re.compile(r"/home/[a-z_][a-z0-9_-]*/|/Users/[^/\s]+/")),
)

IPV4_ALLOWED = frozenset({"127.0.0.1", "0.0.0.0"})
IPV6_ALLOWED = frozenset({"::1"})


def is_ipv6(candidate: str) -> bool:
    return candidate not in IPV6_ALLOWED and ("::" in candidate or candidate.count(":") >= 3)
