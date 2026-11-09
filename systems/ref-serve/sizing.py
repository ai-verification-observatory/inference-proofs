"""Planning arithmetic for production serving (RFC-0015 SRV-6): which GPU count to try first.

Sizing only orders the attempts; the engine's load decides (the adapter fails `resource` when
its KV cache is below the matched load). Every figure here is grade projected, never published,
and comes from a serving record (`workloads/serving/<id>.yaml`: file bytes and the shape
`iproofs serving pin` copied from config.json) and a profile's `gpu.memory_mib_min`.

    python3 systems/ref-serve/sizing.py RECORD BATCH MAX_MODEL_LEN [MEMORY_MIB]

The admission test is deliberately loose: weight bytes below count x the device memory, so a
borderline count is tried rather than skipped. The per-GPU figures assume an even split over
ranks and 0.9 of the memory usable (vLLM's default `gpu_memory_utilization`); they are context,
not the gate.
"""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

MIB = 1024 * 1024
DTYPE_BYTES = {"bfloat16": 2, "float16": 2, "float32": 4, "fp8": 1}
USABLE = 0.9  # vLLM's default gpu_memory_utilization, as context
COUNTS = (1, 2, 4, 8)  # GPUs in one node


@dataclass(frozen=True)
class Sizing:
    first_count: int | None  # the first GPU count to try, or None when 8 do not hold the weights
    weight_bytes: int
    weight_mib_per_gpu: float  # at first_count
    usable_mib_per_gpu: float
    kv_bytes_per_token: int
    kv_mib_per_gpu_matched: float  # batch x max model length, at first_count
    skipped: tuple[int, ...]  # counts that divide the heads but fail the loose test


def kv_bytes_per_token(shape: dict) -> int:
    """K and V for every layer and KV head: 2 x layers x KV heads x head size x dtype bytes."""
    return (
        2 * shape["layers"] * shape["kv_heads"] * shape["head_dim"] * DTYPE_BYTES[shape["kv_dtype"]]
    )


def size(record: dict, batch: int, max_model_len: int, memory_mib: int) -> Sizing:
    """The first GPU count among those dividing the attention and KV heads whose weights fit
    below count x `memory_mib`, with the per-GPU context figures at that count."""
    model = record["model"]
    weights = sum(f["bytes"] for f in model["files"] if f["path"].endswith(".safetensors"))
    shape = model["shape"]
    kv = kv_bytes_per_token(shape)
    usable = USABLE * memory_mib
    dividing = [n for n in COUNTS
                if shape["attention_heads"] % n == 0 and shape["kv_heads"] % n == 0]  # fmt: skip
    fits = [n for n in dividing if weights < n * memory_mib * MIB]
    first = fits[0] if fits else None
    n = first or max(dividing)
    return Sizing(
        first_count=first,
        weight_bytes=weights,
        weight_mib_per_gpu=weights / n / MIB,
        usable_mib_per_gpu=usable,
        kv_bytes_per_token=kv,
        kv_mib_per_gpu_matched=batch * max_model_len * kv / n / MIB,
        skipped=tuple(c for c in dividing if c not in fits),
    )


def main(argv: list[str]) -> int:
    record = yaml.safe_load(Path(argv[1]).read_text())
    memory = int(argv[4]) if len(argv) > 4 else 140_000  # serving-h200x*-hosted memory_mib_min
    out = asdict(size(record, int(argv[2]), int(argv[3]), memory))
    print(json.dumps({"grade": "projected", **out}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
