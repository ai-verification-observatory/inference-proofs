"""Levels (RFC-0018): the level file, its beacon round and the prompt stream of each rung.

A level file `levels/L<k>.yaml` (schema `level/1`) holds every constant a rule of RFC-0018 names.
Its prompts are `beacon-window/1`: `corpus-window/1` (RFC-0003) seeded by a public randomness
beacon round fetched after the level is frozen (PR-1, PR-2). Each rung draws one stream from that
seed: its slots·N prompts, then its KL windows (PR-3).
"""

import dataclasses
import datetime as dt
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Document, Workload
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry, load_document
from iproofs.workloads import (
    BEACON_WINDOW,
    Tokenizer,
    corpus_window_runs,
    corpus_window_v1,
    load_workload,
)

# drand chains whose round times `round_time` knows: chain hash -> (genesis unix time, period s),
# read from https://api.drand.sh/<hash>/info on 2026-11-10 (quicknet, bls-unchained-g1-rfc9380).
CHAINS = {
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971": (1692803367, 3),
}


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Request(Document):
    prompt_tokens: int
    output_tokens: int
    decoding: str
    ignore_eos: bool
    every_reply_token_checked: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Beacon(Document):
    name: str
    chain_hash: str
    relays: tuple[str, ...]
    round: int | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Prompts(Document):
    generator: str
    corpus_digest: str
    beacon: Beacon


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Sessions(Document):
    slots: int
    attempts_per_slot: int
    cap_usd: float


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Steady(Document):
    group_gap_s: float
    min_later_groups: int
    tolerance: float


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Baseline(Document):
    ladder: tuple[int, ...]
    plateau: float
    warmup_batches: int
    timed_batches: int
    prompts: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Order(Document):
    margin: float


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Engine(Document):
    tool: str
    repo: str
    commit: str | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Fidelity(Document):
    score: str
    test: str
    alpha: float
    exact_up_to: int
    resamples: int
    engine: Engine


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Kl(Document):
    texts: int
    tokens: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Price(Document):
    reference: str
    cost: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class HubSource(Document):
    hub: str
    repo: str
    revision: str | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SourceReference(Document):
    """FI-1: the 16-bit reference from a pinned repository."""

    dtype: str
    source: HubSource


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingReference(Document):
    """FI-1: the 16-bit reference from the serving record's own files."""

    dtype: str
    serving_files: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Control(Document):
    """FI-2: one honest or damaged copy, by recipe."""

    id: str
    kind: str
    recipe: str
    type: str | None = None
    every: int | None = None
    model: str | None = None
    source: HubSource | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Rung(Document):
    id: str
    model: str
    publisher: str
    parameters_total: int
    parameters_active: int
    requests_per_session: int
    workloads: Mapping[str, str]
    serving: str
    reference: SourceReference | ServingReference
    controls: tuple[Control, ...]
    cap_usd: float | None = None

    def session_cap_usd(self, level: "Level") -> float:
        """SE-4: the rung's cap per session, else the level's."""
        return self.cap_usd if self.cap_usd is not None else float(level.sessions.cap_usd)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Security(Document):
    stated: bool
    words: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Limit(Document):
    """CH-5: a check the system's own design makes impossible, in the publisher's words."""

    words: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class LevelSystem(Document):
    security: Security
    model_change: str
    limits: Mapping[str, Limit] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Level(Document):
    """`level/1`, field by field (RFC-0018 §The level file). `frozen` is None in a draft."""

    schema: str
    id: str
    name: str
    frozen: str | None
    request: Request
    prompts: Prompts
    sessions: Sessions
    steady: Steady
    baseline: Baseline
    order: Order
    fidelity: Fidelity
    kl: Kl
    price: Price
    rungs: tuple[Rung, ...]
    systems: Mapping[str, LevelSystem]

    def rung(self, rung_id: str) -> Rung:
        for r in self.rungs:
            if r.id == rung_id:
                return r
        known = ", ".join(r.id for r in self.rungs)
        raise IProofsError(ErrorKind.CONFIG, f"{self.id}: no rung {rung_id!r} (rungs: {known})")


# ---------------------------------------------------------------- files


def level_file(root: Path, level_id: str = "L1") -> Path:
    return root / "levels" / f"{level_id}.yaml"


def beacon_file(root: Path, level_id: str = "L1") -> Path:
    return root / "levels" / f"{level_id}-beacon.json"


def level_digest(path: Path) -> str:
    """Digest of the level file's bytes: the `level.digest` a counted run's manifest names."""
    return file_digest(path)


def _registry(root: Path, registry: SchemaRegistry | None) -> SchemaRegistry:
    return registry or SchemaRegistry.from_tree(root / "schema")


def load_level(
    root: Path, level_id: str = "L1", *, registry: SchemaRegistry | None = None
) -> Level:
    """Load and validate `levels/<id>.yaml` (schema `level/1`)."""
    path = level_file(root, level_id)
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown level {level_id!r}: no {path}")
    schema_id, tree = load_document(path, _registry(root, registry))
    if schema_id != "level/1":
        raise IProofsError(ErrorKind.CONFIG, f"{path}: not a level document ({schema_id})")
    level = Level.from_tree(tree)
    if level.id != level_id:
        raise IProofsError(ErrorKind.CONFIG, f"{path}: id {level.id!r} does not match the name")
    return level


# ---------------------------------------------------------------- prompts (PR-1, PR-3)


def beacon_seed(randomness_hex: str) -> int:
    """PR-1: the first 8 bytes, big-endian, of the round's 32-byte randomness."""
    try:
        data = bytes.fromhex(randomness_hex)
    except ValueError as e:
        raise IProofsError(ErrorKind.CONFIG, f"beacon randomness is not hex: {e}") from e
    if len(data) != 32:
        raise IProofsError(ErrorKind.CONFIG, f"beacon randomness is {len(data)} bytes, not 32")
    return int.from_bytes(data[:8], "big")


def beacon_window_v1(
    texts: list[str], tokenizer: Tokenizer, count: int, L: int, randomness_hex: str
) -> list[list[int]]:
    """Prompt generator `beacon-window/1`: `corpus-window/1` with the beacon seed."""
    return corpus_window_v1(texts, tokenizer, count, L, beacon_seed(randomness_hex))


def stream_runs(level: Level, rung: Rung) -> list[tuple[int, int]]:
    """PR-3: a rung's stream as (count, window length) runs: slots·N prompts, then the KL
    windows, then the serving ladder's prompts (CO-4)."""
    prompts = level.sessions.slots * rung.requests_per_session
    return [
        (prompts, level.request.prompt_tokens),
        (level.kl.texts, level.kl.tokens),
        (level.baseline.prompts, level.request.prompt_tokens),
    ]


def rung_stream(
    texts: list[str], tokenizer: Tokenizer, level: Level, rung: Rung, randomness_hex: str
) -> list[list[int]]:
    """PR-3: one stream from the beacon seed, the rung's prompts first, then its KL windows.
    Its first slots·N windows equal `beacon_window_v1` of that count."""
    runs = stream_runs(level, rung)
    return corpus_window_runs(texts, tokenizer, runs, beacon_seed(randomness_hex))


def rung_prompts(stream: Sequence[list[int]], level: Level, rung: Rung) -> list[list[int]]:
    """The rung's slots·N prompts: what the baseline serves and the fidelity reference answers."""
    count = stream_runs(level, rung)[0][0]
    if len(stream) < count:
        raise IProofsError(ErrorKind.CONFIG, f"stream of {len(stream)} has no {count} prompts")
    return list(stream[:count])


def slot_prompts(prompts: Sequence[list[int]], slot: int, n: int) -> list[list[int]]:
    """Slot k (from 1) proves prompts [(k-1)·n, k·n) of the rung's prompt set."""
    if slot < 1 or n < 1 or slot * n > len(prompts):
        raise IProofsError(
            ErrorKind.CONFIG, f"slot {slot} of {n} prompts is outside a set of {len(prompts)}"
        )
    return list(prompts[(slot - 1) * n : slot * n])


def kl_texts(stream: Sequence[list[int]], level: Level, rung: Rung) -> list[list[int]]:
    """PR-3: the KL windows, after the rung's prompts in the same stream."""
    (prompts, _), (texts, _), _ = stream_runs(level, rung)
    if len(stream) < prompts + texts:
        raise IProofsError(
            ErrorKind.CONFIG, f"stream of {len(stream)} has no {prompts} + {texts} windows"
        )
    return list(stream[prompts : prompts + texts])


def baseline_prompts(stream: Sequence[list[int]], level: Level, rung: Rung) -> list[list[int]]:
    """CO-4: the serving ladder's distinct prompts, after the KL windows in the same stream."""
    (prompts, _), (texts, _), (ladder, _) = stream_runs(level, rung)
    start = prompts + texts
    if len(stream) < start + ladder:
        raise IProofsError(
            ErrorKind.CONFIG, f"stream of {len(stream)} has no {start} + {ladder} windows"
        )
    return list(stream[start : start + ladder])


# ---------------------------------------------------------------- beacon (PR-2)


def first_round_after(chain_hash: str, when: dt.datetime) -> int | None:
    """PR-2: the first round of a known drand chain produced after `when`; None for an
    unknown chain. Round r is produced at genesis + (r - 1) * period."""
    if chain_hash not in CHAINS:
        return None
    genesis, period = CHAINS[chain_hash]
    return int((when.timestamp() - genesis) // period) + 2


def freeze_time(root: Path, level_id: str = "L1") -> dt.datetime | None:
    """PR-2: the commit time of the level file as committed, or None when git cannot say or the
    file has changes not yet committed (it is not frozen in the repository yet)."""
    import subprocess  # noqa: PLC0415

    rel = f"levels/{level_id}.yaml"

    def git(*args: str) -> str:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                             check=True)  # fmt: skip
        return out.stdout.strip()

    try:
        if git("rev-parse", "--is-shallow-repository") == "true":
            return None  # a shallow clone (CI) lacks the history that dates the freeze
        dirty = git("status", "--porcelain", "--", rel)
        stamp = git("log", "-1", "--format=%ct", "--", rel)
    except (OSError, subprocess.CalledProcessError):
        return None
    if dirty or not stamp:
        return None
    return dt.datetime.fromtimestamp(int(stamp), tz=dt.UTC)


def beacon_round(root: Path, level: Level) -> int:
    """PR-2: the round the prompts come from: the level file's own `round` if it names one, else
    the first round after the commit that froze the level file."""
    beacon = level.prompts.beacon
    if beacon.round is not None:
        return beacon.round
    if level.frozen is None:
        raise IProofsError(ErrorKind.CONFIG, f"{level.id} is a draft: freeze it first (PR-2)")
    when = freeze_time(root, level.id)
    if when is None:
        raise IProofsError(ErrorKind.CONFIG, f"levels/{level.id}.yaml is not committed as frozen")
    found = first_round_after(beacon.chain_hash, when)
    if found is None:
        raise IProofsError(ErrorKind.CONFIG, f"no round times known for chain {beacon.chain_hash}")
    return found


def round_time(chain_hash: str, round_: int) -> dt.datetime | None:
    """The time a round of a known drand chain is produced; None for an unknown chain."""
    if chain_hash not in CHAINS:
        return None
    genesis, period = CHAINS[chain_hash]
    return dt.datetime.fromtimestamp(genesis + (round_ - 1) * period, tz=dt.UTC)


def beacon_problems(record: Mapping[str, object]) -> list[str]:
    """The checks the harness makes on one round: hex fields, and randomness = sha256 of the
    signature bytes. The BLS signature is not checked here (PR-2)."""
    signature, randomness = record.get("signature"), record.get("randomness")
    if not isinstance(signature, str) or not isinstance(randomness, str):
        return ["signature and randomness must be hex strings"]
    try:
        digest = hashlib.sha256(bytes.fromhex(signature)).hexdigest()
    except ValueError:
        return ["signature is not hex"]
    if digest != randomness.lower():
        return [f"randomness {randomness} is not sha256(signature) {digest}"]
    return []


def fetch_beacon(
    round_: int,
    relays: Sequence[str],
    get: Callable[[str], bytes],
    *,
    chain_hash: str,
    fetched: dt.date | None = None,
) -> dict[str, object]:
    """PR-2: fetch `/{chain_hash}/public/{round}` from every relay (at least two), require each
    answer to be that round with randomness = sha256(signature) and all answers equal; return
    the `beacon/1` record. Any failure raises; nothing is written."""
    if len(relays) < 2:
        raise IProofsError(ErrorKind.CONFIG, "the beacon is read from at least two relays")
    answers = []
    for relay in relays:
        url = f"{relay.rstrip('/')}/{chain_hash}/public/{round_}"
        try:
            answer = json.loads(get(url))
        except ValueError as e:
            raise IProofsError(ErrorKind.FETCH, f"{url}: not JSON") from e
        if not isinstance(answer, dict) or answer.get("round") != round_:
            raise IProofsError(ErrorKind.FETCH, f"{url}: the answer is not round {round_}")
        problems = beacon_problems(answer)
        if problems:
            raise IProofsError(ErrorKind.INTEGRITY, f"{url}: {problems[0]}")
        answers.append((answer["randomness"].lower(), answer["signature"].lower()))
    if len(set(answers)) != 1:
        raise IProofsError(ErrorKind.INTEGRITY, f"relays disagree on round {round_}: {relays}")
    randomness, signature = answers[0]
    return {
        "schema": "beacon/1",
        "chain_hash": chain_hash,
        "round": round_,
        "randomness": randomness,
        "signature": signature,
        "relays": list(relays),
        "fetched": (fetched or dt.datetime.now(dt.UTC).date()).isoformat(),
    }


def beacon_record_problems(record: Mapping[str, object], level: Level) -> list[str]:
    """A stored record against the level: its chain, its round once the level names one, and
    the sha256 rule."""
    beacon = level.prompts.beacon
    problems = [f"beacon record: {p}" for p in beacon_problems(record)]
    if record.get("chain_hash") != beacon.chain_hash:
        problems.append(f"beacon record chain {record.get('chain_hash')} is not the level's")
    if beacon.round is not None and record.get("round") != beacon.round:
        problems.append(f"beacon record round {record.get('round')} is not {beacon.round}")
    return problems


def load_beacon(
    root: Path, level: Level, *, registry: SchemaRegistry | None = None
) -> dict[str, object]:
    """The stored `levels/<id>-beacon.json`, validated and checked against the level."""
    path = beacon_file(root, level.id)
    if not path.is_file():
        raise IProofsError(
            ErrorKind.CONFIG, f"no {path.name}; run `iproofs level beacon` once the round is out"
        )
    schema_id, tree = load_document(path, _registry(root, registry))
    if schema_id != "beacon/1":
        raise IProofsError(ErrorKind.CONFIG, f"{path}: not a beacon record ({schema_id})")
    problems = beacon_record_problems(tree, level)
    if problems:
        raise IProofsError(ErrorKind.INTEGRITY, "\n".join(f"{path}: {p}" for p in problems))
    return tree


# ---------------------------------------------------------------- check


def _frozen_problems(level: Level) -> list[str]:
    """Every value a frozen level needs."""
    problems = []
    if level.frozen is None:
        problems.append("frozen is null: the level is a draft")
    if level.fidelity.engine.commit is None:
        problems.append("fidelity.engine.commit is null (FI-1)")
    for i, rung in enumerate(level.rungs):
        ref = rung.reference
        if isinstance(ref, SourceReference) and ref.source.revision is None:
            problems.append(f"rungs[{i}] {rung.id}: reference.source.revision is null")
        for control in rung.controls:
            if control.source is not None and control.source.revision is None:
                problems.append(f"rungs[{i}] {rung.id}: control {control.id} revision is null")
    return problems


def _tokenizer_sha(wl: Workload) -> str | None:
    if wl.model.tokenizer_source is not None:
        return wl.model.tokenizer_source.file.sha256
    return next((f.sha256 for f in wl.model.files if f.path == wl.model.tokenizer_file), None)


def _workload_problems(wl: Workload, system: str, level: Level, rung: Rung) -> list[str]:
    where = f"rung {rung.id}, {system}: workload {wl.id}"
    pairs = [
        ("prompts.generator", wl.prompts.generator, level.prompts.generator),
        ("prompts.corpus_digest", wl.prompts.corpus_digest, level.prompts.corpus_digest),
        ("prompts.count", wl.prompts.count, rung.requests_per_session),
        ("shape.prompt_tokens", wl.shape.prompt_tokens, level.request.prompt_tokens),
        ("shape.output_tokens", wl.shape.output_tokens, level.request.output_tokens),
        ("decoding.rule", wl.decoding.rule, level.request.decoding),
    ]
    problems = [
        f"{where}: {field} {got!r} != {want!r}" for field, got, want in pairs if got != want
    ]
    if system not in wl.systems:
        problems.append(f"{where}: systems does not name {system}")
    return problems


def _round_problems(root: Path, level: Level) -> list[str]:
    """PR-2: a stored beacon record of a frozen level holds the first round after the commit
    that froze the level file."""
    when = freeze_time(root, level.id)
    path = beacon_file(root, level.id)
    if when is None or not path.is_file():
        return []
    rule = first_round_after(level.prompts.beacon.chain_hash, when)
    stored = json.loads(path.read_text()).get("round")
    if rule is not None and stored != rule:
        return [f"{path.name} holds round {stored}; the first round after the freezing commit is "
                f"{rule} (PR-2)"]  # fmt: skip
    return []


def check_level(
    root: Path, level: Level, *, frozen: bool = False, registry: SchemaRegistry | None = None
) -> list[str]:
    """Rules the schema cannot express, across the level, its workloads, serving records,
    reference file and beacon record; with `frozen`, also every value a frozen level needs."""
    reg = _registry(root, registry)
    problems = _frozen_problems(level) if frozen else []
    if frozen and level.frozen is not None and level.prompts.beacon.round is None:
        problems += _round_problems(root, level)
    totals = [r.parameters_total for r in level.rungs]
    if totals != sorted(totals, reverse=True) or len(set(totals)) != len(totals):
        problems.append("rungs are not in strictly decreasing parameters_total (OR-6)")
    if len({r.id for r in level.rungs}) != len(level.rungs):
        problems.append("rung ids repeat")
    b = level.baseline
    if b.prompts < (b.warmup_batches + b.timed_batches) * max(b.ladder):
        problems.append("baseline.prompts is below (warmup + timed) x the largest rung (CO-4)")
    reference = root / level.price.reference
    if not reference.is_file():
        problems.append(f"price.reference: no {level.price.reference}")
    else:
        _, ref_tree = load_document(reference, reg)
        costs = ref_tree.get("costs")
        if not isinstance(costs, dict) or level.price.cost not in costs:
            problems.append(f"price.cost: {level.price.reference} has no costs.{level.price.cost}")
    for rung in level.rungs:
        problems += _rung_problems(root, level, rung, reg)
    path = beacon_file(root, level.id)
    if path.is_file():
        try:
            load_beacon(root, level, registry=reg)
        except IProofsError as e:
            problems.append(e.message)
    elif frozen and level.prompts.beacon.round is not None:
        problems.append(f"no {path.name}: fetch the round with `iproofs level beacon`")
    return problems


def _rung_problems(root: Path, level: Level, rung: Rung, registry: SchemaRegistry) -> list[str]:
    problems = []
    if rung.parameters_active > rung.parameters_total:
        problems.append(f"rung {rung.id}: parameters_active > parameters_total")
    ids = [c.id for c in rung.controls]
    if len(set(ids)) != len(ids):
        problems.append(f"rung {rung.id}: control ids repeat")
    for kind in ("honest", "damaged"):
        if not any(c.kind == kind for c in rung.controls):
            problems.append(f"rung {rung.id}: no {kind} control (FI-5)")
    if not (root / "workloads" / "serving" / f"{rung.serving}.yaml").is_file():
        problems.append(f"rung {rung.id}: no serving record workloads/serving/{rung.serving}.yaml")
    tokenizers = set()
    for system, workload_id in sorted(rung.workloads.items()):
        if system not in level.systems:
            problems.append(f"rung {rung.id}: system {system} has no entry under systems")
        try:
            wl = load_workload(workload_id, root=root, registry=registry)
        except IProofsError as e:
            problems.append(f"rung {rung.id}, {system}: {e.message}")
            continue
        problems += _workload_problems(wl, system, level, rung)
        tokenizers.add(_tokenizer_sha(wl))
    if len(tokenizers) > 1:
        problems.append(f"rung {rung.id}: its workloads name different tokenizer files")
    return problems


def rung_tokenizer_workload(root: Path, level: Level, rung: Rung) -> Workload:
    """The workload whose tokenizer encodes the rung's stream (the first by system id; the
    check requires every workload of a rung to share one tokenizer file)."""
    if not rung.workloads:
        raise IProofsError(ErrorKind.CONFIG, f"rung {rung.id} names no workload, so no tokenizer")
    system = sorted(rung.workloads)[0]
    workload = load_workload(rung.workloads[system], root=root, registry=_registry(root, None))
    if workload.prompts.generator != BEACON_WINDOW:
        raise IProofsError(ErrorKind.CONFIG, f"{workload.id}: generator is not {BEACON_WINDOW}")
    return workload
