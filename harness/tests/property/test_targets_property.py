"""RFC-0009 §Targets: the result is decided by the least favourable repetition."""

from hypothesis import given
from hypothesis import strategies as st

from iproofs.release import evaluate_target

VALUES = st.lists(st.floats(0, 1e6, allow_nan=False), min_size=1, max_size=12)


@given(VALUES, st.floats(0, 1e6, allow_nan=False), st.sampled_from(["<=", ">=", "=="]))
def test_target_least_favourable_case(values: list[float], limit: float, comparator: str) -> None:
    target = {
        "comparator": comparator,
        "threshold": {"value": limit, "unit": "s", "scope": "verify"},
    }
    inputs = [(f"r{i}", {"value": v, "unit": "s", "scope": "verify"}) for i, v in enumerate(values)]
    result, reason, worst = evaluate_target(target, inputs)
    assert reason is None
    assert worst is not None
    pick = {"<=": max(values), ">=": min(values), "==": max(values, key=lambda v: abs(v - limit))}
    assert worst["value"] == pick[comparator]
    meets = {"<=": max(values) <= limit, ">=": min(values) >= limit,
             "==": all(v == limit for v in values)}  # fmt: skip
    assert result == ("meets" if meets[comparator] else "does_not_meet")
