"""Schema registry and Draft 2020-12 validation (RFC-0012 §Schema catalogue, §Python loading).

Schemas resolve only from the local `schema/` tree; nothing is fetched over the network.
"""

import datetime
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

import referencing
import referencing.exceptions
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.protocols import Validator
from referencing.jsonschema import DRAFT202012

from iproofs.errors import ErrorKind, IProofsError
from iproofs.serialize import load_yaml

ID_PREFIX = "https://inference-proofs.org/schema/"
SCHEMA_FIELD_RE = re.compile(r"^[a-z][a-z-]*/[1-9][0-9]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")

# Formats asserted (RFC-0012): date, date-time, uri. Implemented here so that no
# optional package decides silently whether a format is checked.
FORMATS = FormatChecker(formats=())


@FORMATS.checks("date")
def _is_date(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not _DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


@FORMATS.checks("date-time")
def _is_date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not _DATE_TIME_RE.fullmatch(value):
        return False
    try:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


@FORMATS.checks("uri")
def _is_uri(value: object) -> bool:
    if not isinstance(value, str):
        return True
    parts = urllib.parse.urlsplit(value)
    return bool(parts.scheme) and bool(parts.netloc or parts.path) and " " not in value


def schema_id_url(schema_id: str) -> str:
    """`run/1` -> the `$id` of schema/run/1.schema.json."""
    return f"{ID_PREFIX}{schema_id}.schema.json"


def _no_retrieve(uri: str) -> referencing.Resource[Any]:
    raise referencing.exceptions.NoSuchResource(uri)


class SchemaRegistry:
    def __init__(self, schemas: dict[str, dict[str, Any]]) -> None:
        self._schemas = schemas
        resources = [
            (schema_id_url(sid), referencing.Resource.from_contents(s, DRAFT202012))
            for sid, s in schemas.items()
        ]
        self._registry: referencing.Registry[Any] = referencing.Registry(
            retrieve=_no_retrieve  # type: ignore[call-arg]
        ).with_resources(resources)

    @classmethod
    def from_tree(cls, root: Path) -> "SchemaRegistry":
        """Load every `schema/<name>/<major>.schema.json` under `root`."""
        schemas: dict[str, dict[str, Any]] = {}
        for path in sorted(root.glob("*/*.schema.json")):
            sid = f"{path.parent.name}/{path.name.removesuffix('.schema.json')}"
            if not SCHEMA_FIELD_RE.fullmatch(sid):
                raise IProofsError(ErrorKind.INTERNAL, f"{path}: bad schema file name")
            contents = json.loads(path.read_text("utf-8"))
            if contents.get("$id") != schema_id_url(sid):
                raise IProofsError(
                    ErrorKind.INTERNAL, f"{path}: $id must be {schema_id_url(sid)!r}"
                )
            Draft202012Validator.check_schema(contents)
            schemas[sid] = contents
        return cls(schemas)

    def ids(self) -> list[str]:
        return sorted(self._schemas)

    def validator(self, schema_id: str) -> Validator:
        """Validator for a `schema` field value such as `run/1`."""
        if schema_id not in self._schemas:
            raise IProofsError(ErrorKind.CONFIG, f'unknown schema "{schema_id}"')
        return Draft202012Validator(
            self._schemas[schema_id], registry=self._registry, format_checker=FORMATS
        )

    def is_defs_only(self, schema_id: str) -> bool:
        """A shared-definitions schema such as quantity/1 describes no document."""
        return "properties" not in self._schemas[schema_id]

    def errors(
        self, schema_id: str, tree: dict[str, object], *, def_name: str | None = None
    ) -> list[str]:
        """Every validation error as `<pointer>: <message>`, sorted by JSON Pointer.

        With `def_name`, validate against `$defs/<def_name>` of the schema instead.
        """
        validator = self.validator(schema_id)
        if def_name is not None:
            validator = validator.evolve(
                schema={"$ref": f"{schema_id_url(schema_id)}#/$defs/{def_name}"}
            )
        found = []
        for err in validator.iter_errors(tree):  # type: ignore[arg-type]
            pointer = "".join(
                "/" + str(p).replace("~", "~0").replace("/", "~1") for p in err.absolute_path
            )
            found.append((pointer or "/", err.message))
        return [f"{p}: {m}" for p, m in sorted(found)]


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite number {name}")


def parse_tree(path: Path) -> dict[str, object]:
    if path.suffix in {".yaml", ".yml"}:
        return load_yaml(path)
    if path.suffix != ".json":
        raise IProofsError(ErrorKind.CONFIG, f"{path}: unsupported file type")
    try:
        tree = json.loads(path.read_bytes(), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as e:
        raise IProofsError(ErrorKind.CONFIG, f"{path}: invalid JSON: {e}") from e
    if not isinstance(tree, dict):
        raise IProofsError(ErrorKind.CONFIG, f"{path}: top level must be an object")
    return tree


def load_document(path: Path, registry: SchemaRegistry) -> tuple[str, dict[str, object]]:
    """Parse YAML or JSON by extension, read `schema`, validate, return (schema_id, tree).

    Raises IProofsError(kind=config) with every validation error, sorted by JSON Pointer.
    """
    tree = parse_tree(path)
    value = tree.get("schema")
    if (
        not isinstance(value, str)
        or not SCHEMA_FIELD_RE.fullmatch(value)
        or value not in registry.ids()
    ):
        raise IProofsError(ErrorKind.CONFIG, f'{path}: missing or unknown schema "{value}"')
    errors = registry.errors(value, tree)
    if errors:
        raise IProofsError(ErrorKind.CONFIG, "\n".join(f"{path}: {e}" for e in errors))
    return value, tree


def check_examples(root: Path, registry: SchemaRegistry) -> list[str]:
    """G2 example rule: valid examples validate; invalid ones fail with their `.reason` text."""
    problems: list[str] = []
    for example in sorted(root.glob("*/examples/*/*")):
        if example.suffix not in {".json", ".yaml", ".yml"}:
            continue
        kind = example.parent.name
        try:
            schema_id = f"{example.parents[2].name}/1"
            if schema_id in registry.ids() and registry.is_defs_only(schema_id):
                # `<def>.<name>.json` exercises `$defs/<def>` of a definitions-only schema
                tree = parse_tree(example)
                error = "\n".join(
                    registry.errors(schema_id, tree, def_name=example.name.split(".", 1)[0])
                )
            else:
                load_document(example, registry)
                error = ""
        except IProofsError as e:
            error = e.message
        if kind == "valid" and error:
            problems.append(f"{example}: valid example fails:\n{error}")
        elif kind == "invalid":
            reason_file = example.with_name(example.name + ".reason")
            if not reason_file.exists():
                problems.append(f"{example}: invalid example has no .reason file")
            elif not error:
                problems.append(f"{example}: invalid example validates")
            elif (reason := reason_file.read_text("utf-8").strip()) not in error:
                problems.append(f"{example}: error does not mention {reason!r}:\n{error}")
    return problems
