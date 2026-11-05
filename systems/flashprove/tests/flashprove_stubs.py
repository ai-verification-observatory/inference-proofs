"""Shared set-up for the FlashProve adapter's CPU tests: the entrypoint loaded in process, with
/io, /models and the upstream checkout mapped to temporary directories, and cp_commit, cp_prove
and cp_verify replaced by the stand-ins below. The stand-ins prove nothing: they only lay out the
files and print the lines that upstream documents, so the adapter's plumbing can run on a CPU."""

import hashlib
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
REGISTRY = SchemaRegistry.from_tree(SYSTEM.parents[1] / "schema")
COMMITMENT_ID = "c" * 64
TOKENS = 8  # the stand-ins take any T; the workloads have 1,024

_HEAD = f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\n"
_HEAD += "a = sys.argv\ndef opt(k):\n    return a[a.index(k) + 1]\n"

# cp_commit: the two directories that it creates, and the two lines that the adapter reads.
CP_COMMIT = """
ivk, isk = Path(opt("-ivk")), Path(opt("-isk"))
(ivk / "leaf").mkdir(parents=True)
(ivk / "key.bin").write_bytes(b"key")
(ivk / "leaf/0.bin").write_bytes(b"leaf")
for d in ("leaf/0", "anchor"):
    (isk / d).mkdir(parents=True)
    (isk / d / "count.bin").write_bytes(b"")
(isk / "seed.bin").write_bytes(bytes(32))
print("commitment ID: " + "c" * 64)
print("cp_commit: done. the commitment is complete and can be handed out")
"""

# cp_prove: batches of -batch, oldest request first, each response renamed into out/ in the
# documented order (.y, then .proof). The "proof" is the request's words and y, so the stand-in
# verifier can tell a changed request or token. A first token of 999 gets <id>.failed.
CP_PROVE = """
spool, size = Path(opt("-spool")), int(opt("-batch"))
assert (Path(opt("-isk")) / "seed.bin").is_file() and os.path.isdir(os.environ["TMPDIR"])
(spool / "out/.tmp").mkdir(parents=True, exist_ok=True)
reqs = sorted((spool / "in").glob("*.req"), key=lambda p: (p.stat().st_mtime_ns, p.name))
for b in range(int(opt("-most-batches"))):
    for r in reqs[b * size : (b + 1) * size]:
        words = r.read_bytes()[:-32]
        first = int.from_bytes(words[:4], "little")
        if first == 999:
            (spool / "out" / (r.stem + ".failed")).write_bytes(b"")
            continue
        y = (first % 1000).to_bytes(4, "little")
        for ending, data in ((".y", y), (".proof", words + y)):
            (spool / "out/.tmp" / (r.stem + ending)).write_bytes(data)
            os.rename(spool / "out/.tmp" / (r.stem + ending), spool / "out" / (r.stem + ending))
    print("batch", b, "leaf 0 n", size)
print("p258 end " + os.environ.get("STUB_PROVE_EXIT", "0"))
sys.exit(int(os.environ.get("STUB_PROVE_EXIT", "0")))
"""

# cp_verify: STUB_VERIFY="code:line" forces an ending; otherwise YES when the files belong
# together under the commitment ID, NO: statement when they do not.
CP_VERIFY = """
config, ivk, req, y, proof = map(Path, a[1:6])
assert sorted(p.name for p in config.iterdir()) == ["KL.bin", "layout.txt", "policy.txt"]
assert (ivk / "key.bin").is_file() and (ivk / "leaf/0.bin").is_file()
assert "-next-token" in a and int(opt("-j")) >= 1
forced = os.environ.get("STUB_VERIFY")
if forced:
    code, _, line = forced.partition(":")
    print("some progress line")
    print(line)
    sys.exit(int(code))
ok = proof.read_bytes() == req.read_bytes() + y.read_bytes() and opt("-id") == "c" * 64
print("YES" if ok else "NO: statement")
sys.exit(0 if ok else 1)
"""


def write_stub(path: Path, body: str) -> None:
    path.write_text(_HEAD + body)
    path.chmod(0o755)


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_INPUTS", str(HERE / "fixtures/inputs.json"))
    src = tmp_path / "src"
    (src / "prover/build/hc").mkdir(parents=True)
    for name, body in (("cp_commit", CP_COMMIT), ("cp_prove", CP_PROVE), ("cp_verify", CP_VERIFY)):
        write_stub(src / "prover/build/hc" / name, body)
    # the fit's files, and their digests where upstream publishes them (expected.txt)
    weights, config = tmp_path / "models/UD-Q4_K_XL", tmp_path / "models/flashprove-config"
    weights.mkdir(parents=True)
    config.mkdir()
    (weights / "wsums.txt").write_text("sums\n")
    (weights / "fold.txt").write_text("eres 10\nqkrows asis\n")
    for name in ("policy.txt", "KL.bin", "layout.txt"):
        (config / name).write_text(name)
    (src / "examples/maverick").mkdir(parents=True)
    (src / "examples/maverick/expected.txt").write_text(
        f"{hashlib.sha256(b'sums' + bytes([10])).hexdigest()}  model/wsums.txt\n"
        f"{hashlib.sha256(b'KL.bin').hexdigest()}  config/KL.bin\n"
    )
    monkeypatch.setenv("IPROOFS_FLASHPROVE_SRC", str(src))
    loader = importlib.machinery.SourceFileLoader("flashprove", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("flashprove", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def job(sub: str, **fields: Any) -> dict[str, Any]:
    size, batches = fields.get("batch_size", 2), fields.get("batches", 3)
    return {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": sub, "run_id": "r",
            "workload": {"id": "fp-maverick-w1024-b24", "version": 1},
            "shape": {"prompt_tokens": TOKENS, "output_tokens": 1, "batch_size": size,
                      "batches_per_session": batches, "context_window": TOKENS},
            "control": False} | fields  # fmt: skip


def run(adapter: ModuleType, sub: str, doc: dict[str, Any]) -> dict[str, Any]:
    io = adapter.host("/io")
    (io / "job.json").write_text(json.dumps(doc))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def commands(adapter: ModuleType) -> list[dict[str, Any]]:
    path = adapter.host("/io/commands.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]
