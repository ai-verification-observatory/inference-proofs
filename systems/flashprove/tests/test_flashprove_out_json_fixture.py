"""INV-ADAPTER-9 against the adapter's outputs captured on a GPU host (fixtures/gpu/README.md):
one commit, prove and verify of fp-maverick-w1024-b1."""

import json
from pathlib import Path
from types import ModuleType

import flashprove_stubs
import pytest
from flashprove_stubs import REGISTRY

adapter = flashprove_stubs.adapter  # the fixture

GPU = Path(__file__).resolve().parent / "fixtures/gpu"


@pytest.mark.skipif(
    not GPU.is_dir(), reason="fixtures/gpu/ not captured yet: needs a GPU host (#69)"
)
def test_out_json_fixture(adapter: ModuleType) -> None:
    outs = {
        s: json.loads((GPU / f"{s}.out.json").read_text()) for s in ("commit", "prove", "verify")
    }
    for out in outs.values():
        assert REGISTRY.errors("adapter-out/1", out) == []
    verify = outs["verify"]
    assert adapter.verdict(verify["raw_exit_code"], verify["raw_last_line"]) == (
        verify["verdict"],
        verify.get("policy"),
    )
    assert [p["request_index"] for p in outs["prove"]["proofs"]] == list(range(5))
