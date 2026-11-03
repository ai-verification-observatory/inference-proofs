"""Adapter job and output files, container invocation, path safety (RFC-0005).

Everything an adapter writes is untrusted input (docs/spec/06-security.md). Messages name
container-side paths (`/io/...`) only, so no host path reaches a record.
"""

import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import AdapterOut, System, load
from iproofs.schema import SchemaRegistry

MAX_OUT_JSON_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_PROOF_PARTS = 10_000
DEFAULT_MAX_PROOF_BYTES = 64 * 1024**3  # per part


def _adapter_error(message: str, step: str) -> IProofsError:
    return IProofsError(ErrorKind.ADAPTER, message, step=step)


@dataclass(frozen=True, slots=True)
class IoDirs:
    """Host directories mounted at `/io` and, except for verify, `/models`."""

    io: Path
    models: Path | None = None

    def host(self, container_path: str, step: str) -> Path:
        """Map an absolute container path to the host, refusing anything that escapes."""
        pure = PurePosixPath(container_path)
        if not pure.is_absolute() or ".." in pure.parts:
            raise _adapter_error(f"path {container_path!r} is not an absolute /io path", step)
        if pure.parts[1:2] == ("io",):
            root = self.io
        elif pure.parts[1:2] == ("models",) and self.models is not None:
            root = self.models
        else:
            raise _adapter_error(f"path {container_path!r} is outside /io and /models", step)
        host = root.joinpath(*pure.parts[2:])
        if not host.resolve().is_relative_to(root.resolve()):
            raise _adapter_error(f"path {container_path!r} escapes its mount", step)
        return host


def read_out(dirs: IoDirs, registry: SchemaRegistry, step: str) -> AdapterOut:
    """Read /io/out.json: size cap, stdlib parser, schema validation before any field is used."""
    path = dirs.io / "out.json"
    if not path.is_file() or path.is_symlink():
        raise _adapter_error("/io/out.json is missing or not a regular file", step)
    if path.stat().st_size > MAX_OUT_JSON_BYTES:
        raise _adapter_error(f"/io/out.json is larger than {MAX_OUT_JSON_BYTES} bytes", step)
    try:
        out = load(path, registry)
    except IProofsError as e:
        raise _adapter_error(f"/io/out.json is invalid: {e.message}", step) from e
    if not isinstance(out, AdapterOut) or out.subcommand != step:
        raise _adapter_error(f"/io/out.json is not an out file for {step}", step)
    for container_path in (
        *(out.verifier_files or ()),
        *(out.prover_files or ()),
        *(out.log_files or ()),
        *((out.binding_report,) if out.binding_report else ()),
    ):
        dirs.host(container_path, step)
    return out


def check_proofs(dirs: IoDirs, out: AdapterOut, system: System) -> list[str]:
    """INV-ADAPTER-6 and INV-ADAPTER-8 over /io/proofs after `prove`; returns warnings."""
    step = "prove"
    max_parts = system.max_proof_parts or DEFAULT_MAX_PROOF_PARTS
    max_bytes = system.max_proof_bytes or DEFAULT_MAX_PROOF_BYTES
    root = dirs.io / "proofs"
    warnings: list[str] = []
    released: dict[str, Path] = {}
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        name = f"/io/proofs/{entry.name}"
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise _adapter_error(f"{name} is not a directory", step)
        if entry.name.startswith(".tmp-"):
            warnings.append(f"{name}: unreleased temporary proof directory ignored")
            continue
        released[entry.name] = entry
    listed = {p.proof_id: p for p in out.proofs or ()}
    if set(listed) != set(released):
        unlisted = sorted(set(released) - set(listed))
        unreleased = sorted(set(listed) - set(released))
        raise _adapter_error(
            f"INV-ADAPTER-6: released but not listed {unlisted}, listed but not released "
            f"{unreleased}",
            step,
        )
    for proof_id, directory in released.items():
        parts = sorted(directory.iterdir())
        if len(parts) > max_parts:
            raise _adapter_error(
                f"/io/proofs/{proof_id} has {len(parts)} parts, cap {max_parts}", step
            )
        names = set()
        for part in parts:
            where = f"/io/proofs/{proof_id}/{part.name}"
            mode = part.lstat().st_mode
            if not stat.S_ISREG(mode):  # symlinks, devices, fifos and subdirectories
                raise _adapter_error(f"INV-ADAPTER-8: {where} is not a regular file", step)
            if part.stat().st_size > max_bytes:
                raise _adapter_error(f"{where} is larger than the {max_bytes}-byte cap", step)
            names.add(part.name)
        if names != set(listed[proof_id].parts):
            raise _adapter_error(
                f"/io/proofs/{proof_id}: parts on disk {sorted(names)} != listed "
                f"{sorted(listed[proof_id].parts)}",
                step,
            )
    return warnings
