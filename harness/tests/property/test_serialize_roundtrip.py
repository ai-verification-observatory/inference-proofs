import json

from hypothesis import given
from hypothesis import strategies as st

from iproofs.serialize import dumps

scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False,
    allow_infinity=False) | st.text()  # fmt: skip
values = st.recursive(scalars, lambda c: st.lists(c) | st.dictionaries(st.text(), c), max_leaves=20)
documents = st.dictionaries(st.text(), values)


@given(documents)
def test_roundtrip(doc: dict[str, object]) -> None:
    data = dumps(doc)
    assert json.loads(data) == doc
    assert dumps(json.loads(data)) == data  # canonical form is a fixed point
