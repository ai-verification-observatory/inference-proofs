"""GGUF header reader and the mean bits per active weight (RFC-0003 WB-5, `gguf-active-mean/1`).

Reads only a GGUF file's header (metadata and tensor infos), through a `ByteSource`: a local
file, or HTTP range requests on a pinned Hub revision. Nothing here reads tensor data.

Format and constants as llama.cpp defines them at `cd959bae99ff4bed22bef2604f45241c09bbb8c8`
(llama.cpp v0.9.0, the engine pin of RFC-0015 SRV-6): `ggml/include/gguf.h` and
`ggml/src/gguf.cpp` for the container, `ggml/include/ggml.h` L391 to L437 for the type ids,
`ggml/src/ggml.c` `type_traits` (L639 onward: `blck_size`, `type_size`) and the
`static_assert(sizeof(block_...))` lines of `ggml/src/ggml-common.h` for the block sizes. The
header checks follow `gguf_init_from_file_impl` in `ggml/src/gguf.cpp`: `general.alignment` a
UINT32 power of two (L622 to L636), each tensor's offset the sum of the padded sizes before it in
header order (L790 to L820).
"""

import re
import struct
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError

METHOD = "gguf-active-mean/1"
LLAMA_CPP_COMMIT = "cd959bae99ff4bed22bef2604f45241c09bbb8c8"
MAGIC = b"GGUF"
DEFAULT_ALIGNMENT = 32  # GGUF_DEFAULT_ALIGNMENT, gguf.h L46
CHUNK = 1 << 20

# ggml type id -> (name, elements per block, bytes per block). Bits per weight = bytes x 8 /
# elements, block scales included (Q4_K: 144 x 8 / 256 = 4.5). A type outside this table stops
# the method; a width is never guessed (RFC-0003 WB-3).
GGML_TYPES: dict[int, tuple[str, int, int]] = {
    0: ("F32", 1, 4),
    1: ("F16", 1, 2),
    2: ("Q4_0", 32, 18),  # half + QK4_0/2
    3: ("Q4_1", 32, 20),  # 2 half + QK4_1/2
    6: ("Q5_0", 32, 22),  # half + uint32 + QK5_0/2
    7: ("Q5_1", 32, 24),  # 2 half + uint32 + QK5_1/2
    8: ("Q8_0", 32, 34),  # half + QK8_0
    9: ("Q8_1", 32, 36),  # 2 half + QK8_1
    10: ("Q2_K", 256, 84),  # 2 half + QK_K/16 + QK_K/4
    11: ("Q3_K", 256, 110),  # half + QK_K/4 + QK_K/8 + 12
    12: ("Q4_K", 256, 144),  # 2 half + K_SCALE_SIZE (12) + QK_K/2
    13: ("Q5_K", 256, 176),  # 2 half + 12 + QK_K/2 + QK_K/8
    14: ("Q6_K", 256, 210),  # half + QK_K/16 + 3 QK_K/4
    15: ("Q8_K", 256, 292),  # float + QK_K + QK_K/16 int16
    16: ("IQ2_XXS", 256, 66),  # half + QK_K/8 uint16
    17: ("IQ2_XS", 256, 74),  # half + QK_K/8 uint16 + QK_K/32
    18: ("IQ3_XXS", 256, 98),  # half + 3 (QK_K/8)
    19: ("IQ1_S", 256, 50),  # half + QK_K/8 + QK_K/16
    20: ("IQ4_NL", 32, 18),  # half + QK4_NL/2
    21: ("IQ3_S", 256, 110),  # half + 13 (QK_K/32) + QK_K/64
    22: ("IQ2_S", 256, 82),  # half + QK_K/4 + QK_K/16
    23: ("IQ4_XS", 256, 136),  # half + uint16 + QK_K/64 + QK_K/2
    24: ("I8", 1, 1),
    25: ("I16", 1, 2),
    26: ("I32", 1, 4),
    27: ("I64", 1, 8),
    28: ("F64", 1, 8),
    29: ("IQ1_M", 256, 56),  # QK_K/8 + QK_K/16 + QK_K/32
    30: ("BF16", 1, 2),
    34: ("TQ1_0", 256, 54),  # half + QK_K/64 + (QK_K - 4 QK_K/64)/5
    35: ("TQ2_0", 256, 66),  # half + QK_K/4
    39: ("MXFP4", 32, 17),  # uint8 + QK_MXFP4/2
}

# GGUF metadata value types (gguf.h `enum gguf_type`): fixed sizes, then string 8, array 9.
_SCALARS: dict[int, str] = {
    0: "<B",
    1: "<b",
    2: "<H",
    3: "<h",
    4: "<I",
    5: "<i",
    6: "<f",
    7: "<?",
    10: "<Q",
    11: "<q",
    12: "<d",
}
_STRING, _ARRAY = 8, 9
_UINT32 = 4

# The routed experts' weight tensors, by llama.cpp's names (src/llama-arch.cpp L535 to L538,
# LLM_TENSOR_FFN_{GATE,GATE_UP,DOWN,UP}_EXPS). Any other tensor whose name holds "exps" is a
# layout the method does not define, so it stops rather than guess (shared experts are
# `_shexp`, used by every token, and count in full).
_ROUTED = re.compile(r"blk\.\d+\.ffn_(gate|up|down|gate_up)_exps\.weight")

ByteSource = Callable[[int, int], bytes]  # (offset, length) -> exactly `length` bytes


@dataclass(frozen=True, slots=True)
class Tensor:
    name: str
    dims: tuple[int, ...]  # ggml order: dims[0] is the innermost (contiguous) dimension
    ggml_type: int
    offset: int  # from the start of the data section

    @property
    def elements(self) -> int:
        n = 1
        for d in self.dims:
            n *= d
        return n

    def _block(self) -> tuple[str, int, int]:
        if self.ggml_type not in GGML_TYPES:
            raise IProofsError(
                ErrorKind.CONFIG,
                f"tensor {self.name}: ggml type {self.ggml_type} is not in the {METHOD} table",
            )
        name, block, size = GGML_TYPES[self.ggml_type]
        if not self.dims or self.dims[0] % block:
            raise IProofsError(
                ErrorKind.INTEGRITY,
                f"tensor {self.name}: first dimension {self.dims} is not a multiple of the"
                f" {name} block of {block}",
            )
        return name, block, size

    @property
    def type_name(self) -> str:
        return self._block()[0]

    @property
    def nbytes(self) -> int:
        _, block, size = self._block()
        return self.elements // block * size


@dataclass(frozen=True, slots=True)
class Header:
    version: int
    metadata: dict[str, object]  # scalars and strings; an array is stored as its length
    tensors: tuple[Tensor, ...]
    data_offset: int  # where tensor data starts in the file

    @property
    def alignment(self) -> int:
        """`general.alignment`, a power of two (gguf.cpp L632); read_header has checked that
        the file stores it as a UINT32 (L623)."""
        value = self.metadata.get("general.alignment", DEFAULT_ALIGNMENT)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            or value & (value - 1)
        ):
            raise IProofsError(
                ErrorKind.INTEGRITY, f"general.alignment {value!r} is not a power of two"
            )
        return value


class _Cursor:
    """Sequential reads over a ByteSource, fetched in chunks of `CHUNK` bytes."""

    def __init__(self, source: ByteSource, size: int) -> None:
        self.source, self.size = source, size
        self.pos, self.buf, self.buf_at = 0, b"", 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > self.size:
            raise IProofsError(ErrorKind.INTEGRITY, "GGUF header runs past the end of the file")
        end = self.pos + n
        if end > self.buf_at + len(self.buf):
            start = self.pos
            want = min(max(n, CHUNK), self.size - start)
            self.buf, self.buf_at = self.source(start, want), start
            if len(self.buf) != want:
                raise IProofsError(ErrorKind.FETCH, f"short read: {len(self.buf)} of {want} B")
        lo = self.pos - self.buf_at
        self.pos = end
        return self.buf[lo : lo + n]

    def unpack(self, fmt: str) -> object:
        value: object = struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]
        return value

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def u64(self) -> int:
        return int.from_bytes(self.take(8), "little")

    def string(self) -> str:
        n = self.u64()
        try:
            return self.take(n).decode("utf-8")
        except UnicodeDecodeError as e:
            raise IProofsError(ErrorKind.INTEGRITY, "GGUF string is not UTF-8") from e

    def value(self, kind: int) -> object:
        if kind in _SCALARS:
            return self.unpack(_SCALARS[kind])
        if kind == _STRING:
            return self.string()
        if kind == _ARRAY:
            item, count = self.u32(), self.u64()
            if item in _SCALARS:  # one read, not `count` reads
                self.take(struct.calcsize(_SCALARS[item]) * count)
            elif item == _STRING:
                for _ in range(count):
                    self.take(self.u64())
            else:  # nested arrays: no header field the method reads uses one
                raise IProofsError(ErrorKind.INTEGRITY, f"GGUF array of type {item}")
            return count
        raise IProofsError(ErrorKind.INTEGRITY, f"GGUF value type {kind} is unknown")


def read_header(source: ByteSource, size: int) -> Header:
    """Parse a little-endian GGUF version 2 or 3 header of a file of `size` bytes."""
    cur = _Cursor(source, size)
    if cur.take(4) != MAGIC:
        raise IProofsError(ErrorKind.INTEGRITY, "not a GGUF file (magic)")
    version = cur.u32()
    if version not in {2, 3}:
        raise IProofsError(ErrorKind.INTEGRITY, f"GGUF version {version} is not supported")
    n_tensors, n_kv = cur.u64(), cur.u64()
    metadata: dict[str, object] = {}
    for _ in range(n_kv):
        key, kind = cur.string(), cur.u32()
        if key == "general.alignment" and kind != _UINT32:
            raise IProofsError(
                ErrorKind.INTEGRITY, f"general.alignment is GGUF type {kind}, not UINT32 (4)"
            )
        metadata[key] = cur.value(kind)
    tensors = []
    for _ in range(n_tensors):
        name = cur.string()
        n_dims = cur.u32()
        if not 1 <= n_dims <= 4:  # GGML_MAX_DIMS
            raise IProofsError(ErrorKind.INTEGRITY, f"tensor {name}: {n_dims} dimensions")
        dims = tuple(cur.u64() for _ in range(n_dims))
        tensors.append(Tensor(name, dims, cur.u32(), cur.u64()))
    header = Header(version, metadata, tuple(tensors), 0)
    align = header.alignment
    data_offset = -(-cur.pos // align) * align
    header = Header(version, metadata, tuple(tensors), data_offset)
    check_layout(header, size)
    return header


def check_layout(header: Header, size: int) -> None:
    """The tensor data the header describes tiles the file: in header order, each tensor starts
    where the one before it ends, padded to the alignment (gguf.cpp L790 to L820), and takes
    exactly the bytes the type table gives; the last one ends at the end of the file, or at the
    end padded to the alignment, as llama.cpp's writer pads it (gguf.cpp L1609). Every
    tensor's size, the last one's included, is so checked against the file itself."""
    align = header.alignment
    expected = 0
    for t in header.tensors:
        if t.offset != expected:
            raise IProofsError(
                ErrorKind.INTEGRITY,
                f"tensor {t.name}: offset {t.offset}, expected {expected} from the type table",
            )
        expected = -(-(t.offset + t.nbytes) // align) * align
    if header.tensors:
        last = header.tensors[-1]
        end = header.data_offset + last.offset + last.nbytes
        padded = -(-end // align) * align
        if size not in {end, padded}:
            raise IProofsError(
                ErrorKind.INTEGRITY,
                f"tensor data ends at {end} B ({padded} B padded), the file is {size} B",
            )


def file_source(path: Path) -> ByteSource:
    def read(offset: int, length: int) -> bytes:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)

    return read


def hub_url(repo: str, revision: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/{revision}/{path}"


def http_source(url: str, size: int, *, timeout_s: float = 60.0) -> ByteSource:
    """Range requests on one URL; the server must answer 206 with the file's listed size."""

    def read(offset: int, length: int) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": "iproofs"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                total = str(response.headers.get("Content-Range", "")).rpartition("/")[2]
                if response.status != 206 or total != str(size):
                    raise IProofsError(
                        ErrorKind.INTEGRITY,
                        f"{url}: range read answered {response.status}, size {total!r},"
                        f" not 206 with the listed {size} B",
                    )
                data: bytes = response.read()
                return data
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise IProofsError(ErrorKind.FETCH, f"range read of {url} failed: {e}") from e

    return read


@dataclass(frozen=True, slots=True)
class ActiveWeights:
    """`gguf-active-mean/1` over the tensors of every file of one model."""

    bits: float  # mean storage bits per active weight, binary64 of the exact quotient
    active_weights: Fraction  # weights one token uses: routed experts scaled by used / count
    total_weights: int  # every element of every tensor
    expert_count: int | None
    expert_used_count: int | None


def _meta_int(meta: dict[str, object], key: str) -> int | None:
    value = meta.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise IProofsError(ErrorKind.INTEGRITY, f"GGUF key {key} is {value!r}, not a count")
    return value


def active_mean_bits(headers: Sequence[Header]) -> ActiveWeights:
    """The mean storage bits per active weight (RFC-0003 WB-5).

    Every tensor's bits are its elements x the bits per weight of its ggml type (block scales
    included). A token uses every tensor except the routed experts, of which it uses
    `<arch>.expert_used_count` of `<arch>.expert_count`, so a routed tensor counts with that
    weight; shared experts (`_shexp`) and the router count in full. The model's metadata is in
    the header that holds `general.architecture` (the first file of a split model)."""
    metas = [h.metadata for h in headers if "general.architecture" in h.metadata]
    if len(metas) != 1:
        raise IProofsError(
            ErrorKind.INTEGRITY, f"{len(metas)} headers name general.architecture, not 1"
        )
    meta = metas[0]
    arch = meta["general.architecture"]
    split = _meta_int(meta, "split.count")
    if split is not None and split != len(headers):
        raise IProofsError(ErrorKind.INTEGRITY, f"split.count {split} != {len(headers)} files")
    tensors = [t for h in headers for t in h.tensors]
    listed = _meta_int(meta, "split.tensors.count")
    if listed is not None and listed != len(tensors):
        raise IProofsError(
            ErrorKind.INTEGRITY, f"split.tensors.count {listed} != {len(tensors)} tensors"
        )
    if len({t.name for t in tensors}) != len(tensors):
        raise IProofsError(ErrorKind.INTEGRITY, "a tensor name appears twice")
    count = _meta_int(meta, f"{arch}.expert_count")
    used = _meta_int(meta, f"{arch}.expert_used_count")
    if (count is None) != (used is None) or (
        count is not None and used is not None and used > count
    ):
        raise IProofsError(ErrorKind.INTEGRITY, f"expert counts {used} of {count}")
    dense_elements = dense_bits = routed_elements = routed_bits = 0
    for t in tensors:
        bits = t.nbytes * 8
        if _ROUTED.fullmatch(t.name):
            if count is None or len(t.dims) != 3 or t.dims[2] != count:
                raise IProofsError(
                    ErrorKind.INTEGRITY,
                    f"routed tensor {t.name} {t.dims} does not hold expert_count {count} experts",
                )
            routed_elements += t.elements
            routed_bits += bits
        elif "exps" in t.name:
            raise IProofsError(
                ErrorKind.CONFIG, f"tensor {t.name}: an expert layout {METHOD} does not define"
            )
        else:
            dense_elements += t.elements
            dense_bits += bits
    share = Fraction(used, count) if count is not None and used is not None else Fraction(0)
    active = dense_elements + share * routed_elements
    if active == 0:
        raise IProofsError(ErrorKind.INTEGRITY, "no weights")
    return ActiveWeights(
        bits=float((dense_bits + share * routed_bits) / active),
        active_weights=active,
        total_weights=dense_elements + routed_elements,
        expert_count=count,
        expert_used_count=used,
    )
