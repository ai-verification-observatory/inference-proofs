from hypothesis import given
from hypothesis import strategies as st

from iproofs.derive import measured, statistic
from iproofs.quantity import Scope, Unit

finite = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False)


@given(st.lists(finite, min_size=1, max_size=12), st.integers(min_value=0, max_value=5))
def test_stat_bounds(values: list[float], n_failed: int) -> None:
    """P-STAT-BOUNDS: min <= mean <= max, stdev >= 0, counts preserved."""
    inputs = [
        (f"r{i}", measured(v, Unit.S, Scope.VERIFY, f"r{i}", None)) for i, v in enumerate(values)
    ]
    out = statistic(inputs, [f"failed{i}" for i in range(n_failed)], "0.1.0")
    stats = out["stats"]
    assert isinstance(stats, dict)
    assert stats["n"] == len(values)
    assert stats["n_failed"] == n_failed
    assert stats["min"] <= stats["mean"] <= stats["max"]
    assert stats["stdev"] is None or stats["stdev"] >= 0
    assert out["value"] == stats["mean"]
