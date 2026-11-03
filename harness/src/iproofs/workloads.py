"""Workload resolution, model fetch and prompt materialisation (RFC-0003)."""

import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Workload, load
from iproofs.provenance import corpus_digest, file_digest, model_digest, prompt_set_digest
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_jsonl


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


class Encoding(Protocol):
    @property
    def ids(self) -> Sequence[int]: ...


class Tokenizer(Protocol):
    """The part of a `tokenizers.Tokenizer` the generator uses."""

    def encode(self, sequence: str, *, add_special_tokens: bool) -> Encoding: ...


def load_tokenizer(path: Path) -> Tokenizer:
    """Load a model's tokenizer file; the optional `tokenizers` package is imported lazily."""
    try:
        import tokenizers  # noqa: PLC0415 (optional extra, INV-ARCH-6)
    except ImportError as e:
        raise IProofsError(
            ErrorKind.ENVIRONMENT, "tokenizers is not installed; install the [prompts] extra"
        ) from e
    tokenizer: Tokenizer = tokenizers.Tokenizer.from_file(str(path))
    return tokenizer


def corpus_window_v1(
    texts: list[str],
    tokenizer: Tokenizer,
    count: int,
    L: int,
    seed: int,
) -> list[list[int]]:
    """Prompt generator `corpus-window/1` (RFC-0003). Any change is `corpus-window/2`.

    Only `random.Random(seed).random()` is called: CPython guarantees that sequence
    across versions, not `randrange`, `choice` or `shuffle` (INV-WL-2).
    """
    ids = list(tokenizer.encode("\n".join(texts), add_special_tokens=False).ids)
    n = len(ids)
    if n < L:
        raise IProofsError(ErrorKind.CONFIG, f"corpus shorter than prompt length: {n} tokens < {L}")
    rng = random.Random(seed)
    prompts = []
    for _ in range(count):
        offset = math.floor(rng.random() * (n - L + 1))
        prompts.append(ids[offset : offset + L])
    return prompts


def write_prompt_set(path: Path, prompts: list[list[int]]) -> str:
    """Write `prompts.jsonl`, one JSON array of token ids per line; return its digest."""
    write_jsonl(path, prompts)
    return prompt_set_digest(path)


# ---------------------------------------------------------------- resolution for a job

# Local corpora known by digest. The CI corpus is the fixture corpus; the real corpus is
# fetched into the cache by `iproofs prompts build` (issue #133).
LOCAL_CORPORA = ("harness/tests/fixtures/prompts",)


@dataclass(frozen=True, slots=True)
class _Encoding:
    ids: Sequence[int]


class VocabTokenizer:
    """The toy character vocabulary format `{"vocab": {char: id}}` used by the fake system."""

    def __init__(self, path: Path) -> None:
        self.vocab: dict[str, int] = json.loads(path.read_text())["vocab"]

    def encode(self, sequence: str, *, add_special_tokens: bool) -> Encoding:
        missing = sorted({c for c in sequence if c not in self.vocab})
        if missing:
            raise IProofsError(
                ErrorKind.CONFIG, f"characters outside the toy vocabulary: {missing}"
            )
        return _Encoding([self.vocab[c] for c in sequence])


def tokenizer_for(path: Path) -> Tokenizer:
    """A model's tokenizer file: the toy vocabulary format, else a `tokenizers` file."""
    head = json.loads(path.read_text())
    if isinstance(head, dict) and "vocab" in head and "model" not in head:
        return VocabTokenizer(path)
    return load_tokenizer(path)


def local_corpus(root: Path, digest: str) -> list[str] | None:
    """Corpus texts in id order for a corpus digest, if a local copy has that digest."""
    for rel in LOCAL_CORPORA:
        files = {p.stem: p for p in sorted((root / rel).glob("*.txt"))}
        if files and corpus_digest(files) == digest:
            return [files[k].read_text("utf-8") for k in sorted(files, key=str.encode)]
    return None


def model_dir(root: Path, wl: Workload) -> Path:
    """The weights directory of a workload, hash-checked before any container sees it."""
    if wl.model.source.hub != "repository" or wl.model.source.path is None:
        raise IProofsError(
            ErrorKind.CONFIG,
            f"{wl.id}: weights not fetched; run `iproofs fetch-model {wl.id}` (issue #132)",
        )
    path = root / wl.model.source.path
    if model_digest(path) != wl.model.digest:
        raise IProofsError(
            ErrorKind.INTEGRITY, f"{wl.id}: model digest of {path.name} does not match the workload"
        )
    return path


def materialise_prompts(root: Path, wl: Workload, models: Path, seed: int) -> list[list[int]]:
    """The job's prompt set: corpus-window/1 over the workload's corpus with its tokenizer."""
    texts = local_corpus(root, wl.prompts.corpus_digest)
    if texts is None:
        raise IProofsError(
            ErrorKind.CONFIG, f"{wl.id}: corpus {wl.prompts.corpus_digest} is not available locally"
        )
    tokenizer = tokenizer_for(models / wl.model.tokenizer_file)
    return corpus_window_v1(
        texts, tokenizer, wl.prompts.count, wl.prompts.length_rule.prompt_tokens, seed
    )
