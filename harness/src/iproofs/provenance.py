"""Digests, pin checks and the machine record (RFC-0014, RFC-0006).

Digest byte definitions are normative in RFC-0012 §Digests.
"""

import hashlib
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHUNK = 1 << 20


def check_digest(value: str) -> str:
    """Return `value` if it is a well-formed digest string, else raise ErrorKind.integrity."""
    if not DIGEST_RE.fullmatch(value):
        raise IProofsError(ErrorKind.INTEGRITY, f"malformed digest {value!r}, want sha256:<64 hex>")
    return value


def _hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def file_digest(path: Path) -> str:
    """Digest of the file's bytes as stored, streamed."""
    return "sha256:" + _hex(path)


def _listing_digest(entries: Mapping[str, Path]) -> str:
    """sha256 over `<name>\\t<hex>\\n` lines sorted by the UTF-8 bytes of the name."""
    h = hashlib.sha256()
    for name in sorted(entries, key=lambda n: n.encode("utf-8")):
        h.update(f"{name}\t{_hex(entries[name])}\n".encode())
    return "sha256:" + h.hexdigest()


def _files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.is_symlink():
            raise IProofsError(
                ErrorKind.INTEGRITY, f"{p}: symlinks are not allowed in a hashed tree"
            )
        if p.is_file():
            files[p.relative_to(root).as_posix()] = p
        elif not p.is_dir():
            raise IProofsError(ErrorKind.INTEGRITY, f"{p}: not a regular file")
    return files


def tree_digest(root: Path) -> str:
    """Digest of every file under `root`; empty subdirectories do not count."""
    return _listing_digest(_files(root))


def model_digest(model_root: Path) -> str:
    return tree_digest(model_root)


def proof_digest(proof_dir: Path) -> str:
    """Digest over the part files of one proof directory, named by file name."""
    files = _files(proof_dir)
    nested = [name for name in files if "/" in name]
    if nested:
        raise IProofsError(ErrorKind.INTEGRITY, f"{proof_dir}: nested part files {nested}")
    return _listing_digest(files)


def corpus_digest(entries: Mapping[str, Path]) -> str:
    """Digest over the corpus files, each named by its corpus entry `id`."""
    return _listing_digest(entries)


def prompt_set_digest(prompts_jsonl: Path) -> str:
    return file_digest(prompts_jsonl)


# ---------------------------------------------------------------- git state (RFC-0014)


def git_state(root: Path, paths: Sequence[str] = ()) -> tuple[str, bool]:
    """(HEAD commit, dirty) of the checkout; `paths` limits the dirty check."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", *paths],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise IProofsError(ErrorKind.ENVIRONMENT, f"{root} is not a git checkout") from e
    return head, bool(status.strip())


def file_records(paths: Sequence[Path]) -> list[dict[str, object]]:
    """`{name, digest, bytes}` per file, as manifest.json lists commitment and proof files."""
    return [{"name": p.name, "digest": file_digest(p), "bytes": p.stat().st_size} for p in paths]
