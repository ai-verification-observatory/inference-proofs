"""Labelled quantity vocabularies and single-document checks (RFC-0012, RFC-0004).

The enums mirror schema/quantity/1.schema.json; a test keeps them equal.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from iproofs.errors import ErrorKind, IProofsError


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
    B_PER_BIT_TOKEN = "B/bit_token"
    USD = "USD"
    USD_PER_1K_TOKEN = "USD/1k_token"
    USD_PER_GPU_HOUR = "USD/gpu_hour"
    PERCENT = "%"
    PARAM_TOKEN_PER_S = "param_token/s"
    S_PER_BIT_TOKEN = "s/bit_token"
    GPU_S_PER_TOKEN = "gpu_s/token"
    BIT_PER_WEIGHT = "bit/weight"
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
    Unit.USD, Unit.USD_PER_1K_TOKEN, Unit.PARAM_TOKEN_PER_S, Unit.S_PER_BIT_TOKEN,
    Unit.GPU_S_PER_TOKEN,
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


# ---------------------------------------------------------------- claim class (RFC-0002)

CLAIM_CLASS_TOKENS = (
    ("next-token", "greedy-continuation", "segment-grid", "other"),  # <output>
    ("exact-match", "tolerance", "other"),  # <policy>
    ("committed-weights", "public-weights", "other"),  # <weights>
)


@dataclass(frozen=True, slots=True)
class ClaimClass:
    """`<output>/<policy>/<weights>`: a filter key, not a security statement (RFC-0002)."""

    output: str
    policy: str
    weights: str

    def __str__(self) -> str:
        return f"{self.output}/{self.policy}/{self.weights}"


def _tokens(s: str, *, wildcard: bool) -> tuple[str, str, str]:
    parts = s.split("/")
    ok = len(parts) == 3 and all(
        p in allowed or (wildcard and p == "*")
        for p, allowed in zip(parts, CLAIM_CLASS_TOKENS, strict=False)
    )
    if not ok:
        what = "claim_class filter" if wildcard else "claim_class"
        raise IProofsError(ErrorKind.CONFIG, f"{s!r} is not a {what} (RFC-0002 §Claim class)")
    return parts[0], parts[1], parts[2]


def parse_claim_class(s: str) -> ClaimClass:
    return ClaimClass(*_tokens(s, wildcard=False))


def claim_class_matches(pattern: str, claim_class: str) -> bool:
    """A target filter (RFC-0009): each token is exact or `*`."""
    wanted = _tokens(pattern, wildcard=True)
    have = _tokens(claim_class, wildcard=False)
    return all(w in ("*", h) for w, h in zip(wanted, have, strict=True))


def check_closed_division(division: str, workload_class: str | None, card_class: str) -> None:
    """RFC-0003 §Divisions: a closed workload admits only cards with its exact class."""
    if division == "closed" and str(parse_claim_class(card_class)) != workload_class:
        raise IProofsError(
            ErrorKind.CONFIG,
            f"closed workload fixes claim_class {workload_class!r}; the card has "
            f"{card_class!r} (run it in an open workload)",
        )
