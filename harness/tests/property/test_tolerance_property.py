import math

from hypothesis import given
from hypothesis import strategies as st

from iproofs.release import tolerance

finite = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False)
spread = st.floats(min_value=0, max_value=1e6, allow_nan=False)
count = st.integers(min_value=1, max_value=1000)


@given(finite, spread, count, finite, spread, count)
def test_tolerance_symmetric_in_stats(
    m_o: float, s_o: float, n_o: int, m_r: float, s_r: float, n_r: int
) -> None:
    """Swapping (s_o, n_o) with (s_r, n_r) leaves the statistical term unchanged."""
    a = tolerance(0.0, s_o, n_o, 0.0, s_r, n_r)[0]
    b = tolerance(0.0, s_r, n_r, 0.0, s_o, n_o)[0]
    assert a == b
    bound, difference, within = tolerance(m_o, s_o, n_o, m_r, s_r, n_r)
    assert bound >= 0.1 * abs(m_o)
    assert within == (difference <= bound)
    assert math.isfinite(bound)
