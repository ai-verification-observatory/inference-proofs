"""RFC-0018 §The glyph: each line of the five decision tables (UF, MC, WH, FM, NT) on hand-built
inputs, the offline properties checks, and the board's glyph from synthetic records. Each case
asserts (step, cause, basis, lowered_by), never wording."""

import json
from pathlib import Path

import pytest
import yaml

from fixtures.board import (
    PIN,
    RELEASE,
    SYSTEM,
    TOOLCHAIN,
    WORKLOAD,
    Tree,
    fact,
    fidelity,
    fidelity_row,
    properties2,
    quote,
    three_sessions,
)
from iproofs.board import build_board
from iproofs.errors import IProofsError
from iproofs.fidelity import Header, SignFlipRule, build_fidelity
from iproofs.glyph import (
    PETALS,
    Coverage,
    Petal,
    faithful_model,
    load_properties,
    machine_checked,
    no_trusted_party,
    not_read_rows,
    properties_problems,
    statement_petals,
    unforgeable,
    weights_hidden,
)
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
HELD = dict.fromkeys(("run", "model", "prompt", "reply", "no_weight_file", "fidelity"), "held")
ONE = Coverage("request", 1)  # one reply per proof
GREEN = ("green", None, "statement", ())
NOT_READ = (None, "not_read", "statement", ())


def got(petal: Petal) -> tuple[object, ...]:
    assert petal.state == {"green": "green", "amber_upper": "amber", "amber_lower": "amber",
                           "red": "red", None: "hollow"}[petal.step]  # fmt: skip
    return petal.step, petal.cause, petal.basis, petal.lowered_by


def amber_lower(basis: str = "statement") -> tuple[object, ...]:
    return ("amber_lower", None, basis, ())


def amber_upper(basis: str = "statement") -> tuple[object, ...]:
    return ("amber_upper", None, basis, ())


def red(cause: str, basis: str = "statement", lowered: tuple[str, ...] = ()) -> tuple[object, ...]:
    return ("red", cause, basis, lowered)


def uf(coverage: Coverage = ONE, checks: dict[str, str] = HELD, **bound: object) -> Petal:
    return unforgeable(properties2(bound=bound), checks, PIN, coverage)


# ---------------------------------------------------------------- Unforgeable


def test_uf1_failed_check_is_red_even_unread() -> None:
    """UF-1 before UF-2: a failed Reply check with no properties file is red, check_failed."""
    failed = {**HELD, "reply": "failed", "model": "failed"}
    assert got(unforgeable(None, failed, PIN, ONE)) == red("check_failed", "test",
                                                           ("model", "reply"))  # fmt: skip
    assert got(uf(checks={**HELD, "prompt": "failed"})) == red("check_failed", "test", ("prompt",))
    assert got(uf(checks={**HELD, "reply": "undecided"})) == GREEN  # undecided lowers nothing


def test_uf2_not_read() -> None:
    assert got(unforgeable(None, HELD, PIN, ONE)) == NOT_READ
    assert got(unforgeable(properties2(commit="b" * 40), HELD, PIN, ONE)) == NOT_READ
    old = {**properties2(), "schema": "properties/1"}
    assert got(unforgeable(old, HELD, PIN, ONE)) == NOT_READ
    assert got(unforgeable(properties2(), HELD, None, ONE)) == NOT_READ  # U7: no row commit


def test_uf3_not_stated() -> None:
    assert got(uf(stated=False, expression=None, terms=[])) == red("not_stated")
    assert got(uf(terms=[])) == red("not_stated")


def test_uf4_weaker_adversary() -> None:
    assert got(uf(adversary="weaker")) == red("stated")


def test_uf5_under_80_strict() -> None:
    assert got(uf(terms=[130, 79])) == red("stated")
    assert got(uf(terms=[130, 80])) == amber_lower()  # proved, covers, 80 < 100: UF-9


def test_uf6_conjectured_under_100_strict() -> None:
    assert got(uf(basis="conjectured", terms=[99])) == red("stated")
    assert got(uf(basis="not_said", terms=[99])) == red("stated")
    assert got(uf(basis="conjectured", terms=[100])) == amber_lower()


def test_uf7_green() -> None:
    assert got(uf(terms=[128, 130])) == GREEN
    assert got(uf(unit="proof", terms=[128, 130])) == GREEN  # one reply per proof


def test_uf8_amber_upper() -> None:
    assert got(uf(terms=[124, 101])) == amber_upper()
    assert got(uf(terms=[100])) == amber_upper()  # 100 is not under 100
    assert got(uf(terms=[100, 128])) == amber_upper()


@pytest.mark.parametrize(
    ("coverage", "bound"),
    [
        (ONE, {"basis": "conjectured"}),
        (Coverage("request", 24), {"unit": "proof"}),  # no bound said for batch members
        (Coverage("request", 24), {"batch": "together"}),  # only for members handed in at once
        (Coverage("segment_grid", 1), {"unit": "proof"}),  # more than one reply per proof
        (Coverage(None, 1), {"unit": "proof"}),  # replies per proof not recorded
        (Coverage("request", None), {"unit": "proof"}),  # batch size not recorded
        (Coverage("request", None), {"batch": "each_member"}),
        (ONE, {"program": "not_stated"}),  # U3: not stated for the verifier program run
        (ONE, {"unit": "part"}),
        (ONE, {"conditions_shown": False}),
        (ONE, {"parameters": "not_said"}),
        (ONE, {"adversary": "not_said"}),
        (ONE, {"terms": [124, 90]}),  # proved, under 100
    ],
)
def test_uf9_amber_lower(coverage: Coverage, bound: dict[str, object]) -> None:
    assert got(unforgeable(properties2(bound=bound), HELD, PIN, coverage)) == amber_lower()


def test_uf5_covers_the_run() -> None:
    """U4, U5: one proof per request covers one reply whatever the batch size; a batch of 24
    is covered when the bound is stated for each member checked alone; a program stated or
    proved to implement the verifier the bound is about covers the run."""
    each = uf(Coverage("request", 24), unit="proof", batch="each_member", terms=[128, 130])
    assert got(each) == GREEN
    assert got(uf(Coverage("request", 24), unit="reply", batch="each_member")) == GREEN
    assert got(uf(program="proved")) == GREEN
    assert got(uf(Coverage("request", 1), batch="together")) == GREEN  # batch 1: nothing to say


def test_uf_brief_rows() -> None:
    """Brief §4: FlashProve (proved, [124, 101], per proof, bound for members handed in
    together, batch 24, conditions not shown, not claimed for cp_verify) and SASH
    (conjectured, [100], per part) are both amber in lesser part."""
    flashprove = uf(Coverage("request", 24), unit="proof", terms=[124, 101], batch="together",
                    conditions_shown=False, program="not_stated")  # fmt: skip
    sash = uf(Coverage("segment_grid", 1), basis="conjectured", unit="part", terms=[100],
              adversary="not_said", conditions_shown=False)  # fmt: skip
    assert got(flashprove) == got(sash) == amber_lower()


# ---------------------------------------------------------------- Machine-checked


def build(commit: str = PIN, theorem: str = "Fake.Verifier.sound", status: str = "built",
          axioms: tuple[str, ...] = ("classic",), exit_code: int | None = None,
          version: str = TOOLCHAIN["version"],
          repo: str = "example/fake-prover") -> dict[str, object]:  # fmt: skip
    return {"schema": "proof-build/1", "system": SYSTEM,
            "upstream": {"repo": repo, "commit": commit},
            "theorem": {"name": theorem, "url": "https://example.org/t"},
            "toolchain": {"name": TOOLCHAIN["name"], "version": version,
                          "image": "sha256:" + "5" * 64},
            "status": status,
            "exit_code": (0 if status == "built" else 1) if exit_code is None else exit_code,
            "last_lines": ["x"], "axioms_reported": list(axioms)}  # fmt: skip


def mc(build_: dict[str, object] | None = None, checks: dict[str, str] = HELD,
       **formal: object) -> Petal:  # fmt: skip
    return machine_checked(properties2(formal=formal), checks, PIN, build_)


def test_mc1_not_read() -> None:
    petal = machine_checked(None, HELD, PIN, build())
    assert got(petal) == NOT_READ
    assert petal.formal is None


def test_mc2_stated_red() -> None:
    assert got(mc(build(), reach="not_stated")) == red("not_stated")
    assert got(mc(build(), reach="none")) == red("stated")
    # a stated red keeps its own cause, even with a failed check and a failed build (O5)
    failed = mc(build(status="failed"), {**HELD, "model": "failed"}, reach="not_stated")
    assert got(failed) == red("not_stated")


def test_mc3_failed_check_lowers_green_only() -> None:
    model_failed = {**HELD, "model": "failed"}
    assert got(mc(build(), model_failed)) == red("check_failed", "test", ("model",))
    stated_upper = mc(None, model_failed, reach="protocol_and_statement")
    assert got(stated_upper) == (None, "proof_build_not_run", "statement", ())


def test_mc4_build_failed_or_axioms_differ() -> None:
    lowered = red("check_failed", "test", ("proof_build",))
    assert got(mc(build(status="failed"))) == lowered
    assert got(mc(build(axioms=("classic", "sorryAx")))) == lowered
    assert got(mc(build(axioms=()))) == lowered
    assert got(mc(build(exit_code=1))) == lowered  # M4: built with a nonzero exit is no build
    assert got(mc(build(status="crashed"))) == lowered


def test_mc5_no_matching_build_is_hollow() -> None:
    hollow = (None, "proof_build_not_run", "statement", ())
    assert got(mc(None)) == hollow
    assert got(mc(build(commit="b" * 40))) == hollow  # another commit is no record
    assert got(mc(build(theorem="Other.sound"))) == hollow
    assert got(mc(build(repo="example/other"))) == hollow
    assert got(mc(build(version="8.19.0"))) == hollow  # M2: another toolchain is no record
    assert got(mc(build(), toolchain=None)) == hollow  # no toolchain pinned: nothing matches
    assert got(machine_checked(properties2(), HELD, None, build())) == NOT_READ  # U7


@pytest.mark.parametrize(
    ("formal", "step"),
    [
        ({}, "green"),
        ({"reach": "part"}, "amber_lower"),
        ({"reach": "protocol"}, "amber_lower"),
        ({"reach": "protocol_and_statement"}, "amber_upper"),
        ({"input_code_unverified": True}, "amber_upper"),
        ({"input_code_unverified": None}, "amber_upper"),
        ({"trusted_base": [], "axioms": []}, "amber_upper"),
    ],
)
def test_mc6_stated_step_with_a_build(formal: dict[str, object], step: str) -> None:
    declared = formal.get("axioms", ["classic"])
    assert isinstance(declared, list)
    petal = machine_checked(properties2(formal=formal), HELD, PIN, build(axioms=tuple(declared)))
    assert got(petal) == (step, None, "statement", ())
    assert petal.formal is not None
    assert petal.formal["stated_step"] == step


# ---------------------------------------------------------------- Weights hidden


def wh(checks: dict[str, str] = HELD, **hiding: object) -> Petal:
    return weights_hidden(properties2(hiding=hiding), checks, PIN)


FITTED = [{"item": "Settings fitted to the weights.", "tag": "fitted_to_weights",
           "quotes": [quote("Settings fitted to the weights.")]}]  # fmt: skip


def test_wh1_failed_check() -> None:
    failed = {**HELD, "no_weight_file": "failed"}
    petal = wh(failed)
    assert got(petal) == red("check_failed", "test", ("no_weight_file",))
    assert petal.visible is not None
    unread = weights_hidden(None, failed, PIN)
    assert got(unread) == red("check_failed", "test", ("no_weight_file",))
    assert unread.visible is None


def test_wh2_not_read() -> None:
    petal = weights_hidden(None, HELD, PIN)
    assert (got(petal), petal.visible) == (NOT_READ, None)


def test_wh3_red() -> None:
    assert got(wh(verifier_gets_weights=True)) == red("stated")
    assert got(wh(stated=False)) == red("stated")
    assert got(wh(stated="not_stated")) == red("not_stated")


def test_wh4_no_theorem() -> None:
    assert got(wh(proof="none")) == amber_lower()


def test_wh5_green() -> None:
    assert got(wh()) == GREEN
    assert got(wh(visible=[])) == amber_upper()  # W1: a list said to be published, none copied


@pytest.mark.parametrize(
    "hiding",
    [
        {"proof": "protocol"},
        {"programs": "expected"},
        {"programs": "not_stated"},
        {"visible_listed": False},
        {"visible": FITTED},
    ],
)
def test_wh6_each_missing_condition(hiding: dict[str, object]) -> None:
    assert got(weights_hidden(properties2(hiding=hiding), HELD, PIN)) == amber_upper()


# ---------------------------------------------------------------- No third party trusted


def nt(**trust: object) -> Petal:
    return no_trusted_party(properties2(trust=trust), PIN)


def test_nt_lines() -> None:
    assert got(no_trusted_party(None, PIN)) == NOT_READ  # NT-1
    assert got(nt(rests_on="not_stated")) == red("not_stated")  # NT-2
    for r in ("single_party_setup", "hardware_key", "trusted_key"):  # NT-3
        assert got(nt(rests_on=r)) == red("stated")
    assert got(nt(rests_on="fixed_parties")) == amber_lower()  # NT-4
    assert got(nt(publicly_checkable=False)) == amber_lower()  # transparent, not checkable
    assert got(nt(rests_on="open_ceremony", publicly_checkable=False)) == amber_lower()
    assert got(nt(rests_on="open_ceremony")) == amber_upper()  # NT-5
    assert got(nt()) == GREEN  # NT-6
    assert got(nt(publicly_checkable="not_said")) == GREEN


def test_reading_flag_follows_the_notes_read() -> None:
    """N1: a petal whose decision read a fact with a note is marked as a reading; a note on a
    fact the decision did not read, or no note, leaves it unmarked."""
    noted = {"value": "transparent", "quotes": [quote("q")], "note": "our reading"}
    assert nt(rests_on=noted).reading is True
    assert got(nt(rests_on=noted)) == GREEN
    assert nt().reading is False
    assert "reading" not in nt().tree()
    assert nt(rests_on=noted).tree()["reading"] is True
    later = {"value": "row", "quotes": [quote("q")], "note": "n"}  # read after the basis fails
    assert uf(basis="conjectured", terms=[100], parameters=later).reading is False
    assert uf(parameters=later).reading is True


def test_real_properties_files() -> None:
    """Section 5 of the fixes: the stored properties files of FlashProve and SASH through the
    decision functions, held checks, no proof build, at each file's pin, with each system's
    granularity and the row's batch size (FlashProve 24; SASH None and 1)."""

    def steps(system: str, batch: int | None) -> list[tuple[object, object]]:
        props = load_properties(ROOT, system)
        assert props is not None
        pin = str(props["upstream"]["commit"])  # type: ignore[index]
        found = yaml.safe_load((ROOT / "systems" / system / "system.yaml").read_text())
        coverage = Coverage(found["proofs"]["granularity"], batch)
        petals = statement_petals(props, HELD, pin, coverage, None)
        return [
            (petals[p].step, petals[p].cause)
            for p in ("unforgeable", "weights_hidden", "machine_checked", "no_trusted_party")
        ]

    workload = yaml.safe_load((ROOT / "workloads/l1-maverick-p512-o512.yaml").read_text())
    assert steps("flashprove", workload["shape"]["batch_size"]) == [
        ("amber_lower", None), ("amber_upper", None), (None, "proof_build_not_run"),
        ("green", None)]  # fmt: skip
    for batch in (None, 1):
        assert steps("sash", batch) == [("amber_lower", None), ("red", "not_stated"),
                                        ("red", "not_stated"), ("red", "not_stated")]  # fmt: skip


def test_a_silent_red_carries_its_documents_read() -> None:
    """GL-1: a `not_stated` red carries the petal's `sources_read`, each linked at the pin; no
    other petal carries any. SASH's No third party trusted read four files at 4f41667."""
    props = load_properties(ROOT, "sash")
    assert props is not None
    pin = str(props["upstream"]["commit"])  # type: ignore[index]
    petals = statement_petals(props, HELD, pin, Coverage("part", 1), None)
    assert "sources_read" not in petals["unforgeable"].tree()
    got_ = petals["no_trusted_party"].tree()["sources_read"]
    base = f"https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/{pin}/"
    docs = ("README.md", "prover/README.md", "docs/statement.md", "prover/src/compose.rs")
    assert got_ == [{"path": d, "url": base + d} for d in docs]


def test_deepprove_without_a_file_is_not_read() -> None:
    """Brief §4: no properties file, every statement petal hollow, not read."""
    petals = statement_petals(None, HELD, PIN, Coverage("request", 1), None)
    assert {got(p) for p in petals.values()} == {NOT_READ}
    assert set(petals) == {"unforgeable", "weights_hidden", "machine_checked", "no_trusted_party"}


# ---------------------------------------------------------------- Faithful model


def fdoc(row: list[int], *, slots: int | None = 1, q8: str = "ok", q4: str = "ok",
         scores: tuple[int, int, int] = (6, 4, 2)) -> dict[str, object]:  # fmt: skip
    """n = 5, exact. By default rerun [6]*5, q8_0 [4]*5, q4_k_m [2]*5 (`scores`), so S_green =
    30 + 20 = 50 and T_green = 50 / 10 = 5, S_upper = 20 + 10 = 30 and T_upper = 3. `q4` is ok,
    failed or none (no Q4_K_M control). The step tests' p are counted by hand: d_i = 10 s_i - S,
    all five d_i equal; d > 0 gives p = 1/32 (only the observed sign vector reaches the sum),
    d <= 0 gives p = 1 (every vector reaches it)."""
    r, a, b = scores

    def p(d: int) -> float:
        return 1 / 32 if d > 0 else 1.0

    def test(name: str, value: float, total: int) -> dict[str, object]:
        return {"threshold": name, "value": value, "n": 5, "p": p(10 * row[0] - total),
                "method": "exact", "seed": None}  # fmt: skip

    green_ok, upper_ok = q8 == "ok", q8 == "ok" and q4 == "ok"
    q4_control = {"id": "q4_k_m", "status": q4, "scores": [b] * 5 if q4 == "ok" else []}
    upper_cause = "no Q4_K_M control on this rung" if q4 == "none" else (
        "q8_0 failed" if not green_ok else "q4_k_m failed")  # fmt: skip
    doc: dict[str, object] = {
        "test": {"alpha": 0.05, "exact_up_to": 20, "resamples": 1000},
        "controls": [
            {"id": "reference-2", "status": "ok", "scores": [r] * 5},
            {"id": "q8_0", "status": q8, "scores": [a] * 5 if green_ok else []},
            *([q4_control] if q4 != "none" else []),
        ],
        "steps": {
            "green": {"controls": ["reference-2", "q8_0"],
                      "value": (5 * r + 5 * a) / 10 if green_ok else None,
                      "cause": None if green_ok else "q8_0 failed"},
            "upper": {"controls": ["q8_0", "q4_k_m"] if q4 != "none" else ["q8_0"],
                      "value": (5 * a + 5 * b) / 10 if upper_ok else None,
                      "cause": None if upper_ok else upper_cause},
        },
        "rows": {SYSTEM: {"scores": row, "step_tests": {
            "green": test("T_green", (5 * r + 5 * a) / 10, 5 * r + 5 * a) if green_ok else None,
            "upper": test("T_upper", (5 * a + 5 * b) / 10, 5 * a + 5 * b) if upper_ok else None,
        }}},
    }  # fmt: skip
    if slots is not None:
        doc["slots"] = slots
    return doc


def fm(doc: dict[str, object] | None, state: str = "held", policy: str | None = "exact_match",
       cause: str | None = None,
       level_alpha: float | None = None) -> tuple[object, ...]:  # fmt: skip
    return got(faithful_model(state, cause, doc, SYSTEM, policy, level_alpha))


def test_fm1_failed() -> None:
    assert fm(fdoc([7] * 5), "failed") == red("check_failed", "test", ("fidelity",))


def test_fm2_not_decided() -> None:
    hollow = (None, "not_decided", "test", ())
    assert fm(None) == hollow
    assert fm(fdoc([7] * 5), "undecided", cause="not resolved") == hollow
    assert fm({**fdoc([7] * 5), "rows": {}}) == hollow


def test_fm3_policy_other_than_exact_match() -> None:
    assert fm(fdoc([7] * 5), policy="tolerance") == amber_lower("test")
    assert fm(fdoc([7] * 5), policy=None) == amber_lower("test")  # no claim card


def test_fm4_controls_missing() -> None:
    """F1: T_green or T_upper without a value, or no step tests: amber in lesser part, even for
    a row far above both thresholds."""
    assert fm(fdoc([7] * 5, q8="failed")) == amber_lower("test")
    assert fm(fdoc([7] * 5, q4="failed")) == amber_lower("test")
    assert fm(fdoc([7] * 5, q4="none")) == amber_lower("test")
    no_steps = fdoc([7] * 5)
    del no_steps["steps"]
    assert fm(no_steps) == amber_lower("test")


def test_fm5_to_fm7_hand_counted() -> None:
    """[7]*5: d_green = 70 - 50 = 20, p = 1/32 < 0.05, and d_upper = 70 - 30 = 40, p = 1/32:
    green with one slot, amber in part with two or with none recorded. [5]*5: d_green = 0,
    p = 1; d_upper = 50 - 30 = 20, p = 1/32: amber in part. [3]*5: d_upper = 0, p = 1: amber in
    lesser part."""
    assert fm(fdoc([7] * 5)) == ("green", None, "test", ())
    assert fm(fdoc([7] * 5, slots=2)) == amber_upper("test")
    assert fm(fdoc([7] * 5, slots=None)) == amber_upper("test")
    assert fm(fdoc([5] * 5)) == amber_upper("test")
    assert fm(fdoc([3] * 5)) == amber_lower("test")


def test_fm_slots_need_t_upper_for_amber_in_part() -> None:
    """F3, F4: with 2 slots the row needs T_upper for amber in part. Q4_K_M failed: [7]*5 is
    shown above T_green (p = 1/32) and is amber in lesser part. T_upper above T_green (rerun
    [2]*5, q8_0 [4]*5, q4_k_m [8]*5: T_green = 30 / 10 = 3, T_upper = 60 / 10 = 6): [5]*5 has
    d_green = 50 - 30 = 20, p = 1/32, and d_upper = 50 - 60 < 0, p = 1: green with one slot,
    amber in lesser part with two."""
    assert fm(fdoc([7] * 5, slots=2, q4="failed")) == amber_lower("test")
    crossed = (2, 4, 8)
    assert fm(fdoc([5] * 5, scores=crossed)) == ("green", None, "test", ())
    assert fm(fdoc([5] * 5, slots=2, scores=crossed)) == amber_lower("test")


def test_fm_recheck_stops_on_a_typed_threshold() -> None:
    doc = fdoc([7] * 5)
    doc["steps"]["green"]["value"] = 5.5  # type: ignore[index]
    with pytest.raises(IProofsError, match=r"T_green 5\.5, its controls give 5\.0"):
        faithful_model("held", None, doc, SYSTEM, "exact_match")


@pytest.mark.parametrize(
    ("key", "field", "value"),
    [
        ("green", "value", 4.0),  # a test over another threshold value
        ("green", "n", 4),
        ("upper", "threshold", "T_green"),
        ("green", "p", 0.01),  # an exact p the scores do not give (1/32)
    ],
)
def test_fm_step_tests_tied_to_the_thresholds(key: str, field: str, value: object) -> None:
    """F5: a stored step test that is not the test of the row's scores over the stored threshold
    stops the board."""
    doc = fdoc([7] * 5)
    doc["rows"][SYSTEM]["step_tests"][key][field] = value  # type: ignore[index]
    with pytest.raises(IProofsError):
        faithful_model("held", None, doc, SYSTEM, "exact_match")


def test_fm_alpha_is_the_stored_test_alpha() -> None:
    """F5: no default alpha; the stored one must be the level's."""
    assert fm(fdoc([7] * 5), level_alpha=0.05) == ("green", None, "test", ())
    with pytest.raises(IProofsError):
        faithful_model("held", None, fdoc([7] * 5), SYSTEM, "exact_match", 0.01)
    doc = fdoc([7] * 5)
    del doc["test"]
    with pytest.raises(IProofsError):
        faithful_model("held", None, doc, SYSTEM, "exact_match")


N = 15
REFERENCE = [[1000 * i + j for j in range(512)] for i in range(N)]


def replies(prefixes: list[int]) -> list[list[int]]:
    return [ref[:k] + [-1 - t for t in ref[k:]] for ref, k in zip(REFERENCE, prefixes, strict=True)]


def test_four_of_fifteen_diverging_at_the_first_token_is_not_green() -> None:
    """An exact rerun (512 on every prompt), Q8_0 at 480 and Q4_K_M at 300 on every prompt:
    T_green = (7680 + 7200) / 30 = 496, T_upper = (7200 + 4500) / 30 = 390. The row matches on
    11 prompts and diverges at the first token on 4 (score 0, mean 375.5): it held over the bar
    (q2_k at 10), but d_green = 30 s - 14880 sums to 11 * 480 - 4 * 14880 < 0 and d_upper =
    30 s - 11700 to 11 * 3660 - 4 * 11700 < 0, so neither threshold is shown: not green."""
    specs = [
        ({"id": "reference-2", "kind": "honest", "recipe": "rerun"}, [512] * N),
        ({"id": "q8_0", "kind": "honest", "recipe": "quantize", "type": "Q8_0"}, [480] * N),
        ({"id": "q4_k_m", "kind": "honest", "recipe": "quantize", "type": "Q4_K_M"}, [300] * N),
        ({"id": "q2_k", "kind": "damaged", "recipe": "quantize", "type": "Q2_K"}, [10] * N),
    ]
    header = Header("L1", "sha256:" + "1" * 64, "llama-3.1-8b", "sha256:" + "2" * 64, {},
                    "results/v1.0/fidelity/llama-3.1-8b/reference.jsonl", "sha256:" + "4" * 64,
                    1)  # fmt: skip
    rule = SignFlipRule(0.05, 20, 1000, "ab" * 32)
    doc = build_fidelity(header, rule, REFERENCE,
                         [(s, replies(p), None, None) for s, p in specs],
                         {SYSTEM: replies([512] * 11 + [0] * 4)})  # fmt: skip
    row = doc["rows"][SYSTEM]  # type: ignore[index]
    assert row["state"] == "held"
    assert doc["steps"]["green"]["value"] == 496.0  # type: ignore[index]
    assert doc["steps"]["upper"]["value"] == 390.0  # type: ignore[index]
    assert row["step_tests"]["green"]["p"] >= 0.5
    petal = faithful_model("held", None, json.loads(json.dumps(doc)), SYSTEM, "exact_match")
    assert got(petal) == amber_lower("test")


# ---------------------------------------------------------------- offline checks


def problems(doc: dict[str, object], pin: str | None = PIN) -> list[str]:
    return properties_problems(doc, Path("systems") / SYSTEM, pin)


def test_properties_problems() -> None:
    assert problems(properties2()) == []
    assert len(problems(properties2(), "b" * 40)) == 1  # system.yaml pins another commit
    assert len(problems(properties2(system="other"))) == 1
    doc = properties2(bound={"expression": fact("2^-130 + 2^-128", "at most 2^-131")})
    assert len(problems(doc)) == 1
    assert len(problems(properties2(bound={"terms": [130, 127]}))) == 1  # 127 not in it
    weak = {"expression": fact("2^-130 + 2^-60", "at most 2^-130 + 2^-60")}
    assert len(problems(properties2(bound={**weak, "terms": [130]}))) == 1  # U1: 60 left out
    assert problems(properties2(bound={**weak, "terms": [130, 60]})) == []
    assert len(problems(properties2(bound={"terms": [13, 12]}))) == 1  # substrings of 130, 128
    bits = {"expression": fact("100 conjectured bits", "at 100 conjectured bits")}
    assert problems(properties2(bound={**bits, "terms": [100]})) == []
    assert len(problems(properties2(bound={**bits, "terms": [10]}))) == 1  # not a whole number
    for form in (
        "2^\u2212130 + 2^\u221260",
        "2^{-130} + 2^{-60}",
        "2**-130 + 2**-60",
    ):  # other notations
        other_form = {"expression": fact(form, f"at most {form}")}
        assert len(problems(properties2(bound={**other_form, "terms": [130]}))) == 1
        assert problems(properties2(bound={**other_form, "terms": [130, 60]})) == []
    two = {"expression": fact("130 bits + 60 bits", "130 bits + 60 bits")}
    assert len(problems(properties2(bound={**two, "terms": [130]}))) == 1  # 60 left out
    base = {"trusted_base": fact(["Coq's kernel", "classic", "funext"], "Coq's kernel, classic")}
    assert len(problems(properties2(formal=base))) == 1
    assert len(problems(properties2(formal={"axioms": ["classic", "sorryAx"]}))) == 1
    other = properties2()
    other["petals"]["no_trusted_party"]["trust"]["rests_on"]["quotes"] = [  # type: ignore[index]
        quote("x", commit="b" * 40)
    ]
    assert len(problems(other)) == 1  # a quote url at another commit


def petal_tree(pid: str, state: str, cause: str | None) -> dict[str, object]:
    return {"id": pid, "state": state, "cause": cause}


def test_not_read_rows() -> None:
    board = {"rungs": [{"id": "r1", "rows": [
        {"system": "a", "glyph": [petal_tree("unforgeable", "hollow", "not_read"),
                                  petal_tree("faithful_model", "hollow", "not_decided")]},
        {"system": "b", "glyph": [petal_tree("unforgeable", "red", "not_stated"),
                                  petal_tree("no_trusted_party", "hollow", "not_read")]},
    ]}]}  # fmt: skip
    assert not_read_rows(board) == ["r1/a: unforgeable not read", "r1/b: no_trusted_party not read"]


# ---------------------------------------------------------------- the board's glyph


def test_board_glyph(tmp_path: Path) -> None:
    """The 8B row with a properties/2 file (proved [130, 128] per proof, no_trusted_party not
    stated), one reply per proof (granularity request, batch 1), an exact-match claim card, and
    a fidelity.json whose steps put the row above T_green with one slot: rerun 510, Q8_0 480,
    Q4_K_M 300 on all 15 prompts, T_green = (7650 + 7200) / 30 = 495, T_upper = 390; the row's
    500s give d_green = 150 on each prompt, p = 1 / 2^15."""
    tree = Tree(tmp_path)
    three_sessions(tree)
    system = tmp_path / "systems" / SYSTEM
    flags = {"forbidden_flags": ["--unsound-skip-"], "proofs": {"granularity": "request"}}
    system.joinpath("system.yaml").write_text(yaml.safe_dump(flags))
    workload = tmp_path / "workloads" / f"{WORKLOAD}.yaml"
    workload.parent.mkdir()
    workload.write_text(yaml.safe_dump({"shape": {"batch_size": 1}}))
    system.joinpath("claim.yaml").write_text(
        yaml.safe_dump({"coverage": {"policy": {"kind": "exact_match"}}})
    )
    system.joinpath("properties.yaml").write_text(json.dumps(
        properties2(bound={"unit": "proof"}, trust={"rests_on": "not_stated"})))  # fmt: skip
    controls = [{"id": c, "kind": "honest", "recipe": r, "status": "ok", "scores": [s] * 15,
                 "mean_prefix": float(s), "kl": None}
                for c, r, s in (("reference-2", "rerun", 510), ("q8_0", "quantize", 480),
                                ("q4_k_m", "quantize", 300))]  # fmt: skip
    steps = {"rule": "r", "seed_rule": "s",
             "green": {"controls": ["reference-2", "q8_0"], "value": 495.0, "cause": None},
             "upper": {"controls": ["q8_0", "q4_k_m"], "value": 390.0, "cause": None}}  # fmt: skip

    def tested(name: str, value: float) -> dict[str, object]:
        return {"threshold": name, "value": value, "n": 15, "p": 1 / 2**15, "method": "exact",
                "seed": None}  # fmt: skip

    row = {**fidelity_row(), "step_tests": {"green": tested("T_green", 495.0),
                                            "upper": tested("T_upper", 390.0)}}  # fmt: skip
    fidelity(tree, {SYSTEM: row}, controls=controls, steps=steps, slots=1)
    board = build_board(tree.root, RELEASE, tree.level)
    assert SchemaRegistry.from_tree(ROOT / "schema").errors("board/1", board) == []
    (r,) = board["rungs"][1]["rows"]  # type: ignore[index]
    assert [p["id"] for p in r["glyph"]] == list(PETALS)
    assert [(p["step"], p["cause"]) for p in r["glyph"]] == [
        ("green", None), ("green", None), ("green", None), (None, "proof_build_not_run"),
        ("red", "not_stated")]  # fmt: skip
    # 24 replies a batch: one bound per proof no longer covers one reply (UF-9)
    workload.write_text(yaml.safe_dump({"shape": {"batch_size": 24}}))
    (r,) = build_board(tree.root, RELEASE, tree.level)["rungs"][1]["rows"]  # type: ignore[index]
    assert (r["glyph"][0]["step"], r["glyph"][0]["cause"]) == ("amber_lower", None)


def test_validate_runs_the_offline_checks(tmp_path: Path) -> None:
    """GL-1 and GL-9 in `iproofs validate`: a properties/2 file read at another commit than
    system.yaml pins is a PROPERTIES finding; a frozen release's board with a not-read petal is
    a GLYPH finding, an unfrozen one is not."""
    from iproofs.validate.tree import g2_glyph  # noqa: PLC0415

    system = tmp_path / "systems" / SYSTEM
    system.mkdir(parents=True)
    system.joinpath("system.yaml").write_text(yaml.safe_dump({"upstream": {"commit": PIN}}))
    system.joinpath("properties.yaml").write_text(json.dumps(properties2()))
    release = tmp_path / "releases" / "v9"
    release.mkdir(parents=True)
    row = {"system": SYSTEM, "glyph": [petal_tree("unforgeable", "hollow", "not_read")]}
    board = {"rungs": [{"id": "r", "rows": [row]}]}
    release.joinpath("board.json").write_text(json.dumps(board))
    files = [f"systems/{SYSTEM}/properties.yaml", "releases/v9/board.json"]
    assert g2_glyph(tmp_path, files) == []
    system.joinpath("system.yaml").write_text(yaml.safe_dump({"upstream": {"commit": "b" * 40}}))
    release.joinpath("index.json").write_text("{}")
    assert sorted(f.rule for f in g2_glyph(tmp_path, files)) == ["GLYPH", "PROPERTIES"]
