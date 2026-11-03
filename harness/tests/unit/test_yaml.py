from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.serialize import load_yaml


def load(tmp_path: Path, content: bytes) -> dict[str, object]:
    p = tmp_path / "doc.yaml"
    p.write_bytes(content)
    return load_yaml(p)


def config_error(tmp_path: Path, content: bytes) -> str:
    with pytest.raises(IProofsError) as e:
        load(tmp_path, content)
    assert e.value.kind is ErrorKind.CONFIG
    return e.value.message


def test_plain_types_load(tmp_path: Path) -> None:
    doc = load(tmp_path, b'schema: "workload/1"\nn: 3\nx: 1.5\nok: true\nnone: null\nl: [a, 1]\n')
    assert doc == {"schema": "workload/1", "n": 3, "x": 1.5, "ok": True, "none": None,
                   "l": ["a", 1]}  # fmt: skip


def test_unquoted_date_rejected(tmp_path: Path) -> None:
    msg = config_error(tmp_path, b"review:\n  window:\n    start: 2026-11-03\n")
    assert msg.endswith('/review/window/start: unquoted date, write "YYYY-MM-DD"')


def test_quoted_date_accepted(tmp_path: Path) -> None:
    assert load(tmp_path, b'date: "2026-11-03"\n') == {"date": "2026-11-03"}


def test_alias_rejected(tmp_path: Path) -> None:
    assert "anchor &a" in config_error(tmp_path, b"a: &a 1\nb: *a\n")


def test_merge_key_rejected(tmp_path: Path) -> None:
    assert "merge key" in config_error(tmp_path, b"base: {x: 1}\nc:\n  <<: {x: 2}\n")


def test_multiple_documents_rejected(tmp_path: Path) -> None:
    assert "more than one" in config_error(tmp_path, b"a: 1\n---\nb: 2\n")


def test_bom_rejected(tmp_path: Path) -> None:
    assert "byte-order mark" in config_error(tmp_path, b"\xef\xbb\xbfa: 1\n")


def test_crlf_rejected(tmp_path: Path) -> None:
    assert "CRLF" in config_error(tmp_path, b"a: 1\r\nb: 2\r\n")


def test_non_finite_rejected(tmp_path: Path) -> None:
    assert "/x: non-finite" in config_error(tmp_path, b"x: .inf\n")


def test_non_string_key_rejected(tmp_path: Path) -> None:
    assert "not a string" in config_error(tmp_path, b"1: a\n")


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    assert "mapping" in config_error(tmp_path, b"- a\n- b\n")


def test_invalid_yaml_is_config_error(tmp_path: Path) -> None:
    assert "invalid YAML" in config_error(tmp_path, b"a: [1\n")
