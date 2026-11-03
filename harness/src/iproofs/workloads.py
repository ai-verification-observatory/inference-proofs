"""Workload resolution, model fetch and prompt materialisation (RFC-0003)."""

from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Workload, load
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry


def workload_file(root: Path, workload_id: str) -> Path:
    return root / "workloads" / f"{workload_id}.yaml"


def workload_digest(root: Path, workload_id: str) -> str:
    """File digest of the workload YAML, recorded in the manifest (RFC-0014)."""
    return file_digest(workload_file(root, workload_id))


def check_workload(wl: Workload, root: Path) -> list[str]:
    """Cross-field and cross-file rules the schema cannot express (RFC-0003 §Workload file)."""
    problems = []
    shape = wl.shape
    if wl.prompts.count != shape.batch_size * shape.batches_per_session:
        problems.append(
            f"INV-WL-4: prompts.count {wl.prompts.count} != shape.batch_size {shape.batch_size}"
            f" * shape.batches_per_session {shape.batches_per_session}"
        )
    if wl.prompts.length_rule.prompt_tokens != shape.prompt_tokens:
        problems.append(
            f"INV-WL-4: prompts.length_rule.prompt_tokens {wl.prompts.length_rule.prompt_tokens}"
            f" != shape.prompt_tokens {shape.prompt_tokens}"
        )
    needed = shape.prompt_tokens + shape.output_tokens - 1
    if shape.context_window < needed:
        problems.append(
            f"shape.context_window {shape.context_window} < prompt_tokens + output_tokens - 1"
            f" = {needed}"
        )
    if wl.model.tokenizer_file not in {f.path for f in wl.model.files}:
        problems.append(f"model.tokenizer_file {wl.model.tokenizer_file!r} is not in model.files")
    for system in wl.systems:
        if not (root / "systems" / system / "system.yaml").is_file():
            problems.append(f"systems: {system!r} has no systems/{system}/system.yaml")
    return problems


def load_workload(
    workload_id: str,
    version: int | None = None,
    *,
    root: Path,
    registry: SchemaRegistry,
) -> Workload:
    """Load and validate `workloads/<id>.yaml`, then check the loader rules (config errors)."""
    path = workload_file(root, workload_id)
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown workload {workload_id!r}: no {path}")
    wl = load(path, registry)
    if not isinstance(wl, Workload):
        raise IProofsError(ErrorKind.CONFIG, f"{path}: not a workload document")
    problems = []
    if wl.id != workload_id:
        problems.append(f"id {wl.id!r} does not match the file name")
    if version is not None and wl.version != version:
        problems.append(f"version {wl.version} != requested version {version}")
    problems += check_workload(wl, root)
    if problems:
        raise IProofsError(ErrorKind.CONFIG, "\n".join(f"{path}: {p}" for p in problems))
    return wl
