"""The fidelity gate of a rung (RFC-0018 FI-1 to FI-8), pure and CPU only.

`iproofs fidelity run` stores the reference's and the controls' greedy replies and llama.cpp's
KL logs under `results/<release>/fidelity/<rung>/` (systems/ref-fidelity). This module turns
those records and the rows' counted sessions into `fidelity.json` (schema `fidelity/1`):

- FI-3: a reply's score is its matched prefix, the number of leading tokens equal to the
  reference reply (0 to 512).
- FI-4: "A beats B" is a paired one-sided sign-flip test on the per-prompt score differences
  A - B, statistic the mean difference, p < alpha. The p-value convention:
  p = #{sign vectors s : sum(s_i d_i) >= sum(d_i)} / #{sign vectors counted}, ties counted as
  at least as extreme. With n <= `exact_up_to` every one of the 2^n sign vectors is counted
  (the count is computed by a subset-sum recursion, which gives the same integer as listing
  them); the observed vector is one of them, so p >= 2^-n. Above, `resamples` sign vectors are
  drawn and p = (1 + hits) / (1 + resamples), the observed vector counted once, so p is never
  0. A draw makes one `random.Random(seed).random()` call per difference, in prompt order;
  r < 0.5 flips that difference's sign. Only `.random()` is called, as in `corpus_window_v1`,
  whose sequence CPython guarantees for a given seed. The seed of a pair is `pair_seed`.
  The mean and the sum order sign vectors the same way (n is fixed), so the test counts on
  integer sums and no float rounding decides a tie.
- FI-5: the bar is the damaged control with the highest mean score among those every honest
  control that ran beats; a tie on the mean goes to the control listed first in the level
  file. No honest control ran, or no damaged control qualifies: no bar.
- FI-6: a row is `held` when it beats the bar, `failed` when the bar beats it, else
  `undecided`, cause `not resolved` (also with no bar).
- Faithful model's steps (RFC-0018 FM-4 to FM-7): T_green is the midpoint of the reference
  rerun's and Q8_0's mean scores, T_upper of Q8_0's and Q4_K_M's. A row is shown above a
  threshold T = (S_a + S_b) / (2n), S the two controls' score sums over the n prompts, when the
  FI-4 test on d_i = 2n s_i - (S_a + S_b) gives p < alpha. Multiplying s_i - T by 2n > 0 keeps
  the order of every sign vector and makes the differences integers, so the exact count is the
  same subset-sum count, with no float rounding. Seeds: `pair_seed(randomness, system,
  "T_green" or "T_upper")`.
- FI-7: KL figures are `quantity/1` values in nats per token, measured by llama.cpp
  (`Mean    KLD:` of `llama-perplexity --kl-divergence`), never gating.
"""

import dataclasses
import hashlib
import math
import random
import re
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from iproofs.quantity import Unit

SCHEMA = "fidelity/1"
KL_UNIT = Unit.NAT_PER_TOKEN.value  # FI-7: mean KL divergence per token, in nats
KL_NOTE = "computed by llama.cpp on the committed file, not the proved computation"
NOT_RESOLVED = "not resolved"
NOT_RUN = "not run"
SEED_RULE = (
    "first 8 bytes, big-endian, of sha256(randomness || 0x00 || utf8(a) || 0x00 || utf8(b)), "
    "randomness the beacon round's 32 bytes, a beats b being tested"
)
STEP_SEED_IDS = ("T_green", "T_upper")
STEPS_RULE = (
    "T_green = (mean(rerun) + mean(Q8_0)) / 2 and T_upper = (mean(Q8_0) + mean(Q4_K_M)) / 2 "
    "over the same n prompts; a row is shown above T when the FI-4 sign-flip test on "
    "d_i = 2n*s_i - (S_a + S_b) gives p < alpha"
)
STEPS_SEED_RULE = 'SEED_RULE with a = the row\'s system id and b = "T_green" or "T_upper"'
# llama.cpp tools/perplexity/perplexity.cpp L1926 at cd959bae: `Mean    KLD: %10.6lf ± %10.6lf`
_KLD = re.compile(r"^Mean\s+KLD:\s+([-+0-9.eE]+|nan|inf)\s+±", re.M)

State = Literal["held", "failed", "undecided"]


def matched_prefix(reply: Sequence[int], reference: Sequence[int]) -> int:
    """FI-3: the number of leading tokens of `reply` equal to `reference`."""
    n = 0
    for a, b in zip(reply, reference, strict=False):
        if a != b:
            break
        n += 1
    return n


def _exact_count(diffs: Sequence[int]) -> int:
    """The number of sign vectors s in {-1, +1}^n with sum(s_i d_i) >= sum(d_i). With a_i = |d_i|
    and A = sum a_i, each vector gives A - 2 S, S the sum of a_i over the positions whose signed
    term is negative; each vector is one subset of positions, so the count is the number of
    subsets with S <= (A - observed) / 2 (a zero difference has two vectors, both counted)."""
    observed = sum(diffs)
    sizes = [abs(d) for d in diffs]
    limit = (sum(sizes) - observed) // 2  # A - observed is even: both have A's parity
    counts = [0] * (limit + 1)
    counts[0] = 1
    for a in sizes:  # subsets by sum, over sums up to the limit only; a = 0 doubles each count
        for s in range(limit, a - 1, -1):
            counts[s] += counts[s - a]
    return sum(counts)


def sign_flip_p(diffs: Sequence[int], *, exact_up_to: int, resamples: int, seed: int) -> float:
    """FI-4: the one-sided p-value of a mean difference above 0 (module docstring for the
    convention). `diffs` are integer score differences, one per prompt. No difference: 1.0."""
    n = len(diffs)
    if n == 0:
        return 1.0
    if n <= exact_up_to:
        return _exact_count(diffs) / (1 << n)
    if resamples < 1:
        raise ValueError("a Monte Carlo test needs at least one resample")
    observed = sum(diffs)
    rand = random.Random(seed).random
    hits = 0
    for _ in range(resamples):
        t = 0
        for d in diffs:
            t += -d if rand() < 0.5 else d
        if t >= observed:
            hits += 1
    return (1 + hits) / (1 + resamples)


def pair_seed(randomness_hex: str, a_id: str, b_id: str) -> int:
    """FI-4: the seed of the test "a beats b" (`SEED_RULE`)."""
    if not re.fullmatch(r"[0-9a-f]{64}", randomness_hex):
        raise ValueError("the beacon randomness is 32 bytes, 64 lowercase hex digits")
    data = bytes.fromhex(randomness_hex) + b"\x00" + a_id.encode() + b"\x00" + b_id.encode()
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


@dataclass(frozen=True, slots=True)
class SignFlipRule:
    """The level's `fidelity` constants and the beacon randomness that seeds the tests."""

    alpha: float
    exact_up_to: int
    resamples: int
    randomness_hex: str


@dataclass(frozen=True, slots=True)
class PairTest:
    """One test "a beats b" on paired scores."""

    a: str
    b: str
    n: int
    p: float
    method: Literal["exact", "monte-carlo"]
    seed: int | None  # None for an exact count, which draws nothing

    def beats(self, alpha: float) -> bool:
        return self.p < alpha

    def record(self) -> dict[str, object]:
        return {
            "a": self.a,
            "b": self.b,
            "n": self.n,
            "p": self.p,
            "method": self.method,
            "seed": None if self.seed is None else f"0x{self.seed:016x}",
        }


def beats(
    a_id: str, a_scores: Sequence[int], b_id: str, b_scores: Sequence[int], rule: SignFlipRule
) -> PairTest:
    """FI-4: the paired test of A over B on the same prompts, in the same order."""
    if len(a_scores) != len(b_scores):
        raise ValueError(f"{a_id} has {len(a_scores)} scores, {b_id} {len(b_scores)}")
    diffs = [a - b for a, b in zip(a_scores, b_scores, strict=True)]
    exact = len(diffs) <= rule.exact_up_to
    seed = None if exact else pair_seed(rule.randomness_hex, a_id, b_id)
    p = sign_flip_p(diffs, exact_up_to=rule.exact_up_to, resamples=rule.resamples, seed=seed or 0)
    return PairTest(a_id, b_id, len(diffs), p, "exact" if exact else "monte-carlo", seed)


def mean(scores: Sequence[int]) -> float | None:
    return sum(scores) / len(scores) if scores else None


@dataclass(frozen=True, slots=True)
class ControlResult:
    """One control of FI-2 as run: its scores against the reference, or why it has none."""

    id: str
    kind: Literal["honest", "damaged"]
    recipe: str
    status: Literal["ok", "failed"]
    scores: tuple[int, ...] = ()
    cause: str | None = None
    kl: Mapping[str, object] | None = None

    @property
    def mean_prefix(self) -> float | None:
        return mean(self.scores) if self.status == "ok" else None

    def record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "recipe": self.recipe,
            "status": self.status,
            "cause": self.cause,
            "scores": list(self.scores),
            "mean_prefix": self.mean_prefix,
            "kl": dict(self.kl) if self.kl else None,
        }


@dataclass(frozen=True, slots=True)
class Bar:
    control: str
    mean_prefix: float
    scores: tuple[int, ...]

    def record(self) -> dict[str, object]:
        return {"control": self.control, "mean_prefix": self.mean_prefix}


def choose_bar(
    controls: Sequence[ControlResult], rule: SignFlipRule
) -> tuple[Bar | None, list[PairTest]]:
    """FI-5: the bar and every test run to choose it (each honest control against each damaged
    control, in level-file order). Failed controls take no part."""
    honest = [c for c in controls if c.kind == "honest" and c.status == "ok"]
    damaged = [c for c in controls if c.kind == "damaged" and c.status == "ok"]
    tests: list[PairTest] = []
    qualifying: list[ControlResult] = []
    for d in damaged:
        results = [beats(h.id, h.scores, d.id, d.scores, rule) for h in honest]
        tests += results
        if honest and all(t.beats(rule.alpha) for t in results):
            qualifying.append(d)
    if not qualifying:
        return None, tests
    best = qualifying[0]
    for c in qualifying[1:]:  # strictly higher only: a tie stays with the earlier control
        if (c.mean_prefix or 0.0) > (best.mean_prefix or 0.0):
            best = c
    assert best.mean_prefix is not None
    return Bar(best.id, best.mean_prefix, best.scores), tests


@dataclass(frozen=True, slots=True)
class Threshold:
    """One step threshold (FM-5, FM-6): the two controls it is the midpoint of, the sum S_a +
    S_b of their scores over the `n` prompts, or the cause it has none."""

    name: str  # T_green or T_upper
    controls: tuple[str, ...]
    n: int
    total: int | None
    cause: str | None

    @property
    def value(self) -> float | None:
        return None if self.total is None else self.total / (2 * self.n)

    def record(self) -> dict[str, object]:
        return {"controls": list(self.controls), "value": self.value, "cause": self.cause}


def _honest(
    controls: Sequence[tuple[Mapping[str, object], ControlResult]],
    recipe: str,
    type_: str | None,
) -> ControlResult | None:
    """The first honest control of the level file with this recipe (and quantization type)."""
    for spec, result in controls:
        if spec.get("kind") == "honest" and spec.get("recipe") == recipe and (
                type_ is None or spec.get("type") == type_):  # fmt: skip
            return result
    return None


def _threshold(name: str, named: Sequence[tuple[ControlResult | None, str]], n: int) -> Threshold:
    ids = tuple(c.id for c, _ in named if c is not None)
    cause = None
    for found, label in named:  # the first control, in order, that cannot give a mean
        if found is None:
            cause = f"no {label} control on this rung"
        elif found.status != "ok":
            cause = f"{found.id} failed"
        elif len(found.scores) != n:
            cause = f"{found.id} has {len(found.scores)} scores for {n} prompts"
        if cause:
            break
    if cause is not None:
        return Threshold(name, ids, n, None, cause)
    total = sum(sum(c.scores) for c, _ in named if c is not None)
    return Threshold(name, ids, n, total, None)


def thresholds(
    controls: Sequence[tuple[Mapping[str, object], ControlResult]], n: int
) -> dict[str, Threshold]:
    """T_green and T_upper from the level file's honest controls (`controls` pairs each spec
    with its result): rerun = recipe rerun, Q8_0 and Q4_K_M = recipe quantize of that type."""
    rerun = _honest(controls, "rerun", None)
    q8 = _honest(controls, "quantize", "Q8_0")
    q4 = _honest(controls, "quantize", "Q4_K_M")
    return {
        "green": _threshold("T_green", ((rerun, "rerun"), (q8, "Q8_0")), n),
        "upper": _threshold("T_upper", ((q8, "Q8_0"), (q4, "Q4_K_M")), n),
    }


@dataclass(frozen=True, slots=True)
class StepTest:
    """The FI-4 test "the row is shown above the threshold" on d_i = 2n s_i - (S_a + S_b)."""

    threshold: str
    value: float
    n: int
    p: float
    method: Literal["exact", "monte-carlo"]
    seed: int | None

    def record(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "value": self.value,
            "n": self.n,
            "p": self.p,
            "method": self.method,
            "seed": None if self.seed is None else f"0x{self.seed:016x}",
        }


def step_tests(
    system: str,
    scores: Sequence[int],
    steps: Mapping[str, Threshold],
    rule: SignFlipRule,
) -> dict[str, StepTest | None]:
    """The row's test over each threshold; None where the threshold has no value."""
    out: dict[str, StepTest | None] = {}
    for key, t in steps.items():
        n = len(scores)
        value = t.value
        if t.total is None or value is None or n != t.n:
            out[key] = None
            continue
        diffs = [2 * n * s - t.total for s in scores]
        exact = n <= rule.exact_up_to
        seed = None if exact else pair_seed(rule.randomness_hex, system, t.name)
        p = sign_flip_p(diffs, exact_up_to=rule.exact_up_to, resamples=rule.resamples,
                        seed=seed or 0)  # fmt: skip
        out[key] = StepTest(t.name, value, n, p, "exact" if exact else "monte-carlo", seed)
    return out


@dataclass(frozen=True, slots=True)
class RowResult:
    system: str
    state: State
    cause: str | None
    scores: tuple[int, ...] = ()
    p_above_bar: float | None = None
    p_below_bar: float | None = None
    kl: Mapping[str, object] | None = None
    kl_note: str = ""
    tests: tuple[PairTest, ...] = field(default=())
    step_tests: Mapping[str, StepTest | None] | None = None  # None: the row has no scores

    @property
    def mean_prefix(self) -> float | None:
        return mean(self.scores)

    def record(self) -> dict[str, object]:
        return {
            "scores": list(self.scores),
            "mean_prefix": self.mean_prefix,
            "p_above_bar": self.p_above_bar,
            "p_below_bar": self.p_below_bar,
            "state": self.state,
            "cause": self.cause,
            "kl": dict(self.kl) if self.kl else None,
            "kl_note": self.kl_note,
            "tests": [t.record() for t in self.tests],
            "step_tests": None if self.step_tests is None else {
                k: None if t is None else t.record() for k, t in self.step_tests.items()},
        }  # fmt: skip


def score_row(
    system: str,
    replies: Sequence[Sequence[int]] | None,
    reference: Sequence[Sequence[int]],
    bar: Bar | None,
    rule: SignFlipRule,
    *,
    kl: Mapping[str, object] | None = None,
    kl_note: str = "",
    missing_cause: str = NOT_RUN,
) -> RowResult:
    """FI-6: the row's state from its replies (prompt order, one per reference reply). No
    replies (sessions missing): `undecided` with `missing_cause`. No bar: `undecided`, `not
    resolved`."""
    if replies is None:
        return RowResult(system, "undecided", missing_cause, kl=kl, kl_note=kl_note)
    if len(replies) != len(reference):
        raise ValueError(f"{system}: {len(replies)} replies for {len(reference)} prompts")
    scores = tuple(matched_prefix(r, ref) for r, ref in zip(replies, reference, strict=True))
    if bar is None:
        return RowResult(system, "undecided", NOT_RESOLVED, scores, kl=kl, kl_note=kl_note)
    above = beats(system, scores, bar.control, bar.scores, rule)
    below = beats(bar.control, bar.scores, system, scores, rule)
    state: State = "undecided"
    cause: str | None = NOT_RESOLVED
    if above.beats(rule.alpha):
        state, cause = "held", None
    elif below.beats(rule.alpha):
        state, cause = "failed", None
    return RowResult(system, state, cause, scores, above.p, below.p, kl, kl_note, (above, below))


def score_control(
    spec: Mapping[str, object],
    replies: Sequence[Sequence[int]] | None,
    reference: Sequence[Sequence[int]],
    *,
    cause: str | None = None,
    kl: Mapping[str, object] | None = None,
) -> ControlResult:
    """A control of the level file (`id`, `kind`, `recipe`) with its replies, or failed with
    `cause` when it has none or not one per prompt."""
    kind = str(spec["kind"])
    if kind not in ("honest", "damaged"):
        raise ValueError(f"control {spec['id']}: kind {kind!r}")
    ident, recipe = str(spec["id"]), str(spec["recipe"])
    honest_or_damaged: Literal["honest", "damaged"] = "honest" if kind == "honest" else "damaged"
    if replies is None or len(replies) != len(reference):
        why = cause or (
            "no replies" if replies is None else f"{len(replies)} replies for {len(reference)}"
        )
        return ControlResult(ident, honest_or_damaged, recipe, "failed", cause=why, kl=kl)
    scores = tuple(matched_prefix(r, ref) for r, ref in zip(replies, reference, strict=True))
    return ControlResult(ident, honest_or_damaged, recipe, "ok", scores, kl=kl)


def parse_kl(log_text: str) -> float | None:
    """The mean KL divergence llama-perplexity printed, or None when the log has none."""
    found = _KLD.findall(log_text)
    if not found:
        return None
    try:
        value = float(found[-1])
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def kl_quantity(value: float, source_ref: str) -> dict[str, object]:
    """FI-7: a KL figure as a labelled quantity (AGENTS.md rule 2). llama.cpp measured it in
    the reference image (`source.kind` adapter, the log as its reference); it has no timing
    scope."""
    return {
        "value": value,
        "unit": KL_UNIT,
        "scope": None,
        "grade": "measured",
        "tier": "reported",
        "source": {"kind": "adapter", "ref": source_ref},
        "null_reason": None,
        "note": KL_NOTE,
    }


# ---------------------------------------------------------------- KL of an adapter's copy (AD-2)
#
# llama.cpp's `--kl-divergence-base` file at cd959bae (tools/perplexity/perplexity.cpp L466 to
# L467, L521 to L526 and L79 to L106 write it; L1690 to L1720 and L1738 to L1842 read it back):
# "_logits_", n_ctx (uint32), n_vocab (int32), n_chunk (int32), the n_chunk x n_ctx evaluated
# tokens (int32, as tokenized: the first of each chunk is replaced by BOS at evaluation when the
# vocabulary adds one, and is stored unreplaced), then for each chunk in order, for each scored
# position first = n_ctx / 2 .. n_ctx - 2, one record of nv = 2 ((n_vocab + 1) / 2) + 4 uint16:
# two float32 (scale, min_log_prob) then n_vocab uint16 codes (padded to even), the reference's
# log-probability of token i being scale x code_i + min_log_prob (codes below max - 16 are 0).
# Record r of a chunk is the distribution after tokens 0 .. first + r, the one predicting token
# first + r + 1. All little-endian. The format is not documented beyond the README's "binary
# format" and carries no version: it is read here only at the pinned commit.
KL_BASE_MAGIC = b"_logits_"
KL_FLOOR = -16.0  # perplexity.cpp L226: base log-probabilities at or below it are left out


@dataclass(frozen=True, slots=True)
class KlBase:
    n_ctx: int
    n_vocab: int
    n_chunk: int
    tokens: tuple[tuple[int, ...], ...]  # per chunk, as stored
    data_offset: int

    @property
    def first(self) -> int:
        return self.n_ctx // 2

    @property
    def scored(self) -> int:
        """Scored positions per chunk."""
        return self.n_ctx - 1 - self.first

    @property
    def record_bytes(self) -> int:
        return 2 * (2 * ((self.n_vocab + 1) // 2) + 4)


def read_kl_base(path: Path) -> KlBase:
    """The header and tokens of a `--kl-divergence-base` file; checks its size."""
    with path.open("rb") as f:
        head = f.read(20)
        if len(head) != 20 or head[:8] != KL_BASE_MAGIC:
            raise ValueError(f"{path.name} is not a llama.cpp KL base file")
        n_ctx, n_vocab, n_chunk = struct.unpack("<Iii", head[8:20])
        if n_ctx < 2 or n_vocab < 1 or n_chunk < 1:
            raise ValueError(f"{path.name}: n_ctx {n_ctx}, n_vocab {n_vocab}, n_chunk {n_chunk}")
        raw = f.read(4 * n_ctx * n_chunk)
    if len(raw) != 4 * n_ctx * n_chunk:
        raise ValueError(f"{path.name}: the token list is cut short")
    flat = struct.unpack(f"<{n_ctx * n_chunk}i", raw)
    tokens = tuple(tuple(flat[c * n_ctx : (c + 1) * n_ctx]) for c in range(n_chunk))
    base = KlBase(n_ctx, n_vocab, n_chunk, tokens, 20 + len(raw))
    want = base.data_offset + n_chunk * base.scored * base.record_bytes
    if path.stat().st_size != want:
        raise ValueError(f"{path.name} is {path.stat().st_size} B; its header implies {want} B")
    return base


def scored_texts(base: KlBase, bos: int | None) -> list[list[int]]:
    """The texts the reference was evaluated on, the ones an adapter's `logprobs` is given:
    each chunk's tokens, the first replaced by `bos` when the reference's vocabulary adds a BOS
    token (perplexity.cpp L1798 to L1801)."""
    return [([bos] if bos is not None else [chunk[0]]) + list(chunk[1:]) for chunk in base.tokens]


def _log_softmax_f16(blob: bytes, n_vocab: int) -> list[float]:
    values = struct.unpack(f"<{n_vocab}e", blob)
    top = max(values)
    if not math.isfinite(top):
        raise ValueError("a log-probability row has no finite value")
    lse = top + math.log(math.fsum(math.exp(v - top) for v in values if v != -math.inf))
    return [v - lse for v in values]


def mean_kl_against_base(path: Path, copy_rows: Callable[[int], bytes]) -> tuple[float, int]:
    """FI-7 for a copy llama.cpp cannot load (AD-2): mean KL(reference || copy) per scored token,
    in nats, and the number of tokens. `copy_rows(c)` gives chunk c's scored rows from the
    adapter: scored x n_vocab float16 little-endian log-probabilities, row r the distribution
    predicting token first + r + 1, as the base records it. Each copy row is renormalized
    (log-softmax), as llama.cpp renormalizes a copy's logits; the sum runs over the tokens
    whose base log-probability is above -16, as llama.cpp's does (perplexity.cpp L224 to L233).
    A copy that gives 0 probability to such a token makes the mean infinite."""
    base = read_kl_base(path)
    total, count = 0.0, 0
    row = base.n_vocab * 2
    with path.open("rb") as f:
        f.seek(base.data_offset)
        for c in range(base.n_chunk):
            blob = copy_rows(c)
            if len(blob) != base.scored * row:
                raise ValueError(f"chunk {c}: {len(blob)} B of log-probabilities, want "
                                 f"{base.scored} x {base.n_vocab} float16")  # fmt: skip
            for r in range(base.scored):
                record = f.read(base.record_bytes)
                scale, min_lp = struct.unpack("<ff", record[:8])
                codes = struct.unpack(f"<{base.n_vocab}H", record[8 : 8 + row])
                copy = _log_softmax_f16(blob[r * row : (r + 1) * row], base.n_vocab)
                kl = 0.0
                for code, lq in zip(codes, copy, strict=True):
                    lp = scale * code + min_lp
                    if lp > KL_FLOOR:
                        kl += math.exp(lp) * (lp - lq)
                total += kl
                count += 1
    return total / count, count


def session_replies(run: Mapping[str, object]) -> list[list[int]] | None:
    """FI-6: a counted session's replies by request index, from its `run.json` as the runner
    stores it: the claimed outputs of the proofs of each request, joined in record order
    (RFC-0017 INV-REQ-2), every proof accepted. None when a request has no proof or a proof
    that was not accepted: such a session is not complete (SE-1)."""
    proofs = run.get("proofs")
    if not isinstance(proofs, list) or not proofs:
        return None
    by_request: dict[int, list[int]] = {}
    for proof in proofs:
        if not isinstance(proof, Mapping) or proof.get("verdict") != "accept":
            return None
        index, claimed = proof.get("request_index"), proof.get("claimed_output")
        if not isinstance(index, int) or not isinstance(claimed, list):
            return None
        by_request.setdefault(index, []).extend(int(t) for t in claimed)
    if set(by_request) != set(range(len(by_request))):
        return None
    return [by_request[i] for i in range(len(by_request))]


def row_replies(
    sessions: Mapping[int, Sequence[Sequence[int]]], slots: int, per_session: int
) -> list[list[int]] | None:
    """The row's replies in prompt order: slot k answers prompts [(k-1) N, k N) (RFC-0018
    §Terms). None unless every slot has a session of exactly N replies."""
    out: list[list[int]] = []
    for k in range(1, slots + 1):
        replies = sessions.get(k)
        if replies is None or len(replies) != per_session:
            return None
        out += [list(r) for r in replies]
    return out


@dataclass(frozen=True, slots=True)
class Header:
    """What `fidelity.json` names besides the results: level, rung, prompts and engine."""

    level_id: str
    level_digest: str
    rung: str
    prompts_digest: str
    engine: Mapping[str, object]
    reference_replies: str  # repository path of reference.jsonl
    reference_digest: str
    slots: int  # FI-1: the fidelity run's llama-server slots, from fidelity-run.json


def fidelity_document(
    header: Header,
    rule: SignFlipRule,
    reference: Sequence[Sequence[int]],
    controls: Sequence[ControlResult],
    rows: Sequence[RowResult],
    bar: Bar | None,
    tests: Sequence[PairTest],
    steps: Mapping[str, Threshold],
) -> dict[str, object]:
    """`fidelity.json` (schema `fidelity/1`) from the scored controls and rows."""
    return {
        "schema": SCHEMA,
        "level": {"id": header.level_id, "digest": header.level_digest},
        "rung": header.rung,
        "n": len(reference),
        "prompts_digest": header.prompts_digest,
        "engine": dict(header.engine),
        "reference": {"replies": header.reference_replies, "digest": header.reference_digest},
        "test": {
            "score": "matched_prefix",
            "test": "paired-sign-flip",
            "alpha": rule.alpha,
            "exact_up_to": rule.exact_up_to,
            "resamples": rule.resamples,
            "seed_rule": SEED_RULE,
        },
        "slots": header.slots,
        "steps": {
            "rule": STEPS_RULE,
            "seed_rule": STEPS_SEED_RULE,
            "green": steps["green"].record(),
            "upper": steps["upper"].record(),
        },
        "controls": [c.record() for c in controls],
        "bar_tests": [t.record() for t in tests],
        "bar": bar.record() if bar else None,
        "rows": {r.system: r.record() for r in sorted(rows, key=lambda r: r.system)},
    }


def build_fidelity(
    header: Header,
    rule: SignFlipRule,
    reference: Sequence[Sequence[int]],
    controls: Sequence[
        tuple[
            Mapping[str, object],
            Sequence[Sequence[int]] | None,
            str | None,
            Mapping[str, object] | None,
        ]
    ],
    rows: Mapping[str, Sequence[Sequence[int]] | None],
    row_kl: Mapping[str, tuple[Mapping[str, object] | None, str]] | None = None,
    missing_cause: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """FI-3 to FI-6 for one rung: `controls` are (level-file spec, replies or None, cause or
    None, KL quantity or None) in level-file order; `rows` the rows' replies in prompt order
    (None for a row without its counted sessions); `row_kl` each row's KL quantity and note.
    Returns the `fidelity/1` document, with the step thresholds and each row's step tests."""
    scored = [
        score_control(spec, replies, reference, cause=cause, kl=kl)
        for spec, replies, cause, kl in controls
    ]
    bar, tests = choose_bar(scored, rule)
    steps = thresholds([(spec, c) for (spec, *_), c in zip(controls, scored, strict=True)],
                       len(reference))  # fmt: skip
    kls = row_kl or {}
    results = [
        score_row(
            system,
            replies,
            reference,
            bar,
            rule,
            kl=kls.get(system, (None, ""))[0],
            kl_note=kls.get(system, (None, ""))[1],
            missing_cause=(missing_cause or {}).get(system, NOT_RUN),
        )
        for system, replies in rows.items()
    ]
    results = [
        dataclasses.replace(r, step_tests=step_tests(r.system, r.scores, steps, rule))
        if r.scores else r
        for r in results
    ]  # fmt: skip
    return fidelity_document(header, rule, reference, scored, results, bar, tests, steps)
