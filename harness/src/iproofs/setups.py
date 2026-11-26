"""A setup: the commitment and whatever else a system's commit prepares (SASH's kernel store and
CUDA build), made once by a setup run and reused by every session that names it.

A setup run (`iproofs run --make-setup`) calls info, setup and commit with no prompt, then keeps
the state commit left in /io/state as one archive beside its setup record (`setup/1`). A session
(`iproofs run --setup DIR`) checks the archive's digest and that the record was made for this
session's system pin, image, adapter commit, model and shape, restores the state under
/io/state, and calls commit with `setup_state`: the adapter checks the restored state and makes
nothing again. The commitment the verifier checks is the record's (AGENTS.md hard rule 6).
"""

import json
import os
import posixpath
import tarfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry

SETUP_SCHEMA = "setup/1"
SETUP_RECORD = "setup.json"
ARCHIVE = "state.tar"
ARCHIVE_ROOT = "state"  # the archive's one top-level entry: /io/state as commit left it
SETUPS = "_setups"  # <results>/<release>/<system>/_setups/<setup id>/
GPU_SECONDS_REF = "iproofs.setups.gpu_seconds@1"


def archive_state(state: Path, archive: Path) -> None:
    """`state` as one tar under ARCHIVE_ROOT, symbolic links kept as links (a build directory
    links to the image's cargo registry) and file modes kept (the binaries stay executable)."""
    with tarfile.open(archive, "w") as tar:
        tar.add(state, arcname=ARCHIVE_ROOT, recursive=True)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _member_filter(io: Path) -> Callable[[tarfile.TarInfo, str], tarfile.TarInfo]:
    """tarfile's `tar` filter, then: the entry's normalised name is ARCHIVE_ROOT or under it, it
    is written under io/ARCHIVE_ROOT once every link extracted before it is followed, a hard
    link names an entry under ARCHIVE_ROOT, and a relative symbolic link resolves under
    io/ARCHIVE_ROOT. An absolute symbolic link is kept: it names a path the image provides (a
    build directory's cargo registry), and nothing is written through it (the check above)."""
    root = os.path.realpath(io / ARCHIVE_ROOT)

    def check(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo:
        kept = tarfile.tar_filter(member, path)
        name = posixpath.normpath(kept.name)
        dest = os.path.realpath(os.path.join(path, name))
        wrong = not (name == ARCHIVE_ROOT or name.startswith(ARCHIVE_ROOT + "/")) or not _under(
            dest, root
        )
        if kept.islnk():
            link = posixpath.normpath(kept.linkname)
            wrong = wrong or not (link == ARCHIVE_ROOT or link.startswith(ARCHIVE_ROOT + "/"))
        elif kept.issym() and not posixpath.isabs(kept.linkname):
            target = os.path.realpath(os.path.join(os.path.dirname(dest), kept.linkname))
            wrong = wrong or not _under(target, root)
        if wrong:
            raise IProofsError(ErrorKind.INTEGRITY, f"the setup archive's entry {member.name!r} "
                               f"leaves io/{ARCHIVE_ROOT}")  # fmt: skip
        return kept

    return check


def restore_state(archive: Path, digest: str, io: Path) -> None:
    """The archived state at `io`/state, once the archive's sha256 is the record's. Every entry
    is under ARCHIVE_ROOT once its name is normalised, and nothing is written outside
    io/ARCHIVE_ROOT (`_member_filter`); a symbolic link may point at an absolute path, which the
    image provides."""
    got = file_digest(archive)
    if got != digest:
        raise IProofsError(ErrorKind.INTEGRITY, f"{archive.name} has digest {got}; the setup "
                           f"record names {digest}")  # fmt: skip
    target = io / ARCHIVE_ROOT
    if target.is_symlink() or (target.exists() and any(target.iterdir())):
        raise IProofsError(ErrorKind.CONFIG, "io/state holds files before the setup's state is "
                           "restored")  # fmt: skip
    with tarfile.open(archive) as tar:
        names = [posixpath.normpath(n) for n in tar.getnames()]
        stray = [n for n in names if n != ARCHIVE_ROOT
                 and not n.startswith(ARCHIVE_ROOT + "/")]  # fmt: skip
        if stray:
            raise IProofsError(ErrorKind.INTEGRITY, f"{archive.name} holds entries outside "
                               f"{ARCHIVE_ROOT}/: {stray[:3]}")  # fmt: skip
        if target.is_dir():
            target.rmdir()
        tar.extractall(io, filter=_member_filter(io))


def gpu_seconds(gpu_count: int | None, total_seconds: float) -> float | None:
    """A setup's GPU time: the GPUs its profile binds times its wall seconds, from the first
    state to the archive (every GPU is held for the whole run). None for a CPU-only profile."""
    return None if gpu_count is None else gpu_count * total_seconds


def record_problems(doc: Mapping[str, Any]) -> list[str]:
    """What the schema cannot check: `gpu_seconds` is `gpu_seconds()` of the record's own
    inputs (AGENTS.md hard rule 3)."""
    count, total = doc["gpu_count"]["value"], doc["total_seconds"]["value"]
    want = None if total is None else gpu_seconds(count, total)
    got = doc["gpu_seconds"]["value"]
    if got != want:  # the same product of the same stored floats, bit for bit
        return [f"gpu_seconds {got!r} is not gpu_count {count!r} x total_seconds {total!r}"]
    return []


IDENTITY = ("system", "upstream_commit", "image", "adapter_commit", "adapter_dirty",
            "model_digest", "shape")  # fmt: skip


def record_identity(doc: Mapping[str, Any]) -> dict[str, object]:
    """What a session must share with the setup it reuses, in IDENTITY's keys."""
    system, workload = doc["system"], doc["workload"]
    upstream = system["upstream"]
    return {
        "system": system["name"],
        "upstream_commit": upstream["commit"] if upstream else None,
        "image": system["image"]["ref"],
        "adapter_commit": system["adapter_commit"],
        "adapter_dirty": system["adapter_dirty"],
        "model_digest": workload["model"]["digest"],
        "shape": dict(workload["shape"]),
    }


@dataclass(frozen=True, slots=True)
class Setup:
    """A completed setup directory: its record (schema-checked) and the record's digest."""

    path: Path
    record: Mapping[str, Any]
    digest: str

    @property
    def setup_id(self) -> str:
        return str(self.record["setup_id"])

    @property
    def commitment_id(self) -> str:
        return str(self.record["commitment"]["commitment_id"])

    @property
    def archive_digest(self) -> str:
        return str(self.record["archive"]["digest"])

    @property
    def build_key(self) -> str | None:
        kernels = self.record.get("kernels")
        return str(kernels["build_key"]) if kernels else None

    def mismatches(self, session: Mapping[str, object]) -> list[str]:
        """Each IDENTITY key on which this session differs from the setup."""
        made = record_identity(self.record)
        return [f"{k}: the setup has {made[k]!r}, this session {session[k]!r}"
                for k in IDENTITY if made[k] != session[k]]  # fmt: skip

    def file_problems(self, records: Mapping[str, object]) -> list[str]:
        """The session's commitment files (name and digest, as the harness copied them after
        commit) against the setup record's."""
        out = []
        for kind in ("verifier_files", "prover_files"):
            want = [(f["name"], f["digest"]) for f in self.record["commitment"][kind]]
            entries = records[kind]
            assert isinstance(entries, list)
            got = [(f["name"], f["digest"]) for f in entries]
            if got != want:
                out.append(f"{kind} {got} are not the setup's {want}")
        return out

    def restore(self, io: Path) -> None:
        restore_state(self.path / ARCHIVE, self.archive_digest, io)


def load_setup(path: Path, registry: SchemaRegistry) -> Setup:
    """A setup directory a session can reuse: a schema-valid completed record and its archive."""
    record = path / SETUP_RECORD
    if not record.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{path} holds no {SETUP_RECORD}")
    doc = json.loads(record.read_text())
    errors = registry.errors(SETUP_SCHEMA, doc)
    if errors:
        raise IProofsError(ErrorKind.CONFIG, f"{record} fails {SETUP_SCHEMA}: {errors[0]}")
    if doc["status"] != "completed":
        step = doc["failure"]["step"]
        raise IProofsError(ErrorKind.CONFIG, f"setup {doc['setup_id']} failed at {step}: a "
                           "session reuses a completed setup only")  # fmt: skip
    problems = record_problems(doc)
    if problems:
        raise IProofsError(ErrorKind.INTEGRITY, f"{record}: {problems[0]}")
    if not (path / ARCHIVE).is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{path} holds no {ARCHIVE}")
    return Setup(path, doc, file_digest(record))
