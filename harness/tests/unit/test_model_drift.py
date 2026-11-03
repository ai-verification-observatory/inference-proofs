"""RFC-0012 drift test: schema properties and dataclass fields must agree."""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from iproofs.model import MODELS, Document

ROOT = Path(__file__).resolve().parents[3]


def load_schemas(root: Path) -> dict[str, dict[str, Any]]:
    return {
        f"{p.parent.name}/{p.name.removesuffix('.schema.json')}": json.loads(p.read_text())
        for p in root.glob("*/*.schema.json")
    }


def resolve(schemas: dict[str, dict[str, Any]], sid: str, pointer: str) -> dict[str, Any]:
    node: Any = schemas[sid]
    for part in pointer.removeprefix("#").strip("/").split("/"):
        if part:
            node = node[part.replace("~1", "/").replace("~0", "~")]
    return dict(node)


def properties(
    schemas: dict[str, dict[str, Any]], sid: str, node: dict[str, Any]
) -> tuple[set[str], set[str]]:
    """Property names and required names of an object schema, following local $refs."""
    props, required = set(node.get("properties", {})), set(node.get("required", []))
    refs = [node["$ref"]] if "$ref" in node else []
    refs += [part["$ref"] for part in node.get("allOf", []) if "$ref" in part]
    for ref in refs:
        target = resolve(schemas, sid, ref)
        p, r = properties(schemas, sid, target)
        props |= p
        required |= r
    return props, required


def drift(
    schemas: dict[str, dict[str, Any]], table: dict[tuple[str, str], type[Document]]
) -> list[str]:
    problems = []
    for (sid, pointer), cls in table.items():
        props, required = properties(schemas, sid, resolve(schemas, sid, pointer))
        fields = {f.name: f for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        if props != set(fields):
            problems.append(f"{sid}{pointer} vs {cls.__name__}: {sorted(props ^ set(fields))}")
        for name in required & set(fields):
            f = fields[name]
            if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING:
                problems.append(f"{cls.__name__}.{name} is required but has a default")
    documents = {sid for sid, s in schemas.items() if "properties" in s}
    modelled = {sid for (sid, pointer) in table if pointer == "#"}
    problems += [f"document schema {sid} has no model" for sid in sorted(documents - modelled)]
    return problems


def test_models_match_schemas() -> None:
    assert drift(load_schemas(ROOT / "schema"), MODELS) == []


def test_extra_schema_property_is_detected(tmp_path: Path) -> None:
    schemas = load_schemas(ROOT / "schema")
    schemas["quantity/1"]["$defs"]["source"]["properties"]["extra"] = {"type": "string"}
    problems = drift(schemas, MODELS)
    assert problems == ["quantity/1#/$defs/source vs Source: ['extra']"]


def test_unmodelled_document_schema_is_detected() -> None:
    schemas = load_schemas(ROOT / "schema")
    schemas["toy/1"] = {"type": "object", "properties": {"schema": {"const": "toy/1"}}}
    assert drift(schemas, MODELS) == ["document schema toy/1 has no model"]


MODEL_CLASSES: list[type[Document]] = sorted(set(MODELS.values()), key=lambda c: c.__name__)


@pytest.mark.parametrize("cls", MODEL_CLASSES)
def test_models_are_frozen_and_slotted(cls: type[Document]) -> None:
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen
    assert "__slots__" in cls.__dict__
