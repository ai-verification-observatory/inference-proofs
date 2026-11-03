"""Workload resolution, model fetch and prompt materialisation (RFC-0003)."""

import functools
import hashlib
import json
import math
import os
import random
import shutil
import stat
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Corpus, Workload, load
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
    texts = local_corpus(root, wl.prompts.corpus_digest) or pinned_corpus(
        root, wl.prompts.corpus_digest
    )
    if texts is None:
        raise IProofsError(
            ErrorKind.CONFIG, f"{wl.id}: corpus {wl.prompts.corpus_digest} is not available locally"
        )
    tokenizer = tokenizer_for(models / wl.model.tokenizer_file)
    return corpus_window_v1(
        texts, tokenizer, wl.prompts.count, wl.prompts.length_rule.prompt_tokens, seed
    )


# ---------------------------------------------------------------- model fetch (RFC-0014)

Download = Callable[[str, str, list[str], Path, str | None], None]


def default_cache() -> Path:
    return Path(os.environ.get("IPROOFS_CACHE", Path.home() / ".cache/iproofs"))


def hub_download(repo: str, revision: str, files: list[str], into: Path, token: str | None) -> None:
    """`huggingface_hub.snapshot_download` of exactly `files` (the `[fetch]` extra, lazy)."""
    try:
        from huggingface_hub import snapshot_download  # noqa: PLC0415 (INV-ARCH-6)
    except ImportError as e:
        raise IProofsError(
            ErrorKind.CONFIG, "fetching weights needs the [fetch] extra (huggingface_hub)"
        ) from e
    try:
        snapshot_download(
            repo_id=repo, revision=revision, allow_patterns=files, local_dir=into, token=token
        )
    except Exception as e:
        raise IProofsError(ErrorKind.FETCH, f"download of {repo}@{revision} failed: {e}") from e


def _check_files(wl: Workload, directory: Path) -> None:
    """RFC-0014 step 3 and 4: the exact file set, every digest, then the model digest."""
    want = {f.path: f.sha256 for f in wl.model.files}
    have = {
        p.relative_to(directory).as_posix(): p
        for p in directory.rglob("*")
        if p.is_file() and ".cache" not in p.relative_to(directory).parts
    }
    missing, extra = sorted(set(want) - set(have)), sorted(set(have) - set(want))
    if missing or extra:
        raise IProofsError(
            ErrorKind.INTEGRITY, f"{wl.id}: model files missing {missing}, unexpected {extra}"
        )
    for name, digest in want.items():
        if file_digest(have[name]).removeprefix("sha256:") != digest.removeprefix("sha256:"):
            raise IProofsError(ErrorKind.INTEGRITY, f"{wl.id}: {name} does not match its digest")
    if model_digest(directory) != wl.model.digest:
        raise IProofsError(ErrorKind.INTEGRITY, f"{wl.id}: model digest does not match")


def ensure_model(
    wl: Workload,
    cache: Path,
    *,
    download: Download | None = None,
    retry: Callable[[Callable[[], None]], None] = lambda op: op(),
    token: str | None = None,
) -> Path:
    """Return a read-only directory whose file set and digests equal `wl.model`.

    Absent: download the exact file list into a temporary sibling (`retry` wraps the call,
    RFC-0010), check it, rename it into place and drop write permission. Present: rehash it;
    a mismatch moves the entry to `quarantine/` and fails with `integrity`, never refetching.
    `token` is `HF_TOKEN`, passed to `download` and nowhere else."""
    target = cache / "models" / wl.model.digest.removeprefix("sha256:")
    if target.is_dir():
        try:
            _check_files(wl, target)
        except IProofsError:
            quarantine = cache / "quarantine" / f"{target.name}-{os.getpid()}"
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            _writable(target)
            target.rename(quarantine)
            raise
        return target
    tmp = target.with_name(f".tmp-{target.name}-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        files = [f.path for f in wl.model.files]
        fetch = download or hub_download
        retry(lambda: fetch(wl.model.source.repo, wl.model.revision, files, tmp, token))
        shutil.rmtree(tmp / ".cache", ignore_errors=True)  # the hub client's bookkeeping
        _check_files(wl, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    tmp.rename(target)
    for p in [*target.rglob("*"), target]:
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return target


def _writable(directory: Path) -> None:
    for p in [directory, *directory.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


# ---------------------------------------------------------------- corpus fetch (RFC-0014)

CORPUS_FILE = "workloads/prompts/corpus.yaml"


def http_get(url: str, timeout_s: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "iproofs-corpus-fetch"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise IProofsError(ErrorKind.FETCH, f"download of {url} failed: {e}") from e


def ensure_corpus(
    corpus: Corpus,
    cache: Path,
    *,
    get: Callable[[str], bytes] | None = None,
    retry: Callable[[Callable[[], bytes]], bytes] = lambda op: op(),
) -> dict[str, Path]:
    """RFC-0014 §Corpus fetch: each text in `$IPROOFS_CACHE/corpus/<sha256 hex>`, downloaded
    once and checked every time; a mismatch is `integrity`. Returns id -> verified file."""
    fetch = get or http_get
    out: dict[str, Path] = {}
    for text in corpus.texts:
        path = cache / "corpus" / text.sha256
        if not path.is_file():
            data = retry(functools.partial(fetch, text.source_url))
            if hashlib.sha256(data).hexdigest() != text.sha256:
                raise IProofsError(
                    ErrorKind.INTEGRITY, f"{text.id}: {text.source_url} does not match its sha256"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".tmp-{path.name}-{os.getpid()}")
            tmp.write_bytes(data)
            tmp.rename(path)
        elif file_digest(path) != f"sha256:{text.sha256}":
            raise IProofsError(ErrorKind.INTEGRITY, f"{text.id}: cached corpus file changed")
        out[text.id] = path
    return out


def normalised(data: bytes) -> str:
    """RFC-0003 normalisation: strip a BOM, LF newlines, Unicode NFC."""
    text = data.decode("utf-8").removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def pinned_corpus(
    root: Path, digest: str, *, cache: Path | None = None, get: Callable[[str], bytes] | None = None
) -> list[str] | None:
    """The texts of `workloads/prompts/corpus.yaml` when its digest is `digest`, read only
    from the verified cache, in id order (RFC-0003)."""
    path = root / CORPUS_FILE
    if not path.is_file():
        return None
    corpus = load(path, SchemaRegistry.from_tree(root / "schema"))
    assert isinstance(corpus, Corpus)
    if listed_digest(corpus) != digest:
        return None  # another corpus: nothing to fetch
    files = ensure_corpus(corpus, cache or default_cache(), get=get)
    return [normalised(files[k].read_bytes()) for k in sorted(files, key=str.encode)]


def listed_digest(corpus: Corpus) -> str:
    """RFC-0003: sha256 over `<id>\t<sha256>\n` sorted by id bytes, from the listing alone; it
    equals `corpus_digest` of the verified files."""
    lines = sorted((f"{t.id}\t{t.sha256}\n" for t in corpus.texts), key=str.encode)
    return "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest()


def tokenizer_file(
    root: Path, wl: Workload, cache: Path, *, download: Download | None = None
) -> Path:
    """The workload's tokenizer file, verified: from the toy model in this repository, from a
    verified model cache entry, or fetched alone and checked against its listed sha256 (so
    checking a prompt set needs no weights)."""
    name = wl.model.tokenizer_file
    if wl.model.source.hub == "repository":
        return model_dir(root, wl) / name
    model = cache / "models" / wl.model.digest.removeprefix("sha256:") / name
    if model.is_file():
        return model
    listed = next((f for f in wl.model.files if f.path == name), None)
    if listed is None:
        raise IProofsError(ErrorKind.CONFIG, f"{wl.id}: {name} is not in model.files")
    path = cache / "tokenizers" / listed.sha256.removeprefix("sha256:") / name
    if not path.is_file():
        tmp = path.parent.with_name(f".tmp-{path.parent.name}-{os.getpid()}")
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            (download or hub_download)(wl.model.source.repo, wl.model.revision, [name], tmp, None)
            got = tmp / name
            if file_digest(got).removeprefix("sha256:") != listed.sha256.removeprefix("sha256:"):
                raise IProofsError(
                    ErrorKind.INTEGRITY, f"{wl.id}: {name} does not match its sha256"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            got.rename(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif file_digest(path).removeprefix("sha256:") != listed.sha256.removeprefix("sha256:"):
        raise IProofsError(ErrorKind.INTEGRITY, f"{wl.id}: cached {name} changed")
    return path


def tokenizers_version() -> str | None:
    """The `tokenizers` library version: a different version can tokenize differently, which
    shows as a different prompt-set digest (RFC-0003 §Failure modes)."""
    try:
        import tokenizers  # noqa: PLC0415 (optional extra, INV-ARCH-6)
    except ImportError:
        return None
    return str(tokenizers.__version__)
