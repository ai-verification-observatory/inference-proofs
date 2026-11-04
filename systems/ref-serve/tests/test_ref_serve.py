"""ref-serve on CPU (INV-ADAPTER-9): the outputs builder and the release protocol, against
engine outputs captured once on a GPU host (fixtures/capture, see its README)."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
import yaml

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
CAPTURE = HERE / "fixtures/capture"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    loader = importlib.machinery.SourceFileLoader("ref_serve", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("ref_serve", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Replay:
    """The engine, replaced by outputs captured from it: the same prompt gives the same ids."""

    calls: ClassVar[list[tuple[int, int]]] = []

    def __init__(self, model: str, args: list[str]) -> None:
        self.model, self.args = model, args
        captured = json.loads((CAPTURE / "out.json").read_text())["proofs"]
        prompts = (CAPTURE / "prompts.jsonl").read_text().splitlines()
        self.known = {p: c["claimed_output"] for p, c in zip(prompts, captured, strict=True)}

    def generate(self, prompts: list[list[int]], max_tokens: int) -> list[list[int]]:
        Replay.calls.append((len(prompts), max_tokens))
        return [self.known.get(json.dumps(p), [len(p) % 7] * max_tokens) for p in prompts]


def job(io: Path, workload: str, size: int, batches: int, output_tokens: int) -> dict[str, Any]:
    return {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": "prove",
            "run_id": "r", "workload": {"id": workload, "version": 1},
            "shape": {"prompt_tokens": 1024, "output_tokens": output_tokens, "batch_size": size,
                      "batches_per_session": batches, "context_window": 1024 + output_tokens},
            "model_dir": "/models", "prompts_file": "/io/prompts.jsonl", "batch_size": size,
            "batches": batches, "control": False, "control_flags": [],
            "commitment_id": "not_applicable", "prover_files": []}  # fmt: skip


def run(adapter: ModuleType, sub: str, doc: dict[str, Any]) -> dict[str, Any]:
    io = Path(adapter.host("/io"))
    (io / "job.json").write_text(json.dumps(doc | {"subcommand": sub}))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def test_out_json_fixture(adapter: ModuleType) -> None:
    """The captured GPU run, replayed: same out.json proofs, the same released outputs."""
    adapter.make_engine = Replay
    io = Path(adapter.host("/io"))
    (io / "prompts.jsonl").write_text((CAPTURE / "prompts.jsonl").read_text())
    out = run(adapter, "prove", job(io, "sash-l31-8b-c1024", 1, 1, 64))
    captured = json.loads((CAPTURE / "out.json").read_text())
    assert out["proofs"] == captured["proofs"]
    for proof in out["proofs"]:
        mine = (io / "proofs" / proof["proof_id"] / "outputs.json").read_text()
        theirs = (CAPTURE / "proofs" / proof["proof_id"] / "outputs.json").read_text()
        assert json.loads(mine) == json.loads(theirs)
    assert [p.name for p in (io / "proofs").iterdir()] == ["req-0"]  # no temporary left
    [command] = [json.loads(line) for line in (io / "commands.jsonl").read_text().splitlines()]
    assert command["argv"][3:] == adapter.engine_args("sash-l31-8b-c1024")


def test_captured_out_json_is_valid() -> None:
    captured = json.loads((CAPTURE / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", captured) == []
    assert len(captured["proofs"][0]["claimed_output"]) == 64  # SRV-2: max_tokens = output_tokens


def test_batches_released_per_request(adapter: ModuleType) -> None:
    """SRV-1 and REF-1: batches of batch_size, one release per request, in request order."""
    adapter.make_engine = Replay
    Replay.calls = []
    io = Path(adapter.host("/io"))
    prompts = [[i, i + 1] for i in range(7)]  # one more than the job uses
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    out = run(adapter, "prove", job(io, "fp-maverick-w1024-b24", 2, 3, 1))
    assert Replay.calls == [(2, 1), (2, 1), (2, 1)]
    assert [p["request_index"] for p in out["proofs"]] == list(range(6))
    assert sorted(p.name for p in (io / "proofs").iterdir()) == [f"req-{i}" for i in range(6)]
    released = json.loads((io / "proofs/req-3/outputs.json").read_text())
    want = {"request_index": 3, "batch": 1, "token_ids": out["proofs"][3]["claimed_output"]}
    assert released == want


def test_too_few_prompts_refused(adapter: ModuleType) -> None:
    adapter.make_engine = Replay
    io = Path(adapter.host("/io"))
    (io / "prompts.jsonl").write_text("[1]\n")
    with pytest.raises(SystemExit, match=r"1 prompts for 1 batches of 2"):
        run(adapter, "prove", job(io, "sash-l31-8b-c1024", 2, 1, 1))


def test_release_is_atomic(adapter: ModuleType, tmp_path: Path) -> None:
    proofs = tmp_path / "proofs"
    proofs.mkdir()
    adapter.release(proofs, "req-0", {"token_ids": [1]})
    assert [p.name for p in proofs.iterdir()] == ["req-0"]
    with pytest.raises(OSError, match="req-0"):  # an existing release is never overwritten
        adapter.release(proofs, "req-0", {"token_ids": [2]})


def test_engine_options_verbatim(adapter: ModuleType) -> None:
    """SRV-3: the options come from system.yaml only."""
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    for entry in doc["workloads"]:
        assert adapter.engine_args(entry["id"]) == entry["engine_args"]
    with pytest.raises(SystemExit, match=r"not in system\.yaml"):
        adapter.engine_args("fake-tiny-ci")


def test_gguf_model_path(adapter: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "UD-Q4_K_XL").mkdir()
    for n in (2, 1):
        (tmp_path / f"UD-Q4_K_XL/m-0000{n}-of-00002.gguf").write_bytes(b"")
    assert adapter.model_path(tmp_path).endswith("m-00001-of-00002.gguf")
    empty = tmp_path / "UD-Q4_K_XL" / "none"
    assert adapter.model_path(empty) == str(empty)


def test_info_and_skipped_steps(adapter: ModuleType) -> None:
    io = Path(adapter.host("/io"))
    base = {"schema": "adapter-job/1", "contract": "adapter/1", "run_id": "r",
            "workload": {"id": "sash-l31-8b-c1024", "version": 1}}  # fmt: skip
    out = run(adapter, "info", base)
    assert (out["system"], out["upstream_commit"]) == ("ref-serve", adapter.ENGINE_COMMIT)
    assert "fp-maverick-w1024-b24" in out["workloads"]
    assert run(adapter, "setup", base)["ready"] is True
    (io / "job.json").write_text(json.dumps(base | {"subcommand": "verify"}))
    adapter.sys.argv = ["entrypoint", "verify", "/io/job.json", "/io/out.json"]
    with pytest.raises(SystemExit, match=r"no 'verify' step"):
        adapter.main()


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []
