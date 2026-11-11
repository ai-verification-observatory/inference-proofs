"""Results of the gate checks that read one file and nothing else, kept between runs.

`results/` is append-only and most other tracked files change rarely, so most of a tree was
checked before with the same bytes. A check here is keyed by its name and the sha256 of the
bytes it read; the store as a whole is keyed by a salt: this package's source, the schema tree
and the versions of the interpreter and the parsers. A change to any of them drops every entry.

Only checks that are a function of one file's bytes go through a memo (G2 schema validation of
a document, G3, G9). A check that reads a second file (cross-references, G4's inputs, claim
cards) is computed every time.

The store lives in the user's cache folder, never in the repository, so a fresh checkout (CI
included) has none and checks every file. `iproofs validate --no-cache` does the same locally.
A store that cannot be read is ignored; one that cannot be written is not an error.
"""

import hashlib
import json
import os
import sys
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

from iproofs.schema import SchemaRegistry

PARSERS = ("jsonschema", "referencing", "PyYAML")


def salt(registry: SchemaRegistry) -> str:
    """What every memoised check depends on besides the file it reads."""
    seen = hashlib.sha256()
    package = Path(__file__).resolve().parents[1]
    for path in sorted(package.rglob("*.py")):
        data = path.read_bytes()
        seen.update(f"{path.relative_to(package).as_posix()}\0{len(data)}\0".encode() + data)
    versions = [sys.version, *(f"{name}=={metadata.version(name)}" for name in PARSERS)]
    seen.update("\0".join([registry.digest, *versions]).encode())
    return seen.hexdigest()


def store_path(root: Path) -> Path:
    """One store per checkout, under IPROOFS_CACHE or ~/.cache/iproofs."""
    base = Path(os.environ.get("IPROOFS_CACHE", Path.home() / ".cache/iproofs"))
    return base / "validate" / f"{hashlib.sha256(str(root.resolve()).encode()).hexdigest()}.json"


class Memo:
    def __init__(self, path: Path, registry: SchemaRegistry) -> None:
        self.path = path
        self.salt = salt(registry)
        self.used: dict[str, object] = {}
        self.old: dict[str, object] = {}
        try:
            stored = json.loads(path.read_bytes())
            if stored["salt"] == self.salt and isinstance(stored["entries"], dict):
                self.old = stored["entries"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def check[T](self, name: str, data: bytes, compute: Callable[[], T]) -> T:
        """`compute()`, a JSON value that depends on `data` alone, or its stored result."""
        key = f"{name}:{hashlib.sha256(data).hexdigest()}"
        if key not in self.used:
            self.used[key] = self.old[key] if key in self.old else compute()
        found: T = self.used[key]  # type: ignore[assignment]
        return found

    def save(self, *, whole: bool) -> None:
        """Keep what this run read; a run over part of the tree keeps the other entries too."""
        entries = self.used if whole else {**self.old, **self.used}
        text = json.dumps({"salt": self.salt, "entries": entries}, separators=(",", ":"))
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text)
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
