"""RFC-0003 WB-5: the GGUF header reader and `gguf-active-mean/1`, on hand-made headers and on the
stored headers of the Maverick workloads' files (no network, no weights)."""

import dataclasses
import email.message
import json
import struct
import urllib.error
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from iproofs import cli, gguf, workloads
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import ModelFile, Workload
from iproofs.schema import SchemaRegistry
from iproofs.workloads import (
    check_computed_bits,
    computed_bits,
    ensure_model,
    load_workload,
    local_sources,
    stated_tolerance,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
MAVERICK = ROOT / "harness/tests/fixtures/gguf/fp-maverick-headers.json"
Q4_K, Q6_K, Q8_0, F32 = 12, 14, 8, 0

# ---------------------------------------------------------------- a hand-made GGUF writer


def _str(s: str) -> bytes:
    raw = s.encode()
    return struct.pack("<Q", len(raw)) + raw


def _kv(key: str, value: object) -> bytes:
    if isinstance(value, str):
        return _str(key) + struct.pack("<I", 8) + _str(value)
    if isinstance(value, list):  # an array of strings
        items = b"".join(_str(v) for v in value)
        return _str(key) + struct.pack("<IIQ", 9, 8, len(value)) + items
    if isinstance(value, tuple):  # an array of uint32
        return (
            _str(key)
            + struct.pack("<IIQ", 9, 4, len(value))
            + struct.pack(f"<{len(value)}I", *value)
        )
    if isinstance(value, float):
        return _str(key) + struct.pack("<If", 6, value)
    if isinstance(value, bool):
        return _str(key) + struct.pack("<I?", 7, value)
    assert isinstance(value, int)
    return _str(key) + struct.pack("<II", 4, value)


def write_gguf(
    meta: dict[str, object],
    tensors: list[tuple[str, tuple[int, ...], int]],
    *,
    align: int = 32,
    version: int = 3,
    offsets: list[int] | None = None,
    size_of: dict[int, tuple[int, int]] | None = None,
) -> bytes:
    """A GGUF file: header, padding, then zeroed tensor data laid out as ggml pads it.
    `size_of` maps a type to (weights, bytes) per block in place of the table's, to lay out
    data the table disagrees with or a type it does not hold."""
    infos, at, placed = b"", 0, []
    for _, dims, kind in tensors:
        block, size = (size_of or {}).get(kind) or gguf.GGML_TYPES[kind][1:]
        n = 1
        for d in dims:
            n *= d
        placed.append(at)
        at = -(-(at + n // block * size) // align) * align
    for i, (name, dims, kind) in enumerate(tensors):
        offset = offsets[i] if offsets else placed[i]
        infos += _str(name) + struct.pack(f"<I{len(dims)}QIQ", len(dims), *dims, kind, offset)
    head = b"GGUF" + struct.pack("<IQQ", version, len(tensors), len(meta))
    head += b"".join(_kv(k, v) for k, v in meta.items()) + infos
    head += b"\0" * (-len(head) % align)
    return head + b"\0" * at


TINY_META: dict[str, object] = {
    "general.architecture": "tiny",
    "general.name": "tiny-moe",
    "tiny.expert_count": 4,
    "tiny.expert_used_count": 1,
    "tiny.rope.freq_base": 10000.0,
    "tiny.use_parallel_residual": True,
    "tokenizer.ggml.tokens": ["a", "b", "c"],
    "tokenizer.ggml.token_type": (1, 1, 1),
}
TINY_TENSORS = [
    ("token_embd.weight", (256, 2), Q4_K),  # 512 weights, 2 blocks x 144 B = 2,304 bits
    ("blk.0.attn_q.weight", (32, 4), Q8_0),  # 128 weights, 4 blocks x 34 B = 1,088 bits
    ("blk.0.ffn_gate_exps.weight", (256, 1, 4), Q4_K),  # 4 experts: 1,024 weights, 4,608 bits
    ("blk.0.ffn_down_shexp.weight", (256, 1), Q6_K),  # shared: 256 weights, 210 B = 1,680 bits
    ("output_norm.weight", (32,), F32),  # 32 weights, 1,024 bits
]


def tiny(path: Path, **kwargs: Any) -> Path:
    path.write_bytes(write_gguf(TINY_META, TINY_TENSORS, **kwargs))
    return path


def header_of(data: bytes) -> gguf.Header:
    return gguf.read_header(lambda o, n: data[o : o + n], len(data))


# ---------------------------------------------------------------- the reader


def test_read_header(tmp_path: Path) -> None:
    path = tiny(tmp_path / "t.gguf")
    h = gguf.read_header(gguf.file_source(path), path.stat().st_size)
    assert h.version == 3
    assert h.metadata["general.name"] == "tiny-moe"
    assert h.metadata["tiny.expert_count"] == 4
    assert h.metadata["tiny.rope.freq_base"] == 10000.0
    assert h.metadata["tiny.use_parallel_residual"] is True
    assert h.metadata["tokenizer.ggml.tokens"] == 3  # an array is kept as its length
    assert h.metadata["tokenizer.ggml.token_type"] == 3
    assert [t.name for t in h.tensors] == [t[0] for t in TINY_TENSORS]
    assert [t.offset for t in h.tensors] == [0, 288, 448, 1024, 1248]  # 136 and 210 B padded
    assert [t.type_name for t in h.tensors] == ["Q4_K", "Q8_0", "Q4_K", "Q6_K", "F32"]
    assert h.data_offset % 32 == 0
    assert h.data_offset + 1248 + 128 == path.stat().st_size


def test_active_mean_bits_hand_computed() -> None:
    """Hand-computed: dense tensors 512 + 128 + 256 + 32 = 928 weights in 2,304 + 1,088 +
    1,680 + 1,024 = 6,096 bits; the routed tensor holds 4 experts of which a token uses 1, so
    1,024 / 4 = 256 weights in 4,608 / 4 = 1,152 bits. Mean = 7,248 / 1,184 = 453 / 74."""
    r = gguf.active_mean_bits([header_of(write_gguf(TINY_META, TINY_TENSORS))])
    assert r.active_weights == 1184
    assert r.total_weights == 1952
    assert r.bits == float(Fraction(453, 74))
    assert (r.expert_count, r.expert_used_count) == (4, 1)


def test_dense_model_counts_every_tensor() -> None:
    """No expert keys: every weight is active; (2,304 + 1,088) / (512 + 128) = 5.3."""
    meta: dict[str, object] = {"general.architecture": "dense"}
    r = gguf.active_mean_bits([header_of(write_gguf(meta, TINY_TENSORS[:2]))])
    assert r.active_weights == 640
    assert r.bits == 5.3
    assert r.expert_count is None


def test_split_model_across_files() -> None:
    """The model's metadata sits in the first file; tensors come from all of them."""
    first = {**TINY_META, "split.no": 0, "split.count": 2, "split.tensors.count": 5}
    a = header_of(write_gguf(first, TINY_TENSORS[:3]))
    b = header_of(write_gguf({"split.no": 1, "split.count": 2}, TINY_TENSORS[3:]))
    assert gguf.active_mean_bits([a, b]).bits == float(Fraction(453, 74))
    with pytest.raises(IProofsError, match=r"split\.count 2 != 1 files"):
        gguf.active_mean_bits([a])
    short = {**first, "split.count": 1}
    with pytest.raises(IProofsError, match=r"split\.tensors\.count 5 != 3"):
        gguf.active_mean_bits([header_of(write_gguf(short, TINY_TENSORS[:3]))])
    with pytest.raises(IProofsError, match=r"2 headers name general\.architecture"):
        gguf.active_mean_bits([a, header_of(write_gguf(TINY_META, TINY_TENSORS[3:]))])


def test_small_chunks_read_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    data = write_gguf(TINY_META, TINY_TENSORS)
    reads: list[int] = []

    def source(offset: int, n: int) -> bytes:
        reads.append(n)
        return data[offset : offset + n]

    monkeypatch.setattr(gguf, "CHUNK", 7)
    h = gguf.read_header(source, len(data))
    assert h == header_of(data)
    assert len(reads) > 10


def test_custom_alignment() -> None:
    meta = {**TINY_META, "general.alignment": 64}
    h = header_of(write_gguf(meta, TINY_TENSORS, align=64))
    assert h.alignment == 64
    assert h.data_offset % 64 == 0
    assert [t.offset for t in h.tensors] == [0, 320, 512, 1088, 1344]


def test_alignment_is_a_uint32_power_of_two() -> None:
    """As gguf.cpp L622 to L636: stored as UINT32, and a power of two."""
    bad = {**TINY_META, "general.alignment": "x"}
    with pytest.raises(IProofsError, match=r"general\.alignment is GGUF type 8, not UINT32") as e:
        header_of(write_gguf(bad, TINY_TENSORS))
    assert e.value.kind is ErrorKind.INTEGRITY
    as_u64 = _str("general.alignment") + struct.pack("<IQ", 10, 32)
    data = b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + as_u64
    with pytest.raises(IProofsError, match="GGUF type 10, not UINT32"):
        header_of(data + b"\0" * 64)
    with pytest.raises(IProofsError, match=r"general\.alignment 48 is not a power of two"):
        header_of(write_gguf({**TINY_META, "general.alignment": 48}, TINY_TENSORS, align=48))


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"GGML" + b"\0" * 20, "magic"),
        (b"GGUF" + struct.pack("<IQQ", 1, 0, 0), "version 1"),
        (b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + _str("k") + struct.pack("<I", 13), "type 13"),
        (
            b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + _str("k") + struct.pack("<IIQ", 9, 13, 1),
            "type 13",
        ),
        (b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<Q", 1) + b"\xff", "UTF-8"),
        (b"GGUF" + struct.pack("<IQQ", 3, 1, 0) + _str("t") + struct.pack("<I", 5), "5 dim"),
    ],
)
def test_malformed_header(data: bytes, match: str) -> None:
    with pytest.raises(IProofsError, match=match) as e:
        header_of(data + b"\0" * 64)
    assert e.value.kind is ErrorKind.INTEGRITY


def test_truncated_header() -> None:
    with pytest.raises(IProofsError, match="past the end"):
        header_of(b"GGUF" + struct.pack("<IQ", 3, 0))


def test_layout_checks_the_type_table() -> None:
    """Data laid out with another block size than the table's fails: the table is checked
    against the file itself."""
    with pytest.raises(IProofsError, match="offset 320, expected 288"):
        header_of(write_gguf(TINY_META, TINY_TENSORS, size_of={Q4_K: (256, 160)}))
    with pytest.raises(IProofsError, match=r"ends at 2080 B \(2080 B padded\), the file is 2079 B"):
        header_of(write_gguf(TINY_META, TINY_TENSORS)[:-1])


def test_layout_checks_the_last_tensor() -> None:
    """The last tensor must end at the end of the file (or there padded), so a table that
    gives it too few bytes fails too: here F32 laid out at 8 B per weight, 256 B, where the
    table gives 128 B. Trailing bytes past the padding fail the same way. (The header takes
    704 B, so the data the table gives ends at 704 + 1,248 + 128 = 2,080 B.)"""
    with pytest.raises(IProofsError, match=r"ends at 2080 B \(2080 B padded\), the file is 2208 B"):
        header_of(write_gguf(TINY_META, TINY_TENSORS, size_of={F32: (1, 8)}))
    with pytest.raises(IProofsError, match="the file is 2112 B"):
        header_of(write_gguf(TINY_META, TINY_TENSORS) + b"\0" * 32)
    # The writer pads the last tensor (Q8_0, 136 B) to 160 B: the padded end is the file end.
    data = write_gguf(TINY_META, TINY_TENSORS[:2])
    h = header_of(data)
    assert h.data_offset + h.tensors[-1].offset + h.tensors[-1].nbytes == len(data) - 24


def test_layout_follows_header_order() -> None:
    """gguf.cpp L790 to L820: offsets accumulate in header order. The first two tensors'
    data swapped (Q8_0 at 0, padded to 160 B; Q4_K at 160) tiles the data in offset order,
    but not in header order."""
    offsets = [160, 0, 448, 1024, 1248]
    with pytest.raises(IProofsError, match=r"token_embd\.weight: offset 160, expected 0"):
        header_of(write_gguf(TINY_META, TINY_TENSORS, offsets=offsets))


def test_unknown_type_and_block_multiple() -> None:
    with pytest.raises(IProofsError, match="ggml type 31 is not in") as e:
        header_of(write_gguf(TINY_META, [("x.weight", (32,), 31)], size_of={31: (1, 4)}))
    assert e.value.kind is ErrorKind.CONFIG
    odd = gguf.Tensor("x.weight", (100, 2), Q4_K, 0)
    with pytest.raises(IProofsError, match="not a multiple of the Q4_K block of 256"):
        _ = odd.nbytes


@pytest.mark.parametrize(
    ("meta", "tensors", "match"),
    [
        ({"general.architecture": "d"}, TINY_TENSORS, "does not hold expert_count None"),
        (TINY_META, [("blk.0.ffn_up_exps.weight", (256, 1, 3), Q4_K)], "expert_count 4"),
        (TINY_META, [("blk.0.ffn_norm_exps.weight", (256,), F32)], "an expert layout"),
        ({**TINY_META, "tiny.expert_used_count": 5}, TINY_TENSORS, "expert counts 5 of 4"),
        ({**TINY_META, "tiny.expert_count": 0}, TINY_TENSORS, "not a count"),
        ({"general.architecture": "d", "d.expert_count": 4}, TINY_TENSORS, "None of 4"),
        (TINY_META, [("a", (32,), F32), ("a", (32,), F32)], "appears twice"),
        (TINY_META, [], "no weights"),
    ],
)
def test_method_refuses_what_it_does_not_define(
    meta: dict[str, object], tensors: list[tuple[str, tuple[int, ...], int]], match: str
) -> None:
    with pytest.raises(IProofsError, match=match):
        gguf.active_mean_bits([header_of(write_gguf(meta, tensors))])


# ---------------------------------------------------------------- range reads


class _Response:
    def __init__(self, status: int, total: str, body: bytes) -> None:
        self.status, self.body = status, body
        self.headers = email.message.Message()
        self.headers["Content-Range"] = f"bytes 0-{len(body) - 1}/{total}"

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_http_source(monkeypatch: pytest.MonkeyPatch) -> None:
    data = write_gguf(TINY_META, TINY_TENSORS)
    seen: list[str] = []

    def urlopen(request: Any, timeout: float) -> _Response:
        seen.append(request.get_header("Range"))
        lo, hi = map(int, request.get_header("Range").removeprefix("bytes=").split("-"))
        return _Response(206, str(len(data)), data[lo : hi + 1])

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    url = gguf.hub_url("org/m", "a" * 40, "x/m.gguf")
    assert url == f"https://huggingface.co/org/m/resolve/{'a' * 40}/x/m.gguf"
    assert gguf.read_header(gguf.http_source(url, len(data)), len(data)) == header_of(data)
    assert seen[0] == f"bytes=0-{len(data) - 1}"

    monkeypatch.setattr("urllib.request.urlopen", lambda r, timeout: _Response(200, "9", b"x"))
    with pytest.raises(IProofsError, match="not 206 with the listed") as e:
        gguf.http_source(url, len(data))(0, 1)
    assert e.value.kind is ErrorKind.INTEGRITY

    def down(request: Any, timeout: float) -> _Response:
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr("urllib.request.urlopen", down)
    with pytest.raises(IProofsError, match="range read") as e:
        gguf.http_source(url, len(data))(0, 1)
    assert e.value.kind is ErrorKind.FETCH

    monkeypatch.setattr("urllib.request.urlopen", lambda r, timeout: _Response(206, "9", b"x"))
    with pytest.raises(IProofsError, match="short read") as e:
        gguf.read_header(gguf.http_source(url, 9), 9)
    assert e.value.kind is ErrorKind.FETCH


# ---------------------------------------------------------------- the workload records


def maverick_headers() -> list[gguf.Header]:
    doc = json.loads(MAVERICK.read_text())
    out = []
    for f in doc["files"]:
        tensors = tuple(gguf.Tensor(n, tuple(d), k, o) for n, d, k, o in f["tensors"])
        h = gguf.Header(f["version"], f["metadata"], tensors, f["data_offset"])
        gguf.check_layout(h, f["bytes"])
        out.append(h)
    return out


@pytest.mark.parametrize("wid", ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"])
def test_maverick_record_recomputes_from_stored_headers(wid: str) -> None:
    """AGENTS.md rule 3: CI recomputes the recorded width from the stored headers of the pinned
    files, and the method's active count reproduces the model card's "17B" within its stated
    precision (half a billion), which checks the method."""
    wl = load_workload(wid, root=ROOT, registry=REGISTRY)
    wb = wl.precision.weight_bits
    assert wb is not None
    assert (wb.basis, wb.covers, wb.method) == ("computed", "all", "gguf-active-mean/1")
    doc = json.loads(MAVERICK.read_text())
    listed = {f.path: f.bytes for f in wl.model.files}
    assert [(f["path"], f["bytes"]) for f in doc["files"]] == [
        (p, listed[p]) for p in wb.files or ()
    ]
    assert doc["revision"] == wl.model.revision
    result = gguf.active_mean_bits(maverick_headers())
    assert check_computed_bits(wl, result) == []
    assert (result.expert_count, result.expert_used_count) == (128, 1)
    assert abs(result.active_weights - 17_000_000_000) <= 500_000_000
    # The total, 400,711,848,960, is within the card's "400B" stated to one digit: +/- 5e10.
    assert result.total_weights == 400_711_848_960
    assert wl.model.parameters.total == 400_000_000_000


def test_stated_tolerance() -> None:
    assert stated_tolerance(17_000_000_000) == 500_000_000
    assert stated_tolerance(8_030_261_248) == Fraction(1, 2)
    assert stated_tolerance(400) == 50
    assert stated_tolerance(400_000_000_000) == 50_000_000_000
    assert stated_tolerance(0) == Fraction(1, 2)


def with_bits(wl: Workload, **changes: Any) -> Workload:
    wb = wl.precision.weight_bits
    assert wb is not None
    precision = dataclasses.replace(wl.precision, weight_bits=dataclasses.replace(wb, **changes))
    return dataclasses.replace(wl, precision=precision)


def tiny_workload(tmp_path: Path, bits: float, active: int = 1184, total: int = 1952) -> Workload:
    """fake-tiny-ci with one GGUF weight file and a computed width."""
    data = (tiny(tmp_path / "tiny.gguf")).read_bytes()
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    files = (ModelFile(path="tiny.gguf", sha256="0" * 64, bytes=len(data)),)
    params = dataclasses.replace(wl.model.parameters, active_per_token=active, total=total)
    wl = dataclasses.replace(
        wl, model=dataclasses.replace(wl.model, files=files, parameters=params)
    )
    return with_bits(wl, basis="computed", bits=bits, files=("tiny.gguf",), method=gguf.METHOD)


def test_computed_bits_from_local_files(tmp_path: Path) -> None:
    wl = tiny_workload(tmp_path, float(Fraction(453, 74)))
    assert computed_bits(wl, local_sources(tmp_path)).active_weights == 1184


def test_computed_bits_mismatch_is_config(tmp_path: Path) -> None:
    wl = tiny_workload(tmp_path, 6.12, active=1100, total=3000)
    with pytest.raises(IProofsError) as e:
        computed_bits(wl, local_sources(tmp_path))
    assert e.value.kind is ErrorKind.CONFIG
    assert "bits 6.12 != 6.121621621621622 computed by gguf-active-mean/1" in str(e.value)
    assert "counts 1184 active weights, outside 1100 +/- 50" in str(e.value)
    assert "counts 1952 total weights, outside 3000 +/- 500 (model.parameters.total)" in str(
        e.value
    )


def test_computed_bits_checks_the_total(tmp_path: Path) -> None:
    """A reader that drops or double-counts a whole tensor moves the total: 1,952 counted
    against a stated 1,900 (+/- 50) fails, though the active count and the bits agree."""
    wl = tiny_workload(tmp_path, float(Fraction(453, 74)), total=1900)
    with pytest.raises(IProofsError, match=r"counts 1952 total weights, outside 1900 \+/- 50"):
        computed_bits(wl, local_sources(tmp_path))


def test_computed_bits_needs_a_computed_record(tmp_path: Path) -> None:
    wl = tiny_workload(tmp_path, 1.0)
    plain = with_bits(wl, basis="stated")
    with pytest.raises(IProofsError, match="is not computed"):
        computed_bits(plain, local_sources(tmp_path))
    assert check_computed_bits(plain, None) == [  # type: ignore[arg-type]
        "fake-tiny-ci: precision.weight_bits has no computed basis"
    ]
    with pytest.raises(IProofsError, match="unknown weight-bits method x/1"):
        computed_bits(with_bits(wl, method="x/1"), local_sources(tmp_path))


def test_fetch_model_rechecks_a_computed_width(tmp_path: Path) -> None:
    """RFC-0003 WB-5: fetch-model recomputes the width from the verified files, on a fresh
    fetch and on a cached copy; a record that disagrees is a `config` error."""
    src = tmp_path / "src"
    src.mkdir()
    good = tiny_workload(src, float(Fraction(453, 74)))
    data = (src / "tiny.gguf").read_bytes()
    from iproofs.provenance import file_digest, model_digest  # noqa: PLC0415

    files = (ModelFile(path="tiny.gguf", sha256=file_digest(src / "tiny.gguf"), bytes=len(data)),)
    model = dataclasses.replace(
        good.model,
        files=files,
        digest=model_digest(src),
        source=dataclasses.replace(good.model.source, hub="huggingface", path=None, repo="o/t"),
    )
    good = dataclasses.replace(good, model=model)

    def hub(repo: str, revision: str, names: list[str], into: Path, token: str | None) -> None:
        (into / "tiny.gguf").write_bytes(data)

    cache = tmp_path / "cache"
    path = ensure_model(good, cache, download=hub)
    assert ensure_model(good, cache, download=hub) == path  # the cached copy, rechecked
    with pytest.raises(IProofsError, match=r"bits 4\.5 != ") as e:
        ensure_model(with_bits(good, bits=4.5), cache, download=hub)
    assert e.value.kind is ErrorKind.CONFIG
    assert path.is_dir()  # the files are fine: nothing is quarantined


def test_hub_sources_reads_the_pinned_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    wl = load_workload("fp-maverick-w1024-b1", root=ROOT, registry=REGISTRY)
    urls: list[tuple[str, int]] = []
    monkeypatch.setattr(gguf, "http_source", lambda url, size: urls.append((url, size)))
    workloads.hub_sources(wl)(wl.model.files[0])
    assert urls == [
        (
            "https://huggingface.co/unsloth/Llama-4-Maverick-17B-128E-Instruct-GGUF/resolve/"
            f"{wl.model.revision}/{wl.model.files[0].path}",
            wl.model.files[0].bytes,
        )
    ]


def test_cli_headers_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`iproofs fetch-model WORKLOAD --headers-only` prints the recheck as JSON, from range
    reads (here: the stored headers) and without fetching any weights."""
    headers = {
        f["path"]: h
        for f, h in zip(json.loads(MAVERICK.read_text())["files"], maverick_headers(), strict=True)
    }
    monkeypatch.setattr(gguf, "read_header", lambda source, size: source)
    monkeypatch.setattr(workloads, "hub_sources", lambda wl: lambda f: headers[f.path])
    monkeypatch.setattr(workloads, "ensure_model", lambda *a, **k: pytest.fail("fetched"))
    monkeypatch.chdir(ROOT)
    assert cli.main(["--quiet", "fetch-model", "fp-maverick-w1024-b24", "--headers-only"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workload"] == "fp-maverick-w1024-b24"
    assert out["bits"] == out["recorded_bits"]
    assert out["active_weights"] == 17_184_691_200
    assert (out["active_per_token"], out["expert_count"], out["expert_used_count"]) == (
        17_000_000_000,
        128,
        1,
    )


def test_cli_headers_only_needs_a_computed_width(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["--quiet", "fetch-model", "sash-l31-8b-c1024", "--headers-only"]) == 2
