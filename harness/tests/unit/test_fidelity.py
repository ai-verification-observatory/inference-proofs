"""RFC-0018 FI-3 to FI-6: matched prefix, the sign-flip test, the bar and the row states."""

import hashlib
import itertools
import json
import math
import struct
from pathlib import Path

import pytest

from iproofs.fidelity import (
    NOT_RESOLVED,
    NOT_RUN,
    ControlResult,
    Header,
    SignFlipRule,
    build_fidelity,
    choose_bar,
    kl_quantity,
    matched_prefix,
    mean_kl_against_base,
    pair_seed,
    parse_kl,
    read_kl_base,
    row_replies,
    score_control,
    score_row,
    scored_texts,
    session_replies,
    sign_flip_p,
)
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
RANDOMNESS = "ab" * 32
RULE = SignFlipRule(alpha=0.05, exact_up_to=20, resamples=2000, randomness_hex=RANDOMNESS)
N = 15
REFERENCE = [[1000 * i + j for j in range(512)] for i in range(N)]


def replies(prefixes: list[int]) -> list[list[int]]:
    """Replies whose matched prefix against REFERENCE is each of `prefixes`."""
    return [ref[:k] + [-1 - t for t in ref[k:]] for ref, k in zip(REFERENCE, prefixes, strict=True)]


def test_matched_prefix() -> None:
    assert matched_prefix([1, 2, 3, 4], [1, 2, 9, 4]) == 2
    assert matched_prefix([7, 2], [1, 2]) == 0
    assert matched_prefix(list(range(512)), list(range(512))) == 512
    assert matched_prefix([1, 2], [1, 2, 3]) == 2
    assert [
        matched_prefix(r, ref)
        for r, ref in zip(replies([0, 5, 512] + [9] * 12), REFERENCE, strict=True)
    ][:3] == [0, 5, 512]


def test_exact_p_hand_counted() -> None:
    """diffs (3, 1, -2, 0), observed sum 2. The 8 sums of +-3 +-1 +-2 are 6, 2, 4, 0, 0, -4,
    -2, -6; three are >= 2 (ties count), and the zero doubles every vector: 6 of 16."""
    assert sign_flip_p([3, 1, -2, 0], exact_up_to=20, resamples=1, seed=0) == 6 / 16
    assert sign_flip_p([5, 5, 5, 5], exact_up_to=20, resamples=1, seed=0) == 1 / 16
    assert sign_flip_p([0, 0, 0], exact_up_to=20, resamples=1, seed=0) == 1.0
    assert sign_flip_p([], exact_up_to=20, resamples=1, seed=0) == 1.0


def test_exact_p_n15_against_brute_force() -> None:
    diffs = [12, -3, 0, 7, 7, -15, 2, 0, 31, -1, 4, -9, 6, 0, 3]
    observed = sum(diffs)
    hits = sum(
        1
        for signs in itertools.product((1, -1), repeat=len(diffs))
        if sum(s * d for s, d in zip(signs, diffs, strict=True)) >= observed
    )
    assert sign_flip_p(diffs, exact_up_to=20, resamples=1, seed=0) == hits / 2**15


def test_monte_carlo_is_deterministic_and_counts_the_observed_vector() -> None:
    diffs = [12, -3, 0, 7, 7, -15, 2, 0, 31]
    one = sign_flip_p(diffs, exact_up_to=4, resamples=2000, seed=pair_seed(RANDOMNESS, "a", "b"))
    two = sign_flip_p(diffs, exact_up_to=4, resamples=2000, seed=pair_seed(RANDOMNESS, "a", "b"))
    assert one == two
    exact = sign_flip_p(diffs, exact_up_to=20, resamples=1, seed=0)
    assert abs(one - exact) < 0.05  # 2,000 draws: a few standard errors of 0.011
    # every draw is at least as extreme as all-zero differences: (1 + R) / (1 + R)
    assert sign_flip_p([0] * 30, exact_up_to=4, resamples=50, seed=1) == 1.0
    # all positive and large: only the all-plus vector reaches the sum, (1 + 0) / (1 + R)
    assert sign_flip_p([100] * 30, exact_up_to=4, resamples=50, seed=1) == 1 / 51


def test_pair_seed_rule() -> None:
    data = bytes.fromhex(RANDOMNESS) + b"\x00q8_0\x00q2_k"
    assert pair_seed(RANDOMNESS, "q8_0", "q2_k") == int.from_bytes(
        hashlib.sha256(data).digest()[:8], "big"
    )
    assert pair_seed(RANDOMNESS, "q8_0", "q2_k") != pair_seed(RANDOMNESS, "q2_k", "q8_0")
    with pytest.raises(ValueError, match="64 lowercase hex"):
        pair_seed("AB" * 32, "a", "b")


def scored(
    spec: dict[str, str], prefixes: list[int] | None, cause: str | None = None
) -> ControlResult:
    return score_control(
        spec, None if prefixes is None else replies(prefixes), REFERENCE, cause=cause
    )


HONEST = [
    scored({"id": "reference-2", "kind": "honest", "recipe": "rerun"}, [512] * N),
    scored({"id": "q8_0", "kind": "honest", "recipe": "quantize"}, [512] * 14 + [300]),
    scored({"id": "q4_k_m", "kind": "honest", "recipe": "quantize"}, [400] * N),
]


def test_bar_is_the_highest_mean_every_honest_control_beats() -> None:
    damaged = [
        scored({"id": "q3_k_s", "kind": "damaged", "recipe": "quantize"}, [100] * N),
        scored({"id": "q2_k", "kind": "damaged", "recipe": "quantize"}, [50] * N),
        # higher mean than q3_k_s, but q4_k_m does not beat it (equal scores): never the bar
        scored({"id": "smaller-model", "kind": "damaged", "recipe": "other_model"}, [400] * N),
        scored(
            {"id": "drop-every-4th-block", "kind": "damaged", "recipe": "drop_blocks"},
            None,
            "llama-server exited 1",
        ),
    ]
    bar, tests = choose_bar([*HONEST, *damaged], RULE)
    assert bar is not None
    assert (bar.control, bar.mean_prefix) == ("q3_k_s", 100.0)
    assert len(tests) == 3 * 3  # the failed control takes no part
    assert all(t.p == 1 / 2**15 for t in tests if t.b in {"q3_k_s", "q2_k"})


def test_bar_tie_goes_to_the_first_listed() -> None:
    damaged = [
        scored({"id": "q3_k_s", "kind": "damaged", "recipe": "quantize"}, [60] * N),
        scored({"id": "q2_k", "kind": "damaged", "recipe": "quantize"}, [60] * N),
    ]
    bar, _ = choose_bar([*HONEST, *damaged], RULE)
    assert bar is not None
    assert bar.control == "q3_k_s"


def test_no_bar_when_none_qualifies_or_no_honest_control_ran() -> None:
    damaged = [scored({"id": "q3_k_s", "kind": "damaged", "recipe": "quantize"}, [400] * N)]
    bar, _ = choose_bar([*HONEST, *damaged], RULE)
    assert bar is None
    row = score_row("sash", replies([512] * N), REFERENCE, bar, RULE)
    assert (row.state, row.cause, row.p_above_bar) == ("undecided", NOT_RESOLVED, None)
    failed_honest = [scored({"id": "q8_0", "kind": "honest", "recipe": "quantize"}, None, "x")]
    low = [scored({"id": "q2_k", "kind": "damaged", "recipe": "quantize"}, [0] * N)]
    assert choose_bar([*failed_honest, *low], RULE)[0] is None


def test_row_states() -> None:
    bar, _ = choose_bar(
        [
            *HONEST,
            scored({"id": "q3_k_s", "kind": "damaged", "recipe": "quantize"}, [100, 90, 110] * 5),
        ],
        RULE,
    )
    assert bar is not None
    held = score_row("flashprove", replies([512] * N), REFERENCE, bar, RULE)
    assert (held.state, held.cause, held.p_above_bar) == ("held", None, 1 / 2**15)
    failed = score_row("flashprove", replies([3] * N), REFERENCE, bar, RULE)
    assert (failed.state, failed.cause, failed.p_below_bar) == ("failed", None, 1 / 2**15)
    level = score_row("flashprove", replies([100, 90, 110] * 5), REFERENCE, bar, RULE)
    assert (level.state, level.cause, level.p_above_bar) == ("undecided", NOT_RESOLVED, 1.0)
    missing = score_row("flashprove", None, REFERENCE, bar, RULE)
    assert (missing.state, missing.cause) == ("undecided", NOT_RUN)


def test_parse_kl_reads_llama_perplexity_mean() -> None:
    log = "Mean    KLD:   0.031273 ±   0.000238\nMaximum KLD:  12.3\n"
    assert parse_kl(log) == 0.031273
    assert parse_kl("perplexity: no KL here") is None
    assert parse_kl("Mean    KLD:        nan ±        nan\n") is None


def test_document_validates_and_carries_the_states() -> None:
    specs = [
        ({"id": "reference-2", "kind": "honest", "recipe": "rerun"}, replies([512] * N)),
        ({"id": "q8_0", "kind": "honest", "recipe": "quantize"}, replies([480] * N)),
        ({"id": "q2_k", "kind": "damaged", "recipe": "quantize"}, replies([10] * N)),
        ({"id": "smaller-model", "kind": "damaged", "recipe": "other_model"}, None),
    ]
    header = Header(
        "L1",
        "sha256:" + "1" * 64,
        "llama-3.1-8b",
        "sha256:" + "2" * 64,
        {
            "tool": "llama.cpp",
            "repo": "ggml-org/llama.cpp",
            "commit": "cd959bae99ff4bed22bef2604f45241c09bbb8c8",
            "image": "local/ref-fidelity@sha256:" + "3" * 64,
        },
        "results/v1.0/fidelity/llama-3.1-8b/reference.jsonl",
        "sha256:" + "4" * 64,
    )
    doc = build_fidelity(
        header,
        RULE,
        REFERENCE,
        [(spec, r, None if r else "no replies", None) for spec, r in specs],
        {"sash": replies([512] * N), "flashprove": None},
        missing_cause={"flashprove": NOT_RUN},
    )
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    assert registry.errors("fidelity/1", json.loads(json.dumps(doc))) == []
    assert doc["bar"] == {"control": "q2_k", "mean_prefix": 10.0}
    rows = doc["rows"]
    assert isinstance(rows, dict)
    assert (rows["sash"]["state"], rows["flashprove"]["state"]) == ("held", "undecided")
    controls = doc["controls"]
    assert isinstance(controls, list)
    assert [c["status"] for c in controls] == ["ok", "ok", "ok", "failed"]


def test_kl_quantity_labels() -> None:
    q = kl_quantity(0.0313, "results/v1.0/fidelity/llama-3.1-8b/kl/q4_k_m.log")
    assert (q["unit"], q["scope"], q["grade"], q["source"]) == (
        "nat/token",
        None,
        "measured",
        {"kind": "adapter", "ref": "results/v1.0/fidelity/llama-3.1-8b/kl/q4_k_m.log"},
    )


def test_row_replies_join_proofs_and_order_slots() -> None:
    """FI-6: a request's proofs join in record order; slot k answers prompts [(k-1)N, kN)."""

    def run(first: int) -> dict[str, object]:
        return {"proofs": [
            {"request_index": 0, "claimed_output": [first, 1], "verdict": "accept"},
            {"request_index": 1, "claimed_output": [first, 2], "verdict": "accept"},
            {"request_index": 0, "claimed_output": [3], "verdict": "accept"},
        ]}  # fmt: skip

    assert session_replies(run(7)) == [[7, 1, 3], [7, 2]]
    sessions = {2: session_replies(run(20)), 1: session_replies(run(10))}
    assert row_replies({k: v for k, v in sessions.items() if v}, 2, 2) == [
        [10, 1, 3], [10, 2], [20, 1, 3], [20, 2],
    ]  # fmt: skip
    rejected = run(7)
    proofs = rejected["proofs"]
    assert isinstance(proofs, list)
    proofs[1]["verdict"] = "reject"
    assert session_replies(rejected) is None
    assert row_replies({1: [[1], [2]]}, 2, 2) is None  # slot 2 has no session


def kl_base_file(path: Path, records: list[tuple[float, float, list[int]]], n_vocab: int) -> None:
    """A llama.cpp `--kl-divergence-base` file: n_ctx 4 (one scored position per chunk), one
    chunk per record, each record two float32 then the codes padded to an even count."""
    n_ctx, n_chunk = 4, len(records)
    data = b"_logits_" + struct.pack("<Iii", n_ctx, n_vocab, n_chunk)
    data += struct.pack(f"<{n_ctx * n_chunk}i", *range(10, 10 + n_ctx * n_chunk))
    for scale, min_lp, codes in records:
        padded = codes + [0] * (2 * ((n_vocab + 1) // 2) - n_vocab)
        data += struct.pack("<ff", scale, min_lp) + struct.pack(f"<{len(padded)}H", *padded)
    path.write_bytes(data)


def test_kl_against_a_llama_cpp_base_file(tmp_path: Path) -> None:
    """The base holds p = (1/2, 1/4, 1/4) twice: scale ln 2, min -2 ln 2, codes (1, 0, 0). A
    uniform copy gives KL = 1/2 ln(3/2) + 1/2 ln(3/4) = 0.0588915; a copy equal to the base
    gives 0 (to float16 rounding). Mean over the two scored tokens: 0.0294457."""
    ln2 = math.log(2)
    path = tmp_path / "kl-base.kld"
    kl_base_file(path, [(ln2, -2 * ln2, [1, 0, 0])] * 2, 3)
    uniform = struct.pack("<3e", *[-1.0] * 3)
    same = struct.pack("<3e", -ln2, -2 * ln2, -2 * ln2)
    mean, count = mean_kl_against_base(path, lambda c: [uniform, same][c])
    assert count == 2
    assert abs(mean - (0.5 * math.log(1.5) + 0.5 * math.log(0.75)) / 2) < 2e-4
    base = read_kl_base(path)
    assert (base.first, base.scored) == (2, 1)
    assert scored_texts(base, 1) == [[1, 11, 12, 13], [1, 15, 16, 17]]
    with pytest.raises(ValueError, match="float16"):
        mean_kl_against_base(path, lambda c: uniform + uniform)
