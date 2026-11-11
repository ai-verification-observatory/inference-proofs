#!/usr/bin/env python3
"""The `drop_blocks` control of RFC-0018 FI-2: a GGUF copy of a model with every fourth
transformer block removed.

Usage: drop_blocks.py <in.gguf> <out.gguf> --every 4

A block is the tensors named `blk.<i>.*`. Blocks are taken in groups of `g` consecutive blocks,
`g` the model's `<arch>.interleave_moe_layer_step` (1 when absent): llama.cpp reads a layer as
a mixture-of-experts layer when (i + 1) is a multiple of that step (src/models/llama4.cpp L62 at
the pin), so removing one block of an interleaved model would shift every later layer's kind
and the copy would not load. Group k is removed when k % every == every - 1: blocks 3, 7, 11,
... of a dense model (Llama 3.1 8B: 8 of 32), the pairs (6, 7), (14, 15), ... of Llama 4
Maverick (step 2: 12 of 48). Either way 1/every of the blocks goes. The kept blocks are
renumbered from 0 in order, `<arch>.block_count` is set to their number, and every `<arch>.*`
array with one entry per block loses the removed blocks' entries. Every other key and tensor is
copied byte for byte.

Standard library only, so its CPU test needs no llama.cpp: the format is GGUF version 3 as
llama.cpp writes it at the pin (ggml/src/gguf.cpp; `general.alignment` a UINT32, default 32;
each tensor's offset the sum of the padded sizes before it, in header order). A tensor's bytes
are the span to the next tensor's offset (its padded size), so no type table is needed. The
entrypoint then opens the result with the `gguf` package of llama.cpp's own tree and loads it
with llama.cpp, which are the end checks.
"""

import argparse
import json
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MAGIC = b"GGUF"
DEFAULT_ALIGNMENT = 32
CHUNK = 64 << 20
# GGUF value types (ggml/include/gguf.h enum gguf_type): fixed-size scalars, string 8, array 9.
SCALARS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q",
           11: "<q", 12: "<d"}  # fmt: skip
STRING, ARRAY, UINT32 = 8, 9, 4
BLOCK = re.compile(r"^blk\.(\d+)\.(.+)$")


class GgufError(Exception):
    """The input is not a GGUF file this tool can rewrite."""


@dataclass(frozen=True, slots=True)
class KV:
    key: str
    vtype: int
    raw: bytes  # the encoded value, as stored

    def value(self) -> object:
        return _Reader(self.raw).value(self.vtype)

    def encoded(self) -> bytes:
        key = self.key.encode()
        return struct.pack("<Q", len(key)) + key + struct.pack("<I", self.vtype) + self.raw


@dataclass(frozen=True, slots=True)
class Tensor:
    name: str
    dims: tuple[int, ...]
    ggml_type: int
    offset: int  # from the start of the data section

    def encoded(self, offset: int) -> bytes:
        name = self.name.encode()
        out = struct.pack("<Q", len(name)) + name + struct.pack("<I", len(self.dims))
        out += b"".join(struct.pack("<Q", d) for d in self.dims)
        return out + struct.pack("<IQ", self.ggml_type, offset)


@dataclass(frozen=True, slots=True)
class Gguf:
    version: int
    kvs: tuple[KV, ...]
    tensors: tuple[Tensor, ...]
    alignment: int
    data_offset: int
    size: int  # file bytes

    def kv(self, key: str) -> KV | None:
        return next((kv for kv in self.kvs if kv.key == key), None)

    def spans(self) -> dict[str, int]:
        """Each tensor's bytes in the file: up to the next tensor's offset (its padded size),
        the last one up to the end of the file (llama.cpp's writer pads it, gguf.cpp L1609; a
        file that ends unpadded is read as it is and padded on writing)."""
        order = sorted(self.tensors, key=lambda t: t.offset)
        ends = [t.offset for t in order[1:]] + [self.size - self.data_offset]
        spans = {t.name: end - t.offset for t, end in zip(order, ends, strict=True)}
        if any(s < 0 for s in spans.values()):
            raise GgufError("tensor offsets overlap")
        return spans


def pad(n: int, alignment: int) -> int:
    return -(-n // alignment) * alignment


class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data, self.pos = data, pos

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise GgufError("GGUF header runs past the bytes read")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def u64(self) -> int:
        return int(struct.unpack("<Q", self.take(8))[0])

    def string(self) -> str:
        return self.take(self.u64()).decode("utf-8")

    def value(self, vtype: int) -> object:
        if vtype in SCALARS:
            fmt = SCALARS[vtype]
            return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]
        if vtype == STRING:
            return self.string()
        if vtype == ARRAY:
            item, count = self.u32(), self.u64()
            if item in SCALARS:
                size = struct.calcsize(SCALARS[item])
                return [v[0] for v in struct.iter_unpack(SCALARS[item], self.take(size * count))]
            return [self.value(item) for _ in range(count)]
        raise GgufError(f"GGUF value type {vtype} is unknown")

    def skip_value(self, vtype: int) -> None:
        if vtype in SCALARS:
            self.take(struct.calcsize(SCALARS[vtype]))
        elif vtype == STRING:
            self.take(self.u64())
        elif vtype == ARRAY:
            item, count = self.u32(), self.u64()
            if item in SCALARS:
                self.take(struct.calcsize(SCALARS[item]) * count)
            else:
                for _ in range(count):
                    self.skip_value(item)
        else:
            raise GgufError(f"GGUF value type {vtype} is unknown")


def encode_value(vtype: int, value: object, item_type: int | None = None) -> bytes:
    """The stored bytes of a value of GGUF type `vtype` (an array needs its `item_type`)."""
    if vtype in SCALARS:
        return struct.pack(SCALARS[vtype], value)
    if vtype == STRING:
        data = str(value).encode()
        return struct.pack("<Q", len(data)) + data
    if vtype == ARRAY:
        if item_type is None or not isinstance(value, list):
            raise GgufError("an array value needs a list and its item type")
        items = b"".join(encode_value(item_type, v) for v in value)
        return struct.pack("<IQ", item_type, len(value)) + items
    raise GgufError(f"GGUF value type {vtype} is unknown")


def read(path: Path) -> Gguf:
    """The header of a little-endian GGUF version 2 or 3 file."""
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(min(size, 1 << 20))
        while True:  # grow the read until the header parses (tokenizer arrays run to MBs)
            try:
                return _parse(head, size)
            except GgufError as e:
                if "past the bytes read" not in str(e) or len(head) >= size:
                    raise
                f.seek(0)
                head = f.read(min(size, len(head) * 4))


def _parse(data: bytes, size: int) -> Gguf:
    r = _Reader(data)
    if r.take(4) != MAGIC:
        raise GgufError("not a GGUF file (magic)")
    version = r.u32()
    if version not in (2, 3):
        raise GgufError(f"GGUF version {version}")
    n_tensors, n_kv = r.u64(), r.u64()
    kvs = []
    for _ in range(n_kv):
        key, vtype = r.string(), r.u32()
        start = r.pos
        r.skip_value(vtype)
        kvs.append(KV(key, vtype, data[start : r.pos]))
    tensors = []
    for _ in range(n_tensors):
        name, n_dims = r.string(), r.u32()
        dims = tuple(r.u64() for _ in range(n_dims))
        ggml_type, offset = r.u32(), r.u64()
        tensors.append(Tensor(name, dims, ggml_type, offset))
    align_kv = next((kv for kv in kvs if kv.key == "general.alignment"), None)
    alignment = DEFAULT_ALIGNMENT
    if align_kv is not None:
        value = align_kv.value()
        if align_kv.vtype != UINT32 or not isinstance(value, int) or value & (value - 1):
            raise GgufError("general.alignment is not a UINT32 power of two")
        alignment = value
    return Gguf(version, tuple(kvs), tuple(tensors), alignment, pad(r.pos, alignment), size)


def dropped_blocks(block_count: int, every: int, group: int = 1) -> list[int]:
    """The blocks removed: group k (blocks k*group .. k*group + group - 1) when
    k % every == every - 1."""
    if every < 2 or group < 1:
        raise GgufError(f"every {every} and group {group}: every >= 2, group >= 1")
    return [i for i in range(block_count) if (i // group) % every == every - 1]


def drop_blocks(src: Path, dst: Path, every: int) -> dict[str, object]:
    """Write `dst`, the copy of `src` without the blocks `dropped_blocks` names; return what
    was done (printed by the command line and recorded by the entrypoint)."""
    model = read(src)
    if model.kv("split.count") is not None:
        raise GgufError("a split GGUF file: give the single file convert_hf_to_gguf.py writes")
    arch_kv = model.kv("general.architecture")
    if arch_kv is None:
        raise GgufError("no general.architecture")
    arch = str(arch_kv.value())
    count_kv = model.kv(f"{arch}.block_count")
    if count_kv is None:
        raise GgufError(f"no {arch}.block_count")
    old = int(str(count_kv.value()))
    step_kv = model.kv(f"{arch}.interleave_moe_layer_step")
    group = max(1, int(str(step_kv.value()))) if step_kv is not None else 1
    dropped = dropped_blocks(old, every, group)
    kept = [i for i in range(old) if i not in set(dropped)]
    renumber = {old_i: new_i for new_i, old_i in enumerate(kept)}
    kvs, filtered = [], []
    for kv in model.kvs:
        new = kv
        if kv.key == count_kv.key:
            new = KV(kv.key, kv.vtype, encode_value(kv.vtype, len(kept)))
        elif kv.key.startswith(f"{arch}.") and kv.vtype == ARRAY:
            item = _Reader(kv.raw).u32()
            values = kv.value()
            if isinstance(values, list) and len(values) == old:
                kept_values = [values[i] for i in kept]
                new = KV(kv.key, kv.vtype, encode_value(ARRAY, kept_values, item))
                filtered.append(kv.key)
        kvs.append(new)
    spans = model.spans()
    out: list[tuple[Tensor, Tensor]] = []  # (source, renamed)
    for t in model.tensors:
        m = BLOCK.match(t.name)
        if m is None:
            out.append((t, t))
        elif int(m.group(1)) in renumber:
            name = f"blk.{renumber[int(m.group(1))]}.{m.group(2)}"
            out.append((t, Tensor(name, t.dims, t.ggml_type, 0)))
    if any(int(m.group(1)) >= old for t in model.tensors if (m := BLOCK.match(t.name))):
        raise GgufError(f"a tensor names a block at or above {arch}.block_count {old}")
    _write(src, dst, model, kvs, out, spans)
    return {"architecture": arch, "block_count": old, "new_block_count": len(kept),
            "every": every, "group": group, "dropped": dropped, "arrays_filtered": filtered,
            "tensors": len(model.tensors), "new_tensors": len(out)}  # fmt: skip


def _write(
    src: Path,
    dst: Path,
    model: Gguf,
    kvs: list[KV],
    tensors: list[tuple[Tensor, Tensor]],
    spans: dict[str, int],
) -> None:
    head = MAGIC + struct.pack("<IQQ", model.version, len(tensors), len(kvs))
    head += b"".join(kv.encoded() for kv in kvs)
    offset, infos = 0, []
    for source, renamed in tensors:
        infos.append(renamed.encoded(offset))
        offset += pad(spans[source.name], model.alignment)
    head += b"".join(infos)
    head += b"\x00" * (pad(len(head), model.alignment) - len(head))
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        with src.open("rb") as fin, tmp.open("wb") as fout:
            fout.write(head)
            for source, _ in tensors:
                span = spans[source.name]
                _copy(fin, fout, model.data_offset + source.offset, span)
                fout.write(b"\x00" * (pad(span, model.alignment) - span))
            fout.flush()
            os.fsync(fout.fileno())
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def _copy(fin: BinaryIO, fout: BinaryIO, start: int, length: int) -> None:
    """`length` bytes of `fin` from `start`, appended to `fout`."""
    fin.seek(start)
    remaining = length
    while remaining:
        chunk = fin.read(min(CHUNK, remaining))
        if not chunk:
            raise GgufError(f"the file ends {remaining} bytes before a tensor's end")
        fout.write(chunk)
        remaining -= len(chunk)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--every", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        summary = drop_blocks(args.src, args.dst, args.every)
    except (GgufError, OSError) as e:
        print(f"drop_blocks: {e}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
