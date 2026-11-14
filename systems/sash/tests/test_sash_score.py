"""RFC-0018 AD-7 `score` on CPU: the head pass over given ids, the rows read from the dumps and
the top-k lists against hand-computed values. Every upstream process is stub_upstream.py, whose
head dumps hold a vocabulary of 8."""

import json
import math
import re
import struct
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

SHAPE = {"prompt_tokens": 512, "output_tokens": 512, "batch_size": 1, "batches_per_session": 5,
         "context_window": 1024}  # fmt: skip
REPLY = [(3 * t + 1) % 8 for t in range(512)]
REQUESTS = [{"prompt": [i % 8] * 512, "reply": REPLY} for i in (1, 2, 3)]
# a stub row holds the logits 2 (the token it emits), 1 (one other token) and -1 (six tokens)
LSE = math.log(math.exp(2) + math.exp(1) + 6 * math.exp(-1))


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load(tmp_path, monkeypatch)
    module.host("/io/state/zk-out").mkdir(parents=True)
    module.host("/io/state/zk-out/attn_ranges.json").write_text("{}")
    lines = "".join(json.dumps(r) + "\n" for r in REQUESTS)
    module.host("/io/requests.jsonl").write_text(lines)
    return module


def score(adapter: ModuleType, **more: Any) -> dict[str, Any]:
    return run_step(adapter, "score", shape=SHAPE, model_dir="/models",
                    requests_file="/io/requests.jsonl", out_dir="/io/score", **more)  # fmt: skip


def test_info_lists_score(adapter: ModuleType) -> None:
    assert "score" in run_step(adapter, "info")["optional_subcommands"]


def test_top_tokens_follow_the_reply_except_where_the_model_differs(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reply position 0 is the last row of the prompt block's dump, positions 1 to 511 rows 0
    to 510 of the reply block's: a miss placed at 0, 1 and 511 lands exactly there."""
    monkeypatch.setenv("IPROOFS_SASH_STUB_MISS", "[0, 1, 511]")
    out = score(adapter, top_k=0)
    assert out["scores"] == {"dir": "/io/score", "requests": 3, "positions": 512, "top_k": 0,
                             "failed": []}  # fmt: skip
    top = json.loads(adapter.host("/io/score/0.json").read_text())["top"]
    differs = [t for t in range(512) if top[t] != REPLY[t]]
    assert differs == [0, 1, 511]
    assert top[0] == (REPLY[0] + 1) % 8
    assert not adapter.host("/io/score/0.topk").exists()
    argv = json.loads(adapter.host("/io/commands.jsonl").read_text().splitlines()[0])["argv"]
    # the head pass of prove's extraction, with the given ids and commit's calibration
    assert argv[argv.index("-m") + 1] == "harness.witness.extract"
    for flag, value in (("--tokens", "1024"), ("--chunk", "512"), ("--layer", "16"),
                        ("--spec", "y-delay-vw12"), ("--blocks", "0,1"),
                        ("--attn-ranges", "/io/state/zk-out/attn_ranges.json")):  # fmt: skip
        assert argv[argv.index(flag) + 1] == value
    assert {"--head", "--slim", "--diagonal-block"} <= set(argv)
    assert not any(a.startswith("--unsound") for a in argv)
    assert not adapter.host("/io/state/score-0").exists()  # the dumps are removed


def test_the_ids_file_is_the_prompt_then_the_reply(adapter: ModuleType, tmp_path: Path) -> None:
    adapter.write_npy(tmp_path / "ids.npy", [5, 6, 7])
    blob = (tmp_path / "ids.npy").read_bytes()
    assert blob[:8] == b"\x93NUMPY\x01\x00"
    (length,) = struct.unpack("<H", blob[8:10])
    assert (10 + length) % 64 == 0
    assert b"'descr': '<i8'" in blob[10 : 10 + length]
    assert b"'shape': (3,)" in blob[10 : 10 + length]
    assert struct.unpack("<3q", blob[10 + length :]) == (5, 6, 7)


def test_top_k_lists_are_the_log_softmax_of_the_bf16_logits(adapter: ModuleType) -> None:
    score(adapter, top_k=3)
    blob = adapter.host("/io/score/1.topk").read_bytes()
    assert blob[:4] == b"TFK1"
    assert struct.unpack("<II", blob[4:12]) == (512, 3)
    ids = struct.unpack("<1536i", blob[12 : 12 + 4 * 1536])
    lps = struct.unpack("<1536f", blob[12 + 4 * 1536 :])
    top = json.loads(adapter.host("/io/score/1.json").read_text())["top"]
    for t in (0, 1, 300, 511):
        row_ids, row_lps = ids[3 * t : 3 * t + 3], lps[3 * t : 3 * t + 3]
        # the emitted token (logit 2), the token after it (logit 1), then the lowest id of the
        # six tokens at -1
        rest = min(v for v in range(8) if v not in (REPLY[t], (REPLY[t] + 1) % 8))
        assert row_ids == (REPLY[t], (REPLY[t] + 1) % 8, rest)
        assert row_ids[0] == top[t]
        assert row_lps == pytest.approx((2 - LSE, 1 - LSE, -1 - LSE), abs=1e-6)


def test_order_keys_invert_to_bf16_values(adapter: ModuleType) -> None:
    value = adapter.bf16_of_key()
    assert (value[0x8000 + 0x4000], value[0x8000 + 0x3F80], value[0x7FFF - 0x3F80]) == (2, 1, -1)
    assert value[0x8000] == 0.0
    assert value[0x8000 + 0x3FC0] == 1.5  # bf16 0x3FC0
    assert all(value[k] < value[k + 1] for k in (0x1000, 0x7FFE, 0x8000, 0xC000))  # one order


def test_a_request_the_extractor_refuses_is_recorded_failed(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IPROOFS_SASH_STUB_REFUSE", "1")
    out = score(adapter, top_k=3)
    assert out["scores"]["failed"] == [1]
    failed = json.loads(adapter.host("/io/score/1.json").read_text())
    assert failed["failed"] == (
        "the extractor refused the ids: AssertionError: block 1 layer 16: the attention output "
        "leaves the no-wrap window (stub)"
    )
    assert not adapter.host("/io/score/1.topk").exists()
    assert "top" in json.loads(adapter.host("/io/score/2.json").read_text())


def test_another_failure_of_the_extraction_stops_the_call(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IPROOFS_SASH_STUB_REFUSE", "crash")
    with pytest.raises(SystemExit, match="CUDA out of memory"):
        score(adapter, top_k=0)


def test_score_needs_the_calibration_commit_kept(adapter: ModuleType) -> None:
    adapter.host("/io/state/zk-out/attn_ranges.json").unlink()
    with pytest.raises(SystemExit, match="calibration"):
        score(adapter, top_k=0)


def test_prover_files_from_the_harness_are_put_where_the_extractor_reads_them(
    adapter: ModuleType,
) -> None:
    adapter.host("/io/state/zk-out/attn_ranges.json").unlink()
    given = adapter.host("/io/state/prover-files")
    given.mkdir(parents=True)
    (given / "attn_ranges.json").write_text('{"L0.k": [1.0]}')
    (given / "tokens.npz").write_bytes(b"npz")
    score(adapter, top_k=0, prover_files=["/io/state/prover-files/attn_ranges.json",
                                           "/io/state/prover-files/tokens.npz"])  # fmt: skip
    assert adapter.host("/io/state/zk-out/attn_ranges.json").read_text() == '{"L0.k": [1.0]}'
    assert adapter.host("/io/state/zk-out/tokens.npz").read_bytes() == b"npz"


def test_the_scoring_image_is_the_pinned_image_plus_the_adapter() -> None:
    """RFC-0018 FI-14: Dockerfile.score starts from system.yaml's image, the one the counted
    sessions ran, and adds only files of this directory."""
    here = Path(__file__).resolve().parents[1]
    text = (here / "Dockerfile.score").read_text()
    pin = re.search(r'digest: "(sha256:[0-9a-f]{64})"', (here / "system.yaml").read_text())
    assert pin is not None
    froms = re.findall(r"^FROM (\S+)", text, re.M)
    assert froms == [f"ghcr.io/ai-verification-observatory/sash@{pin.group(1)}"]
    assert not re.search(r"^(RUN|ADD) ", text, re.M)
