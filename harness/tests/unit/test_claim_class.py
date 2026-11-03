import json
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.quantity import (
    CLAIM_CLASS_TOKENS,
    ClaimClass,
    check_closed_division,
    claim_class_matches,
    parse_claim_class,
)

ROOT = Path(__file__).resolve().parents[3]
EXACT = "next-token/exact-match/committed-weights"


def test_parse_claim_class() -> None:
    c = parse_claim_class(EXACT)
    assert c == ClaimClass("next-token", "exact-match", "committed-weights")
    assert str(c) == EXACT


def test_claim_class_wildcard() -> None:
    assert claim_class_matches("next-token/*/committed-weights", EXACT)
    assert not claim_class_matches(
        "next-token/*/committed-weights", "segment-grid/exact-match/committed-weights"
    )
    assert claim_class_matches("*/*/*", "other/other/other")
    assert claim_class_matches(EXACT, EXACT)


@pytest.mark.parametrize(
    "bad",
    [
        "next-token/exact-match",  # two tokens
        "next-token/exact-match/committed-weights/hiding",  # no fourth token (RFC-0002 Q3)
        "Next-Token/exact-match/committed-weights",  # lowercase only
        "next-token/approximate/committed-weights",  # unknown token
        "next-token/*/committed-weights",  # a wildcard is a filter, not a class
        "",
    ],
)
def test_claim_class_bad_pattern(bad: str) -> None:
    with pytest.raises(IProofsError) as e:
        parse_claim_class(bad)
    assert e.value.kind is ErrorKind.CONFIG


def test_claim_class_bad_filter() -> None:
    for bad in ["next-token/**/committed-weights", "*/*", "x/*/*"]:
        with pytest.raises(IProofsError):
            claim_class_matches(bad, EXACT)


def test_closed_workload_class_mismatch() -> None:
    check_closed_division("closed", EXACT, EXACT)  # same class competes
    check_closed_division("native", None, "segment-grid/tolerance/public-weights")
    check_closed_division("open", None, EXACT)
    with pytest.raises(IProofsError) as e:
        check_closed_division("closed", EXACT, "segment-grid/exact-match/committed-weights")
    assert e.value.kind is ErrorKind.CONFIG


def test_tokens_match_the_schemas() -> None:
    """The vocabulary here and the schema patterns cannot drift apart."""
    exact = "^" + "/".join(f"({'|'.join(t)})" for t in CLAIM_CLASS_TOKENS) + "$"
    wild = "^" + "/".join(f"({'|'.join(t)}|\\*)" for t in CLAIM_CLASS_TOKENS) + "$"
    text = {
        s: (ROOT / f"schema/{s}/1.schema.json").read_text() for s in ("claim", "workload", "target")
    }
    assert json.dumps(exact) in text["claim"]
    assert json.dumps(exact) in text["workload"]
    assert json.dumps(wild) in text["target"]
