"""RFC-0016 §Validation rules (G2): `CRIT-1` to `CRIT-14` on `web/_data/criteria.json`.

The schema (`criteria/1`) holds the shape; these rules hold what a schema cannot: which quote
decides a cell, the pins, the sources a row class allows, the states a claim card allows, the
reference rows' table, the RFC-0015 text and git objects the quotes cite, and the negative
control override recomputed from the stored `controls.json` files (OVR-2 to OVR-8). Every rule
reads only the tree being validated and its git objects: no clock, no network.
"""

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from iproofs.controls import CONTROL_PROPERTY, runs_read
from iproofs.errors import ErrorKind, IProofsError
from iproofs.serialize import load_yaml
from iproofs.validate import Finding

PATH = "web/_data/criteria.json"
RFC_0015 = "rfcs/0015-reference-rows.md"
PROPERTIES = (
    "weights_hidden",
    "model_bound",
    "whole_output",
    "formally_verified",
    "security_level",
    "no_trusted_party",
)
STATES = ("yes", "partly", "no", "not_stated")
CARD, REFERENCE, PUBLIC = "claim_card_at_pin", "reference_rfc_0015", "public_sources"
AGGREGATE = {"total", "score", "rank", "count", "sum", "average", "mean", "weight"}  # CRIT-10
# ST-8: the stated state of a cell whose allowed quotes meet the rules of two states
CONFLICT = {
    frozenset({"yes", "partly"}): "partly",
    frozenset({"yes", "no"}): "no",
    frozenset({"partly", "no"}): "no",
}
# RFC-0016 §Reference rows, the table: the states of each method with no declared precision
# substitution, by `reference_role` (SRC-5). SRC-6: a recompute row whose workloads declare a
# substitution is `partly` on Model bound.
REFERENCE_TABLE: Mapping[str, Mapping[str, str]] = {
    "serve": dict.fromkeys(PROPERTIES, "no"),
    "recompute": {
        "weights_hidden": "no",
        "model_bound": "yes",
        "whole_output": "yes",
        "formally_verified": "no",
        "security_level": "no",
        "no_trusted_party": "yes",
    },
}
STATE_HINT = "RFC-0016 §States, §Properties"


def control_map() -> Mapping[str, str | None]:
    """The OVR-2 control map the override reads: `iproofs.controls.CONTROL_PROPERTY`, which the
    site reads too, tested against the RFC table."""
    return CONTROL_PROPERTY


def _f(rule: str, message: str, kind: ErrorKind, pointer: str = "", hint: str = "") -> Finding:
    return Finding("G2", PATH, rule, message, kind, pointer, hint)


def _config(rule: str, message: str, pointer: str = "", hint: str = "") -> Finding:
    return _f(rule, message, ErrorKind.CONFIG, pointer, hint)


def _integrity(rule: str, message: str, pointer: str = "", hint: str = "") -> Finding:
    return _f(rule, message, ErrorKind.INTEGRITY, pointer, hint)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _list(node: object) -> list[Any]:
    return node if isinstance(node, list) else []


def _map(node: object) -> Mapping[str, Any]:
    return node if isinstance(node, Mapping) else {}


def stated_of(cell: Mapping[str, Any]) -> object:
    """The cell's stated state: `stated` on an overridden cell, else `state` (OVR-4)."""
    return cell.get("stated", cell.get("state"))


def check(root: Path, files: Iterable[str]) -> list[Finding]:
    """The CRIT rules, when the criteria file is among `files` (shape is G2 SCHEMA's)."""
    if PATH not in set(files):
        return []
    try:
        doc = json.loads((root / PATH).read_text("utf-8"))
    except (OSError, ValueError):
        return []  # G2 SCHEMA reports a file that does not parse
    return rules(root, doc) if isinstance(doc, Mapping) else []


def rules(root: Path, doc: Mapping[str, Any]) -> list[Finding]:
    """CRIT-1 to CRIT-14 on one parsed criteria file in the tree at `root`, in rule order."""
    rows = [r for r in _list(doc.get("rows")) if isinstance(r, Mapping)]
    found = crit_9(doc, rows) + crit_10(doc)
    for i, row in enumerate(rows):
        where = f"/rows/{i}"
        found += crit_1(row, where) + crit_4(row, where) + crit_11(row, where)
        found += crit_12(row, where) + crit_14(row, where)
        if row.get("source_class") == CARD:
            found += crit_5(root, row, where) + crit_6(root, row, where)
        elif row.get("source_class") == REFERENCE:
            found += crit_7(root, row, where)
    found += crit_2(doc, rows) + crit_3(root, doc, rows) + crit_8(root, rows)
    found += crit_13(root, doc, rows)
    order = {f"CRIT-{n}": n for n in range(1, 15)}
    return sorted(found, key=lambda f: (order.get(f.rule, 99), f.pointer, f.message))


# ---------------------------------------------------------------- walking the file


def cells(row: Mapping[str, Any], where: str) -> list[tuple[str, str, Mapping[str, Any]]]:
    """(property, pointer, cell) for each of the six cells a row carries."""
    got = _map(row.get("cells"))
    return [
        (p, f"{where}/cells/{p}", got[p]) for p in PROPERTIES if isinstance(got.get(p), Mapping)
    ]


def quotes_of(
    cell: Mapping[str, Any], pointer: str, *, outside: bool = True
) -> list[tuple[str, Mapping[str, Any]]]:
    """(pointer, quote) for the cell's quotes, its `aside` quotes and, unless `outside` is
    False, its `outside_pin` quotes."""
    out = [(f"{pointer}/quotes/{i}", q) for i, q in enumerate(_list(cell.get("quotes")))]
    parts = ("aside", "outside_pin") if outside else ("aside",)
    for part in parts:
        node = _map(cell.get(part))
        out += [
            (f"{pointer}/{part}/quotes/{i}", q) for i, q in enumerate(_list(node.get("quotes")))
        ]
    return [(p, q) for p, q in out if isinstance(q, Mapping)]


def all_quotes(
    rows: list[Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    """(pointer, quote, row) for every quote of the file."""
    return [
        (p, q, row)
        for i, row in enumerate(rows)
        for _, cp, c in cells(row, f"/rows/{i}")
        for p, q in quotes_of(c, cp)
    ]


# ---------------------------------------------------------------- CRIT-1 deciding quotes


def crit_1(row: Mapping[str, Any], where: str) -> list[Finding]:
    """A coloured cell has a deciding first quote and no other; side quotes never decide;
    an ST-8 cell follows the table; every quote is checked."""
    found = []
    for _, pointer, cell in cells(row, where):
        quotes = [q for q in _list(cell.get("quotes")) if isinstance(q, Mapping)]
        stated = stated_of(cell)
        if stated in ("yes", "partly", "no"):
            if not quotes:
                found.append(
                    _config(
                        "CRIT-1",
                        f"a {stated} cell has no quote",
                        pointer,
                        "quote the sentence that meets the rule, or set not_stated",
                    )
                )
            elif quotes[0].get("decides") is not True:
                found.append(
                    _config(
                        "CRIT-1",
                        "the first quote does not decide the cell",
                        f"{pointer}/quotes/0",
                        "put the deciding quote first, with decides: true",
                    )
                )
            for i, q in enumerate(quotes[1:], 1):
                if q.get("decides") is True:
                    found.append(
                        _config(
                            "CRIT-1",
                            "a second deciding quote; one quote decides a cell",
                            f"{pointer}/quotes/{i}",
                            "set decides: false on supporting quotes",
                        )
                    )
        found += _side_quotes(cell, pointer)
        if cell.get("conflict") is True:
            found += _conflict(cell, pointer, quotes, stated)
        else:
            found += [
                _config(
                    "CRIT-1",
                    "meets is only for the quotes of a conflict cell",
                    qp,
                    "drop it, or set conflict: true (ST-8)",
                )
                for qp, q in quotes_of(cell, pointer)
                if "meets" in q
            ]
        for qp, q in quotes_of(cell, pointer):
            if q.get("checked") is not True:
                found.append(
                    _config(
                        "CRIT-1",
                        "quote not checked against its source",
                        qp,
                        "check it and set checked: true with checked_how",
                    )
                )
    return found


def _side_quotes(cell: Mapping[str, Any], pointer: str) -> list[Finding]:
    """`aside` and `outside_pin` quotes set nothing (ST-5, SRC-1, SRC-3)."""
    return [
        _config(
            "CRIT-1",
            f"an {part} quote decides; it sets nothing",
            f"{pointer}/{part}/quotes/{i}",
            "set decides: false",
        )
        for part in ("aside", "outside_pin")
        for i, q in enumerate(_list(_map(cell.get(part)).get("quotes")))
        if _map(q).get("decides") is not False
    ]


def _conflict(
    cell: Mapping[str, Any], pointer: str, quotes: list[Mapping[str, Any]], stated: object
) -> list[Finding]:
    """ST-8: two quotes meeting the rules of different states; each names the state whose rule
    it meets in `meets`, and the cell's stated state is the table's."""
    if len(quotes) < 2:
        return [
            _config(
                "CRIT-1",
                "a conflict cell quotes fewer than two sources",
                pointer,
                "quote both statements (ST-8)",
            )
        ]
    met = frozenset(str(q.get("meets")) for q in quotes if q.get("meets") in STATES)
    want = CONFLICT.get(met)
    if want is None:
        return [
            _config(
                "CRIT-1",
                "a conflict cell's quotes do not meet two of yes, partly and no",
                pointer,
                "name each quote's state in meets (ST-8)",
            )
        ]
    if stated != want:
        return [
            _config(
                "CRIT-1",
                f"a conflict of {' and '.join(sorted(met))} is {want}, the cell is {stated}",
                pointer,
                "apply the ST-8 table",
            )
        ]
    return []


# ---------------------------------------------------------------- CRIT-2 pins


def crit_2(doc: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> list[Finding]:
    """Repository quotes sit at the pinned full commit; every pin is used."""
    pins = _map(doc.get("pins"))
    found, used = [], set()
    for pointer, q, _ in all_quotes(rows):
        if q.get("kind") not in ("repository", "this_repository"):
            continue
        repo, commit = str(q.get("repo")), str(q.get("commit"))
        used.add(repo)
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            found.append(
                _integrity(
                    "CRIT-2",
                    f"commit {commit!r} is not a full 40-hex commit",
                    f"{pointer}/commit",
                    "quote at the full commit hash",
                )
            )
        elif pins.get(repo) != commit:
            found.append(
                _integrity(
                    "CRIT-2",
                    f"{repo} is quoted at {commit[:12]}, pinned at {str(pins.get(repo))[:12]}",
                    f"{pointer}/commit",
                    "quote at the pinned commit, or move the pin",
                )
            )
        if commit not in str(q.get("url")):
            found.append(
                _integrity(
                    "CRIT-2",
                    "the url does not name the quote's commit",
                    f"{pointer}/url",
                    "link the file at the commit",
                )
            )
    for i, row in enumerate(rows):
        for _, _, cell in cells(row, f"/rows/{i}"):
            used |= {
                str(s.get("repo"))
                for s in _list(cell.get("sources_read"))
                if isinstance(s, Mapping) and "repo" in s
            }
    for repo in sorted(set(pins) - used):
        found.append(
            _integrity(
                "CRIT-2",
                f"pin {repo} is used by no quote or source read",
                f"/pins/{repo}",
                "remove the pin",
            )
        )
    return found


# ---------------------------------------------------------------- CRIT-3 web quotes, own sources


def crit_3(root: Path, doc: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> list[Finding]:
    """A web quote carries what was read (SRC-9); a public row decides from its own sources."""
    found = []
    date = str(doc.get("date"))
    for pointer, q, _ in all_quotes(rows):
        if q.get("kind") == "web":
            found += _web_quote(root, q, pointer, date)
    for i, row in enumerate(rows):
        if row.get("source_class") != PUBLIC:
            continue
        own = [s for s in _list(row.get("own_sources")) if isinstance(s, Mapping)]
        for _, pointer, cell in cells(row, f"/rows/{i}"):
            quotes = _list(cell.get("quotes"))
            first = _map(quotes[0]) if quotes else {}
            if first.get("decides") is True and not own_source(first, own):
                found.append(
                    _integrity(
                        "CRIT-3",
                        "the deciding quote is not from one of the row's own sources",
                        f"{pointer}/quotes/0",
                        "quote the system's own authors, or move the quote "
                        "to sources_read and set not_stated (SRC-8)",
                    )
                )
    return found


def _web_quote(root: Path, q: Mapping[str, Any], pointer: str, date: str) -> list[Finding]:
    found = []
    if not str(q.get("url")).startswith("https://"):
        found.append(_integrity("CRIT-3", "a web quote's url is not https", f"{pointer}/url"))
    retrieved = q.get("retrieved")
    if not isinstance(retrieved, str):
        found.append(
            _integrity(
                "CRIT-3",
                "a web quote has no retrieved date",
                f"{pointer}/retrieved",
                "re-read the page and record the date",
            )
        )
    elif retrieved > date:
        found.append(
            _integrity(
                "CRIT-3",
                f"retrieved {retrieved} is after the file's date {date}",
                f"{pointer}/retrieved",
            )
        )
    copy = q.get("copy")
    if not q.get("archive_url") and not isinstance(copy, Mapping):
        found.append(
            _integrity(
                "CRIT-3",
                "a web quote has no archive_url and no copy",
                pointer,
                "archive the page as read, or set the cell not_stated with the "
                "url in sources_read (SRC-9)",
            )
        )
    elif isinstance(copy, Mapping):
        path = root / str(copy.get("path"))
        if not path.is_file():
            found.append(
                _integrity(
                    "CRIT-3", f"copy {copy.get('path')} does not exist", f"{pointer}/copy/path"
                )
            )
        elif hashlib.sha256(path.read_bytes()).hexdigest() != copy.get("sha256"):
            found.append(
                _integrity(
                    "CRIT-3",
                    f"copy {copy.get('path')} does not match its sha256",
                    f"{pointer}/copy/sha256",
                )
            )
    return found


def own_source(q: Mapping[str, Any], own: list[Mapping[str, Any]]) -> bool:
    """SRC-8: a repository quote from a listed repository; a web quote whose host is a listed
    domain or whose url starts with a listed url."""
    if q.get("kind") == "repository":
        return any(s.get("repo") == q.get("repo") for s in own)
    if q.get("kind") == "web":
        url = str(q.get("url"))
        host = urlparse(url).hostname or ""
        return any(
            s.get("domain") == host or ("url" in s and url.startswith(str(s["url"]))) for s in own
        )
    return False


# ---------------------------------------------------------------- CRIT-4 Not stated cells


def crit_4(row: Mapping[str, Any], where: str) -> list[Finding]:
    """A Not stated cell decides nothing and lists what was read, or says nothing was."""
    found = []
    for _, pointer, cell in cells(row, where):
        if cell.get("not_copied") is True and row.get("source_class") != PUBLIC:
            found.append(
                _config(
                    "CRIT-4",
                    "not_copied on a row that is not a public-source row",
                    f"{pointer}/not_copied",
                    "list the sources read",
                )
            )
        if stated_of(cell) != "not_stated":
            if "not_copied" in cell:
                found.append(
                    _config(
                        "CRIT-4",
                        f"not_copied on a {stated_of(cell)} cell; it marks a not_stated cell "
                        "where nothing was read",
                        f"{pointer}/not_copied",
                        "drop not_copied, or set not_stated if nothing was read (Q2)",
                    )
                )
            continue
        if any(_map(q).get("decides") is True for q in _list(cell.get("quotes"))):
            found.append(
                _config(
                    "CRIT-4",
                    "a not_stated cell has a deciding quote",
                    pointer,
                    "set the state its quote meets, or decides: false",
                )
            )
        listed, marker = bool(_list(cell.get("sources_read"))), cell.get("not_copied") is True
        if listed == marker:
            found.append(
                _config(
                    "CRIT-4",
                    "a not_stated cell needs exactly one of sources_read or not_copied: true",
                    pointer,
                    "list what was read; not_copied only where nothing was",
                )
            )
    return found


# ---------------------------------------------------------------- CRIT-5, CRIT-6 card rows


def card_file(root: Path, card: Mapping[str, Any]) -> Path | None:
    """The claim card a row names (RFC-0002 §File and identity), or None."""
    system, configuration = str(card.get("system")), str(card.get("configuration"))
    for path in (
        root / "systems" / system / "claims" / f"{configuration}.yaml",
        root / "systems" / system / "claim.yaml",
    ):
        if path.is_file():
            doc = load_yaml(path)
            if doc.get("configuration") == configuration:
                return path
    return None


def _card(root: Path, row: Mapping[str, Any]) -> dict[str, Any] | None:
    path = card_file(root, _map(row.get("card")))
    return None if path is None else dict(load_yaml(path))


def crit_5(root: Path, row: Mapping[str, Any], where: str) -> list[Finding]:
    """The card exists with the row's identity; every quote (outside `outside_pin`) is at the
    card's pin, and every Not stated cell read the card's repository at it."""
    card = _map(row.get("card"))
    doc = _card(root, row)
    if doc is None:
        return [
            _integrity(
                "CRIT-5",
                f"no claim card {card.get('system')}/{card.get('configuration')}",
                f"{where}/card",
                "name a card under systems/<system>/",
            )
        ]
    found = []
    if str(doc.get("card_version")) != str(card.get("card_version")):
        found.append(
            _integrity(
                "CRIT-5",
                f"the card is version {doc.get('card_version')}, the row "
                f"names {card.get('card_version')}",
                f"{where}/card/card_version",
                "re-read every cell against the new card",
            )
        )
    if doc.get("system") != card.get("system"):
        found.append(_integrity("CRIT-5", "the card names another system", f"{where}/card/system"))
    up = _map(doc.get("upstream"))
    repo, commit = up.get("repo"), up.get("commit")
    for _, pointer, cell in cells(row, where):
        for qp, q in quotes_of(cell, pointer, outside=False):
            if (q.get("repo"), q.get("commit")) != (repo, commit):
                found.append(
                    _integrity(
                        "CRIT-5",
                        f"quote from {q.get('repo') or q.get('url')}, "
                        f"not the card's {repo} at {str(commit)[:12]}",
                        qp,
                        "quote the card's pin, or move it to outside_pin (SRC-2, SRC-3)",
                    )
                )
        if stated_of(cell) == "not_stated" and not any(
            _map(s).get("repo") == repo and _map(s).get("commit") == commit
            for s in _list(cell.get("sources_read"))
        ):
            found.append(
                _integrity(
                    "CRIT-5",
                    f"sources_read does not include {repo} at {str(commit)[:12]}",
                    f"{pointer}/sources_read",
                    "read the card's repository at its pin",
                )
            )
    return found


def card_allows(card: Mapping[str, Any], prop: str) -> frozenset[str]:
    """The stated states a card value allows for one property (RFC-0016 §Card rows table); a
    value the table does not name allows all four."""
    zk, sec = _map(card.get("zero_knowledge")), _map(card.get("security"))
    policy = _map(_map(card.get("coverage")).get("policy")).get("kind")
    table = {
        "weights_hidden": [
            (zk.get("claimed") == "not stated", {"not_stated"}),
            (zk.get("claimed") is False, {"partly", "no"}),
        ],
        "model_bound": [
            (policy == "tolerance", {"partly", "no"}),
            (policy == "not_stated" and card.get("binding") == "not stated", {"not_stated"}),
        ],
        "formally_verified": [
            (card.get("relation_formal") == "not stated", {"partly", "no", "not_stated"}),
        ],
        "security_level": [(sec.get("level") == "not stated", {"not_stated"})],
        "no_trusted_party": [
            (sec.get("setup") == "trusted", {"partly", "no"}),
            (
                sec.get("setup") == "not_stated" and card.get("assumptions_not_stated") is True,
                {"not_stated"},
            ),
        ],
    }
    return next((frozenset(a) for hit, a in table.get(prop, []) if hit), frozenset(STATES))


def crit_6(root: Path, row: Mapping[str, Any], where: str) -> list[Finding]:
    """Each stated state is one the card's fields allow (SRC-4)."""
    doc = _card(root, row)
    if doc is None:
        return []  # CRIT-5
    found = []
    for prop, pointer, cell in cells(row, where):
        allowed, stated = card_allows(doc, prop), stated_of(cell)
        if stated not in allowed:
            found.append(
                _integrity(
                    "CRIT-6",
                    f"the card allows {', '.join(sorted(allowed))} on "
                    f"{prop}, the cell states {stated}",
                    pointer,
                    "re-read the cell against the card",
                )
            )
    return found


# ---------------------------------------------------------------- CRIT-7 reference rows


def crit_7(root: Path, row: Mapping[str, Any], where: str) -> list[Finding]:
    """Reference quotes are RFC-0015's current text; workloads exist and agree; states are the
    table's, SRC-6 applied."""
    found = []
    rfc = root / RFC_0015
    text = _norm(rfc.read_text("utf-8")) if rfc.is_file() else ""
    for _, pointer, cell in cells(row, where):
        for qp, q in quotes_of(cell, pointer):
            if q.get("kind") != "this_repository" or q.get("path") != RFC_0015:
                found.append(_integrity("CRIT-7", f"a reference quote not from {RFC_0015}", qp))
            elif _norm(str(q.get("text"))) not in text:
                found.append(
                    _integrity(
                        "CRIT-7",
                        f"quote no longer in {RFC_0015}",
                        qp,
                        "amend the quote and, if a state changes, the "
                        "RFC-0016 reference table (SRC-5)",
                    )
                )
    path = root / "systems" / str(row.get("id")) / "system.yaml"
    system = dict(load_yaml(path)) if path.is_file() else {}
    role = system.get("reference_role")
    if role not in REFERENCE_TABLE:
        return [
            *found,
            _integrity(
                "CRIT-7",
                f"no reference system {row.get('id')} with a role of the reference table",
                f"{where}/id",
            ),
        ]
    listed = {str(w.get("id")): w for w in _list(system.get("workloads")) if isinstance(w, Mapping)}
    substituted = set()
    for i, wid in enumerate(_list(row.get("workloads"))):
        if wid not in listed:
            found.append(
                _integrity(
                    "CRIT-7",
                    f"workload {wid} is not in {row.get('id')}'s system.yaml",
                    f"{where}/workloads/{i}",
                )
            )
        else:
            substituted.add(listed[wid].get("precision_substitution") is not None)
    if len(substituted) > 1:
        found.append(
            _integrity(
                "CRIT-7",
                "the row's workloads disagree on whether a precision substitution is declared",
                f"{where}/workloads",
                "one row per substitution case (SRC-6)",
            )
        )
    want = dict(REFERENCE_TABLE[str(role)])
    if role == "recompute" and substituted == {True}:
        want["model_bound"] = "partly"
    for prop, pointer, cell in cells(row, where):
        if cell.get("state") != want[prop]:
            found.append(
                _integrity(
                    "CRIT-7",
                    f"the reference table sets {want[prop]}, the cell is {cell.get('state')}",
                    f"{pointer}/state",
                    "follow the RFC-0016 reference table",
                )
            )
    return found


# ---------------------------------------------------------------- CRIT-8 this repository's text


def git_show(root: Path, commit: str, path: str) -> str | None:
    """`git show <commit>:<path>` in the tree at `root`; None when the object is absent."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True, check=False
        )
    except OSError:
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def crit_8(root: Path, rows: list[Mapping[str, Any]]) -> list[Finding]:
    """Each `this_repository` quote reads at its lines in git; a missing commit is an
    environment error, never a pass."""
    found, shown = [], {}
    for pointer, q, _ in all_quotes(rows):
        if q.get("kind") != "this_repository":
            continue
        commit, path = str(q.get("commit")), str(q.get("path"))
        key = (commit, path)
        if key not in shown:
            shown[key] = git_show(root, commit, path)
        body = shown[key]
        if body is None:
            found.append(
                _f(
                    "CRIT-8",
                    f"{commit[:12]}:{path} is not in the local object store",
                    ErrorKind.ENVIRONMENT,
                    pointer,
                    "fetch the full history (fetch-depth: 0)",
                )
            )
            continue
        span = re.fullmatch(r"L(\d+)(?:-L(\d+))?", str(q.get("lines")))
        lines = body.splitlines()
        if span is None:
            continue  # schema
        first, last = int(span[1]), int(span[2] or span[1])
        if _norm(str(q.get("text"))) not in _norm(" ".join(lines[first - 1 : last])):
            found.append(
                _integrity(
                    "CRIT-8",
                    f"text not at {path} {q.get('lines')} in {commit[:12]}",
                    f"{pointer}/text",
                    "copy the text verbatim and its lines",
                )
            )
    return found


# ---------------------------------------------------------------- CRIT-9 to CRIT-12 shape


def crit_9(doc: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> list[Finding]:
    found = []
    if _list(doc.get("order")) != list(PROPERTIES):
        found.append(
            _config(
                "CRIT-9",
                "order is not the six properties in display order",
                "/order",
                ", ".join(PROPERTIES),
            )
        )
    ids = [_map(p).get("id") for p in _list(doc.get("properties"))]
    if ids != list(PROPERTIES):
        found.append(
            _config("CRIT-9", "properties are not the six in display order", "/properties")
        )
    seen: set[object] = set()
    for i, row in enumerate(rows):
        if set(_map(row.get("cells"))) != set(PROPERTIES):
            found.append(
                _config("CRIT-9", "a row does not have exactly the six cells", f"/rows/{i}/cells")
            )
        if row.get("id") in seen:
            found.append(_config("CRIT-9", f"row id {row.get('id')} repeats", f"/rows/{i}/id"))
        seen.add(row.get("id"))
    return found


def crit_10(doc: object, pointer: str = "") -> list[Finding]:
    """No number and no aggregate key anywhere (INV-GLYPH-1, INV-GLYPH-2)."""
    found = []
    if isinstance(doc, Mapping):
        for k, v in doc.items():
            here = f"{pointer}/{k}"
            if str(k).lower() in AGGREGATE:
                found.append(
                    _config(
                        "CRIT-10",
                        f"key {k!r} would total, rank or weigh states",
                        here,
                        "remove it (INV-GLYPH-1)",
                    )
                )
            found += crit_10(v, here)
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            found += crit_10(v, f"{pointer}/{i}")
    elif isinstance(doc, int | float) and not isinstance(doc, bool):
        found.append(
            _config(
                "CRIT-10",
                "a number in the criteria file",
                pointer or "/",
                "the file holds no number (INV-GLYPH-2)",
            )
        )
    return found


ONLY = {"outside_pin": CARD, "stated": CARD, "contradicted_by": CARD}


def crit_11(row: Mapping[str, Any], where: str) -> list[Finding]:
    found = []
    cls = row.get("source_class")
    for key, owner in (("disclosures", CARD), ("workloads", REFERENCE), ("own_sources", PUBLIC)):
        if key in row and cls != owner:
            found.append(_config("CRIT-11", f"{key} on a {cls} row", f"{where}/{key}"))
    for _, pointer, cell in cells(row, where):
        for key, owner in ONLY.items():
            if key in cell and cls != owner:
                found.append(
                    _config(
                        "CRIT-11",
                        f"{key} on a {cls} row",
                        f"{pointer}/{key}",
                        "only card rows carry it (SRC-3, OVR-1)",
                    )
                )
    return found


def crit_12(row: Mapping[str, Any], where: str) -> list[Finding]:
    public = row.get("source_class") == PUBLIC
    tab = row.get("tab")
    if (public and tab not in ("not_benchmarked", "archived")) or (
        not public and tab != "benchmarked"
    ):
        return [
            _config(
                "CRIT-12",
                f"a {row.get('source_class')} row in tab {tab}",
                f"{where}/tab",
                "public-source rows are never benchmarked; card and reference rows are",
            )
        ]
    return []


# ---------------------------------------------------------------- CRIT-13, CRIT-14 the override


def crit_14(row: Mapping[str, Any], where: str) -> list[Finding]:
    """`stated` with `contradicted_by`, on a `no` cell, from mapped controls, sorted; disclosure
    entries sorted and complete."""
    found = []
    for prop, pointer, cell in cells(row, where):
        has_stated, has_by = "stated" in cell, "contradicted_by" in cell
        if has_stated != has_by:
            found.append(_config("CRIT-14", "stated and contradicted_by come together", pointer))
        if has_stated and (
            cell.get("state") != "no" or cell.get("stated") not in ("yes", "partly")
        ):
            found.append(
                _config(
                    "CRIT-14", "an overridden cell is no, stated yes or partly", pointer, "OVR-4"
                )
            )
        entries = [_map(e) for e in _list(cell.get("contradicted_by"))]
        for i, e in enumerate(entries):
            if CONTROL_PROPERTY.get(str(e.get("control"))) != prop:
                found.append(
                    _config(
                        "CRIT-14",
                        f"control {e.get('control')} cannot contradict {prop}",
                        f"{pointer}/contradicted_by/{i}",
                        "the RFC-0016 control map (OVR-2)",
                    )
                )
        pairs = [(str(e.get("control")), str(e.get("run_id"))) for e in entries]
        if pairs != sorted(set(pairs)):
            found.append(
                _config(
                    "CRIT-14",
                    "contradicted_by is not sorted and unique",
                    f"{pointer}/contradicted_by",
                )
            )
    disclosures = [_map(d) for d in _list(row.get("disclosures"))]
    ids = [str(d.get("run_id")) for d in disclosures]
    if ids != sorted(set(ids)):
        found.append(
            _config(
                "CRIT-14", "disclosures are not sorted by run_id and unique", f"{where}/disclosures"
            )
        )
    for i, d in enumerate(disclosures):
        if d.get("state") == "published" and not (d.get("date") and d.get("url")):
            found.append(
                _config(
                    "CRIT-14",
                    "a published disclosure needs its date and url",
                    f"{where}/disclosures/{i}",
                )
            )
    return found


def contradictions(
    root: Path, run_dirs: list[str]
) -> tuple[dict[str, set[tuple[str, str]]], set[str]]:
    """OVR-3 over the runs read: property -> {(control, run id)} of contradicting outcomes of
    mapped controls, and the run ids whose controls.json has `disclosure_pending: true`.
    Raises IProofsError(environment) on a run directory or controls.json it cannot read."""
    out: dict[str, set[tuple[str, str]]] = {p: set() for p in PROPERTIES}
    pending: set[str] = set()
    for run_dir in run_dirs:
        name = run_dir.rstrip("/").rsplit("/", 1)[-1]
        path = root / run_dir / "controls.json"
        if not (root / run_dir).is_dir():
            raise IProofsError(ErrorKind.ENVIRONMENT, f"CRIT-13: no run directory {run_dir}")
        if not path.is_file():
            continue  # not run: never raises or lowers a state
        try:
            doc = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as e:
            raise IProofsError(ErrorKind.ENVIRONMENT, f"CRIT-13: cannot read {path}: {e}") from e
        if not isinstance(doc, Mapping) or doc.get("run_id") != name:
            raise IProofsError(ErrorKind.INTEGRITY, f"CRIT-13: {path} does not name run {name}")
        if doc.get("disclosure_pending") is True:
            pending.add(name)
        for entry in _list(doc.get("controls")):
            control = _map(entry)
            outcomes = [control.get("outcome")]
            outcomes += [_map(t).get("outcome") for t in _list(control.get("trials"))]
            prop = CONTROL_PROPERTY.get(str(control.get("id")))
            if prop and "accepted" in outcomes and "accepted" not in _list(control.get("expected")):
                out[prop].add((str(control.get("id")), name))
    return out, pending


def _read_releases(root: Path, release: str) -> list[dict[str, Any]]:
    """The release.yaml files OVR-5 reads for `release`: it and every earlier freeze."""
    named = root / "releases" / release / "release.yaml"
    cutoff = str(load_yaml(named)["freeze_date"])
    docs = [dict(load_yaml(p)) for p in sorted((root / "releases").glob("*/release.yaml"))]
    return [d for d in docs if d.get("release") == release or str(d.get("freeze_date")) < cutoff]


def crit_13(root: Path, doc: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> list[Finding]:
    """The override recomputed from the stored files (OVR-3 to OVR-5, OVR-8)."""
    release = doc.get("release")
    found = []
    card_rows = [(i, r) for i, r in enumerate(rows) if r.get("source_class") == CARD]
    if release is None:
        for i, row in card_rows:
            if "disclosures" in row:
                found.append(
                    _integrity(
                        "CRIT-13",
                        "disclosures without a release",
                        f"/rows/{i}/disclosures",
                        "no run is read (OVR-5)",
                    )
                )
            for _, pointer, cell in cells(row, f"/rows/{i}"):
                if "stated" in cell or "contradicted_by" in cell:
                    found.append(
                        _integrity(
                            "CRIT-13",
                            "an override without a release",
                            pointer,
                            "no run is read, so no cell is overridden (OVR-5)",
                        )
                    )
        return found
    if not (root / "releases" / str(release) / "release.yaml").is_file():
        return [_integrity("CRIT-13", f"no releases/{release}/release.yaml", "/release")]
    try:
        read_releases = _read_releases(root, str(release))
    except (IProofsError, KeyError, OSError, ValueError) as e:
        return [_f("CRIT-13", f"cannot read the releases: {e}", ErrorKind.ENVIRONMENT, "/release")]
    for i, row in card_rows:
        found += _override(root, str(release), read_releases, row, f"/rows/{i}")
    return found


def _override(
    root: Path,
    release: str,
    read_releases: list[dict[str, Any]],
    row: Mapping[str, Any],
    where: str,
) -> list[Finding]:
    card = _map(row.get("card"))
    system, configuration = str(card.get("system")), str(card.get("configuration"))
    try:
        run_dirs = runs_read(root, release, system, configuration)
        found_by, pending_runs = contradictions(root, run_dirs)
    except IProofsError as e:
        return [_f("CRIT-13", e.message, e.kind, where)]
    listed = any(
        _map(c).get("system") == system and _map(c).get("configuration") == configuration
        for d in read_releases
        for c in _list(d.get("claim_cards"))
    )
    if not listed or not run_dirs:
        return [
            _integrity(
                "CRIT-13",
                f"{system}/{configuration} is not benchmarked in {release}: "
                f"{'no run is read' if listed else 'no claim_cards entry'}",
                f"{where}/card",
                "remove the row, or add the run (OVR-5)",
            )
        ]
    found = []
    entries = [_map(d) for d in _list(row.get("disclosures"))]
    named = {str(d.get("run_id")) for d in entries}
    if named != pending_runs:
        missing, extra = sorted(pending_runs - named), sorted(named - pending_runs)
        found.append(
            _integrity(
                "CRIT-13",
                "disclosures do not list the read runs with "
                f"disclosure_pending: missing {missing}, extra {extra}",
                f"{where}/disclosures",
                "one entry per such run (OVR-8)",
            )
        )
    withheld = any(d.get("state") == "pending" for d in entries)
    for prop, pointer, cell in cells(row, where):
        want = sorted(found_by[prop])
        stated = stated_of(cell)
        has = "stated" in cell or "contradicted_by" in cell
        if withheld:
            if has:
                found.append(
                    _integrity(
                        "CRIT-13",
                        "an override while a disclosure is pending",
                        pointer,
                        "draw no override until it is published (OVR-8)",
                    )
                )
            continue
        if stated in ("yes", "partly") and want:
            got = [
                (str(_map(e).get("control")), str(_map(e).get("run_id")))
                for e in _list(cell.get("contradicted_by"))
            ]
            if cell.get("state") != "no" or cell.get("stated") != stated or got != want:
                found.append(
                    _integrity(
                        "CRIT-13",
                        f"{', '.join(f'{c} in {r}' for c, r in want)} "
                        f"contradicts {prop}: the cell must be no, stated "
                        f"{stated}, contradicted_by those",
                        pointer,
                        "OVR-4",
                    )
                )
        elif has:
            why = "no read run contradicts it" if not want else f"its stated state is {stated}"
            found.append(
                _integrity(
                    "CRIT-13",
                    f"an override where {why}",
                    pointer,
                    "drop stated and contradicted_by (OVR-3, OVR-4)",
                )
            )
    return found
