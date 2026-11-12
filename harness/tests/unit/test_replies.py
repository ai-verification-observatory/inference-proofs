"""iproofs.replies: a serving ladder run's reply token ids beside its run.json (SIZE-1)."""

import json
from pathlib import Path

import pytest

from iproofs.replies import REPLIES_FILE, read_replies, split_replies
from iproofs.runner import recorded_claims


def run_doc() -> dict[str, object]:
    proofs = [{"proof_id": f"c1-b{k}-r0", "request_index": k, "release_mono_ns": 10 + k,
               "tokens_covered": 3, "verdict": None, "claimed_output": [k, k + 1, k + 2]}
              for k in range(3)]  # fmt: skip
    return {"run_id": "r", "status": "completed", "proofs": proofs}


def test_split_keeps_counts_and_reads_back(tmp_path: Path) -> None:
    """Three outputs of three tokens: the entries keep claimed_tokens 3 and every other field;
    the file reads back the same token ids by proof id, and run.json names it by digest."""
    doc = run_doc()
    new = split_replies(tmp_path, doc)
    proofs = new["proofs"]
    assert isinstance(proofs, list)
    assert [p["claimed_tokens"] for p in proofs] == [3, 3, 3]
    assert all("claimed_output" not in p for p in proofs)
    assert [p["release_mono_ns"] for p in proofs] == [10, 11, 12]
    block = new["replies"]
    assert isinstance(block, dict)
    assert (block["file"], block["outputs"]) == (REPLIES_FILE, 3)
    assert block["bytes"] == (tmp_path / REPLIES_FILE).stat().st_size
    assert read_replies(tmp_path, new) == {f"c1-b{k}-r0": [k, k + 1, k + 2] for k in range(3)}
    (tmp_path / "run.json").write_text(json.dumps(new))
    assert recorded_claims(tmp_path) == [[0, 1, 2], [1, 2, 3], [2, 3, 4]]


def test_changed_replies_file_is_refused(tmp_path: Path) -> None:
    new = split_replies(tmp_path, run_doc())
    path = tmp_path / REPLIES_FILE
    path.write_text(path.read_text().replace("[0,1,2]", "[0,1,9]"))
    with pytest.raises(Exception, match="digest"):
        read_replies(tmp_path, new)
