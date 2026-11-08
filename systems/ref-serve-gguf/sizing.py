"""The starting `--n-cpu-moe N` for the Maverick plain-serving row (RFC-0015 SRV-6): a computation
from the GGUF tensor tables, not a measurement. README §Sizing prints its output; a test checks
that the README table is this script's output.

Usage (from the repository root, with the harness installed):
  python systems/ref-serve-gguf/sizing.py [TENSORS_JSON]

TENSORS_JSON defaults to tests/fixtures/maverick-tensors.json next to this file.

Placement at llama.cpp `cd959bae99ff4bed22bef2604f45241c09bbb8c8` with `-ngl all`: every tensor
is on the GPU except the input embedding, which stays in host memory (src/llama-model.cpp L1772
to L1774), and the routed experts of layers 0 to N-1, which `--n-cpu-moe N` keeps in host memory
(common/arg.cpp L2718 to L2726, the regex of common/common.h L1262 and the per-layer loop of
L1274 to L1281).
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from iproofs.gguf import Tensor

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "tests/fixtures/maverick-tensors.json"
MIB = 1 << 20
EXPERTS = re.compile(r"\.ffn_(up|down|gate|gate_up)_(ch|)exps")  # LLM_FFN_EXPS_REGEX
LAYER = re.compile(r"^blk\.(\d+)\.")
INPUT = "token_embd.weight"

# The GPU memory one job may count on, and what it needs besides the weights. Profile value:
# reference/v0.1.yaml prover-h200-hosted gpu.memory_mib_min. The others are assumptions until
# the first run's log prints the engine's own buffer sizes (README §Sizing).
GPU_MIB = 140_000
COMPUTE_MIB = 8_192  # compute buffers, with room for a CPU-held expert tensor copied to the
#                      GPU for a large batch (--op-offload, on by default, README L94). The
#                      scheduler copies one such tensor per split: a weight on another backend
#                      starts a new split "so the memory of the previously offloaded weights can
#                      be reused" (ggml/src/ggml-backend.cpp L1739 to L1748), and the copies are
#                      graph nodes, freed after their last use (L1938). largest_expert_mib()
#                      must fit in it; the rest is activations (an assumption)
CONTEXT_MIB = 1_024  # CUDA context and cuBLAS workspace
MARGIN_MIB = 1_024  # the engine's own --fit margin default (--fit-target, README L90)
KV_PAD = 256  # cells rounded up to a multiple of 256 (an upper bound on the engine's padding)
KV_BYTES = 2  # f16, the default cache type (-ctk/-ctv, README L71 to L72)


@dataclass(frozen=True)
class Placement:
    n: int
    gpu_weight_bytes: int
    host_weight_bytes: int


def tensors(path: Path = FIXTURE) -> tuple[dict[str, object], list[Tensor]]:
    doc = json.loads(path.read_text())
    found = [Tensor(name, tuple(dims), ggml_type, 0)
             for f in doc["files"] for name, dims, ggml_type in f["tensors"]]  # fmt: skip
    return doc["metadata"], found


def placement(found: list[Tensor], n: int) -> Placement:
    gpu = host = 0
    for t in found:
        layer = LAYER.match(t.name)
        on_host = t.name == INPUT or (
            EXPERTS.search(t.name) is not None and layer is not None and int(layer.group(1)) < n
        )
        if on_host:
            host += t.nbytes
        else:
            gpu += t.nbytes
    return Placement(n, gpu, host)


def largest_expert_mib(found: list[Tensor]) -> float:
    """The largest routed-expert tensor: the most --op-offload copies to the GPU at a time."""
    return max(t.nbytes for t in found if EXPERTS.search(t.name) is not None) / MIB


def kv_bytes(meta: dict[str, object], slots: int, per_slot: int) -> int:
    """K and V for every layer and cell, the cells of all slots padded up (an upper bound: the
    chunked-attention layers of llama4 may hold fewer cells)."""
    cells = -(-slots * per_slot // KV_PAD) * KV_PAD
    layers, heads, k, v = (int(str(meta[f"llama4.{key}"])) for key in (
        "block_count", "attention.head_count_kv", "attention.key_length",
        "attention.value_length"))  # fmt: skip
    return cells * layers * heads * (k + v) * KV_BYTES


def weight_budget_mib(meta: dict[str, object], slots: int, per_slot: int) -> float:
    return GPU_MIB - kv_bytes(meta, slots, per_slot) / MIB - COMPUTE_MIB - CONTEXT_MIB - MARGIN_MIB


def start_n(meta: dict[str, object], found: list[Tensor], slots: int, per_slot: int) -> int:
    """The smallest N whose GPU weights fit the budget. Odd N place as the even N below them
    (the MoE layers of the pinned files are the odd ones, `interleave_moe_layer_step` 2), so
    only even N are listed."""
    budget = weight_budget_mib(meta, slots, per_slot)
    blocks = int(str(meta["llama4.block_count"]))
    for n in range(0, blocks + 1, 2):
        if placement(found, n).gpu_weight_bytes / MIB <= budget:
            return n
    raise SystemExit("no N fits: --cpu-moe is the next step (SRV-6)")


def report(path: Path = FIXTURE) -> str:
    meta, found = tensors(path)
    per_slot = 1025  # prompt plus output tokens of both Maverick workloads
    lines = [f"budget per job: {GPU_MIB:,} MiB of GPU memory"]
    lines.append(
        f"compute buffers: {COMPUTE_MIB:,} MiB, of which the largest routed-expert tensor"
        f" copied for --op-offload is {largest_expert_mib(found):,.0f} MiB"
    )
    for slots in (1, 24):
        kv = kv_bytes(meta, slots, per_slot) / MIB
        lines.append(
            f"-np {slots}: KV cache at most {kv:,.0f} MiB; weights may use"
            f" {weight_budget_mib(meta, slots, per_slot):,.0f} MiB;"
            f" start N = {start_n(meta, found, slots, per_slot)}"
        )
    lines.append("")
    lines.append("| N | GPU weights (MiB) | host weights (GB) | fits -np 1 | fits -np 24 |")
    lines.append("|---|---|---|---|---|")
    for n in range(14, 31, 2):
        p = placement(found, n)
        fits = [
            "yes" if p.gpu_weight_bytes / MIB <= weight_budget_mib(meta, s, per_slot) else "no"
            for s in (1, 24)
        ]
        lines.append(f"| {n} | {p.gpu_weight_bytes / MIB:,.0f} | {p.host_weight_bytes / 1e9:,.1f}"
                     f" | {fits[0]} | {fits[1]} |")  # fmt: skip
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(report(Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE))
