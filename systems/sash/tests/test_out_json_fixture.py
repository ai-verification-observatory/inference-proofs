"""INV-ADAPTER-9: the entrypoint's mapping run on upstream outputs captured once on a GPU host.

No capture exists yet. The fixtures land under fixtures/gpu/ from one `prove` and `verify` of
sash-l31-8b-c1024 on the H100 host (RFC-0005 §Testing Strategy, GPU tests); until then this
test is skipped rather than fed outputs nobody captured."""

from pathlib import Path

import pytest

GPU = Path(__file__).resolve().parent / "fixtures" / "gpu"


@pytest.mark.skip(reason="awaiting the GPU capture of sash-l31-8b-c1024 (#65)")
def test_out_json_fixture() -> None:
    assert (GPU / "grid.json").is_file()
