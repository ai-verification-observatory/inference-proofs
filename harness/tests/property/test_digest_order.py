import random
import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from iproofs.provenance import model_digest

names = st.text(alphabet="abcXYZé._-", min_size=1, max_size=8).filter(
    lambda n: n not in {".", ".."}
)
trees = st.dictionaries(names, st.binary(max_size=16), min_size=1, max_size=6)


@given(trees, st.randoms())
def test_digest_order_independent(files: dict[str, bytes], rnd: random.Random) -> None:
    order = list(files)
    rnd.shuffle(order)
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        for name, data in files.items():
            (Path(a) / name).write_bytes(data)
        for name in order:
            (Path(b) / name).write_bytes(files[name])
        assert model_digest(Path(a)) == model_digest(Path(b))
