"""RFC-0008 C3 and P1: the perturbed copy of the weights."""

import json
import struct
from pathlib import Path

import pytest

from iproofs.controls import NotApplicable, perturb_model, safetensors_header, ulp_up


def write_safetensors(path: Path, tensors: dict[str, tuple[str, list[int], bytes]]) -> None:
    """A safetensors file: 8-byte little-endian header length, JSON header, then the data."""
    header: dict[str, object] = {"__metadata__": {"format": "pt"}}
    data = b""
    for name, (dtype, shape, raw) in tensors.items():
        header[name] = {
            "dtype": dtype,
            "shape": shape,
            "data_offsets": [len(data), len(data) + len(raw)],
        }
        data += raw
    blob = json.dumps(header).encode()
    path.write_bytes(len(blob).to_bytes(8, "little") + blob + data)


def f32(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def model(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    write_safetensors(src / "model-00002.safetensors", {
        "b.weight": ("F32", [32, 32], f32(*[0.5] * 1024)),
        "a.small": ("F32", [4], f32(1, 2, 3, 4)),  # under 1,024 elements: never chosen
    })  # fmt: skip
    write_safetensors(src / "model-00001.safetensors", {
        "c.weight": ("BF16", [1024], b"\x80\x3f" * 1024),
    })  # fmt: skip
    (src / "config.json").write_text("{}")
    return src


def test_perturb_is_deterministic_and_changes_one_element(tmp_path: Path) -> None:
    src = model(tmp_path)
    first = perturb_model(src, tmp_path / "w1")
    second = perturb_model(src, tmp_path / "w2")
    assert first == second
    assert (first.file, first.tensor, first.dtype) == ("model-00002.safetensors", "b.weight", "F32")
    assert struct.unpack("<f", bytes.fromhex(first.after))[0] == 0.5 + 2**-24  # one ulp of 0.5
    changed = [
        (p.relative_to(tmp_path / "w1").as_posix(), i)
        for p in sorted((tmp_path / "w1").rglob("*"))
        if p.is_file()
        for i, (a, b) in enumerate(
            zip(p.read_bytes(), (src / p.relative_to(tmp_path / "w1")).read_bytes(), strict=True)
        )
        if a != b
    ]
    start, header = safetensors_header(src / "model-00002.safetensors")
    offset = start + header["b.weight"]["data_offsets"][0]  # type: ignore[index]
    assert changed == [("model-00002.safetensors", offset)]  # one byte of element 0 here
    assert (tmp_path / "w1/model-00002.safetensors").read_bytes() == (
        tmp_path / "w2/model-00002.safetensors"
    ).read_bytes()


@pytest.mark.parametrize(
    ("raw", "dtype", "want"),
    [
        (f32(1.0), "F32", f32(1.0 + 2**-23)),
        (f32(-1.0), "F32", f32(-(1.0 - 2**-24))),  # toward +infinity: magnitude shrinks
        (f32(-0.0), "F32", (1).to_bytes(4, "little")),  # the smallest positive subnormal
        (b"\x80\x3f", "BF16", b"\x81\x3f"),
        (b"\x00\x3c", "F16", b"\x01\x3c"),
        (b"\x7f", "I8", None),
        (b"\xff", "I8", b"\x00"),  # -1 + 1
        (b"\x05", "U8", b"\x06"),
        (f32(float("inf")), "F32", None),
        (b"\x00", "F8_E4M3", None),
    ],
)
def test_ulp_up(raw: bytes, dtype: str, want: bytes | None) -> None:
    if want is None:
        with pytest.raises(NotApplicable):
            ulp_up(raw, dtype)
    else:
        assert ulp_up(raw, dtype) == want


def test_largest_finite_is_not_applicable() -> None:
    with pytest.raises(NotApplicable, match="largest finite"):
        ulp_up(b"\xff\xff\x7f\x7f", "F32")


def test_no_qualifying_tensor(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/weights.bin").write_bytes(bytes(64))
    with pytest.raises(NotApplicable, match="1024 elements"):
        perturb_model(tmp_path / "src", tmp_path / "dst")
    assert not (tmp_path / "dst").exists()
