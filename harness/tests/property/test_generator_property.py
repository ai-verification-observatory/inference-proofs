from hypothesis import given
from hypothesis import strategies as st

from iproofs.workloads import corpus_window_v1
from toy_tokenizer import RangeTokenizer


@given(
    n=st.integers(min_value=1, max_value=500),
    data=st.data(),
    count=st.integers(min_value=1, max_value=20),
    seed=st.integers(min_value=0, max_value=2**64 - 1),
)
def test_generator_offset_bounds(n: int, data: st.DataObject, count: int, seed: int) -> None:
    length = data.draw(st.integers(min_value=1, max_value=n))
    prompts = corpus_window_v1(["x" * n], RangeTokenizer(), count, length, seed)
    assert len(prompts) == count
    for p in prompts:
        offset = p[0]
        assert 0 <= offset <= n - length
        assert p == list(range(offset, offset + length))  # one contiguous window


@given(seed=st.integers(min_value=0, max_value=2**64 - 1))
def test_generator_deterministic(seed: int) -> None:
    a = corpus_window_v1(["x" * 300], RangeTokenizer(), 5, 7, seed)
    assert a == corpus_window_v1(["x" * 300], RangeTokenizer(), 5, 7, seed)
