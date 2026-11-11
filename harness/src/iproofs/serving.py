"""Production-serving records: the publisher's release, pinned by an ungated byte-identical copy
(RFC-0015 SRV-6; RFC-0014 §Model fetch, SM-1 to SM-3).

A record `workloads/serving/<id>.yaml` (`serving-model/1`) lists, per file, the path, sha256,
bytes, storage and the publisher's git blob id at its pinned revision. Two files with equal git
blob ids are equal byte for byte: for a small file the id hashes the bytes, for an LFS file it
hashes the pointer, which holds the sha256 and the size. So the publisher's anonymous tree
listing proves the mirror's bytes are the publisher's, although the gated repository masks the
LFS sha256.

It also sizes a lengthened matched serving session from a stored capture (`session_size`,
RFC-0015 SRV-1).

Pure functions apart from `ensure_serving_model` (cache writes) and the `get` callables that
`check_mirror` and `pin` take (network in the CLI, fixtures in the tests).
"""

import dataclasses
import hashlib
import json
import math
import os
import shutil
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from fnmatch import fnmatch
from fractions import Fraction
from pathlib import Path
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import ServingModel, Workload, load
from iproofs.provenance import checked_tree_digest, file_digest, hex_digests
from iproofs.schema import SchemaRegistry

SERVING_DIR = "workloads/serving"
LFS_POINTER = "version https://git-lfs.github.com/spec/v1\noid sha256:{sha}\nsize {size}\n"
HUB = "https://huggingface.co"

Get = Callable[[str], bytes]  # URL -> response body
Download = Callable[[str, str, list[str], Path, str | None], None]


def git_blob_id(data: bytes) -> str:
    """The git blob id of a file's bytes: sha1 over `blob <n>\\0` and the bytes."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data, usedforsecurity=False).hexdigest()


def lfs_pointer_blob(sha256_hex: str, size: int) -> str:
    """The git blob id of the LFS pointer for a file of this sha256 and size (SM-1)."""
    return git_blob_id(LFS_POINTER.format(sha=sha256_hex, size=size).encode())


def listing_digest(files: Iterable[tuple[str, str]]) -> str:
    """The RFC-0012 model digest over (path, sha256 hex) pairs: sha256 over `<path>\\t<hex>\\n`
    lines sorted by the UTF-8 bytes of the path, as `provenance.model_digest` over the files."""
    h = hashlib.sha256()
    for path, sha in sorted(files, key=lambda f: f[0].encode("utf-8")):
        h.update(f"{path}\t{sha}\n".encode())
    return "sha256:" + h.hexdigest()


# ---------------------------------------------------------------- SM-1 (offline)


def sm1_problems(record: ServingModel) -> list[str]:
    """SM-1: every `lfs` file's pointer blob, rebuilt from sha256 and bytes, is the publisher's
    blob id; the digest is the listing digest of the files."""
    problems = []
    for f in record.model.files:
        if f.storage == "lfs" and lfs_pointer_blob(f.sha256, f.bytes) != f.publisher_blob:
            problems.append(f"SM-1: {f.path}: the LFS pointer of sha256 {f.sha256[:12]} and "
                            f"{f.bytes} B has another blob id than the publisher's "
                            f"{f.publisher_blob[:12]}")  # fmt: skip
    want = listing_digest((f.path, f.sha256) for f in record.model.files)
    if want != record.model.digest:
        problems.append(f"SM-1: model.digest {record.model.digest} is not the files' {want}")
    return problems


# ---------------------------------------------------------------- records and the workload map


def record_paths(root: Path) -> list[Path]:
    return sorted((root / SERVING_DIR).glob("*.yaml"))


def load_records(root: Path, registry: SchemaRegistry) -> dict[str, ServingModel]:
    """Every serving record by id, schema-validated."""
    out = {}
    for path in record_paths(root):
        doc = load(path, registry)
        if not isinstance(doc, ServingModel):
            raise IProofsError(ErrorKind.CONFIG, f"{path}: not a serving-model/1 record")
        if doc.id != path.stem:
            raise IProofsError(ErrorKind.CONFIG, f"{path}: id {doc.id!r} is not the file name")
        out[doc.id] = doc
    return out


def record_for(root: Path, registry: SchemaRegistry, workload_id: str) -> ServingModel | None:
    """The record that names the workload (SRV-6: its `workloads` is the only mapping)."""
    found = [r for r in load_records(root, registry).values() if workload_id in r.workloads]
    return found[0] if len(found) == 1 else None


def mapping_problems(
    records: Mapping[str, ServingModel], workloads: Mapping[str, Workload], serve: Sequence[str]
) -> list[str]:
    """SRV-6 loader rules over the records and the workload files: each listed workload exists
    and names a serve-role system (`serve`: the serve-role system names), no workload is named by
    two records, every workload that names a serve-role system is named by one record, and the
    record's `vocab_size` is the workload's (the prompts are token ids of one vocabulary)."""
    problems = []
    named: dict[str, list[str]] = {}
    for rid, rec in sorted(records.items()):
        for wid in rec.workloads:
            named.setdefault(wid, []).append(rid)
            wl = workloads.get(wid)
            if wl is None:
                problems.append(f"{rid}: workload {wid!r} has no workloads/{wid}.yaml")
                continue
            if not set(wl.systems) & set(serve):
                problems.append(f"{rid}: workload {wid} names no serve-role system")
            if wl.model.vocab_size != rec.model.vocab_size:
                problems.append(f"{rid}: vocab_size {rec.model.vocab_size} differs from "
                                f"{wid}'s {wl.model.vocab_size}")  # fmt: skip
    for wid, rids in sorted(named.items()):
        if len(rids) > 1:
            problems.append(f"workload {wid} is named by {len(rids)} serving records {rids}")
    for wid, wl in sorted(workloads.items()):
        if set(wl.systems) & set(serve) and wid not in named:
            problems.append(f"workload {wid} names a serve-role system and no serving record")
    return problems


def serving_manifest(record: ServingModel) -> dict[str, object]:
    """The manifest's `serving_model` (RFC-0010): id and version for display, digest the key."""
    return {
        "id": record.id,
        "version": record.version,
        "digest": record.model.digest,
        "source": {"repo": record.model.source.repo, "revision": record.model.revision},
        "publisher": {
            "repo": record.publisher.release.repo,
            "revision": record.publisher.release.revision,
        },
    }


# RFC-0015 SRV-1: the warning of a serving run whose steady scope lasts under 60 s; such a run
# keeps its value and joins no D-OVERHEAD-S (RFC-0004 INV-DERIVE-2)
SHORT_STEADY = "steady scope under 60 s"


# ---------------------------------------------------------------- session length (SRV-1)

# RFC-0015 SRV-1 (Draft amendment of 2026-11-09): a lengthened matched session aims its steady
# scope at 120 s, twice the 60 s join minimum, so a run up to twice as slow per batch as its
# capture still clears 60 s. The join minimum stays 60 s (SHORT_STEADY).
SESSION_TARGET_S = 120
# RFC-0015 SRV-1: a sizing capture (`iproofs run --sizing-batches N`) serves N batches while the
# entry's count is null; it has a steady scope from 2 batches on, and joins no overhead.
SIZING_MIN_BATCHES = 2
SIZING_WARNING = ("sizing capture: it sizes batches_per_session_run and joins no overhead "
                  "(RFC-0015 SRV-1)")  # fmt: skip


@dataclasses.dataclass(frozen=True, slots=True)
class SessionSize:
    """`batches_per_session_run` of one (workload, GPU count), computed from a stored matched
    capture (RFC-0015 SRV-1). Seconds of the capture are its measured values; the `expected_*`
    seconds are projections from it (grade projected), never results."""

    run_id: str
    workload: str
    gpus: int
    batch_size: int
    capture_batches: int
    capture_steady_s: float  # prove.steady: the first batch's last release to the last release
    capture_session_s: float | None  # prove.session, start-up included
    seconds_per_batch: float  # capture_steady_s / (capture_batches - 1)
    target_s: int
    steady_batches: int  # the smallest n with n x seconds_per_batch >= target_s
    batches: int  # batches_per_session_run: steady_batches + 1, at least the workload's
    expected_steady_s: float
    expected_session_s: float | None

    @property
    def prompt_count(self) -> int:
        return self.batch_size * self.batches


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def session_size(
    run: Mapping[str, Any],
    manifest: Mapping[str, Any],
    workload_batches: int,
    target_s: int = SESSION_TARGET_S,
) -> SessionSize:
    """RFC-0015 SRV-1: the batches per session at which a matched serving run's steady scope
    is expected to reach `target_s`, from one completed matched capture of the configuration
    (its run.json and manifest.json).

    The steady scope runs from the first batch's last release to the last batch's last release
    (RFC-0004 INV-SCOPE-5), so it spans the capture's batches minus one. Seconds per steady
    batch = `prove_steady_seconds` / (batches - 1); steady batches = the smallest integer n with
    n x that time >= `target_s`, computed exactly on the stored binary64 value (no rounding at
    the boundary); the count adds the first batch, which the steady scope excludes, and is never
    below the workload's `batches_per_session`.

    A sizing capture (`iproofs run --sizing-batches N`, manifest `workload.sizing_capture`)
    is sized like any other matched capture: it serves N batches while the count is null, so a
    workload of one batch (the SASH workloads) gets a steady scope to size from (RFC-0015 Q10,
    resolved). A capture without a steady scope (one batch: one request at batch size 1, or a
    single batch) is refused (`config`). Its record cannot give the time per batch after
    start-up: the one batch's releases follow engine start-up inside the same `prove` call,
    and neither run.json nor manifest.json timestamps the end of start-up (the adapter's
    command record holds the engine's launch time, and its engine log has wall-clock seconds
    at best)."""
    run_id = str(run.get("run_id"))
    wl = manifest.get("workload") or {}
    if run.get("status") != "completed":
        raise IProofsError(ErrorKind.CONFIG, f"{run_id}: status {run.get('status')!r}; a session "
                           "is sized from a completed capture (RFC-0015 SRV-1)")  # fmt: skip
    if run.get("system_kind") != "reference" or wl.get("load_point") != "matched":
        raise IProofsError(ErrorKind.CONFIG, f"{run_id}: not a matched production-serving run "
                           f"(load point {wl.get('load_point')!r}); only the matched load is "
                           "lengthened (RFC-0015 SRV-1)")  # fmt: skip
    batch, batches = wl.get("batch_size_run"), wl.get("batches_per_session_run")
    gpus = ((run.get("inputs") or {}).get("gpu_count") or {}).get("value")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1
               for v in (batch, batches, gpus)):  # fmt: skip
        raise IProofsError(ErrorKind.CONFIG, f"{run_id}: the record lacks the run's batch "
                           "size, batch count or GPU count (manifest workload.batch_size_run, "
                           "workload.batches_per_session_run, run.json "
                           "inputs.gpu_count)")  # fmt: skip
    assert isinstance(batch, int)
    assert isinstance(batches, int)
    assert isinstance(gpus, int)
    metrics = run.get("metrics") or {}
    steady_q = metrics.get("prove_steady_seconds") or {}
    steady = _number(steady_q.get("value"))
    session = _number((metrics.get("prove_session_seconds") or {}).get("value"))
    if batches < 2 or steady is None or steady <= 0:
        raise IProofsError(ErrorKind.CONFIG, f"{run_id}: no steady scope ({batches} batch(es) of "
                           f"{batch}; prove_steady_seconds {steady_q.get('value')!r}, null reason "
                           f"{steady_q.get('null_reason')!r}). The only batch's releases follow "
                           "engine start-up in the same prove call, and the record does not "
                           "timestamp the end of start-up, so its time per batch after start-up "
                           "cannot be told from start-up. Size the session from a matched "
                           "capture of at least 2 batches: for a workload of one batch, a "
                           "sizing capture (`iproofs run --sizing-batches N`, RFC-0015 "
                           "SRV-1)")  # fmt: skip
    capture_steady_batches = batches - 1
    n = math.ceil(Fraction(target_s) * capture_steady_batches / Fraction(steady))
    total = max(workload_batches, n + 1)
    per = steady / capture_steady_batches
    return SessionSize(
        run_id=run_id,
        workload=str(wl.get("id")),
        gpus=gpus,
        batch_size=batch,
        capture_batches=batches,
        capture_steady_s=steady,
        capture_session_s=session,
        seconds_per_batch=per,
        target_s=target_s,
        steady_batches=n,
        batches=total,
        expected_steady_s=per * (total - 1),
        expected_session_s=None if session is None else session + per * (total - batches),
    )


# ---------------------------------------------------------------- SM-2 (fetch-model --serving)


def check_files(record: ServingModel, directory: Path) -> None:
    """SM-2: the exact file set; every sha256 and size; every `git` file's blob id; the model
    digest. Any mismatch is `config` (RFC-0014): no job runs on a file that is not the record's."""
    want = {f.path: f for f in record.model.files}
    have = {
        p.relative_to(directory).as_posix(): p
        for p in directory.rglob("*")
        if p.is_file() and ".cache" not in p.relative_to(directory).parts
    }
    missing, extra = sorted(set(want) - set(have)), sorted(set(have) - set(want))
    if missing or extra:
        raise IProofsError(
            ErrorKind.CONFIG, f"{record.id}: files missing {missing}, unexpected {extra} (SM-2)"
        )
    hexes = hex_digests(have)  # every file read once; the model digest is over these
    for path, f in sorted(want.items()):
        got = have[path]
        if got.stat().st_size != f.bytes or hexes[path] != f.sha256:
            raise IProofsError(ErrorKind.CONFIG, f"{record.id}: {path} is not the record's (SM-2)")
        if f.storage == "git" and git_blob_id(got.read_bytes()) != f.publisher_blob:
            raise IProofsError(
                ErrorKind.CONFIG, f"{record.id}: {path} is not the publisher's bytes (SM-2)"
            )
    if checked_tree_digest(directory, hexes) != record.model.digest:
        raise IProofsError(ErrorKind.CONFIG, f"{record.id}: model digest differs (SM-2)")


def ensure_serving_model(
    record: ServingModel,
    cache: Path,
    *,
    download: Download,
    retry: Callable[[Callable[[], None]], None] = lambda op: op(),
    token: str | None = None,
) -> Path:
    """The read-only directory of the record's files, fetched once into
    `$IPROOFS_CACHE/models/<digest hex>/` and checked (SM-2), rehashed when present. Files with
    `source: publisher` come from the publisher's repository with `token`; the rest from the
    mirror without it."""
    target = cache / "models" / record.model.digest.removeprefix("sha256:")
    if target.is_dir():
        check_files(record, target)
        return target
    tmp = target.with_name(f".tmp-{target.name}-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        mirror = [f.path for f in record.model.files if f.source != "publisher"]
        publisher = [f.path for f in record.model.files if f.source == "publisher"]
        src = record.model.source.repo, record.model.revision
        retry(lambda: download(*src, mirror, tmp, None))
        if publisher:
            pub = record.publisher.release.repo, record.publisher.release.revision
            retry(lambda: download(*pub, publisher, tmp, token))
        shutil.rmtree(tmp / ".cache", ignore_errors=True)
        check_files(record, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    tmp.rename(target)
    for p in [*target.rglob("*"), target]:
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return target


def fetch_no_weights(
    record: ServingModel,
    directory: Path,
    *,
    download: Download,
    retry: Callable[[Callable[[], None]], None] = lambda op: op(),
    token: str | None = None,
) -> list[str]:
    """`fetch-model --serving RECORD --no-weights DIR`: every file of the record but the
    `.safetensors` weights, each checked as SM-2 checks it (sha256, size, git blob id), so the
    engine's tokenizer and processor load can be tried before the weights are fetched. Returns
    the paths written."""
    small = [f for f in record.model.files if not f.path.endswith(".safetensors")]
    directory.mkdir(parents=True, exist_ok=True)
    mirror = [f.path for f in small if f.source != "publisher"]
    publisher = [f.path for f in small if f.source == "publisher"]
    if mirror:
        src = record.model.source.repo, record.model.revision
        retry(lambda: download(*src, mirror, directory, None))
    if publisher:
        pub = record.publisher.release.repo, record.publisher.release.revision
        retry(lambda: download(*pub, publisher, directory, token))
    shutil.rmtree(directory / ".cache", ignore_errors=True)
    for f in small:
        got = directory / f.path
        if (not got.is_file() or got.stat().st_size != f.bytes
                or file_digest(got) != f"sha256:{f.sha256}"):  # fmt: skip
            raise IProofsError(
                ErrorKind.CONFIG, f"{record.id}: {f.path} is not the record's (SM-2)"
            )
        if f.storage == "git" and git_blob_id(got.read_bytes()) != f.publisher_blob:
            raise IProofsError(
                ErrorKind.CONFIG, f"{record.id}: {f.path} is not the publisher's bytes (SM-2)"
            )
    return [f.path for f in small]


# ---------------------------------------------------------------- SM-3 and pin (network)


def tree(repo: str, revision: str, get: Get) -> dict[str, Mapping[str, Any]]:
    """The Hub's recursive tree listing at a revision, by path (anonymous for a gated repo)."""
    body = get(f"{HUB}/api/models/{repo}/tree/{revision}?recursive=true")
    return {str(e["path"]): e for e in json.loads(body) if e.get("type") == "file"}


def check_mirror(record: ServingModel, get: Get) -> list[str]:
    """SM-3: for every pinned file the mirror's blob id, the publisher's and `publisher_blob`
    are equal, at the pinned revisions. Returns the problems; empty means the record holds."""
    mirror = tree(record.model.source.repo, record.model.revision, get)
    publisher = tree(record.publisher.release.repo, record.publisher.release.revision, get)
    problems = []
    for f in record.model.files:
        ids = {
            "mirror": None if f.source == "publisher" else (mirror.get(f.path) or {}).get("oid"),
            "publisher": (publisher.get(f.path) or {}).get("oid"),
        }
        if f.source == "publisher":
            ids.pop("mirror")
        wrong = {k: v for k, v in ids.items() if v != f.publisher_blob}
        if wrong:
            problems.append(f"SM-3: {f.path}: blob ids {wrong} differ from {f.publisher_blob}")
    return problems


def pin_files(
    mirror_repo: str,
    mirror_rev: str,
    publisher_repo: str,
    publisher_rev: str,
    include: Sequence[str],
    get: Get,
) -> list[dict[str, object]]:
    """`iproofs serving pin`: the record's file list from the two tree listings, every mirror
    file matching an `include` pattern. sha256 is the mirror's `lfs.oid`, or the sha256 of the
    fetched small file; a file whose mirror and publisher blob ids differ is refused."""
    mirror = tree(mirror_repo, mirror_rev, get)
    publisher = tree(publisher_repo, publisher_rev, get)
    out: list[dict[str, object]] = []
    for path in sorted(p for p in mirror if any(fnmatch(p, pat) for pat in include)):
        entry, theirs = mirror[path], publisher.get(path)
        if theirs is None or theirs.get("oid") != entry.get("oid"):
            message = f"{path}: the mirror's bytes are not the publisher's at {publisher_rev[:12]}"
            raise IProofsError(ErrorKind.CONFIG, f"{message} (blob ids differ)")
        lfs = entry.get("lfs")
        if isinstance(lfs, Mapping):
            sha, size, storage = str(lfs["oid"]), int(lfs["size"]), "lfs"
            if lfs_pointer_blob(sha, size) != entry["oid"]:
                raise IProofsError(ErrorKind.CONFIG, f"{path}: LFS pointer blob differs")
        else:
            data = get(f"{HUB}/{mirror_repo}/resolve/{mirror_rev}/{path}")
            if git_blob_id(data) != entry["oid"]:
                raise IProofsError(ErrorKind.CONFIG, f"{path}: fetched bytes are not the blob")
            sha, size, storage = hashlib.sha256(data).hexdigest(), len(data), "git"
        out.append({"path": path, "sha256": sha, "bytes": size, "storage": storage,
                    "publisher_blob": str(entry["oid"])})  # fmt: skip
    if not out:
        raise IProofsError(ErrorKind.CONFIG, f"no mirror file matches {list(include)}")
    return out


KV_DTYPES = {"bfloat16": "bfloat16", "float16": "float16", "float32": "float32"}


def shape_of(config: Mapping[str, Any]) -> dict[str, object]:
    """The sizing inputs from a model's config.json (its `text_config` for a multimodal one):
    layers, heads, KV heads, head size and the KV-cache dtype (`kv_cache_scheme` when the
    release quantizes the cache, else the model dtype)."""
    text = config.get("text_config") or config
    if "n_head" in text:  # GPT-2's own key names; no grouped KV heads; no torch_dtype in its
        # config.json, so the transformers default, float32, which its F32 safetensors hold
        heads = int(text["n_head"])
        return {"layers": int(text["n_layer"]), "attention_heads": heads, "kv_heads": heads,
                "head_dim": int(text["n_embd"]) // heads,
                "kv_dtype": KV_DTYPES[str(text.get("torch_dtype") or "float32")]}  # fmt: skip
    heads = int(text["num_attention_heads"])
    head_dim = text.get("head_dim") or int(text["hidden_size"]) // heads
    scheme = (config.get("quantization_config") or {}).get("kv_cache_scheme")
    dtype = "fp8" if scheme else KV_DTYPES[str(text.get("torch_dtype") or config["torch_dtype"])]
    return {"layers": int(text["num_hidden_layers"]), "attention_heads": heads,
            "kv_heads": int(text["num_key_value_heads"]), "head_dim": int(head_dim),
            "kv_dtype": dtype}  # fmt: skip


def vocab_of(config: Mapping[str, Any]) -> int:
    text = config.get("text_config") or config
    return int(text["vocab_size"])


def pin_record(text: str, doc: Mapping[str, Any], include: Sequence[str], get: Get) -> str:
    """The record text with `model.files`, `digest`, `vocab_size` and `shape` written from the
    listings and the mirror's config.json (`iproofs serving pin`). Files the record fetches from
    the publisher (`source: publisher`) are kept as they are. The text above `model:` and the
    record's other fields are kept; the model block is rendered in one fixed layout."""
    model = doc["model"]
    repo, rev = str(model["source"]["repo"]), str(model["revision"])
    pub = doc["publisher"]["release"]
    files = pin_files(repo, rev, str(pub["repo"]), str(pub["revision"]), include, get)
    kept = [f for f in model.get("files") or [] if f.get("source") == "publisher"]
    files += [dict(f) for f in kept if f["path"] not in {g["path"] for g in files}]
    files.sort(key=lambda f: str(f["path"]).encode("utf-8"))
    config = json.loads(get(f"{HUB}/{repo}/resolve/{rev}/config.json"))
    digest = listing_digest((str(f["path"]), str(f["sha256"])) for f in files)
    head = text[: text.index("\nmodel:\n") + 1]
    lic = model["licence"]
    lines = [
        "model:",
        f'  source: {{hub: "{model["source"]["hub"]}", repo: "{repo}"}}',
        f'  revision: "{rev}"',
        "  # generated by `iproofs serving pin` from the two tree listings (RFC-0014 SM-3)",
        "  files:",
    ]
    for f in files:
        extra = f', source: "{f["source"]}"' if f.get("source") else ""
        fields = (
            f'path: "{f["path"]}", sha256: "{f["sha256"]}", bytes: {f["bytes"]}, '
            f'storage: "{f["storage"]}", publisher_blob: "{f["publisher_blob"]}"'
        )
        lines.append(f"    - {{{fields}{extra}}}")
    shape = shape_of(config)
    lines += [
        f'  digest: "{digest}"',
        f'  licence: {{name: "{lic["name"]}", url: "{lic["url"]}", '
        f"gated: {str(lic['gated']).lower()}}}",
        f"  vocab_size: {vocab_of(config)}",
        "  shape: {" + ", ".join(
            f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {v}" for k, v in shape.items()
        ) + "}",
    ]  # fmt: skip
    return head + "\n".join(lines) + "\n"
