"""RFC-0008 §Split suites, the pure part: seeds, subsets, part names and the merge checks."""

from typing import Any

import pytest

from iproofs import controls as ctl
from iproofs.errors import IProofsError

SUITE = ["C1", "C2", "P1", "sys-a"]
SEED = "0x0123456789abcdef"


def record(cid: str, outcome: str = "rejected") -> dict[str, object]:
    side = "prover" if cid in ("P1", "sys-a") else "verifier"
    return {"id": cid, "side": side, "source": "shared", "expected": ["rejected"],
            "twin": {"verdict": "accept", "raw_exit_code": 0}, "trials": [],
            "outcome": outcome, "passed": outcome == "rejected", "note": None}  # fmt: skip


def part(*ids: str, **changes: object) -> dict[str, Any]:
    same: dict[str, object] = {
        "run_id": "2026-11-09-fake-fake-tiny-ci-ci-cpu-1",
        "run_manifest_digest": "sha256:" + "0" * 64,
        "control_seed": SEED,
        "suite": SUITE,
        "image": "local/in-process@sha256:" + "0" * 64,
        "verifier_profile": "ci-cpu",
        "profile": "ci-cpu",
        "verifier_cpus": 1,
        "perturbed_commitment": None,
        "harness_version": "0.1.0",
        "harness_commit": "a" * 40,
        "harness_dirty": False,
    }
    doc = ctl.part_document(same, ids, [record(cid) for cid in ids])
    return doc | changes


@pytest.mark.parametrize(
    ("text", "seed"),
    [
        ("0x0123456789abcdef", "0x0123456789abcdef"),
        ("0X0123456789ABCDEF", "0x0123456789abcdef"),
        ("0x1", "0x0000000000000001"),
        ("1", "0x0000000000000001"),
        ("0", "0x0000000000000000"),
        ("18446744073709551615", "0xffffffffffffffff"),
    ],
)
def test_seed_hex_or_decimal_in_recorded_form(text: str, seed: str) -> None:
    assert ctl.parse_control_seed(text) == seed
    assert ctl.CONTROL_SEED_RE.fullmatch(seed)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("18446744073709551616", "above 2\\*\\*64"),
        ("0x", "64-bit value"),
        ("0x10000000000000000", "64-bit value"),
        ("-1", "64-bit value"),
        ("seed", "64-bit value"),
        (" 1", "64-bit value"),
    ],
)
def test_seed_refused(text: str, message: str) -> None:
    with pytest.raises(IProofsError, match=message):
        ctl.parse_control_seed(text)


def test_only_in_suite_order_across_repeats() -> None:
    assert ctl.parse_only(["sys-a,C1", "C2"], SUITE) == ("C1", "C2", "sys-a")
    assert ctl.parse_only([" P1 "], SUITE) == ("P1",)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([], "unknown control ''"),
        ([""], "unknown control ''"),
        (["C1,C9"], "unknown control 'C9'; this suite is C1, C2, P1, sys-a"),
        (["C1", "C1,C2"], "names C1 twice"),
    ],
)
def test_only_refused(values: list[str], message: str) -> None:
    with pytest.raises(IProofsError, match=message):
        ctl.parse_only(values, SUITE)


def test_part_name_carries_seed_and_subset() -> None:
    name = ctl.part_name(SEED, ("C1", "C2"))
    assert name.startswith("controls-part-0123456789abcdef-")
    assert name.endswith(".json")
    assert ctl.part_name(SEED, ("C1", "C2")) == name
    assert ctl.part_name(SEED, ("C1",)) != name
    assert ctl.part_name("0x" + "f" * 16, ("C1", "C2")) != name


def test_part_document_shape() -> None:
    doc = part("C1", "P1")
    assert doc["schema"] == "controls-part/1"
    assert doc["only"] == ["C1", "P1"]
    assert [r["id"] for r in doc["controls"]] == ["C1", "P1"]
    assert set(ctl.PART_KEYS) < set(doc)


def test_merge_restores_suite_order_and_recomputes() -> None:
    a, b = part("sys-a", "C1"), part("P1", "C2")
    a["controls"] = [record("sys-a", "accepted"), record("C1")]
    a["only"] = ["sys-a", "C1"]
    merged = ctl.merge_parts({"b.json": b, "a.json": a})
    assert [r["id"] for r in merged["controls"]] == SUITE  # type: ignore[attr-defined]
    assert merged["summary"] == ctl.summary(merged["controls"])  # type: ignore[arg-type]
    assert merged["disclosure_pending"] is True
    assert set(merged) == {"schema", "run_id", "control_seed", "image", "verifier_profile",
                           "perturbed_commitment", "controls", "summary",
                           "disclosure_pending"}  # fmt: skip
    single = ctl.controls_document(a["run_id"], SEED, a["image"], "ci-cpu", None,
                                   [record("C1"), record("C2"), record("P1"),
                                    record("sys-a", "accepted")])  # fmt: skip
    assert merged == single


@pytest.mark.parametrize("key", ctl.PART_KEYS)
def test_merge_refuses_parts_that_differ(key: str) -> None:
    other = part("C2", "P1", "sys-a", **{key: {"different": True}})
    with pytest.raises(IProofsError, match=rf"b\.json differs from a\.json in {key}"):
        ctl.merge_parts({"a.json": part("C1"), "b.json": other})


def test_merge_refuses_records_other_than_the_subset() -> None:
    bad = part("C1", "C2")
    bad["only"] = ["C1"]
    with pytest.raises(IProofsError, match="are not its subset"):
        ctl.merge_parts({"a.json": bad})


def test_merge_refuses_overlap_gap_and_strangers() -> None:
    with pytest.raises(IProofsError, match=r"C2 is in both a\.json and b\.json"):
        ctl.merge_parts({"a.json": part("C1", "C2"), "b.json": part("C2", "P1", "sys-a")})
    with pytest.raises(IProofsError, match="no part ran P1, sys-a"):
        ctl.merge_parts({"a.json": part("C1"), "b.json": part("C2")})
    with pytest.raises(IProofsError, match="C9 not in the suite"):
        ctl.merge_parts({"a.json": part(*SUITE), "b.json": part("C9")})
    with pytest.raises(IProofsError, match="no part given"):
        ctl.merge_parts({})
