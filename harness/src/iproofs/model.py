"""Frozen dataclasses for every document: parse, validate, construct (RFC-0012 §Python loading).

Construction is generic: field types drive the conversion. Nested objects become nested
dataclasses, arrays become tuples, open maps become read-only mappings, enums become their
StrEnum. `from_tree` runs only on trees that `load` has validated.
"""

import dataclasses
import types
import typing
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, Union, get_args, get_origin, get_type_hints

from iproofs.errors import ErrorKind, Failure, IProofsError
from iproofs.quantity import Grade, NullReason, Scope, ScopeMapping, SourceKind, Tier, Unit
from iproofs.schema import SchemaRegistry, load_document


def _convert(tp: Any, value: object) -> object:  # noqa: PLR0911 (one return per type kind)
    if value is None:
        return None
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        options = [a for a in get_args(tp) if a is not type(None)]
        if len(options) == 1:
            return _convert(options[0], value)
        if not isinstance(value, dict):
            return value  # a primitive union such as `bool | str` ("not stated")
        return _convert(_pick_dataclass(options, value), value)
    if origin is tuple:
        item = get_args(tp)[0]
        assert isinstance(value, list)
        return tuple(_convert(item, v) for v in value)
    if origin in (Mapping, typing.Mapping):
        item = get_args(tp)[1]
        assert isinstance(value, dict)
        return types.MappingProxyType({k: _convert(item, v) for k, v in value.items()})
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        assert isinstance(value, dict)
        return _build(tp, value)
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        assert isinstance(value, str)
        return tp(value)
    return value


def _pick_dataclass(options: list[Any], value: object) -> Any:
    """Choose the one dataclass whose fields fit the keys (for example Quantity | Statistic)."""
    assert isinstance(value, dict)
    keys = set(value)
    fitting = [
        c for c in options
        if dataclasses.is_dataclass(c)
        and keys <= {f.name for f in dataclasses.fields(c)}
        and {f.name for f in dataclasses.fields(c) if f.default is dataclasses.MISSING} <= keys
    ]  # fmt: skip
    if len(fitting) != 1:
        raise TypeError(f"cannot choose among {options} for keys {sorted(keys)}")
    return fitting[0]


def _build(cls: type[Any], tree: Mapping[str, object]) -> Any:
    hints = get_type_hints(cls)
    kwargs = {f.name: _convert(hints[f.name], tree[f.name])
              for f in dataclasses.fields(cls) if f.name in tree}  # fmt: skip
    return cls(**kwargs)


class Document:
    """Base for every model built from a validated tree."""

    __slots__ = ()

    @classmethod
    def from_tree(cls, tree: Mapping[str, object]) -> Self:
        built: Self = _build(cls, tree)
        return built


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Quality(Document):
    degraded: bool | None = None
    precision_substituted: bool | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Source(Document):
    kind: SourceKind
    ref: str
    inputs: tuple[str, ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Pairs(Document):
    """RFC-0004 INV-DERIVE-9: the range of an overhead over every pair of repetitions."""

    n_system: int
    n_serving: int
    min: float | None
    max: float | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Quantity(Document):
    value: float | None
    unit: Unit
    scope: Scope | None
    grade: Grade
    tier: Tier
    source: Source
    null_reason: NullReason | None
    upstream_scope: str | None = None
    upstream_grade: str | None = None
    mapping: ScopeMapping | None = None
    quality: Quality | None = None
    note: str | None = None
    pairs: Pairs | None = None  # RFC-0004 INV-DERIVE-9, overheads only


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Stats(Document):
    n: int
    n_failed: int
    mean: float | None
    stdev: float | None
    min: float | None
    max: float | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Statistic(Quantity):
    stats: Stats


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class WorkloadRef(Document):
    id: str
    version: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ClaimRef(Document):
    system: str
    configuration: str
    card_version: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Replaces(Document):
    run_id: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RawSteps(Document):
    info: Mapping[str, Quantity] | None = None
    setup: Mapping[str, Quantity] | None = None
    commit: Mapping[str, Quantity] | None = None
    prove: Mapping[str, Quantity] | None = None
    verify: Mapping[str, Quantity] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Event(Document):
    event: str
    mono_ns: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Agreement(Document):
    agree: int
    disagree: int
    first_disagreement: int | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProofResult(Document):
    proof_id: str
    release_mono_ns: int | None
    tokens_covered: int
    verdict: str | None
    request_index: int | None = None
    claimed_output: tuple[int, ...] | None = None
    agreement: Agreement | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RunInputs(Document):
    """The workload record's asserted inputs, copied at run time (RFC-0003 WB-4)."""

    active_parameters_per_token: Quantity
    weight_bits: Quantity
    gpu_count: Quantity | None = None  # RFC-0004 INV-DERIVE-8; absent in runs stored before


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Run(Document):
    schema: str
    run_id: str
    release: str
    system: str
    workload: WorkloadRef
    profile: str
    repetition: int
    control: bool
    system_kind: str
    claim: ClaimRef | None
    status: str
    failure: Failure | None
    replaces: Replaces | None
    raw: RawSteps
    adapter_phases: Mapping[str, Quantity]
    metrics: Mapping[str, Quantity | Statistic]
    events: tuple[Event, ...]
    proofs: tuple[ProofResult, ...]
    warnings: tuple[str, ...]
    inputs: RunInputs | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class HarnessRecord(Document):
    version: str
    git_commit: str
    git_dirty: bool
    lock_digest: str
    nonconforming: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RunnerRecord(Document):
    handle: str
    organisation: str
    affiliated_systems: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Upstream(Document):
    repo: str
    commit: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ImageRef(Document):
    ref: str
    digest_kind: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ImageInput(Document):
    name: str
    url: str
    digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SystemRecord(Document):
    name: str
    system_manifest_digest: str
    claim_digest: str | None
    upstream: Upstream | None
    adapter_commit: str
    adapter_dirty: bool
    image: ImageRef
    image_inputs: tuple[ImageInput, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelRecord(Document):
    source: str
    revision: str
    digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class WorkloadRecord(Document):
    id: str
    version: int
    file_digest: str
    model: ModelRecord
    corpus_digest: str
    prompt_seed: str
    prompt_set_digest: str
    load_point: str | None = None  # RFC-0015 SRV-1 (serving runs)
    batch_size_run: int | None = None
    batches_per_session_run: int | None = None
    prompt_count_run: int | None = None
    prompt_prefix_digest: str | None = None  # RFC-0015 SRV-8
    sizing_capture: bool | None = None  # RFC-0015 SRV-1: joins no overhead
    steady_rule: str | None = None  # RFC-0004 INV-SCOPE-5 (absent: first-proof boundary)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProfileRecord(Document):
    prover: str
    verifier: str
    verifier_host: str
    reference_file: str
    reference_digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SelfTestCheck(Document):
    name: str
    passed: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SelfTest(Document):
    passed: bool
    checks: tuple[SelfTestCheck, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Command(Document):
    step: str
    argv: tuple[str, ...]
    cpuset: str
    mems: str
    gpus: str | None
    network: str
    started_at: str
    exit_code: int | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class FileRecord(Document):
    name: str
    digest: str
    bytes: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Commitment(Document):
    commitment_id: str
    verifier_files: tuple[FileRecord, ...]
    prover_files: tuple[FileRecord, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProofRecord(Document):
    proof_id: str
    digest: str
    parts: tuple[FileRecord, ...]
    archive: str | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Manifest(Document):
    schema: str
    run_id: str
    release: str
    control: bool
    harness: HarnessRecord
    runner: RunnerRecord
    claim: ClaimRef | None
    provider: str
    system: SystemRecord
    workload: WorkloadRecord
    profile: ProfileRecord
    machine: Mapping[str, object]  # RFC-0006 record; schema $defs/machine fixes its fields
    self_test: SelfTest
    commands: tuple[Command, ...]
    commitment: Commitment | None
    proofs: tuple[ProofRecord, ...]
    warnings: tuple[str, ...]
    machine_verifier: Mapping[str, object] | None = None  # verifier_host: separate
    prompts_from: str | None = None  # RFC-0015 RC-1
    engine: Mapping[str, object] | None = None  # RFC-0015 SRV-6: name, version, image, interface
    serving_model: Mapping[str, object] | None = None  # RFC-0015 SRV-6: the serving record


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseCard(Document):
    system: str
    configuration: str
    card_version: int
    path: str
    digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SupersededRun(Document):
    run_id: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Release(Document):
    schema: str
    release: str
    reference_file: str
    rfc_commit: str
    harness_version: str
    runs: tuple[str, ...]
    superseded_runs: tuple[SupersededRun, ...]
    claim_cards: tuple[ReleaseCard, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Ineligible(Document):
    run_id: str
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class IndexConfiguration(Document):
    system: str
    workload: WorkloadRef
    profile: str
    configuration: str | None
    runs: tuple[str, ...]
    ineligible: tuple[Ineligible, ...]
    insufficient_repetitions: bool
    statistics: Mapping[str, Quantity | Statistic]
    load_point: str | None = None  # RFC-0015 SRV-1 (absent: matched)
    overhead_conditions: Mapping[str, object] | None = None  # RFC-0004 INV-DERIVE-9
    overhead_headline: Mapping[str, object] | None = None  # RFC-0004 INV-DERIVE-10
    steady_boundary: str | None = None  # RFC-0004 INV-SCOPE-5 label of earlier runs (APP-1)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class OutcomeCounts(Document):
    rejected: int
    accepted: int
    no_verdict: int
    invalid_call: int
    void: int
    not_applicable: int
    error: int
    prover_failed: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class OutsideExpected(Document):
    control_id: str
    run_id: str
    outcome: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ControlSummary(Document):
    system: str
    workload: WorkloadRef
    profile: str
    counts: OutcomeCounts
    outside_expected: tuple[OutsideExpected, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class TargetResult(Document):
    target: str
    system: str
    workload: WorkloadRef
    profile: str
    result: str
    reason: str | None
    mean: Quantity | Statistic | None
    least_favourable: Quantity | Statistic | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceRecord(Document):
    file: str
    digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseIndex(Document):
    schema: str
    release: str
    configurations: tuple[IndexConfiguration, ...]
    controls: tuple[ControlSummary, ...]
    targets: tuple[TargetResult, ...]
    claim_cards: tuple[ReleaseCard, ...]
    reference: ReferenceRecord
    inputs_digest: str
    freeze_derived: Mapping[str, Mapping[str, Quantity | Statistic]] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Author(Document):
    name: str
    affiliation: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Target(Document):
    schema: str
    id: str
    author: Author
    date: str
    metric: str
    comparator: str
    threshold: Quantity
    claim_class: str
    rationale: str
    applies_to: Mapping[str, object] | None = None
    profile: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SecurityNotion(Document):
    kind: str
    verifier: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SecurityModel(Document):
    assumption: str
    adversary: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Security(Document):
    notion: SecurityNotion
    level: str
    model: SecurityModel
    setup: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ZeroKnowledge(Document):
    claimed: bool | str  # bool, or the literal "not stated"
    hidden: str
    not_hidden: str
    status: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CoveragePolicy(Document):
    kind: str
    detail: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Coverage(Document):
    phase: str
    unit: str
    tokens_covered: str
    operations: str
    policy: CoveragePolicy


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class BindingEdge(Document):
    edge: str
    state: str
    switch: str | None
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Binding(Document):
    edges: tuple[BindingEdge, ...] | None = None
    statement: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class QualityGap(Document):
    metric: str
    value: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Review(Document):
    handle: str
    organisation: str
    date: str
    card_version: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ClaimCard(Document):
    schema: str
    system: str
    configuration: str
    card_version: int
    upstream: Upstream
    claim_class: str
    relation: str
    security: Security
    zero_knowledge: ZeroKnowledge
    assumptions: tuple[str, ...]
    coverage: Coverage
    binding: Binding | str  # or the literal "not stated"
    residual: tuple[str, ...]
    availability: str
    sources: Mapping[str, str]
    reviewed_by: tuple[Review, ...]
    relation_formal: str | None = None
    assumptions_not_stated: bool | None = None
    quality_gap: tuple[QualityGap, ...] | None = None
    forbidden_flags: tuple[str, ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelSource(Document):
    hub: str
    repo: str
    path: str | None = None  # hub "repository": toy test data inside this repository


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelFile(Document):
    path: str
    sha256: str
    bytes: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class TokenizerSource(Document):
    """The tokenizer file alone, from a second pinned repository (RFC-0003)."""

    hub: str
    repo: str
    revision: str
    file: ModelFile


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Licence(Document):
    name: str
    url: str
    gated: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Parameters(Document):
    total: int
    active_per_token: int
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelSpec(Document):
    source: ModelSource
    revision: str
    files: tuple[ModelFile, ...]
    digest: str
    licence: Licence
    parameters: Parameters
    tokenizer_file: str
    vocab_size: int
    tokenizer_source: TokenizerSource | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class WeightBits(Document):
    """Bits per weight of the precision as proved, an asserted input (RFC-0003 §Weight bits).
    `bits` is typed for a `stated` basis (WB-1) and for a `computed` one, whose `method`
    `fetch-model` reruns on the listed files (WB-5); for `file_size` the loader computes it
    (WB-2)."""

    basis: str  # "stated", "file_size" or "computed"
    covers: str  # "all" or "part" of the active weights (WB-1)
    source: str
    bits: float | None = None
    files: tuple[str, ...] | None = None
    method: str | None = None  # `computed` only: "gguf-active-mean/1"
    note: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Precision(Document):
    served: str
    proved: str
    alternatives: tuple[str, ...] | None = None
    weight_bits: WeightBits | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class LengthRule(Document):
    prompt_tokens: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Prompts(Document):
    generator: str
    corpus_digest: str
    count: int
    length_rule: LengthRule


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Shape(Document):
    prompt_tokens: int
    output_tokens: int
    batch_size: int
    batches_per_session: int
    context_window: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Decoding(Document):
    rule: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Workload(Document):
    schema: str
    id: str
    version: int
    division: str
    model: ModelSpec
    precision: Precision
    prompts: Prompts
    shape: Shape
    decoding: Decoding
    phase: str
    systems: tuple[str, ...]
    claim_class: str | None = None
    notes: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Normalisation(Document):
    unicode: str
    newlines: str
    strip_bom: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CorpusText(Document):
    id: str
    source_url: str
    licence: str
    sha256: str
    bytes: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Corpus(Document):
    schema: str
    normalisation: Normalisation
    texts: tuple[CorpusText, ...]


Verdict = Literal["accept", "reject", "no_verdict", "invalid_call"]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class AdapterJob(Document):
    """/io/job.json (RFC-0005); fields beyond the common ones depend on `subcommand`."""

    schema: str
    contract: str
    subcommand: str
    run_id: str
    workload: WorkloadRef
    shape: Shape
    control: bool
    model_dir: str | None = None
    commitment_id: str | None = None
    prover_files: tuple[str, ...] | None = None
    prompts_file: str | None = None
    batch_size: int | None = None
    batches: int | None = None
    control_flags: tuple[str, ...] | None = None
    verifier_files: tuple[str, ...] | None = None
    request: tuple[int, ...] | None = None
    claimed_output: tuple[int, ...] | None = None
    proof_dir: str | None = None
    claims_file: str | None = None
    load_point: str | None = None  # RFC-0015 SRV-1 (production serving)
    gpus: int | None = None  # RFC-0015 SRV-6


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Phase(Document):
    name: str
    seconds: float


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Sizes(Document):
    verifier_bytes: int
    prover_bytes: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProofEntry(Document):
    proof_id: str
    request_index: int
    parts: tuple[str, ...]
    claimed_output: tuple[int, ...]
    tokens_covered: int | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CommandLine(Document):
    """One line of /io/commands.jsonl (RFC-0005 §Command log)."""

    argv: tuple[str, ...]
    cwd: str
    started_mono_ns: int
    exit_code: int | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class AdapterOut(Document):
    """/io/out.json (RFC-0005); fields beyond the common ones depend on `subcommand`."""

    schema: str
    contract: str
    subcommand: str
    phases: tuple[Phase, ...]
    warnings: tuple[str, ...]
    system: str | None = None
    upstream_commit: str | None = None
    image_inputs: tuple[ImageInput, ...] | None = None
    workloads: tuple[str, ...] | None = None
    profile: str | None = None
    contract_versions: tuple[str, ...] | None = None
    ready: bool | None = None
    log_files: tuple[str, ...] | None = None
    commitment_id: str | None = None
    verifier_files: tuple[str, ...] | None = None
    prover_files: tuple[str, ...] | None = None
    sizes: Sizes | None = None
    proofs: tuple[ProofEntry, ...] | None = None
    binding_report: str | None = None
    verdict: Verdict | None = None
    policy: str | None = None
    raw_exit_code: int | None = None
    raw_last_line: str | None = None
    seconds: float | None = None
    adapter_commit: str | None = None  # info, RFC-0014 B6
    adapter_dirty: bool | None = None


# RFC-0005 §system.yaml default wall limits per step, in seconds (targets, not measurements).
DEFAULT_TIMEOUTS_S = {"info": 60.0, "setup": 3600.0, "commit": 14400.0, "prove": 43200.0,
                      "verify": 3600.0}  # fmt: skip


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class UpstreamSpec(Document):
    repo: str
    url: str
    commit: str
    tag: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ImageSpec(Document):
    repository: str
    digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Engine(Document):
    name: str
    version: str
    image: str
    commit: str | None = None  # RFC-0015 Q1: the source commit (the image's VLLM_BUILD_COMMIT)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Maintainer(Document):
    handle: str
    organisation: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PrecisionSubstitution(Document):
    reason: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceWorkload(Document):
    id: str
    precision_used: str
    precision_substitution: PrecisionSubstitution | None
    engine_args: tuple[str, ...]
    load_point: str | None = None  # RFC-0015 SRV-1, serve role only: matched | high
    gpus: int | None = None  # RFC-0015 SRV-6: the serving profile's GPU count
    batch_size: int | None = None  # RFC-0015 SRV-1: the high-load batch
    batches_per_session_run: int | None = None  # RFC-0015 SRV-1: a lengthened session


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PartNotRead(Document):
    part: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class VerifyReads(Document):
    """RFC-0008 §Parts the verifier reads, when some part is not read."""

    read: tuple[str, ...]
    not_read: tuple[PartNotRead, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProofsSpec(Document):
    granularity: str
    tokens_covered: str
    steady_boundary: str
    steady_approximate: bool
    verify_reads: str | VerifyReads | None = None  # "all", or absent: every part is read


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Timeouts(Document):
    info: float | None = None
    setup: float | None = None
    commit: float | None = None
    prove: float | None = None
    verify: float | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class System(Document):
    schema: str
    name: str
    kind: str
    contract: str
    workloads: tuple[str | ReferenceWorkload, ...]
    deterministic_proofs: bool
    incremental_proofs: bool
    forbidden_flags: tuple[str, ...]
    upstream: UpstreamSpec | None = None
    image: ImageSpec | None = None
    reference_role: str | None = None
    engine: Engine | None = None
    maintainers: tuple[Maintainer, ...] | None = None
    profile: str | None = None
    max_proof_parts: int | None = None
    max_proof_bytes: int | None = None
    proofs: ProofsSpec | None = None
    timeouts_s: Timeouts | None = None

    def timeout(self, step: str) -> float:
        """Wall limit for a step: the declared value, else the RFC-0005 default."""
        declared = getattr(self.timeouts_s, step, None) if self.timeouts_s else None
        return float(declared) if declared is not None else DEFAULT_TIMEOUTS_S[step]

    def workload_ids(self) -> tuple[str, ...]:
        return tuple(w if isinstance(w, str) else w.id for w in self.workloads)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SystemControl(Document):
    id: str
    kind: str
    expected: tuple[str, ...]
    description: str | None = None
    source: str | None = None
    control_flags: tuple[str, ...] | None = None
    requires_unbound_edge: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SystemControls(Document):
    schema: str
    controls: tuple[SystemControl, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class GpuSpec(Document):
    model: str
    form_factor: str
    count: int
    memory_mib_min: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProverCpu(Document):
    logical_cpus_on_gpu_numa_node: int
    logical_cpus_total_min: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Disk(Document):
    type: str
    free_gib_min: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class OsSpec(Document):
    id: str
    version_id: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ContainerRuntime(Document):
    docker_engine_min: str
    nvidia_container_toolkit_min: str
    cgroup_driver: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class HostedRuntime(Document):
    """RFC-0006 §Hosted execution: the provider starts the adapter image, the harness runs in it."""

    kind: Literal["hosted"]
    cgroup_version: Literal["2"]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ProverProfile(Document):
    kind: str
    gpu: GpuSpec | None
    cpu: ProverCpu
    host_memory_gib_min: int
    disk: Disk
    os: OsSpec
    kernel_min: str
    driver: str
    container_runtime: ContainerRuntime | HostedRuntime
    cost: str | None = None  # a basis of `costs` (RFC-0006 C7); None: the release's `cost`

    @property
    def serving(self) -> bool:
        """RFC-0006 R6: a serving profile, for `reference_role: serve` systems only."""
        return self.kind == "serving"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingProfile(ProverProfile):
    """RFC-0006 R6: a profile of `kind: serving`, binding `gpu.count` GPUs for production
    serving (RFC-0015 SRV-6); its rows divide only against the prover profiles it pairs with."""

    gpu: GpuSpec
    pairs_with: tuple[str, ...]
    shm_gib_min: int | None = None  # RFC-0006 PC-SHM


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class VerifierCpu(Document):
    logical_cpus: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Emulation(Document):
    allowed_on: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class VerifierProfile(Document):
    kind: str
    gpu: None
    cpu: VerifierCpu
    host_memory_gib: int
    emulation: Emulation


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PriceReading(Document):
    provider: str
    url: str
    offer: str
    list_price_usd_per_hour: float
    gpus: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Cost(Document):
    price_per_gpu_hour_usd: Quantity
    basis: str
    providers: tuple[str, ...]
    date: str
    priced: tuple[str, ...]
    not_priced: tuple[str, ...]
    readings: tuple[PriceReading, ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceFile(Document):
    schema: str
    release: str
    profiles: Mapping[str, ProverProfile | ServingProfile | VerifierProfile]
    cost: Cost
    costs: Mapping[str, Cost] | None = None  # RFC-0006 C7: bases of GPU models priced apart

    def price_pointer(self, profile: str) -> str:
        """The JSON pointer of the price that costs a row on `profile` (RFC-0006 C1, C7)."""
        found = self.profiles.get(profile)
        basis = found.cost if isinstance(found, ProverProfile) else None
        if basis is None:
            return "/cost/price_per_gpu_hour_usd"
        if basis not in (self.costs or {}):
            raise IProofsError(
                ErrorKind.CONFIG, f"profile {profile} names cost basis {basis!r}, not in `costs`"
            )
        return f"/costs/{basis}/price_per_gpu_hour_usd"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Twin(Document):
    verdict: str
    raw_exit_code: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Trial(Document):
    seed_index: int
    mutation: Mapping[str, object]
    verdict: str | None
    outcome: str
    raw_exit_code: int | None
    raw_last_line: str
    seconds: float | None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ControlResult(Document):
    id: str
    side: str
    source: str
    expected: tuple[str, ...]
    twin: Twin | None
    trials: tuple[Trial, ...]
    outcome: str
    passed: bool | None
    note: str | None
    parts_not_read: tuple[PartNotRead, ...] | None = None  # C5, C6, C8 (RFC-0008 READ-4)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PerturbedCommitment(Document):
    commitment_id: str
    model_digest: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ControlSummaryCounts(Document):
    run: int
    passed: int
    rejected: int
    accepted: int
    no_verdict: int
    invalid_call: int
    void: int
    not_applicable: int
    error: int
    prover_failed: int


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Controls(Document):
    schema: str
    run_id: str
    control_seed: str
    image: str
    verifier_profile: str
    perturbed_commitment: PerturbedCommitment | None
    controls: tuple[ControlResult, ...]
    summary: ControlSummaryCounts
    disclosure_pending: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ControlsSeed(Document):
    """`controls-seed/1`, the one seed of a run's split suite (RFC-0008 SPLIT-1)."""

    schema: str
    run_id: str
    run_manifest_digest: str
    control_seed: str
    drawn_at: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PartHost(Document):
    """The host one part of a split suite ran on (RFC-0008 SPLIT-4)."""

    machine: Mapping[str, object]  # RFC-0006 record; schema manifest $defs/machine
    nonconforming: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ControlsPart(Document):
    """`controls-part/1`, one part of a suite split across hosts (RFC-0008 §Split suites)."""

    schema: str
    run_id: str
    run_manifest_digest: str
    control_seed: str
    seed_record_digest: str
    suite: tuple[str, ...]
    only: tuple[str, ...]
    image: str
    verifier_profile: str
    profile: str
    verifier_cpus: int
    perturbed_commitment: PerturbedCommitment | None
    harness_version: str
    harness_commit: str
    harness_dirty: bool
    host: PartHost
    controls: tuple[ControlResult, ...]


# Schema location -> model class. The drift test walks this table and requires every
# document schema in the tree to appear here.
@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ExternalFigure(Document):
    id: str  # the upstream's own name for the figure
    metric: str
    workload: str | None
    quantity: Quantity  # grade external, tier reported (RFC-0004 §Mapping from upstream scopes)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class External(Document):
    """`external/1`: upstream figures of one system, never mixed with measured inputs."""

    schema: str
    system: str
    upstream: Upstream
    figures: tuple[ExternalFigure, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class PerturbedCommitmentRecord(Document):
    """`perturbed-commitment/1`, the C3 and P1 commitment of one workload (RFC-0008)."""

    schema: str
    release: str
    system: str
    workload: Mapping[str, object]
    source_model_digest: str
    model_digest: str
    perturbation: Mapping[str, object]
    commitment: Mapping[str, object]
    image: str
    harness_version: str


# ---------------------------------------------------------------- site-facts/1 (RFC-0009 §Site)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SiteInfo(Document):
    licence: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelFacts(Document):
    name: str
    precision_words: Mapping[str, str] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class LicenceFacts(Document):
    name: str
    url: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class StatusFacts(Document):
    state: str
    last_push: str | None = None
    source: str | None = None
    retrieved: str | None = None
    quote: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RowFacts(Document):
    name: str
    technique: str | None = None
    kind_words: str | None = None
    models: tuple[str, ...] | None = None
    code: str | None = None
    licence: LicenceFacts | None = None
    status: StatusFacts | None = None
    overview_workload: str | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SiteFacts(Document):
    """`site-facts/1`, the display facts no harness record holds (`web/_data/facts.json`)."""

    schema: str
    site: SiteInfo
    gpus: Mapping[str, str]
    models: Mapping[str, ModelFacts]
    rows: Mapping[str, RowFacts]


# ---------------------------------------------------------------- criteria/1 (RFC-0016)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CriteriaState(Document):
    word: str
    meaning: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CriteriaProperty(Document):
    id: str
    name: str
    question: str
    not_here: str
    rules: Mapping[str, str]
    card_fields: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CriteriaRow(Document):
    """One row; its cells stay as validated trees (the site reads them)."""

    id: str
    name: str
    family: str
    tab: str
    source_class: str
    cells: Mapping[str, Mapping[str, object]]
    card: Mapping[str, str] | None = None
    workloads: tuple[str, ...] | None = None
    own_sources: tuple[Mapping[str, str], ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CriteriaFile(Document):
    """`criteria/1`, the glyph's properties, states and rows (`web/_data/criteria.json`)."""

    schema: str
    rfc: str
    date: str
    note: str
    order: tuple[str, ...]
    states: Mapping[str, CriteriaState]
    properties: tuple[CriteriaProperty, ...]
    pins: Mapping[str, str]
    rows: tuple[CriteriaRow, ...]
    release: str | None = None


# ---------------------------------------------------------------- serving-model/1 (RFC-0015 SRV-6)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingRelease(Document):
    hub: str
    repo: str
    revision: str
    gated: bool


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingPublisher(Document):
    name: str
    release: ServingRelease


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseStatement(Document):
    quote: str
    url: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingPrecision(Document):
    name: str
    statement: str
    release_statement: ReleaseStatement | str  # or "not stated"
    chosen_by: str
    sources: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingRepo(Document):
    hub: str
    repo: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingFile(Document):
    path: str
    sha256: str
    bytes: int
    storage: str  # git | lfs
    publisher_blob: str
    source: str | None = None  # mirror (default) | publisher


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingShape(Document):
    layers: int
    attention_heads: int
    kv_heads: int
    head_dim: int
    kv_dtype: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingFiles(Document):
    source: ServingRepo
    revision: str
    files: tuple[ServingFile, ...]
    digest: str
    licence: Licence
    vocab_size: int
    shape: ServingShape


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ServingModel(Document):
    """`serving-model/1`: the publisher's release production serving runs (RFC-0015 SRV-6),
    pinned by an ungated byte-identical copy (RFC-0014 SM-1 to SM-3)."""

    schema: str
    id: str
    version: int
    workloads: tuple[str, ...]
    publisher: ServingPublisher
    precision: ServingPrecision
    model: ServingFiles


MODELS: dict[tuple[str, str], type[Any]] = {
    ("quantity/1", "#/$defs/quantityCore"): Quantity,
    ("quantity/1", "#/$defs/statistic"): Statistic,
    ("quantity/1", "#/$defs/source"): Source,
    ("quantity/1", "#/$defs/stats"): Stats,
    ("quantity/1", "#/$defs/quantityCore/properties/quality"): Quality,
    ("quantity/1", "#/$defs/quantityCore/properties/pairs"): Pairs,
    ("run/1", "#"): Run,
    ("run/1", "#/properties/workload"): WorkloadRef,
    ("run/1", "#/properties/inputs"): RunInputs,
    ("run/1", "#/properties/claim/anyOf/1"): ClaimRef,
    ("run/1", "#/properties/replaces/anyOf/1"): Replaces,
    ("run/1", "#/properties/raw"): RawSteps,
    ("run/1", "#/properties/events/items"): Event,
    ("run/1", "#/properties/proofs/items"): ProofResult,
    ("run/1", "#/properties/proofs/items/properties/agreement"): Agreement,
    ("run/1", "#/$defs/failure"): Failure,
    ("manifest/1", "#"): Manifest,
    ("manifest/1", "#/properties/harness"): HarnessRecord,
    ("manifest/1", "#/properties/runner"): RunnerRecord,
    ("manifest/1", "#/properties/claim/anyOf/1"): ClaimRef,
    ("manifest/1", "#/properties/system"): SystemRecord,
    ("manifest/1", "#/properties/system/properties/upstream/anyOf/1"): Upstream,
    ("manifest/1", "#/properties/system/properties/image"): ImageRef,
    ("manifest/1", "#/properties/system/properties/image_inputs/items"): ImageInput,
    ("manifest/1", "#/properties/workload"): WorkloadRecord,
    ("manifest/1", "#/properties/workload/properties/model"): ModelRecord,
    ("manifest/1", "#/properties/profile"): ProfileRecord,
    ("manifest/1", "#/properties/self_test"): SelfTest,
    ("manifest/1", "#/properties/self_test/properties/checks/items"): SelfTestCheck,
    ("manifest/1", "#/properties/commands/items"): Command,
    ("manifest/1", "#/$defs/file"): FileRecord,
    ("manifest/1", "#/properties/commitment/anyOf/1"): Commitment,
    ("manifest/1", "#/properties/proofs/items"): ProofRecord,
    ("release/1", "#"): Release,
    ("release/1", "#/$defs/card"): ReleaseCard,
    ("release/1", "#/properties/superseded_runs/items"): SupersededRun,
    ("release-index/1", "#"): ReleaseIndex,
    ("release-index/1", "#/$defs/card"): ReleaseCard,
    ("release-index/1", "#/properties/configurations/items"): IndexConfiguration,
    ("release-index/1", "#/properties/configurations/items/properties/workload"): WorkloadRef,
    (
        "release-index/1",
        "#/properties/configurations/items/properties/ineligible/items",
    ): Ineligible,
    ("release-index/1", "#/properties/controls/items"): ControlSummary,
    ("release-index/1", "#/properties/controls/items/properties/counts"): OutcomeCounts,
    ("release-index/1", "#/properties/controls/items/properties/outside_expected/items"): (
        OutsideExpected
    ),
    ("release-index/1", "#/properties/targets/items"): TargetResult,
    ("release-index/1", "#/properties/reference"): ReferenceRecord,
    ("claim/1", "#"): ClaimCard,
    ("claim/1", "#/properties/upstream"): Upstream,
    ("claim/1", "#/properties/security"): Security,
    ("claim/1", "#/properties/security/properties/notion"): SecurityNotion,
    ("claim/1", "#/properties/security/properties/model"): SecurityModel,
    ("claim/1", "#/properties/zero_knowledge"): ZeroKnowledge,
    ("claim/1", "#/properties/coverage"): Coverage,
    ("claim/1", "#/properties/coverage/properties/policy"): CoveragePolicy,
    ("claim/1", "#/properties/binding/anyOf/1"): Binding,
    ("claim/1", "#/$defs/edge"): BindingEdge,
    ("claim/1", "#/properties/quality_gap/items"): QualityGap,
    ("claim/1", "#/properties/reviewed_by/items"): Review,
    ("workload/1", "#"): Workload,
    ("workload/1", "#/properties/model"): ModelSpec,
    ("workload/1", "#/properties/model/properties/source"): ModelSource,
    ("workload/1", "#/properties/model/properties/files/items"): ModelFile,
    ("workload/1", "#/properties/model/properties/tokenizer_source"): TokenizerSource,
    ("workload/1", "#/properties/model/properties/tokenizer_source/properties/file"): ModelFile,
    ("workload/1", "#/properties/model/properties/licence"): Licence,
    ("workload/1", "#/properties/model/properties/parameters"): Parameters,
    ("workload/1", "#/properties/precision"): Precision,
    ("workload/1", "#/properties/precision/properties/weight_bits"): WeightBits,
    ("workload/1", "#/properties/prompts"): Prompts,
    ("workload/1", "#/properties/prompts/properties/length_rule"): LengthRule,
    ("workload/1", "#/properties/shape"): Shape,
    ("workload/1", "#/properties/decoding"): Decoding,
    ("corpus/1", "#"): Corpus,
    ("corpus/1", "#/properties/normalisation"): Normalisation,
    ("corpus/1", "#/properties/texts/items"): CorpusText,
    ("adapter-job/1", "#"): AdapterJob,
    ("adapter-job/1", "#/properties/workload"): WorkloadRef,
    ("adapter-job/1", "#/properties/shape"): Shape,
    ("adapter-out/1", "#"): AdapterOut,
    ("adapter-out/1", "#/properties/phases/items"): Phase,
    ("adapter-out/1", "#/properties/image_inputs/items"): ImageInput,
    ("adapter-out/1", "#/properties/sizes"): Sizes,
    ("adapter-out/1", "#/$defs/proof"): ProofEntry,
    ("adapter-out/1", "#/$defs/commandLine"): CommandLine,
    ("system/1", "#"): System,
    ("system/1", "#/properties/upstream"): UpstreamSpec,
    ("system/1", "#/properties/image"): ImageSpec,
    ("system/1", "#/properties/engine"): Engine,
    ("system/1", "#/properties/maintainers/items"): Maintainer,
    ("system/1", "#/properties/workloads/items/anyOf/1"): ReferenceWorkload,
    (
        "system/1",
        "#/properties/workloads/items/anyOf/1/properties/precision_substitution/anyOf/1",
    ): (PrecisionSubstitution),
    ("system/1", "#/properties/proofs"): ProofsSpec,
    ("system/1", "#/properties/timeouts_s"): Timeouts,
    ("system-controls/1", "#"): SystemControls,
    ("system-controls/1", "#/$defs/control"): SystemControl,
    ("reference/1", "#"): ReferenceFile,
    ("reference/1", "#/$defs/prover"): ProverProfile,
    ("reference/1", "#/$defs/serving"): ServingProfile,
    ("reference/1", "#/$defs/gpu"): GpuSpec,
    ("reference/1", "#/$defs/prover/properties/cpu"): ProverCpu,
    ("reference/1", "#/$defs/prover/properties/disk"): Disk,
    ("reference/1", "#/$defs/prover/properties/os"): OsSpec,
    ("reference/1", "#/$defs/prover/properties/container_runtime/anyOf/0"): ContainerRuntime,
    ("reference/1", "#/$defs/prover/properties/container_runtime/anyOf/1"): HostedRuntime,
    ("reference/1", "#/$defs/verifier"): VerifierProfile,
    ("reference/1", "#/$defs/verifier/properties/cpu"): VerifierCpu,
    ("reference/1", "#/$defs/verifier/properties/emulation"): Emulation,
    ("reference/1", "#/$defs/cost"): Cost,
    ("reference/1", "#/$defs/cost/properties/readings/items"): PriceReading,
    ("controls/1", "#"): Controls,
    ("controls/1", "#/$defs/control"): ControlResult,
    ("controls/1", "#/$defs/trial"): Trial,
    ("controls/1", "#/$defs/control/properties/twin/anyOf/1"): Twin,
    ("controls/1", "#/properties/perturbed_commitment/anyOf/1"): PerturbedCommitment,
    ("controls/1", "#/properties/summary"): ControlSummaryCounts,
    ("controls-part/1", "#"): ControlsPart,
    ("controls-part/1", "#/properties/host"): PartHost,
    ("controls-seed/1", "#"): ControlsSeed,
    ("target/1", "#"): Target,
    ("target/1", "#/properties/author"): Author,
    ("external/1", "#"): External,
    ("external/1", "#/properties/upstream"): Upstream,
    ("external/1", "#/$defs/figure"): ExternalFigure,
    ("perturbed-commitment/1", "#"): PerturbedCommitmentRecord,
    ("site-facts/1", "#"): SiteFacts,
    ("site-facts/1", "#/properties/site"): SiteInfo,
    ("site-facts/1", "#/$defs/model"): ModelFacts,
    ("site-facts/1", "#/$defs/row"): RowFacts,
    ("site-facts/1", "#/$defs/row/properties/licence"): LicenceFacts,
    ("site-facts/1", "#/$defs/row/properties/status"): StatusFacts,
    ("serving-model/1", "#"): ServingModel,
    ("serving-model/1", "#/properties/publisher"): ServingPublisher,
    ("serving-model/1", "#/properties/publisher/properties/release"): ServingRelease,
    ("serving-model/1", "#/properties/precision"): ServingPrecision,
    (
        "serving-model/1",
        "#/properties/precision/properties/release_statement/anyOf/1",
    ): ReleaseStatement,
    ("serving-model/1", "#/properties/model"): ServingFiles,
    ("serving-model/1", "#/properties/model/properties/source"): ServingRepo,
    ("serving-model/1", "#/properties/model/properties/files/items"): ServingFile,
    ("serving-model/1", "#/properties/model/properties/licence"): Licence,
    ("serving-model/1", "#/properties/model/properties/shape"): ServingShape,
    ("criteria/1", "#"): CriteriaFile,
    ("criteria/1", "#/$defs/property"): CriteriaProperty,
    ("criteria/1", "#/$defs/row"): CriteriaRow,
}


def model_for(schema_id: str) -> type[Document]:
    for (sid, pointer), cls in MODELS.items():
        if sid == schema_id and pointer == "#":
            return cls
    raise IProofsError(ErrorKind.INTERNAL, f'no model registered for schema "{schema_id}"')


def load(path: Path, registry: SchemaRegistry) -> Document:
    """Parse, validate against the document's own schema, then construct its model."""
    schema_id, tree = load_document(path, registry)
    return model_for(schema_id).from_tree(tree)


def load_reference(release: str, root: Path, registry: SchemaRegistry) -> ReferenceFile:
    """Load `reference/<release>.yaml` (RFC-0006 §Reference file)."""
    path = root / "reference" / f"{release}.yaml"
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no reference file {path} for release {release!r}")
    ref = load(path, registry)
    if not isinstance(ref, ReferenceFile) or ref.release != release:
        raise IProofsError(ErrorKind.CONFIG, f"{path}: not the reference file of {release!r}")
    return ref


def card_path(root: Path, system: str, configuration: str) -> Path | None:
    """The card for a configuration: `claims/<configuration>.yaml`, else a single `claim.yaml`."""
    multi = root / "systems" / system / "claims" / f"{configuration}.yaml"
    single = root / "systems" / system / "claim.yaml"
    return multi if multi.is_file() else single if single.is_file() else None
