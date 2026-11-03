"""Labelled quantity vocabularies and single-document checks (RFC-0012, RFC-0004).

The enums mirror schema/quantity/1.schema.json; a test keeps them equal.
"""

from collections.abc import Mapping
from enum import StrEnum


class Unit(StrEnum):
    S = "s"
    NS = "ns"
    B = "B"
    MIB = "MiB"
    J = "J"
    COUNT = "count"
    TOKEN = "token"
    TOKEN_PER_S = "token/s"
    S_PER_TOKEN = "s/token"
    B_PER_TOKEN = "B/token"
    USD = "USD"
    USD_PER_1K_TOKEN = "USD/1k_token"
    USD_PER_GPU_HOUR = "USD/gpu_hour"
    PERCENT = "%"
    PARAM_TOKEN_PER_S = "param_token/s"
    RATIO = "ratio"


class Scope(StrEnum):
    SETUP = "setup"
    COMMIT = "commit"
    PROVE_STEADY = "prove.steady"
    PROVE_SESSION = "prove.session"
    WHOLE_WALL = "whole_wall"
    VERIFY = "verify"
    VERIFY_SINGLE_THREAD = "verify.single_thread"
    PRIMITIVE = "primitive"


class Grade(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    PROJECTED = "projected"
    EXTERNAL = "external"
    ASSERTED = "asserted"


class Tier(StrEnum):
    """Ordered from least to most independent (INV-QTY-6a)."""

    REPORTED = "reported"
    PEER_REVIEWED = "peer-reviewed"
    REPRODUCED = "reproduced"


class SourceKind(StrEnum):
    HARNESS = "harness"
    ADAPTER = "adapter"
    DERIVATION = "derivation"
    UPSTREAM = "upstream"
    REFERENCE_FILE = "reference_file"


class NullReason(StrEnum):
    NOT_EXTERNALLY_OBSERVABLE = "not_externally_observable"
    FEWER_THAN_TWO_PROOFS = "fewer_than_two_proofs"
    NOT_APPLICABLE = "not_applicable"
    STEP_FAILED = "step_failed"
    NOT_MEASURABLE_ON_PROFILE = "not_measurable_on_profile"
    MISSING_INPUT = "missing_input"


class ScopeMapping(StrEnum):
    """How an upstream scope maps onto this project's scope (RFC-0004)."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    NONE = "none"


# INV-QTY-3: these units are time-based and require a scope.
TIME_UNITS = frozenset({
    Unit.S, Unit.NS, Unit.TOKEN_PER_S, Unit.S_PER_TOKEN,
    Unit.USD, Unit.USD_PER_1K_TOKEN, Unit.PARAM_TOKEN_PER_S,
})  # fmt: skip

TIER_ORDER = (Tier.REPORTED, Tier.PEER_REVIEWED, Tier.REPRODUCED)


def lowest_tier(tiers: list[Tier]) -> Tier:
    """INV-QTY-6a: a derived quantity carries the lowest tier among its inputs."""
    if not tiers:
        raise ValueError("no input tiers")
    return min(tiers, key=TIER_ORDER.index)


def statistic_problems(q: Mapping[str, object]) -> list[str]:
    """INV-QTY-8 checks the schema cannot express: value equals stats.mean."""
    stats = q.get("stats")
    if not isinstance(stats, Mapping):
        return []
    if q.get("value") != stats.get("mean"):
        return [f"INV-QTY-8: value {q.get('value')!r} != stats.mean {stats.get('mean')!r}"]
    return []
