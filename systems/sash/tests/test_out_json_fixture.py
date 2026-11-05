"""INV-ADAPTER-9: the adapter's outputs captured once on a GPU host (fixtures/gpu/README.md):
one commit, prove and verify of sash-l31-8b-c1024."""

import json
from pathlib import Path
from typing import Any

from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
GPU = HERE / "fixtures" / "gpu"
REGISTRY = SchemaRegistry.from_tree(HERE.parents[2] / "schema")


def out(step: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((GPU / f"{step}.out.json").read_text())
    return doc


def test_out_json_fixture() -> None:
    for step in ("commit", "prove", "verify"):
        assert REGISTRY.errors("adapter-out/1", out(step)) == []
    [proof] = out("prove")["proofs"]  # one grid: the sequence's segments, released once
    assert len(proof["claimed_output"]) == 64  # output_tokens of sash-l31-8b-c1024
    assert len(proof["parts"]) == 3 * 546 + 1  # three files a segment, plus plan.txt
    verify = out("verify")
    assert (verify["verdict"], verify["raw_exit_code"]) == ("accept", 0)
    assert "verified 546/546" in verify["raw_last_line"]
    assert "(0 bad, 0 unbacked)" in verify["raw_last_line"]
