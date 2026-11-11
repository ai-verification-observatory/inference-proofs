"""The single JSON writer and the YAML subset loader (RFC-0012 §JSON writer, §YAML subset).

INV-ARCH-2: every generated JSON file is written through this module.
"""

import datetime
import hashlib
import json
import math
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from iproofs.errors import ErrorKind, IProofsError


def dumps(obj: Mapping[str, object]) -> bytes:
    """Canonical bytes of a generated document. NaN and infinities raise ValueError."""
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    return (text + "\n").encode("utf-8")


def _write_atomic(path: Path, data: bytes) -> str:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: Mapping[str, object]) -> str:
    """Write `obj` canonically and atomically; return the sha256 digest of the bytes."""
    return _write_atomic(path, dumps(obj))


def write_text(path: Path, text: str) -> str:
    """Write a UTF-8 text record (for example digests.txt) atomically; return its digest."""
    return _write_atomic(path, text.encode("utf-8"))


def write_jsonl(path: Path, rows: Iterable[object]) -> str:
    """One compact JSON value per line, keys sorted, LF after every line (prompts.jsonl)."""
    lines = [
        json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + "\n"
        for row in rows
    ]
    return _write_atomic(path, "".join(lines).encode("utf-8"))


def check_format(path: Path) -> bool:
    """RFC-0013 G3: the file's bytes equal the canonical re-serialization."""
    data = path.read_bytes()
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(obj, dict) and dumps(obj) == data


def _config(path: Path, message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"{path}: {message}")


def _check_events(path: Path, text: str) -> None:
    documents = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.DocumentStartEvent):
            documents += 1
            if documents > 1:
                raise _config(path, "more than one YAML document")
        elif isinstance(event, yaml.AliasEvent):
            raise _config(path, f"alias *{event.anchor} is not allowed")
        elif isinstance(event, yaml.NodeEvent) and event.anchor is not None:
            raise _config(path, f"anchor &{event.anchor} is not allowed")
        elif isinstance(event, yaml.ScalarEvent) and event.value == "<<" and event.style is None:
            raise _config(path, "merge key << is not allowed")


def _plain(path: Path, node: object, pointer: str) -> object:
    """Convert a parsed tree to JSON types, failing on anything else."""
    if node is None or isinstance(node, bool | int | str):
        return node
    if isinstance(node, float):
        if not math.isfinite(node):
            raise _config(path, f"{pointer or '/'}: non-finite number")
        return node
    if isinstance(node, datetime.date):  # also datetime.datetime
        raise _config(path, f'{pointer or "/"}: unquoted date, write "YYYY-MM-DD"')
    if isinstance(node, list):
        return [_plain(path, v, f"{pointer}/{i}") for i, v in enumerate(node)]
    if isinstance(node, dict):
        out: dict[str, object] = {}
        for k, v in node.items():
            if not isinstance(k, str):
                raise _config(path, f"{pointer or '/'}: key {k!r} is not a string")
            escaped = k.replace("~", "~0").replace("/", "~1")
            out[k] = _plain(path, v, f"{pointer}/{escaped}")
        return out
    raise _config(path, f"{pointer or '/'}: {type(node).__name__} is not a JSON type")


# Parsed YAML by the sha256 of the file's bytes, kept as JSON text: a tree is a function of the
# bytes alone, and every caller gets its own copy. Failures are not kept (they name the path).
_YAML_TREES: dict[bytes, str] = {}
_YAML_TREES_MAX = 4096


def load_yaml(path: Path) -> dict[str, object]:
    """Load an authored YAML file under the RFC-0012 subset rules; plain JSON types only."""
    raw = path.read_bytes()
    key = hashlib.sha256(raw).digest()
    if key in _YAML_TREES:
        known: dict[str, object] = json.loads(_YAML_TREES[key])
        return known
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _config(path, "byte-order mark is not allowed")
    if b"\r" in raw:
        raise _config(path, "CRLF or CR line endings are not allowed, use LF")
    try:
        text = raw.decode("utf-8")
        _check_events(path, text)
        tree = yaml.safe_load(text)
    except UnicodeDecodeError as e:
        raise _config(path, "not valid UTF-8") from e
    except yaml.YAMLError as e:
        raise _config(path, f"invalid YAML: {e}") from e
    if not isinstance(tree, dict):
        raise _config(path, "top level must be a mapping")
    plain = _plain(path, tree, "")
    assert isinstance(plain, dict)
    if len(_YAML_TREES) >= _YAML_TREES_MAX:
        _YAML_TREES.clear()
    _YAML_TREES[key] = json.dumps(plain, ensure_ascii=False, allow_nan=False)
    return plain
