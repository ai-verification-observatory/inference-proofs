import dataclasses
import json
import re
import types
from collections.abc import Mapping
from pathlib import Path

import pytest

from iproofs.errors import IProofsError
from iproofs.model import Quantity, Statistic, _convert, load
from iproofs.quantity import Grade, Scope, SourceKind, Unit
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "schema/quantity/examples/valid"


def test_from_tree_tuples_and_mappingproxy() -> None:
    tree = json.loads((EXAMPLES / "statistic.three-repetitions.json").read_text())
    stat = Statistic.from_tree(tree)
    assert stat.unit is Unit.S
    assert stat.scope is Scope.PROVE_SESSION
    assert stat.grade is Grade.DERIVED
    assert stat.source.kind is SourceKind.DERIVATION
    assert isinstance(stat.source.inputs, tuple)
    assert stat.stats.n == 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        stat.value = 1.0  # type: ignore[misc]


def test_open_map_becomes_mappingproxy() -> None:
    converted = _convert(Mapping[str, int], {"witness": 3})
    assert isinstance(converted, types.MappingProxyType)
    assert dict(converted) == {"witness": 3}


def test_optional_fields_default_to_none() -> None:
    tree = json.loads((EXAMPLES / "quantity.measured-time.json").read_text())
    q = Quantity.from_tree(tree)
    assert q.quality is None
    assert q.upstream_scope is None


def test_load_without_document_model_is_internal_error(tmp_path: Path) -> None:
    root = tmp_path / "schema"
    (root / "toy").mkdir(parents=True)
    (root / "toy/1.schema.json").write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://inference-proofs.org/schema/toy/1.schema.json",
        "type": "object", "properties": {"schema": {"const": "toy/1"}},
    }))  # fmt: skip
    doc = tmp_path / "d.json"
    doc.write_text('{"schema": "toy/1"}')
    with pytest.raises(IProofsError, match='no model registered for schema "toy/1"'):
        load(doc, SchemaRegistry.from_tree(root))


def test_from_tree_called_only_from_load() -> None:
    """No production path constructs a model from an unvalidated tree."""
    calls = []
    for path in (ROOT / "harness/src/iproofs").glob("*.py"):
        for line in path.read_text().splitlines():
            if re.search(r"\.from_tree\(", line) and "SchemaRegistry.from_tree" not in line:
                calls.append(f"{path.name}: {line.strip()}")
    assert calls == ["model.py: return model_for(schema_id).from_tree(tree)"]
