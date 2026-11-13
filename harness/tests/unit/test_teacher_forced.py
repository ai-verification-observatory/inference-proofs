"""RFC-0018 FI-10 to FI-12 against hand-computed cases: a vocabulary of four tokens, known top
tokens and a known KL."""

from math import log
from pathlib import Path

import pytest

from iproofs.fidelity import SignFlipRule
from iproofs.teacher_forced import (
    Entry,
    Pass,
    above,
    agreement,
    build,
    kl_figure,
    measure_kl,
    position_kl,
    prompt_kl,
    read_topk,
    row_tests,
    score_pass,
    write_topk,
)

RULE = SignFlipRule(0.05, 20, 1000, "00" * 32)


def test_agreement_counts_positions_not_a_prefix() -> None:
    # reference reply 7 7 3 1: the top tokens differ at position 1 only, so 3 positions agree
    # (FI-3's matched prefix of the same lists would be 1)
    assert agreement([7, 2, 3, 1], [7, 7, 3, 1]) == 3
    assert agreement([0, 0, 0, 0], [7, 7, 3, 1]) == 0
    with pytest.raises(ValueError, match="top tokens"):
        agreement([7, 7], [7, 7, 3, 1])


def test_kl_of_a_full_small_vocabulary() -> None:
    # p = (1/2, 1/4, 1/8, 1/8), q = (1/4, 1/4, 1/4, 1/4), every token in both lists:
    # KL = 1/2 ln 2 + 1/4 ln 1 + 2 (1/8) ln (1/2) = 1/4 ln 2
    ids = [0, 1, 2, 3]
    p = [log(0.5), log(0.25), log(0.125), log(0.125)]
    q = [log(0.25)] * 4
    kl, rest = position_kl(ids, p, [3, 2, 1, 0], q)
    assert kl == pytest.approx(0.25 * log(2), abs=1e-12)
    assert rest == pytest.approx(0.0, abs=1e-12)
    assert position_kl(ids, p, ids, p)[0] == 0.0


def test_kl_pools_the_tokens_one_list_lacks() -> None:
    # reference lists tokens 0, 1 (1/2, 1/4); the engine lists 0, 2 (1/4, 1/2). Common: token
    # 0. Rest masses: 1/2 and 3/4. KL = 1/2 ln 2 + 1/2 ln (2/3)
    kl, rest = position_kl([0, 1], [log(0.5), log(0.25)], [0, 2], [log(0.25), log(0.5)])
    assert kl == pytest.approx(0.5 * log(2) + 0.5 * log(2 / 3), abs=1e-12)
    assert rest == pytest.approx(0.5)
    # the pooled value never exceeds the full one: with the full lists p = (1/2, 1/4, 1/4),
    # q = (1/4, 1/4, 1/2), KL = 1/2 ln 2 + 1/4 ln (1/2) = 1/4 ln 2, above 0.1438
    assert kl < 0.25 * log(2)


def test_prompt_kl_is_the_mean_over_positions(tmp_path: Path) -> None:
    ref = [([0, 1], [log(0.5), log(0.5)]), ([0, 1], [log(0.75), log(0.25)])]
    eng = [([0, 1], [log(0.5), log(0.5)]), ([0, 1], [log(0.5), log(0.5)])]
    write_topk(tmp_path / "r.topk", ref)
    write_topk(tmp_path / "e.topk", eng)
    found = prompt_kl(read_topk(tmp_path / "r.topk"), read_topk(tmp_path / "e.topk"))
    assert found is not None
    kl, rest, positions = found
    # position 0: 0. position 1: 3/4 ln (3/2) + 1/4 ln (1/2) = 0.130812; mean 0.065406
    want = (0.75 * log(1.5) + 0.25 * log(0.5)) / 2
    assert kl == pytest.approx(want, abs=1e-7)  # float32 log-probabilities
    assert rest == pytest.approx(0.0, abs=1e-6)
    assert positions == 2
    # a position where one side has no list is left out: only position 1 counts
    write_topk(tmp_path / "e2.topk", [([-1, -1], [0.0, 0.0]), eng[1]])
    found = prompt_kl(read_topk(tmp_path / "r.topk"), read_topk(tmp_path / "e2.topk"))
    assert found is not None
    assert found[0] == pytest.approx(2 * want, abs=1e-7)
    assert found[2] == 1
    write_topk(tmp_path / "e3.topk", [([-1, -1], [0.0, 0.0])] * 2)
    assert prompt_kl(read_topk(tmp_path / "r.topk"), read_topk(tmp_path / "e3.topk")) is None
    (tmp_path / "bad").write_bytes(b"nope")
    with pytest.raises(ValueError, match="not a top-k file"):
        read_topk(tmp_path / "bad")


def test_a_failed_prompt_of_a_system_scores_zero_and_is_listed() -> None:
    reference = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 9, 9, 9]]
    run = Pass("sys", ((1, 2, 3, 0), None, (9, 9, 9, 9)), {1: "range condition failed"})
    row = score_pass(run, reference, system=True)
    assert row.status == "ok"
    assert row.scores == (3, 0, 4)
    assert row.failed == ((1, "range condition failed"),)
    assert row.mean == pytest.approx(7 / 3)
    assert row.mean_not_failed == 3.5
    assert row.median == 3.0
    # a control with such a prompt did not run as a whole: no engine result is made of it
    control = score_pass(run, reference, system=False)
    assert control.status == "failed"
    assert control.cause == "prompt 1: range condition failed"
    assert score_pass(Pass("c", None, {}, "not run: left out"), reference, system=False).cause \
        == "not run: left out"  # fmt: skip


def test_tests_against_each_control_are_exact_at_small_n() -> None:
    reference = [[1, 1, 1, 1]] * 4
    full = score_pass(Pass("row", tuple((1, 1, 1, 1) for _ in range(4)), {}), reference,
                      system=True)  # fmt: skip
    low = score_pass(Pass("ctl", tuple((1, 0, 0, 0) for _ in range(4)), {}), reference,
                     system=False)  # fmt: skip
    # differences 3, 3, 3, 3: only the all-plus sign vector reaches the observed sum, 1 of 16
    assert above(full, low, RULE).p == 1 / 16
    assert above(low, full, RULE).p == 1.0
    tests = row_tests(full, [low, score_pass(Pass("gone", None, {}), reference, system=False)],
                      RULE)  # fmt: skip
    assert [(t.a, t.b) for t in tests] == [("row", "ctl"), ("ctl", "row")]


def test_kl_figure_is_the_mean_over_prompts_with_a_value() -> None:
    q = kl_figure([0.1, None, 0.3], [0.01, None, 0.03], [512, 0, 510], "x#kl", "note")
    assert q is not None
    assert q["value"] == pytest.approx(0.2)
    assert q["n"] == 2
    assert q["positions"] == 1022
    assert q["unit"] == "nat/token"
    assert q["reference_rest_mass"] == pytest.approx(0.02)
    assert kl_figure([None], [None], [0], "x", "note") is None


def test_a_listed_token_of_probability_zero_adds_nothing() -> None:
    kl, _ = position_kl([0, 1], [log(1.0), float("-inf")], [0, 1], [log(0.5), log(0.5)])
    assert kl == pytest.approx(log(2))


def test_document_holds_scores_tests_and_kl(tmp_path: Path) -> None:
    reference = [[1, 1, 1, 1]] * 4
    for name, q in (("reference", 0.5), ("ctl", 0.5), ("row", 0.25)):
        (tmp_path / name).mkdir()
        for i in range(4):
            rows = (
                [([1, 2], [log(0.5), log(0.5)])] * 4
                if name == "reference"
                else [([1, 2], [log(q), log(1 - q)])] * 4
            )
            write_topk(tmp_path / name / f"{i}.topk", rows)
    full = tuple((1, 1, 1, 1) for _ in range(4))
    ctl = Entry(
        {"id": "ctl", "kind": "honest", "recipe": "quantize", "type": "Q8_0"},
        score_pass(Pass("ctl", tuple((1, 0, 0, 0) for _ in range(4)), {}), reference, system=False),
        "run-controls.json",
        measure_kl(tmp_path / "reference", tmp_path / "ctl", 4),
    )
    row = Entry(
        {"id": "row"},
        score_pass(Pass("row", full, {}), reference, system=True),
        "run-row.json",
        measure_kl(tmp_path / "reference", tmp_path / "row", 4),
    )
    gone = Entry(
        {"id": "gone", "kind": "damaged", "recipe": "drop_blocks"},
        score_pass(Pass("gone", None, {}, "not run: no file"), reference, system=False),
        None,
        None,
    )
    doc = build(
        {"rung": "r", "n": 4},
        RULE,
        None,
        [ctl, gone],
        [row],
        "kl.json",
        True,
        {"row": "the system's extractor"},
    )
    assert doc["gating"] is False
    controls: list[dict[str, object]] = doc["controls"]  # type: ignore[assignment]
    assert [c["mean"] for c in controls] == [1.0, None]
    assert controls[1]["cause"] == "not run: no file"
    assert controls[0]["kl"]["value"] == 0.0  # type: ignore[index]
    assert controls[1]["kl"] is None
    rows_out: dict[str, dict[str, object]] = doc["rows"]  # type: ignore[assignment]
    out = rows_out["row"]
    assert (out["mean"], out["median"]) == (4.0, 4.0)
    # p = (1/2, 1/2), q = (1/4, 3/4): KL = 1/2 ln 2 + 1/2 ln (2/3)
    assert out["kl"]["value"] == pytest.approx(0.5 * log(2) + 0.5 * log(2 / 3), abs=1e-6)  # type: ignore[index]
    assert out["kl"]["n"] == 4  # type: ignore[index]
    assert out["label"] == (
        "computed by the system's own code on the reference reply, not by the proved computation"
    )
    tests: list[dict[str, object]] = out["tests"]  # type: ignore[assignment]
    assert [(t["a"], t["b"], t["p"]) for t in tests] == [
        ("row", "ctl", 1 / 16),
        ("ctl", "row", 1.0),
    ]
