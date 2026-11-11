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
isk.chmod(0o700)  # as cp_commit makes it
print("commitment ID: " + "c" * 64)
print("cp_commit: done. the commitment is complete and can be handed out")
"""

# cp_prove: batches of -batch, oldest request first, each response renamed into out/ in the
# documented order (.y, then .proof). The "proof" is the request's words and y, so the stand-in
# verifier can tell a changed request or token; y is 0 unless e = T. A first token of 999 gets
# <id>.failed.
CP_PROVE = """
spool, size = Path(opt("-spool")), int(opt("-batch"))
assert (Path(opt("-isk")) / "seed.bin").is_file() and os.path.isdir(os.environ["TMPDIR"])
if Path(opt("-isk")).stat().st_mode & 0o777 != 0o700:  # refusal cp-isk
    print("p258 end 1 cp-isk")
    sys.exit(1)
(spool / "out/.tmp").mkdir(parents=True, exist_ok=True)
reqs = sorted((spool / "in").glob("*.req"), key=lambda p: (p.stat().st_mtime_ns, p.name))
for b in range(int(opt("-most-batches"))):
    for r in reqs[b * size : (b + 1) * size]:
        words = r.read_bytes()[:-32]
        first = int.from_bytes(words[:4], "little")
        if first == 999:
            (spool / "out" / (r.stem + ".failed")).write_bytes(b"")
            continue
        n, e = len(words) // 4 - 2, int.from_bytes(words[-4:], "little")
        y = (first % 1000 if e == n else 0).to_bytes(4, "little")  # y unused when e < T
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
words = req.read_bytes()
assert ("-next-token" in a) == (int.from_bytes(words[-4:], "little") == len(words) // 4 - 2)
assert int(opt("-j")) >= 1
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


# The integer model's Python: the float64 check prints a pytest summary (STUB_FLOAT64 replaces it);
# a `-c` program runs as given, with FAKE_INTEGER_MODEL below importable as `integer_model`.
IM_PYTHON = """
if "-m" in a:
    assert a[a.index("-m") + 1] == "pytest" and os.environ["INTEGER_MODEL_TEST_DEVICE"] == "cuda"
    assert Path("tests/test_arithmetic_edges.py").is_file()
    print(os.environ.get("STUB_FLOAT64", "==== 12 passed in 0.50s ===="))
    sys.exit(0)
sys.path.insert(0, os.environ["STUB_FAKE_MODULES"])
sys.argv = a[a.index("-c") + 1 :]
exec(compile(sys.argv[0], "<-c>", "exec"), {"__name__": "__main__"})
"""

# A stand-in for the package's load_from_folder: it checks the folder and the digests as the
# loader does, and its "greedy choice" after a token t at position n is (7 t + n) mod 1000.
FAKE_INTEGER_MODEL = """
import hashlib, json
from pathlib import Path


class _Model:
    def new_sequence(self):
        return []

    def extend(self, seq, ids):
        out = []
        for t in ids:
            seq.append(int(t))
            out.append((7 * seq[-1] + len(seq)) % 1000)
        return out

    def free(self, seq):
        seq.clear()


def load_from_folder(folder, device, options):
    spec = json.loads((Path(folder) / "integer_model.json").read_text())["weight_settings"]
    assert device == "cuda" and spec["blocks"] == "gguf"
    assert all(Path(s).is_file() for s in spec["shards"]) and len(spec["shards"]) == 5
    where = {"wsums.txt": spec["setup_folder"], "fold.txt": spec["setup_folder"]}
    for name, digest in options["sha256"].items():
        data = (Path(where.get(name, folder)) / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
    return _Model()
"""


def greedy(prompt: list[int], length: int) -> list[int]:
    """The reply FAKE_INTEGER_MODEL writes, computed here by its rule."""
    seq, reply = list(prompt), [(7 * prompt[-1] + len(prompt)) % 1000]
    while len(reply) < length:
        seq.append(reply[-1])
        reply.append((7 * seq[-1] + len(seq)) % 1000)
    return reply


# The fit's four programs: each writes the file the next one reads, with the bytes whose digests
# the fixture's expected.txt holds; STUB_WSUMS changes wsums.txt to test the digest check.
FIT_STUBS = {
    "scales/make_calibration_set.py": "Path(a[4]).write_bytes(b'set')",
    "bin/weight_sums": "Path(opt('--out')).write_text(os.environ.get('STUB_WSUMS', 'sums') + "
    "'\\n')",
    "scales/calibrate.py": "o = Path(opt('--out')); o.mkdir(); (o / 'words.json').write_text('{}')",
    "scales/words_to_policy.py": "Path(a[4]).write_text('policy'); Path(a[5]).write_text('KL.bin')",
}


def fit_stubs(src: Path, tmp_path: Path) -> None:
    for rel, body in FIT_STUBS.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        write_stub(src / rel, body + "\n")
    base = src / "prover/examples/target_full_f2"
    base.mkdir(parents=True)
    for name in ("policy.txt", "layout.txt"):
        (base / name).write_text(name)
    model = tmp_path / "models/UD-Q4_K_XL"
    model.mkdir(parents=True)
    for i in range(1, 6):
        name = f"Llama-4-Maverick-17B-128E-Instruct-UD-Q4_K_XL-0000{i}-of-00005.gguf"
        (model / name).write_bytes(bytes([i]))
    (tmp_path / "calibration").mkdir()


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
    # the fit's files as setup leaves them, and their digests where upstream publishes them
    weights, config = tmp_path / "io/fit/weights", tmp_path / "io/fit/config"
    weights.mkdir(parents=True)
    config.mkdir()
    (weights / "wsums.txt").write_text("sums\n")
    (weights / "fold.txt").write_text("eres 10\nqkrows asis\n")
    for i in range(1, 6):
        name = f"Llama-4-Maverick-17B-128E-Instruct-UD-Q4_K_XL-0000{i}-of-00005.gguf"
        (weights / name).write_bytes(bytes([i]))
    for name in ("policy.txt", "KL.bin", "layout.txt"):
        (config / name).write_text(name)
    fit_stubs(src, tmp_path)
    monkeypatch.setenv("IPROOFS_FLASHPROVE_PYTHON", sys.executable)
    monkeypatch.setenv("IPROOFS_FLASHPROVE_CALIBRATION", str(tmp_path / "calibration"))
    (src / "examples/maverick").mkdir(parents=True)
    (src / "examples/maverick/expected.txt").write_text(
        f"{hashlib.sha256(b'sums' + bytes([10])).hexdigest()}  model/wsums.txt\n"
        f"{hashlib.sha256(b'KL.bin').hexdigest()}  config/KL.bin\n"
    )
    monkeypatch.setenv("IPROOFS_FLASHPROVE_SRC", str(src))
    edges = src / "integrations/vllm/integer_model/tests/test_arithmetic_edges.py"
    edges.parent.mkdir(parents=True)
    edges.write_text("")
    write_stub(tmp_path / "im-python", IM_PYTHON)
    monkeypatch.setenv("IPROOFS_FLASHPROVE_IM_PYTHON", str(tmp_path / "im-python"))
    (tmp_path / "fake").mkdir()
    (tmp_path / "fake/integer_model.py").write_text(FAKE_INTEGER_MODEL)
    monkeypatch.setenv("STUB_FAKE_MODULES", str(tmp_path / "fake"))
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
