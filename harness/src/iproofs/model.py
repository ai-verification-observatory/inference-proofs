"""Frozen dataclasses for every document: parse, validate, construct (RFC-0012 §Python loading).

Construction is generic: field types drive the conversion. Nested objects become nested
dataclasses, arrays become tuples, open maps become read-only mappings, enums become their
StrEnum. `from_tree` runs only on trees that `load` has validated.
"""

import dataclasses
import types
import typing
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Self, Union, get_args, get_origin, get_type_hints

from iproofs.errors import ErrorKind, IProofsError
from iproofs.quantity import Grade, NullReason, Scope, ScopeMapping, SourceKind, Tier, Unit
from iproofs.schema import SchemaRegistry, load_document


def _convert(tp: Any, value: object) -> object:  # noqa: PLR0911 (one return per type kind)
    if value is None:
        return None
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        options = [a for a in get_args(tp) if a is not type(None)]
        if len(options) != 1:
            raise TypeError(f"ambiguous union {tp}")
        return _convert(options[0], value)
    if origin is tuple:
        item = get_args(tp)[0]
        assert isinstance(value, list)
        return tuple(_convert(item, v) for v in value)
    if origin in (Mapping, typing.Mapping):
        item = get_args(tp)[1]
        assert isinstance(value, dict)
        return types.MappingProxyType({k: _convert(item, v) for k, v in value.items()})
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        assert isinstance(value, dict)
        return _build(tp, value)
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        assert isinstance(value, str)
        return tp(value)
    return value


def _build(cls: type[Any], tree: Mapping[str, object]) -> Any:
    hints = get_type_hints(cls)
    kwargs = {f.name: _convert(hints[f.name], tree[f.name])
              for f in dataclasses.fields(cls) if f.name in tree}  # fmt: skip
    return cls(**kwargs)


class Document:
    """Base for every model built from a validated tree."""

    __slots__ = ()

    @classmethod
    def from_tree(cls, tree: Mapping[str, object]) -> Self:
        built: Self = _build(cls, tree)
        return built


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Quality(Document):
    degraded: bool | None = None
    precision_substituted: bool | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Source(Document):
    kind: SourceKind
    ref: str
    inputs: tuple[str, ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Quantity(Document):
    value: float | None
    unit: Unit
    scope: Scope | None
    grade: Grade
    tier: Tier
    source: Source
    null_reason: NullReason | None
    upstream_scope: str | None = None
    upstream_grade: str | None = None
    mapping: ScopeMapping | None = None
    quality: Quality | None = None
    note: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Stats(Document):
    n: int
    n_failed: int
    mean: float | None
    stdev: float | None
    min: float | None
    max: float | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Statistic(Quantity):
    stats: Stats


# Schema location -> model class. The drift test walks this table and requires every
# document schema in the tree to appear here.
MODELS: dict[tuple[str, str], type[Document]] = {
    ("quantity/1", "#/$defs/quantityCore"): Quantity,
    ("quantity/1", "#/$defs/statistic"): Statistic,
    ("quantity/1", "#/$defs/source"): Source,
    ("quantity/1", "#/$defs/stats"): Stats,
    ("quantity/1", "#/$defs/quantityCore/properties/quality"): Quality,
}


def model_for(schema_id: str) -> type[Document]:
    for (sid, pointer), cls in MODELS.items():
        if sid == schema_id and pointer == "#":
            return cls
    raise IProofsError(ErrorKind.INTERNAL, f'no model registered for schema "{schema_id}"')


def load(path: Path, registry: SchemaRegistry) -> Document:
    """Parse, validate against the document's own schema, then construct its model."""
    schema_id, tree = load_document(path, registry)
    return model_for(schema_id).from_tree(tree)
