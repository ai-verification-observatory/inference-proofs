"""RFC-0018 AD-7 `score` on CPU: the integer-model package's greedy choice at every position of
a given reply, the failed requests and the top-k lists, against the stand-in package's rule
(flashprove_stubs.FAKE_INTEGER_MODEL): its choice after token t at position n is
(7 t + n) mod 1000."""

import json
import math
import re
import struct
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from flashprove_stubs import adapter, commands, job, run  # noqa: F401 (adapter is a fixture)

PROMPT = [3, 5, 7, 11]
REPLY = [100, 200, 300, 400]
# the choices at the reply's positions: after the prompt's last token (position 4), then after
# each reply token but the last (positions 5, 6, 7)
TOP = [(7 * 11 + 4) % 1000, (7 * 100 + 5) % 1000, (7 * 200 + 6) % 1000, (7 * 300 + 7) % 1000]
# a stand-in row holds the logits 2 (the choice), 1 (the id after it) and -1 (998 tokens)
LSE = math.log(math.exp(2) + math.exp(1) + 998 * math.exp(-1))


def score(adapter: ModuleType, requests: list[dict[str, Any]], top_k: int) -> dict[str, Any]:  # noqa: F811
    adapter.host("/io/fit/config/policy.txt").write_text("lt 3\ns 15\nsh 8\nsT 4\n")
    lines = "".join(json.dumps(r) + "\n" for r in requests)
    adapter.host("/io/requests.jsonl").write_text(lines)
    doc = job("score", model_dir="/models", requests_file="/io/requests.jsonl",
              out_dir="/io/score", top_k=top_k)  # fmt: skip
    doc["shape"] = {"prompt_tokens": 4, "output_tokens": 4, "batch_size": 1,
                    "batches_per_session": 1, "context_window": 8}  # fmt: skip
    return run(adapter, "score", doc)


def test_the_choices_at_the_reply_positions(adapter: ModuleType) -> None:  # noqa: F811
    own = {"prompt": PROMPT, "reply": [*TOP[:1], 9, 9, 9]}  # its first token is the choice
    out = score(adapter, [{"prompt": PROMPT, "reply": REPLY}, own], top_k=0)
    assert out["scores"] == {"dir": "/io/score", "requests": 2, "positions": 4, "top_k": 0,
                             "failed": []}  # fmt: skip
    first = json.loads(adapter.host("/io/score/0.json").read_text())
    assert first["top"] == TOP == [81, 705, 406, 107]
    second = json.loads(adapter.host("/io/score/1.json").read_text())
    assert second["top"][0] == 81  # agrees with the reply at position 0
    assert not adapter.host("/io/score/0.topk").exists()
    ran = [c["argv"] for c in commands(adapter)]
    assert ran[0][2:4] == ["-m", "pytest"]  # the float64 check comes first, as for generate
    assert "gap_for=reply" in ran[1][3]
    assert [p["name"] for p in out["phases"]] == ["float64_check", "score"]


def test_top_k_lists_are_the_log_softmax_of_the_logits_over_two_to_the_s(
    adapter: ModuleType,  # noqa: F811
) -> None:
    score(adapter, [{"prompt": PROMPT, "reply": REPLY}], top_k=3)
    blob = adapter.host("/io/score/0.topk").read_bytes()
    assert blob[:4] == b"TFK1"
    assert struct.unpack("<II", blob[4:12]) == (4, 3)
    ids = struct.unpack("<12i", blob[12:60])
    lps = struct.unpack("<12f", blob[60:])
    for t, choice in enumerate(TOP):
        # the choice, the id after it, then one of the 998 tokens at -1: which of several equal
        # values takes the last place is the tensor library's choice
        assert ids[3 * t : 3 * t + 2] == (choice, (choice + 1) % 1000)
        assert ids[3 * t + 2] not in (choice, (choice + 1) % 1000)
        assert lps[3 * t : 3 * t + 3] == pytest.approx((2 - LSE, 1 - LSE, -1 - LSE), abs=1e-6)


def test_a_range_condition_failure_is_a_failed_request_not_a_dropped_one(
    adapter: ModuleType,  # noqa: F811
) -> None:
    requests = [{"prompt": PROMPT, "reply": [100, 999, 300, 400]},
                {"prompt": PROMPT, "reply": REPLY}]  # fmt: skip
    out = score(adapter, requests, top_k=3)
    assert out["scores"]["failed"] == [0]
    failed = json.loads(adapter.host("/io/score/0.json").read_text())
    assert failed["failed"] == ("RangeConditionFailed: position 5: condition (b) of the final "
                                "norm")  # fmt: skip
    assert "top" not in failed
    assert not adapter.host("/io/score/0.topk").exists()
    assert json.loads(adapter.host("/io/score/1.json").read_text())["top"] == TOP


def test_a_request_past_the_window_is_refused_before_the_model_loads(
    adapter: ModuleType,  # noqa: F811
) -> None:
    with pytest.raises(SystemExit, match="do not fit a window of 8"):
        score(adapter, [{"prompt": PROMPT, "reply": [*REPLY, 1]}], top_k=0)
    assert commands(adapter) == []


def test_generate_still_writes_the_models_own_reply(adapter: ModuleType) -> None:  # noqa: F811
    """`generate` and `score` share the model folder and the float64 check."""
    phases: list[dict[str, Any]] = []
    adapter.host("/io/fit/config/policy.txt").write_text("lt 3\n")
    work = adapter.workdir(adapter.host("/io/state/prove"))
    replies = adapter.generate({"control": False}, [PROMPT], 4, work, phases)
    assert replies[0][0] == 81
    assert [p["name"] for p in phases] == ["float64_check", "generate"]


def test_the_scoring_image_is_the_pinned_image_plus_the_adapter() -> None:
    """RFC-0018 FI-14: Dockerfile.score starts from system.yaml's image, the one the counted
    sessions ran, and adds only the entrypoint."""
    here = Path(__file__).resolve().parents[1]
    text = (here / "Dockerfile.score").read_text()
    pin = re.search(r'digest: "(sha256:[0-9a-f]{64})"', (here / "system.yaml").read_text())
    assert pin is not None
    froms = re.findall(r"^FROM (\S+)", text, re.M)
    assert froms == [f"ghcr.io/ai-verification-observatory/flashprove@{pin.group(1)}"]
    assert not re.search(r"^(RUN|ADD) ", text, re.M)
