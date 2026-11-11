"""weight_change.py against hand-computed cases (RFC-0018 CH-2). One output channel of BF16
weights: 2.0, 1.0, 0.25, -0.5 (patterns 0x4000, 0x3F80, 0x3E80, 0xBF00).

By hand: max |w| = 2.0, 2/127 = 0.015748..., the BF16 values around it are 129/8192 =
0.0157470703125 (below) and 130/8192 = 0.015869140625, so s = 0.015869140625.
- 1.0: 1/s = 63.015 -> 63. One step up, 1.0078125 (0x3F81), gives 63.508 -> 64: 1 step.
- 0.25: 15.754 -> 16. Steps below 0.25 are 2^-10: four give 0.24609375 -> 15.508 -> 16, five
  give 0.2451171875 (0x3E7B) -> 15.446 -> 15. Steps above are 2^-9: six give 0.26171875 ->
  16.492 -> 16, seven give 17. So 5 steps down.
- -0.5: -31.508 -> -32. One step toward zero, -0.498046875 (0xBEFF), gives -31.385 -> -31.
- 2.0 sets the scale and is never chosen."""

import importlib.machinery
import importlib.util
import json
import struct
from pathlib import Path
from types import ModuleType

import pytest

SYSTEM = Path(__file__).resolve().parents[1]
ROW = [0x4000, 0x3F80, 0x3E80, 0xBF00]


@pytest.fixture
def tool() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("weight_change", str(SYSTEM / "weight_change.py"))
    spec = importlib.util.spec_from_loader("weight_change", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_scale_and_codes(tool: ModuleType) -> None:
    s = tool.scale(ROW)
    assert s == 0.015869140625
    assert [tool.code(tool.bf16(b), s) for b in ROW] == [126, 63, 16, -32]


def test_one_step_up(tool: ModuleType) -> None:
    c = tool.smallest_change(ROW, 1)
    assert (c.after, c.steps, c.code_before, c.code_after) == (0x3F81, 1, 63, 64)


def test_five_steps_down(tool: ModuleType) -> None:
    c = tool.smallest_change(ROW, 2)
    assert (c.after, c.steps, c.code_before, c.code_after) == (0x3E7B, -5, 16, 15)


def test_negative_weight_toward_zero(tool: ModuleType) -> None:
    c = tool.smallest_change(ROW, 3)
    assert (c.after, c.steps, c.code_before, c.code_after) == (0xBEFF, 1, -32, -31)


def test_the_scale_weight_is_never_chosen(tool: ModuleType) -> None:
    assert tool.smallest_change(ROW, 0) is None
    best = tool.best_in_row(ROW)
    assert (best.col, best.steps) == (1, 1)  # columns 1 and 3 tie at one step; the lower wins


def test_from_a_safetensors_file(
    tool: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Row 1 of a [2, 4] BF16 tensor is ROW; the element's offset is in the file as a whole."""
    name = "model.layers.0.self_attn.o_proj.weight"
    header = json.dumps({name: {"dtype": "BF16", "shape": [2, 4], "data_offsets": [0, 16]}})
    data = struct.pack("<8H", 0x3F80, 0x3F80, 0x3F80, 0x3F80, *ROW)
    path = tmp_path / "model.safetensors"
    path.write_bytes(len(header).to_bytes(8, "little") + header.encode() + data)
    assert tool.main([str(path), name, "1"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["offset"] == 8 + len(header) + 8 + 2  # row 1 starts 8 bytes in; column 1
    assert (doc["before"], doc["after"], doc["steps"]) == ("803f", "813f", 1)
    assert path.read_bytes()[doc["offset"] : doc["offset"] + 2].hex() == doc["before"]
