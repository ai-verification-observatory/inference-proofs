#!/usr/bin/env python3
"""The MODEL check's weight change for SASH (RFC-0018 CH-2; levels/L1.yaml
systems.sash.model_change), on a CPU, standard library only.

SASH loads the BF16 checkpoint and quantizes every layer matrix at load: one scale per output
channel, s = bf16_ceil(max |w| / 127), and each weight's int8 code q = round_half_away(w / s),
clamped to +-127 (U/harness/witness/quant.py L18-L21, L37-L46, L90-L97, L145-L148; the matrix
is transposed so the scale reduces over the input index, model.py L193-L216; under the recorded
spec `y-delay-vw12` a layer projection gets the bf16 scale, not a power of two: common.py
L232-L233 with model.py L202 and L576-L581). U is
https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b

A change to one BF16 weight that leaves its int8 code as it was is not a change to the model SASH
commits. This finds, for one output channel (one row of the checkpoint's [out, in] tensor), the
change of one weight by the fewest BF16 steps that changes its code while the channel's scale
stays the same, so no other code moves. The weight that sets the scale is never chosen.

    weight_change.py MODEL.safetensors TENSOR ROW [COL]

prints the change as JSON: the file offset of the element, its bytes before and after (little
endian hex), the steps, the scale and both codes. Without COL it picks the column with the
fewest steps (the lowest index on a tie). Arithmetic is float32 as torch does it: a float64
result rounded once to float32 is the correctly rounded float32 result for +, -, * and /.
"""

import json
import math
import struct
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

INT8_MAX = 127
EPS = 1e-30  # quant.py qscale's clamp_min
EXPONENT = 0x7F80  # a BF16 pattern with all exponent bits set is not finite


def f32(x: float) -> float:
    """x rounded to float32, ties to even."""
    return float(struct.unpack("<f", struct.pack("<f", x))[0])


def bf16(bits: int) -> float:
    """The value of a BF16 bit pattern (the upper half of a float32)."""
    return float(struct.unpack("<f", struct.pack("<I", (bits & 0xFFFF) << 16))[0])


def bf16_ceil(x: float) -> float:
    """quant.py bf16_ceil: the smallest BF16 value >= x > 0. torch rounds float32 to BF16 to
    nearest, ties to even, then steps up once if that fell below x."""
    u = struct.unpack("<I", struct.pack("<f", x))[0]
    upper, lower = u >> 16, u & 0xFFFF
    if lower > 0x8000 or (lower == 0x8000 and upper & 1):
        upper += 1
    if bf16(upper) < x:
        upper += 1
    return bf16(upper)


def scale(row: Sequence[int]) -> float:
    """quant.py qscale over one output channel: bf16_ceil(max(max |w|, eps) / 127), float32."""
    top = max(abs(bf16(b)) for b in row)
    return bf16_ceil(f32(max(top, f32(EPS)) / INT8_MAX))


def code(w: float, s: float) -> int:
    """quant.py quantize: sign(x) floor(|x| + 0.5) with x = w / s in float32, clamped."""
    x = f32(w / s)
    q = math.copysign(math.floor(f32(abs(x) + 0.5)), x)
    return int(max(-INT8_MAX, min(INT8_MAX, q)))


def step(bits: int, up: bool) -> int:
    """The next BF16 pattern toward +infinity (up) or -infinity."""
    negative = bool(bits & 0x8000)
    if bits & 0x7FFF == 0:  # +0 or -0
        return 0x0001 if up else 0x8001
    return bits - 1 if negative == up else bits + 1


@dataclass(frozen=True)
class Change:
    col: int
    before: int  # BF16 bits
    after: int
    steps: int  # signed: BF16 steps toward +infinity
    scale: float
    code_before: int
    code_after: int


def smallest_change(row: Sequence[int], col: int) -> Change | None:
    """The fewest BF16 steps on row[col] that change its code with the scale unchanged; up wins a
    tie. None for the weight that sets the scale, or when no such step exists."""
    s = scale(row)
    w = row[col]
    if abs(bf16(w)) == max(abs(bf16(b)) for b in row):
        return None
    before = code(bf16(w), s)
    best: Change | None = None
    for up in (True, False):
        bits, n = w, 0
        while True:
            bits, n = step(bits, up), n + 1
            if bits & EXPONENT == EXPONENT or (best and n >= abs(best.steps)):
                break
            changed = [*row[:col], bits, *row[col + 1 :]]
            if scale(changed) != s:  # the weight would set the scale: every code could move
                break
            after = code(bf16(bits), s)
            if after != before:
                best = Change(col, w, bits, n if up else -n, s, before, after)
                break
    return best


def best_in_row(row: Sequence[int]) -> Change | None:
    found = [c for c in (smallest_change(row, j) for j in range(len(row))) if c is not None]
    return min(found, key=lambda c: (abs(c.steps), c.col), default=None)


def read_row(path: Path, tensor: str, row: int) -> tuple[int, list[int]]:
    """(file offset of the row's first element, its BF16 patterns) from a safetensors file: an
    8-byte little-endian header length, the JSON header, then the data."""
    with path.open("rb") as f:
        size = int.from_bytes(f.read(8), "little")
        info = json.loads(f.read(size))[tensor]
        if info["dtype"] != "BF16" or len(info["shape"]) != 2:
            raise SystemExit(f"weight_change: {tensor} is {info['dtype']} {info['shape']}, "
                             "not a BF16 matrix")  # fmt: skip
        cols = int(info["shape"][1])
        offset = 8 + size + int(info["data_offsets"][0]) + 2 * cols * row
        f.seek(offset)
        data = f.read(2 * cols)
    return offset, [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


def main(argv: list[str]) -> int:
    path, tensor, row = Path(argv[0]), argv[1], int(argv[2])
    offset, values = read_row(path, tensor, row)
    change = best_in_row(values) if len(argv) < 4 else smallest_change(values, int(argv[3]))
    if change is None:
        raise SystemExit("weight_change: no single-weight change of this row moves a code")
    doc = asdict(change) | {
        "file": path.name, "tensor": tensor, "row": row, "dtype": "BF16",
        "offset": offset + 2 * change.col,
        "before": change.before.to_bytes(2, "little").hex(),
        "after": change.after.to_bytes(2, "little").hex(),
    }  # fmt: skip
    print(json.dumps(doc, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
