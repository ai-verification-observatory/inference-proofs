"""drop_blocks.py on a tiny synthetic GGUF (RFC-0018 FI-2), read back by the harness's own GGUF
reader (iproofs.gguf, an independent implementation that checks the layout)."""

import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

from iproofs.gguf import file_source, read_header

SYSTEM = Path(__file__).resolve().parents[1]
F32, F16 = 0, 1


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drop_blocks", SYSTEM / "drop_blocks.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["drop_blocks"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


db = _module()


Kvs = list[tuple[str, int, object, int | None]]
Tensors = list[tuple[str, tuple[int, ...], int, bytes]]


def write_gguf(path: Path, kvs: Kvs, tensors: Tensors, alignment: int = 32) -> None:
    """A GGUF v3 file as llama.cpp lays it out: header, padding, each tensor padded."""
    encoded = [db.KV(k, t, db.encode_value(t, v, item)) for k, t, v, item in kvs]
    head = db.MAGIC + struct.pack("<IQQ", 3, len(tensors), len(encoded))
    head += b"".join(kv.encoded() for kv in encoded)
    offset, data = 0, b""
    for name, dims, ggml_type, payload in tensors:
        head += db.Tensor(name, dims, ggml_type, 0).encoded(offset)
        padded = db.pad(len(payload), alignment)
        data += payload + b"\x00" * (padded - len(payload))
        offset += padded
    head += b"\x00" * (db.pad(len(head), alignment) - len(head))
    path.write_bytes(head + data)


def f32(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def model(path: Path, arch: str, blocks: int, step: int | None = None) -> None:
    kvs: Kvs = [
        ("general.architecture", db.STRING, arch, None),
        ("general.alignment", db.UINT32, 32, None),
        (f"{arch}.block_count", db.UINT32, blocks, None),
        (f"{arch}.feed_forward_length", db.ARRAY, [100 + i for i in range(blocks)], db.UINT32),
        (f"{arch}.context_length", db.UINT32, 4096, None),
        ("tokenizer.ggml.tokens", db.ARRAY, ["a", "b", "c"], db.STRING),
    ]
    if step is not None:
        kvs.append((f"{arch}.interleave_moe_layer_step", db.UINT32, step, None))
    tensors: Tensors = [("token_embd.weight", (4, 3), F32, f32(*range(12)))]
    for i in range(blocks):
        tensors.append((f"blk.{i}.attn_norm.weight", (4,), F32, f32(i, i, i, i)))
        tensors.append((f"blk.{i}.ffn_down.weight", (3,), F16, struct.pack("<3e", i, -i, 0.5)))
    tensors.append(("output_norm.weight", (4,), F32, f32(9, 9, 9, 9)))
    write_gguf(path, kvs, tensors)


def tensor_bytes(path: Path, name: str) -> bytes:
    header = read_header(file_source(path), path.stat().st_size)
    t = next(t for t in header.tensors if t.name == name)
    with path.open("rb") as f:
        f.seek(header.data_offset + t.offset)
        return f.read(t.nbytes)


def test_every_fourth_block_removed_and_renumbered(tmp_path: Path) -> None:
    src, dst = tmp_path / "in.gguf", tmp_path / "out.gguf"
    model(src, "llama", 8)
    summary = db.drop_blocks(src, dst, 4)
    assert (summary["dropped"], summary["new_block_count"]) == ([3, 7], 6)
    header = read_header(file_source(dst), dst.stat().st_size)  # checks the layout too
    assert header.metadata["llama.block_count"] == 6
    assert header.metadata["llama.feed_forward_length"] == 6  # arrays are read as lengths
    names = [t.name for t in header.tensors]
    assert (names[0], names[-1]) == ("token_embd.weight", "output_norm.weight")
    assert sorted({n.split(".")[1] for n in names if n.startswith("blk.")}) == list("012345")
    # new block 3 is old block 4, new block 5 is old block 6
    assert tensor_bytes(dst, "blk.3.attn_norm.weight") == f32(4, 4, 4, 4)
    assert tensor_bytes(dst, "blk.5.ffn_down.weight") == struct.pack("<3e", 6, -6, 0.5)
    assert tensor_bytes(dst, "output_norm.weight") == f32(9, 9, 9, 9)
    ffn = db.read(dst).kv("llama.feed_forward_length").value()
    assert ffn == [100, 101, 102, 104, 105, 106]
    assert db.read(dst).kv("tokenizer.ggml.tokens").value() == ["a", "b", "c"]


def test_interleaved_moe_model_drops_whole_groups(tmp_path: Path) -> None:
    """Llama 4's step 2: a block's kind follows its index, so groups of 2 go together."""
    src, dst = tmp_path / "in.gguf", tmp_path / "out.gguf"
    model(src, "llama4", 16, step=2)
    summary = db.drop_blocks(src, dst, 4)
    assert (summary["dropped"], summary["new_block_count"]) == ([6, 7, 14, 15], 12)
    assert tensor_bytes(dst, "blk.6.attn_norm.weight") == f32(8, 8, 8, 8)


def test_refuses_a_file_that_ends_inside_a_tensor(tmp_path: Path) -> None:
    src, dst = tmp_path / "in.gguf", tmp_path / "out.gguf"
    model(src, "llama", 8)
    data = src.read_bytes()
    src.write_bytes(data[:-40])  # cuts into output_norm.weight
    with pytest.raises(db.GgufError):
        db.drop_blocks(src, dst, 4)
    assert not dst.exists()
