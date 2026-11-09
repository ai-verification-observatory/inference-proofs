"""ref-serve on CPU (INV-ADAPTER-9): production serving's checks before the engine (SRV-3,
SRV-6), the engine command, the outputs builder and the release protocol, against a fake server
that replays engine outputs captured once on a GPU host (fixtures/capture, see its README), and
the sizing arithmetic (sizing.py)."""

import importlib.machinery
import importlib.util
import json
import os
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


IMAGE_ENV = ["CUDA_VERSION=12.9.1", "NCCL_VERSION=2.27.3-1"]  # fixture ENV of an engine image


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    (tmp_path / "image_env.json").write_text(json.dumps(IMAGE_ENV))
    monkeypatch.setenv("IPROOFS_IMAGE_ENV", str(tmp_path / "image_env.json"))
    for key in list(os.environ):
        if key.startswith(("VLLM_", "NCCL_", "CUDA_", "TORCH_")):
            monkeypatch.delenv(key)
    for pair in IMAGE_ENV:
        monkeypatch.setenv(*pair.split("=", 1))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    loader = importlib.machinery.SourceFileLoader("ref_serve", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("ref_serve", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RESOLVED = (HERE / "fixtures/resolved-default.txt").read_text().strip()


class Replay:
    """The engine's server, replaced by outputs captured from the engine: the same prompt gives
    the same ids. It logs the lines the adapter reads (resolved configuration, KV capacity)."""

    calls: ClassVar[list[tuple[int, int]]] = []
    started: ClassVar[list[list[str]]] = []
    kv_tokens = 1_000_000
    short_by = 0
    resolved = RESOLVED

    def __init__(self, model: str, args: list[str]) -> None:
        self.model, self.args = model, args
        self.argv = ["vllm", "serve", model, "--host", "127.0.0.1", "--port", "8000", *args]
        Replay.started.append(self.argv)
        captured = json.loads((CAPTURE / "out.json").read_text())["proofs"]
        prompts = (CAPTURE / "prompts.jsonl").read_text().splitlines()
        self.known = {p: c["claimed_output"] for p, c in zip(prompts, captured, strict=True)}
        self.stopped = False

    def resolved_config(self) -> str:
        return self.resolved

    def kv_capacity(self) -> tuple[int, str]:
        line = (f"GPU KV cache size: {self.kv_tokens:,} tokens, Maximum concurrency for 1,025 "
                "tokens per request: 9.00x")  # fmt: skip
        return self.kv_tokens, line

    def generate(self, prompts: list[list[int]], max_tokens: int) -> list[list[int]]:
        Replay.calls.append((len(prompts), max_tokens))
        out = [self.known.get(json.dumps(p), [len(p) % 7] * max_tokens) for p in prompts]
        return [o[: len(o) - self.short_by] for o in out]

    def stop(self) -> None:
        self.stopped = True


def job(io: Path, workload: str, size: int, batches: int, output_tokens: int,
        load_point: str = "matched", gpus: int = 1) -> dict[str, Any]:  # fmt: skip
    return {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": "prove",
            "run_id": "r", "workload": {"id": workload, "version": 1},
            "shape": {"prompt_tokens": 1024, "output_tokens": output_tokens, "batch_size": size,
                      "batches_per_session": batches, "context_window": 1024 + output_tokens},
            "model_dir": "/models", "prompts_file": "/io/prompts.jsonl", "batch_size": size,
            "batches": batches, "control": False, "control_flags": [],
            "commitment_id": "not_applicable", "prover_files": [], "load_point": load_point,
            "gpus": gpus}  # fmt: skip


def run(adapter: ModuleType, sub: str, doc: dict[str, Any]) -> dict[str, Any]:
    io = Path(adapter.host("/io"))
    (io / "job.json").write_text(json.dumps(doc | {"subcommand": sub}))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def test_out_json_fixture(adapter: ModuleType) -> None:
    """The captured GPU run, replayed: same out.json proofs, the same released outputs; the
    recorded command is `vllm serve /models ...` ending with the entry's engine_args (SRV-3),
    with the engine environment and the engine's own lines beside it."""
    adapter.make_serve_engine = Replay
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
    args = adapter.engine_args("sash-l31-8b-c1024", "matched", 1)
    assert command["argv"][:3] == ["vllm", "serve", str(adapter.host("/models"))]
    assert command["argv"][-len(args) :] == args
    assert command["environment"] == {"CUDA_VERSION": "12.9.1", "CUDA_VISIBLE_DEVICES": "0",
                                      "NCCL_VERSION": "2.27.3-1"}  # fmt: skip
    assert command["resolved_config"] == RESOLVED
    assert command["kv_capacity"].startswith("GPU KV cache size: 1,000,000 tokens")
    # no vllm package and no VLLM_BUILD_COMMIT here, and the replay logs no batched-token line
    assert command["engine_observed"] == {"version": None, "build_commit": None,
                                          "max_num_batched_tokens": None}  # fmt: skip


def test_captured_out_json_is_valid() -> None:
    captured = json.loads((CAPTURE / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", captured) == []
    assert len(captured["proofs"][0]["claimed_output"]) == 64  # SRV-2: max_tokens = output_tokens


def test_batches_released_per_request(adapter: ModuleType) -> None:
    """SRV-1 and REF-1: batches of batch_size, one release per request, in request order."""
    adapter.make_serve_engine = Replay
    Replay.calls = []
    io = Path(adapter.host("/io"))
    adapter.os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"
    prompts = [[i, i + 1] for i in range(7)]  # one more than the job uses
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    out = run(adapter, "prove", job(io, "fp-maverick-w1024-b24", 2, 3, 1, gpus=4))
    assert Replay.calls == [(2, 1), (2, 1), (2, 1)]
    assert [p["request_index"] for p in out["proofs"]] == list(range(6))
    assert sorted(p.name for p in (io / "proofs").iterdir()) == [f"req-{i}" for i in range(6)]
    released = json.loads((io / "proofs/req-3/outputs.json").read_text())
    want = {"request_index": 3, "batch": 1, "token_ids": out["proofs"][3]["claimed_output"]}
    assert released == want


def test_lengthened_session_serves_every_batch(adapter: ModuleType) -> None:
    """TC-SRV-LENGTHEN-REPLAY in the adapter (SRV-1): a matched job whose `batches` (the run's
    `batches_per_session_run`, 7) exceeds the workload's `batches_per_session` (5) serves all 7
    batches of 2 from the prompt file, in file order."""
    adapter.make_serve_engine = Replay
    Replay.calls = []
    io = Path(adapter.host("/io"))
    adapter.os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"
    (io / "prompts.jsonl").write_text("".join(json.dumps([i, i]) + "\n" for i in range(14)))
    doc = job(io, "fp-maverick-w1024-b24", 2, 5, 1, gpus=4) | {"batches": 7}
    out = run(adapter, "prove", doc)
    assert Replay.calls == [(2, 1)] * 7
    assert [p["request_index"] for p in out["proofs"]] == list(range(14))
    assert json.loads((io / "proofs/req-13/outputs.json").read_text())["batch"] == 6


def test_too_few_prompts_refused(adapter: ModuleType) -> None:
    adapter.make_serve_engine = Replay
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
        found = adapter.engine_args(entry["id"], entry["load_point"], entry["gpus"])
        assert found == entry["engine_args"]
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


def test_engine_caches_under_scratch(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only root and no home: HOME and the cache root move to the writable scratch."""
    import sys  # noqa: PLC0415
    import types  # noqa: PLC0415

    vllm = types.ModuleType("vllm")
    vllm.LLM = lambda **kw: kw  # type: ignore[attr-defined]
    for name in ("vllm.engine", "vllm.utils"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    arg_utils = types.ModuleType("vllm.engine.arg_utils")
    parser = types.ModuleType("vllm.utils.argparse_utils")

    class Args:
        @staticmethod
        def add_cli_args(p: Any) -> Any:
            return p

        @staticmethod
        def from_cli_args(_: Any) -> Any:
            import dataclasses  # noqa: PLC0415

            return dataclasses.make_dataclass("E", [])()

    class Parser:
        def parse_args(self, argv: list[str]) -> list[str]:
            return argv

    arg_utils.EngineArgs = Args  # type: ignore[attr-defined]
    parser.FlexibleArgumentParser = Parser  # type: ignore[attr-defined]
    for name, mod in (("vllm", vllm), ("vllm.engine.arg_utils", arg_utils),
                      ("vllm.utils.argparse_utils", parser)):  # fmt: skip
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(adapter, "SCRATCH", str(tmp_path / "scratch"))
    monkeypatch.setenv("HOME", "/nonexistent")
    adapter.VllmEngine("/models/m", [])
    assert adapter.os.environ["HOME"] == str(tmp_path / "scratch")
    assert adapter.os.environ["XDG_CACHE_HOME"] == str(tmp_path / "scratch/.cache")
    assert (tmp_path / "scratch").is_dir()


def serve_job(adapter: ModuleType, workload: str = "fp-maverick-w1024-b24", size: int = 24,
              load_point: str = "matched", gpus: int = 4) -> dict[str, Any]:  # fmt: skip
    io = Path(adapter.host("/io"))
    (io / "prompts.jsonl").write_text("".join(json.dumps([i] * 4) + "\n" for i in range(size)))
    adapter.os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, range(gpus)))
    return job(io, workload, size, 1, 1, load_point=load_point, gpus=gpus)


def refused(adapter: ModuleType, doc: dict[str, Any]) -> dict[str, Any]:
    io = Path(adapter.host("/io"))
    (io / "job.json").write_text(json.dumps(doc | {"subcommand": "prove"}))
    adapter.sys.argv = ["entrypoint", "prove", "/io/job.json", "/io/out.json"]
    with pytest.raises(SystemExit) as e:
        adapter.main()
    assert e.value.code == 3
    out: dict[str, Any] = json.loads((io / "failure.json").read_text())
    return out


def test_env_refused(adapter: ModuleType) -> None:
    """TC-SRV-ENV: VLLM_ATTENTION_BACKEND, absent from the image ENV, is refused `config`
    before the engine is built; CUDA_VISIBLE_DEVICES alone (the harness's binding) passes."""
    adapter.make_serve_engine = Replay
    Replay.started = []
    adapter.os.environ["VLLM_ATTENTION_BACKEND"] = "FLASHINFER"
    try:
        failure = refused(adapter, serve_job(adapter))
    finally:
        del adapter.os.environ["VLLM_ATTENTION_BACKEND"]
    assert failure["kind"] == "config"
    assert "VLLM_ATTENTION_BACKEND=FLASHINFER" in failure["message"]
    assert Replay.started == []  # refused before the engine
    assert run(adapter, "prove", serve_job(adapter))["proofs"]  # binding alone passes
    adapter.os.environ["CUDA_VERSION"] = "13.0"  # another value than the image's is refused
    assert "CUDA_VERSION=13.0" in refused(adapter, serve_job(adapter))["message"]


def test_gpu_count_mismatch(adapter: ModuleType) -> None:
    """TC-SRV-GPU-COUNT in the adapter: TP 4 with one visible GPU is `config` before load."""
    adapter.make_serve_engine = Replay
    Replay.started = []
    doc = serve_job(adapter)
    adapter.os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    failure = refused(adapter, doc)
    assert failure["kind"] == "config"
    assert "1 visible GPU(s) ['0'], --tensor-parallel-size 4" in failure["message"]
    assert Replay.started == []


def test_kv_capacity(adapter: ModuleType) -> None:
    """A KV cache of 20,000 tokens for b24 (24 x 1,025 = 24,600) is `resource` with the engine's
    line as evidence; at high load it is a warning and the engine queues the batch (SRV-1)."""
    adapter.make_serve_engine = Replay
    Replay.kv_tokens = 20_000
    try:
        failure = refused(adapter, serve_job(adapter))
        assert failure["kind"] == "resource"
        assert "below the matched load's 24600 tokens" in failure["message"]
        assert failure["evidence"][0].startswith("GPU KV cache size: 20,000 tokens")
        out = run(adapter, "prove", serve_job(adapter, load_point="high"))
        assert out["warnings"] == ["KV cache of 20000 tokens holds part of the 24-request batch "
                                   "at once; the engine queues the rest"]  # fmt: skip
    finally:
        Replay.kv_tokens = 1_000_000


def test_output_length(adapter: ModuleType) -> None:
    """SRV-2: a request returning 63 of 64 tokens is an adapter failure (non-zero exit)."""
    adapter.make_serve_engine = Replay
    Replay.short_by = 1
    io = Path(adapter.host("/io"))
    (io / "prompts.jsonl").write_text((CAPTURE / "prompts.jsonl").read_text())
    try:
        with pytest.raises(SystemExit, match=r"returned \[63\] tokens, not 64"):
            run(adapter, "prove", job(io, "sash-l31-8b-c1024", 1, 1, 64))
    finally:
        Replay.short_by = 0


def test_high_load_has_no_max_num_seqs(adapter: ModuleType) -> None:
    """SRV-1: the high-load engine keeps --max-num-seqs at its default."""
    adapter.make_serve_engine = Replay
    Replay.started = []
    run(adapter, "prove", serve_job(adapter, load_point="high"))
    assert "--max-num-seqs" not in Replay.started[-1]
    assert Replay.started[-1][-4:] == ["--tensor-parallel-size", "4", "--max-model-len", "1025"]
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    for entry in doc["workloads"]:
        assert ("--max-num-seqs" in entry["engine_args"]) == (entry["load_point"] == "matched")


def test_allowlist_refused_in_the_adapter(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-SRV-ALLOWLIST: a system.yaml whose entry adds an option outside SRV-3 (one the schema
    refuses, written past it) is `config` in the adapter too; no entry for the job is `config`."""
    adapter.make_serve_engine = Replay
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    for entry in doc["workloads"]:
        entry["engine_args"] = [*entry["engine_args"], "--cpu-offload-gb", "160"]
    path = tmp_path / "system.yaml"
    path.write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(adapter, "SYSTEM_YAML", path)
    assert "outside the SRV-3 allowlist" in refused(adapter, serve_job(adapter))["message"]
    assert "lists no matched entry" in refused(adapter, serve_job(adapter, gpus=2))["message"]


def test_resolved_config_defaults(adapter: ModuleType) -> None:
    """TC-SRV-RESOLVED: the resolved configuration differs from the stored default dump only in
    the fields the allowlisted options set (tensor_parallel_size, max_seq_len)."""
    ours = RESOLVED.replace("tensor_parallel_size=1", "tensor_parallel_size=4").replace(
        "max_seq_len=1088", "max_seq_len=1025")  # fmt: skip
    assert adapter.resolved_problems(ours, RESOLVED) == []
    fields = adapter.resolved_fields(RESOLVED)
    assert fields["compilation_config"] == "{'level': 3, 'cudagraph_mode': [2, 1]}"
    assert fields["structured_outputs_config"].startswith("StructuredOutputsConfig(")
    eager = ours.replace("enforce_eager=False", "enforce_eager=True")
    assert adapter.resolved_problems(eager, RESOLVED) == ["enforce_eager: 'False' -> 'True'"]
    # the precision is the release's own: checked against its config.json, not the default
    unquantized = adapter.model_expected({"torch_dtype": "bfloat16"})
    assert adapter.resolved_problems(ours, RESOLVED, unquantized) == []
    quant = ours.replace("quantization=None", "quantization=fp8")
    assert adapter.resolved_problems(quant, RESOLVED, unquantized) == [
        "quantization: the release states 'None', the engine resolved 'fp8'"
    ]
    fp8 = adapter.model_expected({"quantization_config": {"quant_method": "compressed-tensors"}})
    maverick = ours.replace("quantization=None", "quantization=compressed-tensors")
    assert adapter.resolved_problems(maverick, RESOLVED, fp8) == []
    assert adapter.resolved_problems(ours, RESOLVED, fp8) == [
        "quantization: the release states 'compressed-tensors', the engine resolved 'None'"
    ]


def test_engine_lines_parsed(adapter: ModuleType, tmp_path: Path) -> None:
    """The pinned version's log lines the adapter reads (vLLM v0.32.0 core.py L134 and
    kv_cache_utils.py L2328, fixture text)."""
    log = tmp_path / "engine.log"
    log.write_text(f"INFO 11-09 core.py:134] Initializing a V1 LLM engine (v0.32.0) with config: "
                   f"{RESOLVED}\nINFO kv_cache_utils.py] GPU KV cache size: 1,234,567 tokens, "
                   "Maximum concurrency for 1,025 tokens per request: 1204.45x\n")  # fmt: skip
    engine = object.__new__(adapter.ServeEngine)
    engine.log_path = log
    assert engine.resolved_config() == RESOLVED
    assert engine.kv_capacity()[0] == 1_234_567
    log.write_text("nothing\n")
    assert engine.resolved_config() is None
    assert engine.kv_capacity() is None
    assert engine.max_num_batched_tokens() is None
    log.write_text("INFO scheduler.py:307] Chunked prefill is enabled with "
                   "max_num_batched_tokens=8192.\n")  # fmt: skip
    assert engine.max_num_batched_tokens() == 8192


def test_out_of_memory_at_start_is_resource(adapter: ModuleType, tmp_path: Path) -> None:
    """SRV-6: the engine exiting at start out of GPU memory is `resource`, with the engine's
    line as evidence (the release admits a larger GPU count on it); another exit stays an
    adapter failure."""
    log = tmp_path / "engine.log"
    engine = object.__new__(adapter.ServeEngine)
    engine.log_path = log
    engine.port = 1
    engine.proc = type("P", (), {"returncode": 1, "poll": lambda self: 1})()
    line = "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB"
    log.write_text(f"INFO loading\n{line}\n")
    with pytest.raises(SystemExit) as e:
        engine.wait_ready()
    assert e.value.code == 3
    failure = json.loads((Path(adapter.host("/io")) / "failure.json").read_text())
    assert (failure["kind"], failure["evidence"]) == ("resource", [line])
    log.write_text("ValueError: Unrecognized model\n")
    with pytest.raises(SystemExit, match="exited 1 at start"):
        engine.wait_ready()


def sizing() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("sizing", str(SYSTEM / "sizing.py"))
    spec = importlib.util.spec_from_loader("sizing", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def record(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load((ROOT / f"workloads/serving/{name}.yaml").read_text())
    return doc


def test_sizing_hand_computed() -> None:
    """sizing.py (grade projected): Maverick FP8 on 140,000 MiB GPUs. Weights 416,755,504,016 B
    over 4 = 99,362.16 MiB per GPU; TP2 would need 198,724.3 MiB, above 140,000, so TP4 is
    tried first. KV: 2 x 48 x 8 x 128 x 2 B = 196,608 B per token; 24 x 1,025 tokens over 4
    GPUs = 1,152.4 MiB per GPU. Llama 3.1 8B BF16: TP1, 131,072 B per token."""
    size = sizing().size
    mav = size(record("llama-4-maverick-17b-128e-instruct-fp8"), 24, 1025, 140_000)
    assert (mav.first_count, mav.skipped) == (4, (1, 2))
    assert mav.weight_bytes == 416_755_504_016
    assert mav.weight_mib_per_gpu == pytest.approx(416_755_504_016 / 4 / 2**20)
    assert mav.kv_bytes_per_token == 196_608
    assert mav.kv_mib_per_gpu_matched == pytest.approx(24 * 1025 * 196_608 / 4 / 2**20)
    assert mav.usable_mib_per_gpu == pytest.approx(126_000)
    l31 = size(record("llama-3.1-8b-instruct-bf16"), 1, 1088, 140_000)
    assert (l31.first_count, l31.kv_bytes_per_token) == (1, 131_072)


def test_sizing_borderline_and_kv_dtype() -> None:
    """A count whose weights sit just below count x memory is tried, not skipped; the KV dtype
    follows a `kv_cache_scheme` record (fp8, 1 byte); 8 GPUs that do not hold the weights give
    no first count."""
    m = sizing()
    doc = record("llama-3.1-8b-instruct-bf16")
    weights = sum(f["bytes"] for f in doc["model"]["files"] if f["path"].endswith(".safetensors"))
    just = weights // 2**20 + 1  # MiB: weights sit just below one GPU of this size
    assert m.size(doc, 1, 1088, just).first_count == 1
    assert m.size(doc, 1, 1088, just - 1).first_count == 2
    doc["model"]["shape"]["kv_dtype"] = "fp8"
    assert m.kv_bytes_per_token(doc["model"]["shape"]) == 65_536
    assert m.size(doc, 1, 1088, 1).first_count is None
