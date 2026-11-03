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
from typing import Any, Self, Union, get_args, get_origin, get_type_hints

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
class ProofResult(Document):
    proof_id: str
    release_mono_ns: int | None
    tokens_covered: int
    verdict: str | None


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
    machine: Mapping[str, object]  # RFC-0006 record; typed fields land with issue #73
    self_test: SelfTest
    commands: tuple[Command, ...]
    commitment: Commitment | None
    proofs: tuple[ProofRecord, ...]
    warnings: tuple[str, ...]


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
class ReviewWindow(Document):
    opens: str
    closes: str


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Sponsor(Document):
    name: str
    provided: str
    period: str


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
    review_window: ReviewWindow
    freeze_date: str
    replies: Mapping[str, str]
    sponsors: tuple[Sponsor, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Ineligible(Document):
    run_id: str
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Evidence(Document):
    reviews: tuple[str, ...]
    reproductions: tuple[str, ...]


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
    effective_tier: Tier
    evidence: Evidence


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


# Schema location -> model class. The drift test walks this table and requires every
# document schema in the tree to appear here.
MODELS: dict[tuple[str, str], type[Any]] = {
    ("quantity/1", "#/$defs/quantityCore"): Quantity,
    ("quantity/1", "#/$defs/statistic"): Statistic,
    ("quantity/1", "#/$defs/source"): Source,
    ("quantity/1", "#/$defs/stats"): Stats,
    ("quantity/1", "#/$defs/quantityCore/properties/quality"): Quality,
    ("run/1", "#"): Run,
    ("run/1", "#/properties/workload"): WorkloadRef,
    ("run/1", "#/properties/claim/anyOf/1"): ClaimRef,
    ("run/1", "#/properties/replaces/anyOf/1"): Replaces,
    ("run/1", "#/properties/raw"): RawSteps,
    ("run/1", "#/properties/events/items"): Event,
    ("run/1", "#/properties/proofs/items"): ProofResult,
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
    ("release/1", "#/properties/review_window"): ReviewWindow,
    ("release/1", "#/properties/sponsors/items"): Sponsor,
    ("release-index/1", "#"): ReleaseIndex,
    ("release-index/1", "#/$defs/card"): ReleaseCard,
    ("release-index/1", "#/properties/configurations/items"): IndexConfiguration,
    ("release-index/1", "#/properties/configurations/items/properties/workload"): WorkloadRef,
    (
        "release-index/1",
        "#/properties/configurations/items/properties/ineligible/items",
    ): Ineligible,
    ("release-index/1", "#/properties/configurations/items/properties/evidence"): Evidence,
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
    ("target/1", "#"): Target,
    ("target/1", "#/properties/author"): Author,
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
