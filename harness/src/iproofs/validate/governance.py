"""MAINTAINERS.md rows and maintainer seat rules (RFC-0001 §Roles, rules 1 to 4).

Rule ids, under gate G2 (RFC-0013 §G2): GOV-1 a row lacks a handle, role, organisation or
declared interests (`undeclared` is a warning: not a final value); GOV-2 INV-GOV-1, fewer than
two organisations among maintainers (a warning, a failure at release approval); GOV-3
INV-GOV-2, four or more seats and one organisation holds more than half.
"""

from collections import Counter
from dataclasses import dataclass

from iproofs.errors import ErrorKind
from iproofs.validate import Finding

PATH = "MAINTAINERS.md"
COLUMNS = ("Handle", "Role", "Organisation", "Systems maintained", "Declared interests", "Since")
REQUIRED = {"handle": "Handle", "role": "Role", "organisation": "Organisation"}
PLACEHOLDER = "undeclared"
UNAFFILIATED = frozenset({"none", "independent", "individual"})


@dataclass(frozen=True, slots=True)
class Row:
    line: int
    handle: str
    role: str
    organisation: str
    systems: str
    interests: str
    since: str

    def seat_organisation(self) -> str:
        """Rule 3: an individual without an affiliation counts as their own organisation."""
        org = self.organisation.strip().lower()
        return f"individual:{self.handle}" if org in UNAFFILIATED | {PLACEHOLDER, ""} else org


def parse(text: str) -> list[Row]:
    """Every row of every table whose header is the RFC-0001 maintainer shape."""
    rows, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        if tuple(_cells(lines[i])) == COLUMNS:
            i += 2  # header and separator
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = _cells(lines[i])
                cells += [""] * (len(COLUMNS) - len(cells))
                rows.append(Row(i + 1, *cells[: len(COLUMNS)]))
                i += 1
        i += 1
    return rows


def _cells(line: str) -> list[str]:
    s = line.strip()
    return [c.strip() for c in s.strip("|").split("|")] if s.startswith("|") else []


def check(text: str, *, release: bool = False) -> list[Finding]:
    rows = parse(text)
    found = [f for r in rows for f in _row(r)]
    maintainers = [r for r in rows if r.role == "maintainer"]
    seats = Counter(r.seat_organisation() for r in maintainers)
    if len(seats) < 2:
        found.append(
            _finding(
                "GOV-2",
                "",
                f"INV-GOV-1: maintainers from {len(seats)} organisation(s); two are needed "
                "before the first public release",
                warning=not release,
                hint="elect a maintainer from another organisation",
            )
        )
    if len(maintainers) >= 4:
        org, held = seats.most_common(1)[0]
        if held * 2 > len(maintainers):
            found.append(
                _finding(
                    "GOV-3",
                    "",
                    f"INV-GOV-2: {org} holds {held} of {len(maintainers)} maintainer seats",
                    hint="no organisation may hold more than half the seats (60 days to restore)",
                )
            )
    return found


def _row(r: Row) -> list[Finding]:
    found = []
    values = {"handle": r.handle, "role": r.role, "organisation": r.organisation}
    values["declared interests"] = r.interests
    for name, value in values.items():
        if not value:
            found.append(
                _finding(
                    "GOV-1",
                    str(r.line),
                    f"row {r.handle or '?'} has no {name}",
                    hint="every row names it; `none` is a valid declaration of no interests",
                )
            )
        elif value == PLACEHOLDER:
            found.append(
                _finding(
                    "GOV-1",
                    str(r.line),
                    f"row {r.handle} has {name} `undeclared`, not a final value",
                    warning=True,
                    hint="state it before RFC Last call (RFC-0001 §Migration / Rollout)",
                )
            )
    return found


def _finding(rule: str, line: str, message: str, *, warning: bool = False, hint: str) -> Finding:
    path = f"{PATH}:{line}" if line else PATH
    return Finding("G2", path, rule, message, ErrorKind.POLICY, hint=hint, warning=warning)
