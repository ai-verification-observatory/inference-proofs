import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from iproofs import controls as ctl
from iproofs.controls import HonestProof

seeds = st.integers(min_value=0, max_value=2**64 - 1).map(lambda n: f"0x{n:016x}")
parts = st.dictionaries(
    st.sampled_from(["a.bin", "b.bin", "c.bin"]), st.binary(min_size=1, max_size=64), min_size=2
)


@given(seed=seeds, request=st.lists(st.integers(0, 99), min_size=1, max_size=32), files=parts)
def test_mutations_deterministic(seed: str, request: list[int], files: dict[str, bytes]) -> None:
    """INV-CTRL-3: a mutation is a function of the seed, the control id and the honest inputs."""
    target = HonestProof("p", tuple(request), (7,), "accept", 1, 0)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        for name, data in files.items():
            (src / name).write_bytes(data)
        runs = []
        for k in range(2):
            out = Path(tmp) / str(k)
            calls = [
                ctl.c2(target, "c", src, 100, seed),
                *(ctl.c6(target, "c", src, out / f"c6-{s}", seed, s) for s in range(5)),
                ctl.c8(target, "c", src, out / "c8", seed),
            ]
            runs.append(
                [
                    (
                        c.request,
                        c.mutation,
                        c.parts,
                        sorted((p.name, p.read_bytes()) for p in c.proof_dir.iterdir()),
                    )
                    for c in calls
                ]
            )
        assert runs[0] == runs[1]
