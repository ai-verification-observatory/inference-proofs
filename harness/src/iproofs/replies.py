"""The replies of a serving ladder run beside its run.json (RFC-0013 SIZE-1, RFC-0018 CO-4).

A ladder run serves every prompt of the rung's ladder (4,096 timed replies and their warm-ups)
and its run.json would hold every reply's token ids: about 60 MB for 512-token replies, above
the 10 MiB a run directory may take in git. The baseline reads only release times, so the
token ids go to `replies.jsonl` in the run directory, one line per output in record order, and
each proof entry keeps `claimed_tokens`, their count. run.json names the file by sha256. The
file travels with the run to the bucket and is not committed (`.gitignore`); a run that reads
the replies (a ref-recompute replay, RFC-0015 RC-1) checks the digest first.
"""

import json
from collections.abc import Mapping
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import file_digest
from iproofs.serialize import write_jsonl

REPLIES_FILE = "replies.jsonl"


def split_replies(run_dir: Path, doc: Mapping[str, object]) -> dict[str, object]:
    """Write `run_dir/replies.jsonl` from the claimed outputs of `doc`; return `doc` with each
    proof's `claimed_output` replaced by `claimed_tokens` and a `replies` block naming the
    file by digest. A document with no claimed output is returned unchanged."""
    proofs = doc.get("proofs")
    if not isinstance(proofs, list) or not any(
        isinstance(p, Mapping) and "claimed_output" in p for p in proofs
    ):
        return dict(doc)
    rows: list[dict[str, object]] = []
    kept: list[object] = []
    for p in proofs:
        if not isinstance(p, Mapping) or "claimed_output" not in p:
            kept.append(p)
            continue
        entry = {k: v for k, v in p.items() if k != "claimed_output"}
        out = p["claimed_output"]
        assert isinstance(out, list)
        entry["claimed_tokens"] = len(out)
        rows.append({"proof_id": p["proof_id"], "claimed_output": out})
        kept.append(entry)
    digest = write_jsonl(run_dir / REPLIES_FILE, rows)
    size = (run_dir / REPLIES_FILE).stat().st_size
    block = {"file": REPLIES_FILE, "sha256": digest, "bytes": size, "outputs": len(rows)}
    return {**doc, "proofs": kept, "replies": block}


def read_replies(run_dir: Path, doc: Mapping[str, object]) -> dict[str, list[int]]:
    """The claimed outputs of a run by proof id: from the proof entries, or from the replies
    file its run.json names, checked against its digest."""
    block = doc.get("replies")
    proofs = doc.get("proofs")
    if not isinstance(block, Mapping):
        entries = proofs if isinstance(proofs, list) else []
        return {
            str(p["proof_id"]): list(p["claimed_output"])
            for p in entries
            if isinstance(p, Mapping) and isinstance(p.get("claimed_output"), list)
        }
    path = run_dir / str(block.get("file"))
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir}: {path.name} is not here; fetch it "
                           "with the run from the bucket")  # fmt: skip
    if file_digest(path) != block.get("sha256"):
        raise IProofsError(ErrorKind.INTEGRITY, f"{path}: digest is not the one run.json names")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    return {str(r["proof_id"]): list(r["claimed_output"]) for r in rows}
