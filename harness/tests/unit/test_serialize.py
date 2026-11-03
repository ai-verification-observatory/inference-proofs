import hashlib
import json
import os
from pathlib import Path

import pytest

from iproofs.serialize import check_format, dumps, write_json, write_jsonl


def test_dumps_sorted_indented_lf() -> None:
    assert (
        dumps({"b": 1, "a": {"d": [1.5, None], "c": "é"}})
        == (
            '{\n  "a": {\n    "c": "é",\n    "d": [\n      1.5,\n      null\n    ]\n  },\n'
            '  "b": 1\n}\n'
        ).encode()
    )


def test_nan_rejected() -> None:
    with pytest.raises(ValueError, match="Out of range"):
        dumps({"x": [float("nan")]})


@pytest.mark.parametrize("bad", [float("inf"), float("-inf")])
def test_inf_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="Out of range"):
        dumps({"x": bad})


def test_write_json_returns_digest_of_bytes(tmp_path: Path) -> None:
    p = tmp_path / "run.json"
    digest = write_json(p, {"schema": "run/1"})
    assert digest == "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    assert check_format(p)


def test_atomic_write_leaves_no_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "run.json"
    write_json(p, {"ok": 1})

    def crash(src: object, dst: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="disk gone"):
        write_json(p, {"ok": 2})
    assert json.loads(p.read_text()) == {"ok": 1}  # previous content intact
    assert os.listdir(tmp_path) == ["run.json"]  # no temp file left behind


def test_write_jsonl_compact_sorted(tmp_path: Path) -> None:
    p = tmp_path / "prompts.jsonl"
    write_jsonl(p, [{"b": 2, "a": [1, 2]}, {"id": "é"}])
    assert p.read_bytes() == '{"a":[1,2],"b":2}\n{"id":"é"}\n'.encode()


@pytest.mark.parametrize(
    "content",
    [b'{"a":1}\n', b'{\n  "a": 1\n}', b'{\n  "a": 1\n}\r\n', b"[1]\n", b"not json"],
)
def test_check_format_rejects_non_canonical(tmp_path: Path, content: bytes) -> None:
    p = tmp_path / "x.json"
    p.write_bytes(content)
    assert not check_format(p)
