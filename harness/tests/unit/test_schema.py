import json
import socket
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.schema import FORMATS, SchemaRegistry, check_examples, load_document, schema_id_url

SHARED = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": schema_id_url("shared/1"),
    "$defs": {"count": {"type": "integer", "minimum": 0}},
}


def doc_schema(name: str) -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id_url(f"{name}/1"),
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "n"],
        "properties": {
            "schema": {"const": f"{name}/1"},
            "n": {"$ref": "../shared/1.schema.json#/$defs/count"},
            "date": {"type": "string", "format": "date"},
        },
    }


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "schema"
    for sid, contents in {"shared/1": SHARED, "run/1": doc_schema("run"),
                          "manifest/1": doc_schema("manifest")}.items():  # fmt: skip
        p = root / f"{sid}.schema.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(contents))
    return root


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def config_message(path: Path, registry: SchemaRegistry) -> str:
    with pytest.raises(IProofsError) as e:
        load_document(path, registry)
    assert e.value.kind is ErrorKind.CONFIG
    return e.value.message


def test_load_valid_yaml_and_json(tree: Path, tmp_path: Path) -> None:
    reg = SchemaRegistry.from_tree(tree)
    y = write(tmp_path, "a.yaml", 'schema: "run/1"\nn: 2\n')
    j = write(tmp_path, "b.json", '{"schema": "manifest/1", "n": 0}')
    assert load_document(y, reg) == ("run/1", {"schema": "run/1", "n": 2})
    assert load_document(j, reg)[0] == "manifest/1"


def test_schema_field_missing(tree: Path, tmp_path: Path) -> None:
    msg = config_message(write(tmp_path, "a.yaml", "n: 2\n"), SchemaRegistry.from_tree(tree))
    assert msg.endswith('missing or unknown schema "None"')


def test_schema_field_unknown(tree: Path, tmp_path: Path) -> None:
    p = write(tmp_path, "a.yaml", 'schema: "run/9"\nn: 2\n')
    assert msg_end(config_message(p, SchemaRegistry.from_tree(tree))) == (
        'missing or unknown schema "run/9"'
    )


def msg_end(msg: str) -> str:
    return msg.split(": ", 1)[1]


def test_schema_const_mismatch(tree: Path) -> None:
    reg = SchemaRegistry.from_tree(tree)
    errors = reg.errors("manifest/1", {"schema": "run/1", "n": 1})
    assert errors == ["/schema: 'manifest/1' was expected"]


def test_errors_sorted_by_pointer(tree: Path, tmp_path: Path) -> None:
    p = write(tmp_path, "a.yaml", 'schema: "run/1"\nn: -1\nextra: 1\ndate: "2026-02-30"\n')
    lines = config_message(p, SchemaRegistry.from_tree(tree)).splitlines()
    pointers = [line.split(": ")[1] for line in lines]
    assert pointers == sorted(pointers)
    assert pointers == ["/", "/date", "/n"]


def test_json_nan_rejected(tree: Path, tmp_path: Path) -> None:
    p = write(tmp_path, "a.json", '{"schema": "run/1", "n": NaN}')
    assert "non-finite" in config_message(p, SchemaRegistry.from_tree(tree))


def test_no_network_resolution(tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    reg = SchemaRegistry.from_tree(tree)
    p = write(tmp_path, "a.yaml", 'schema: "run/1"\nn: 3\n')
    assert load_document(p, reg)[0] == "run/1"


def test_unknown_ref_fails_without_fetching(tmp_path: Path) -> None:
    root = tmp_path / "schema"
    bad = doc_schema("run")
    bad["properties"]["n"] = {"$ref": "https://example.org/remote.json"}  # type: ignore[index]
    write(root, "run/1.schema.json", json.dumps(bad))
    reg = SchemaRegistry.from_tree(root)
    with pytest.raises(Exception, match=r"example\.org"):
        reg.errors("run/1", {"schema": "run/1", "n": 1})


def test_id_must_match_path(tmp_path: Path) -> None:
    root = tmp_path / "schema"
    write(root, "run/1.schema.json", json.dumps({**doc_schema("run"), "$id": "x"}))
    with pytest.raises(IProofsError, match=r"\$id must be"):
        SchemaRegistry.from_tree(root)


def test_examples_runner_reason_match(tree: Path) -> None:
    ex = tree / "run/examples"
    write(ex, "valid/ok.yaml", 'schema: "run/1"\nn: 1\n')
    write(ex, "invalid/neg.yaml", 'schema: "run/1"\nn: -1\n')
    write(ex, "invalid/neg.yaml.reason", "less than the minimum of 0\n")
    reg = SchemaRegistry.from_tree(tree)
    assert check_examples(tree, reg) == []
    # a wrong reason, a missing reason, a passing invalid and a failing valid are all reported
    write(ex, "invalid/neg.yaml.reason", "something else\n")
    write(ex, "invalid/extra.yaml", 'schema: "run/1"\nn: 1\nx: 2\n')
    write(ex, "invalid/passes.yaml", 'schema: "run/1"\nn: 1\n')
    write(ex, "invalid/passes.yaml.reason", "anything\n")
    write(ex, "valid/broken.yaml", 'schema: "run/1"\n')
    problems = check_examples(tree, reg)
    assert len(problems) == 4
    assert any("does not mention 'something else'" in p for p in problems)
    assert any("has no .reason file" in p for p in problems)
    assert any("invalid example validates" in p for p in problems)
    assert any("valid example fails" in p for p in problems)


@pytest.mark.parametrize(
    ("fmt", "value", "ok"),
    [
        ("date", "2026-11-03", True),
        ("date", "2026-11-31", False),
        ("date", "26-11-03", False),
        ("date-time", "2026-11-03T10:00:00Z", True),
        ("date-time", "2026-11-03T10:00:00+01:00", True),
        ("date-time", "2026-11-03 10:00:00", False),
        ("uri", "https://github.com/x/y", True),
        ("uri", "not a uri", False),
    ],
)
def test_formats_asserted(fmt: str, value: str, ok: bool) -> None:
    assert FORMATS.conforms(value, fmt) is ok
