"""Typed readers of every file the site reads (RFC-0009 §Site, #320).

No git call and no clock: the same files give the same view in a full clone, a depth-1 clone
or a tree with no `.git` (CLI-4). Each file is read once per build.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import SiteFacts, load
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry
from iproofs.serialize import load_yaml

REPOSITORY = "https://github.com/ai-verification-observatory/inference-proofs"
CRITERIA = "web/_data/criteria.json"
FACTS = "web/_data/facts.json"
# RFC-0016 §States: the prototype criteria file's colour ids and the state ids they stand for.
STATE_OF = {"green": "yes", "amber": "partly", "red": "no", "grey": "not_stated"}
STATES = ("yes", "partly", "no", "not_stated")
FAMILIES = ("proved", "attested", "re_executed", "fingerprinted", "unchecked")
SOURCE_CLASSES = ("claim_card_at_pin", "reference_rfc_0015", "public_sources")
ROW_KEYS = {"id", "name", "family", "source_class", "tab", "pencil", "states", "cells", "card",
            "disclosures"}  # fmt: skip
CELL_KEYS = {"state", "reason", "quotes", "searched", "aside", "note", "outside_pin",
             "conflict", "stated", "contradicted_by"}  # fmt: skip
STATUS_LINE = re.compile(r"^- Status: (.+)$", re.M)


def _config(message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"site: {message}")


def _state(value: object, where: str) -> str | None:
    if value is None:
        return None
    state = STATE_OF.get(str(value), str(value))
    if state not in STATES:
        raise _config(f"{where}: unknown state {value!r}")
    return state


# ---------------------------------------------------------------- criteria (RFC-0016)


def _outside(statement: object, where: str) -> dict[str, Any] | None:
    """SRC-3: a system's own statement outside the pin, its state in RFC-0016 ids; never
    part of the cell's state."""
    if not isinstance(statement, Mapping):
        return None
    return {**statement, "state": _state(statement.get("state"), where)}


@dataclass(frozen=True)
class Criteria:
    """The criteria file in RFC-0016 vocabulary: state ids, sources read, the release it names."""

    path: str
    sha256: str
    release: str | None
    order: tuple[str, ...]
    properties: tuple[dict[str, Any], ...]
    rows: dict[str, dict[str, Any]]
    pins: dict[str, str]  # repository -> the commit the sources read were read at


def load_criteria(root: Path) -> Criteria:
    """Read `web/_data/criteria.json`. Prototype colour ids map to RFC-0016 state ids; the
    derived copies the prototype still holds (`test_mapping`, `rows[].states`) must equal the
    cells; an unknown row or cell key, state, family or source class raises. A card row with a
    `pending` disclosure gets `state: None` on every cell (OVR-8: drawn as no state)."""
    path = root / CRITERIA
    doc = json.loads(path.read_text("utf-8"))
    order = tuple(str(p) for p in doc["order"])
    # each property's rule per state, keyed by RFC-0016 state id (the prototype keys colours)
    properties = tuple(
        {**p, "rules": {state: p[colour] for colour, state in STATE_OF.items() if colour in p}}
        for p in doc["properties"]
    )
    if [p["id"] for p in properties] != list(order):
        raise _config(f"{CRITERIA}: properties are not in `order`")
    mapping = doc.get("test_mapping") or {}
    rows: dict[str, dict[str, Any]] = {}
    for raw in doc["rows"]:
        rid = str(raw["id"])
        if unknown := set(raw) - ROW_KEYS:
            raise _config(f"{CRITERIA} row {rid}: unknown keys {sorted(unknown)}")
        if raw["family"] not in FAMILIES:
            raise _config(f"{CRITERIA} row {rid}: unknown family {raw['family']!r}")
        if raw["source_class"] not in SOURCE_CLASSES:
            raise _config(f"{CRITERIA} row {rid}: unknown source class {raw['source_class']!r}")
        pending = any(d.get("state") == "pending" for d in raw.get("disclosures") or [])
        cells = {}
        for prop in order:
            cell = raw["cells"][prop]
            if unknown := set(cell) - CELL_KEYS:
                raise _config(f"{CRITERIA} {rid}/{prop}: unknown keys {sorted(unknown)}")
            state = _state(cell["state"], f"{rid}/{prop}")
            cells[prop] = {
                "state": None if pending else state,
                "stated": _state(cell.get("stated"), f"{rid}/{prop} stated"),
                "reason": cell.get("reason"),
                "quotes": list(cell.get("quotes") or []),
                "sources_read": list(cell.get("searched") or []),
                "aside": cell.get("aside"),
                "note": cell.get("note"),
                "outside_pin": _outside(cell.get("outside_pin"), f"{rid}/{prop} outside_pin"),
                "conflict": bool(cell.get("conflict")),
                "contradicted_by": list(cell.get("contradicted_by") or []),
            }
        stored = [_state(s, f"{rid} states") for s in raw.get("states") or []]
        derived = [_state(s, f"{rid} test_mapping") for s in mapping.get(rid) or []]
        actual = [_state(raw["cells"][p]["state"], rid) for p in order]
        for name, copy in (("states", stored), ("test_mapping", derived)):
            if copy and copy != actual:
                raise _config(f"{CRITERIA} row {rid}: {name} {copy} disagrees with its cells")
        rows[rid] = {
            "id": rid,
            "name": raw["name"],
            "family": raw["family"],
            "source_class": raw["source_class"],
            "tab": raw["tab"],
            "pending": pending,
            "disclosures": list(raw.get("disclosures") or []),
            "cells": cells,
        }
    pins = {str(k): str(v) for k, v in (doc.get("pins") or {}).items()}
    return Criteria(CRITERIA, file_digest(path), doc.get("release"), order, properties, rows, pins)


def rfc_status(root: Path, number: str) -> dict[str, str]:
    """RFC-0016 contract: the site reads the RFC's own status line."""
    found = sorted((root / "rfcs").glob(f"{number}-*.md"))
    if not found:
        raise _config(f"no rfcs/{number}-*.md")
    match = STATUS_LINE.search(found[0].read_text("utf-8"))
    if match is None:
        raise _config(f"{found[0].name}: no status line")
    return {"file": found[0].name, "status": match[1].strip()}


# ---------------------------------------------------------------- facts (site-facts/1)


def load_facts(root: Path, registry: SchemaRegistry) -> SiteFacts:
    facts = load(root / FACTS, registry)
    assert isinstance(facts, SiteFacts)
    return facts


def check_facts(facts: SiteFacts, criteria: Criteria, rows: list[str], digests: list[str]) -> None:
    """Every printed row has a name, every model a table needs has a name, and an archived
    row is archived in both files (#320 plan §3)."""
    for rid in rows:
        if rid not in facts.rows:
            raise _config(f"{FACTS}: no row {rid!r}")
    for digest in digests:
        if digest not in facts.models:
            raise _config(f"{FACTS}: no model {digest}")
    for rid, row in criteria.rows.items():
        state = facts.rows[rid].status if rid in facts.rows else None
        archived = state is not None and state.state == "archived"
        if (row["tab"] == "archived") != archived:
            raise _config(f"{rid}: criteria tab {row['tab']!r} disagrees with facts status")


# ---------------------------------------------------------------- release tree


def newest_release(root: Path) -> str:
    """The newest frozen release (freeze_date, then id); a tree with none is a config error."""
    found = []
    for path in sorted(root.glob("releases/*/index.json")):
        doc = load_yaml(path.with_name("release.yaml"))
        found.append((str(doc["freeze_date"]), path.parent.name))
    if not found:
        raise IProofsError(
            ErrorKind.CONFIG,
            "site: no frozen release (releases/*/index.json); until v0.1 build the placeholder: "
            "PYTHONPATH=harness/tests uv run python -m fixtures.placeholder_release --site web",
        )
    return max(found)[1]


def read_json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise IProofsError(ErrorKind.ENVIRONMENT, f"site: cannot read {path}: {e}") from e
    assert isinstance(doc, dict)
    return doc


def read_yaml(path: Path) -> dict[str, Any]:
    return dict(load_yaml(path))


def systems(root: Path) -> dict[str, dict[str, Any]]:
    return {p.parent.name: read_yaml(p) for p in sorted(root.glob("systems/*/system.yaml"))}


def run_records(root: Path, run_dirs: list[str]) -> dict[str, dict[str, Any]]:
    """run id -> {run, controls} for every listed run directory, each file read once."""
    out = {}
    for rel in run_dirs:
        run = read_json(root / rel / "run.json")
        controls = root / rel / "controls.json"
        out[str(run["run_id"])] = {
            "dir": rel,
            "run": run,
            "controls": read_json(controls) if controls.is_file() else None,
        }
    return out


def maintainer_rows(path: Path) -> list[dict[str, str]]:
    """The MAINTAINERS.md tables (RFC-0001 §Roles) as rows; the site may not import the
    validator (docs/spec/01 layers), so it reads the six columns itself."""
    columns = ("handle", "role", "organisation", "systems", "interests", "since")
    rows, inside = [], False
    for line in path.read_text("utf-8").splitlines() if path.is_file() else []:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells[0] == "Handle":
            inside = True
        elif inside and line.lstrip().startswith("|") and not set(cells[0]) <= {"-"}:
            rows.append(dict(zip(columns, cells + [""] * 6, strict=False)))
        elif not line.lstrip().startswith("|"):
            inside = False
    return rows


def maybe(mapping: Mapping[str, Any], *keys: str) -> Any:
    node: Any = mapping
    for key in keys:
        node = node.get(key) if isinstance(node, Mapping) else None
    return node
