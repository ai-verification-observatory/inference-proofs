"""Typed readers of every file the site reads (RFC-0009 §Site, #320).

No git call and no clock: the same files give the same view in a full clone, a depth-1 clone
or a tree with no `.git` (CLI-4). Each file is read once per build.
"""

import json
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
SCHEMA = "criteria/1"  # RFC-0016 §Criteria file contract
STATES = ("yes", "partly", "no", "not_stated")
FAMILIES = ("proved", "attested", "re_executed", "fingerprinted", "unchecked")
SOURCE_CLASSES = ("claim_card_at_pin", "reference_rfc_0015", "public_sources")
ROW_KEYS = {"id", "name", "family", "source_class", "tab", "cells", "card", "workloads",
            "own_sources"}  # fmt: skip
CELL_KEYS = {"state", "stated", "reason", "quotes", "sources_read", "not_copied", "note",
             "conflict", "aside", "outside_pin", "contradicted_by"}  # fmt: skip


def _config(message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"site: {message}")


def _state(value: object, where: str) -> str | None:
    if value is None:
        return None
    if value not in STATES:
        raise _config(f"{where}: unknown state {value!r}")
    return str(value)


# ---------------------------------------------------------------- criteria (RFC-0016)


@dataclass(frozen=True)
class Criteria:
    """The criteria file (`criteria/1`): state ids and words, sources read, the release it names."""

    path: str
    sha256: str
    release: str | None
    order: tuple[str, ...]
    states: dict[str, dict[str, str]]  # state id -> {word, meaning}
    properties: tuple[dict[str, Any], ...]
    rows: dict[str, dict[str, Any]]
    pins: dict[str, str]  # repository -> the commit its quotes and sources read are at
    cards: dict[tuple[str, str], str]  # (system, configuration) of a card row -> its row id


def load_criteria(root: Path) -> Criteria:
    """Read `web/_data/criteria.json` (`criteria/1`; G2 validates it against the schema). An
    unknown schema, row or cell key, state, family or source class raises. Each cell keeps the
    state the file sets. Card rows are also keyed by their card's system and configuration
    (SRC-1: one row per card)."""
    path = root / CRITERIA
    doc = json.loads(path.read_text("utf-8"))
    if doc.get("schema") != SCHEMA:
        raise _config(f"{CRITERIA}: schema {doc.get('schema')!r}, the site reads {SCHEMA!r}")
    order = tuple(str(p) for p in doc["order"])
    properties = tuple(dict(p) for p in doc["properties"])
    if [p["id"] for p in properties] != list(order):
        raise _config(f"{CRITERIA}: properties are not in `order`")
    states = {str(k): dict(v) for k, v in doc["states"].items()}
    if set(states) != set(STATES):
        raise _config(f"{CRITERIA}: states {sorted(states)} are not {list(STATES)}")
    rows: dict[str, dict[str, Any]] = {}
    cards: dict[tuple[str, str], str] = {}
    for raw in doc["rows"]:
        rid = str(raw["id"])
        if unknown := set(raw) - ROW_KEYS:
            raise _config(f"{CRITERIA} row {rid}: unknown keys {sorted(unknown)}")
        if raw["family"] not in FAMILIES:
            raise _config(f"{CRITERIA} row {rid}: unknown family {raw['family']!r}")
        if raw["source_class"] not in SOURCE_CLASSES:
            raise _config(f"{CRITERIA} row {rid}: unknown source class {raw['source_class']!r}")
        cells: dict[str, dict[str, Any]] = {}
        for prop in order:
            cell = raw["cells"][prop]
            if unknown := set(cell) - CELL_KEYS:
                raise _config(f"{CRITERIA} {rid}/{prop}: unknown keys {sorted(unknown)}")
            cells[prop] = {
                "state": _state(cell["state"], f"{rid}/{prop}"),
                "stated": _state(cell.get("stated"), f"{rid}/{prop} stated"),
                "reason": cell.get("reason"),
                "quotes": list(cell.get("quotes") or []),
                "sources_read": list(cell.get("sources_read") or []),
                "not_copied": bool(cell.get("not_copied")),
                "aside": cell.get("aside"),
                "note": cell.get("note"),
                "outside_pin": cell.get("outside_pin"),
                "conflict": bool(cell.get("conflict")),
                "contradicted_by": list(cell.get("contradicted_by") or []),
            }
        card = dict(raw["card"]) if "card" in raw else None
        if card is not None:
            cards[(str(card["system"]), str(card["configuration"]))] = rid
        rows[rid] = {
            "id": rid,
            "name": raw["name"],
            "family": raw["family"],
            "source_class": raw["source_class"],
            "tab": raw["tab"],
            "card": card,
            "cells": cells,
            # where a public-source row's system presents itself (its repository, its paper)
            "own_sources": [dict(s) for s in raw.get("own_sources") or []],
        }
    pins = {str(k): str(v) for k, v in (doc.get("pins") or {}).items()}
    return Criteria(CRITERIA, file_digest(path), doc.get("release"), order, states, properties,
                    rows, pins, cards)  # fmt: skip


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
    """The newest frozen release (the highest vX.Y with an index.json); a tree with none is a
    config error."""
    found = []
    for path in sorted(root.glob("releases/*/index.json")):
        name = path.parent.name
        found.append((tuple(int(x) for x in name.removeprefix("v").split(".")), name))
    if not found:
        raise IProofsError(
            ErrorKind.CONFIG,
            "site: no frozen release (releases/*/index.json); freeze one with "
            "`iproofs release freeze`",
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
    """run id -> {dir, run, manifest, controls} for every listed run directory, each file read
    once."""
    out = {}
    for rel in run_dirs:
        run = read_json(root / rel / "run.json")
        controls = root / rel / "controls.json"
        out[str(run["run_id"])] = {
            "dir": rel,
            "run": run,
            "manifest": read_json(root / rel / "manifest.json"),
            "controls": read_json(controls) if controls.is_file() else None,
        }
    return out


def maybe(mapping: Mapping[str, Any], *keys: str) -> Any:
    node: Any = mapping
    for key in keys:
        node = node.get(key) if isinstance(node, Mapping) else None
    return node
