"""The starting `--n-cpu-moe N` (README §Sizing): sizing.py against a hand-computed case, the
README table against sizing.py, and system.yaml against the computed start. Computed values from
the GGUF headers, not measurements."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from iproofs.gguf import Tensor

SYSTEM = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sizing() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ref_serve_gguf_sizing", SYSTEM / "sizing.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def test_placement_hand_computed(sizing: ModuleType) -> None:
    """Two layers, the routed experts in layer 1: F32 is 4 B a weight, F16 2 B, Q8_0 34 B a block
    of 32 weights. The input embedding (32 B) is always in host memory; the experts (2 blocks,
    68 B) move there from N 2 on."""
    found = [
        Tensor("token_embd.weight", (4, 2), 0, 0),  # 32 B
        Tensor("blk.0.attn_q.weight", (2, 2), 0, 0),  # 16 B
        Tensor("blk.1.ffn_gate_inp.weight", (2, 2), 0, 0),  # 16 B, the router stays
        Tensor("blk.1.ffn_up_exps.weight", (32, 1, 2), 8, 0),  # 68 B
        Tensor("output.weight", (2, 4), 1, 0),  # 16 B
    ]
    assert sizing.placement(found, 0) == sizing.Placement(0, 116, 32)
    assert sizing.placement(found, 1) == sizing.Placement(1, 116, 32)  # layer 0 has no experts
    assert sizing.placement(found, 2) == sizing.Placement(2, 48, 100)


def test_kv_bytes_hand_computed(sizing: ModuleType) -> None:
    """2 layers, 1 KV head of 2 for K and 2 for V, f16: 16 B a cell; 3 cells pad to 256."""
    meta = {"llama4.block_count": 2, "llama4.attention.head_count_kv": 1,
            "llama4.attention.key_length": 2, "llama4.attention.value_length": 2}  # fmt: skip
    assert sizing.kv_bytes(meta, 1, 3) == 256 * 16
    assert sizing.kv_bytes(meta, 2, 200) == 512 * 16


def test_fixture_is_the_pinned_files(sizing: ModuleType) -> None:
    """The tensor tables cover the workload's five files at their listed sizes, and their tensor
    bytes fit inside each file."""
    doc = json.loads(sizing.FIXTURE.read_text())
    wl = yaml.safe_load((SYSTEM.parents[1] / "workloads/fp-maverick-w1024-b1.yaml").read_text())
    pinned = [(f["path"], f["bytes"]) for f in wl["model"]["files"]]
    assert [(f["path"], f["bytes"]) for f in doc["files"]] == pinned
    meta, found = sizing.tensors()
    assert len(found) == meta["split.tensors.count"] == 531
    for f in doc["files"]:
        tensor_bytes = sum(Tensor(n, tuple(d), t, 0).nbytes for n, d, t in f["tensors"])
        assert 0 < tensor_bytes < f["bytes"]


def test_readme_table_is_computed(sizing: ModuleType) -> None:
    """AGENTS.md rule 3: the README prints sizing.py's output, not typed numbers."""
    readme = (SYSTEM / "README.md").read_text()
    assert sizing.report() in readme


def test_system_yaml_starts_at_the_computed_n(sizing: ModuleType) -> None:
    meta, found = sizing.tensors()
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    for entry in doc["workloads"]:
        args = entry["engine_args"]
        slots = int(args[args.index("-np") + 1])
        n = int(args[args.index("--n-cpu-moe") + 1])
        assert n == sizing.start_n(meta, found, slots, 1025), entry["id"]


def test_compute_allowance_holds_one_expert_tensor(sizing: ModuleType) -> None:
    """--op-offload copies one host-held weight per split (ggml-backend.cpp L1739 to L1748), so
    the compute allowance must hold the largest routed-expert tensor, with room left over."""
    _, found = sizing.tensors()
    assert sizing.largest_expert_mib(found) < sizing.COMPUTE_MIB / 2


def test_gpu_budget_is_the_profiles(sizing: ModuleType) -> None:
    """AGENTS.md rule 3: the budget is the profile's GPU minimum, not a typed copy."""
    ref = yaml.safe_load((SYSTEM.parents[1] / "reference/v0.1.yaml").read_text())["profiles"]
    assert ref["prover-h200-hosted"]["gpu"]["memory_mib_min"] == sizing.GPU_MIB


def test_no_n_fits(sizing: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    meta, found = sizing.tensors()
    monkeypatch.setattr(sizing, "GPU_MIB", 1_000)
    with pytest.raises(SystemExit, match="--cpu-moe is the next step"):
        sizing.start_n(meta, found, 1, 1025)
