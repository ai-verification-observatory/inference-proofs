import dataclasses
import datetime as dt
import hashlib
import json
import math
import random
from pathlib import Path

import pytest

from iproofs.cli import main
from iproofs.errors import ErrorKind, IProofsError
from iproofs.level import (
    CHAINS,
    Kl,
    beacon_seed,
    beacon_window_v1,
    check_level,
    fetch_beacon,
    first_round_after,
    kl_texts,
    load_level,
    rung_prompts,
    rung_stream,
    slot_prompts,
)
from iproofs.schema import SchemaRegistry, load_document
from iproofs.workloads import corpus_window_v1, generator_seed, load_workload
from toy_tokenizer import RangeTokenizer, ToyTokenizer

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "harness/tests/fixtures/prompts"
QUICKNET = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
# drand quicknet round 1000, as api.drand.sh and drand.cloudflare.com served it on 2026-11-10.
SIGNATURE = (
    "b44679b9a59af2ec876b1a6b1ad52ea9b1615fc3982b19576350f93447cb1125"
    "e342b73a8dd2bacbe47e4b6b63ed5e39"
)
RANDOMNESS = "fe290beca10872ef2fb164d2aa4442de4566183ec51c56ff3cd603d930e54fdd"
RELAYS = ("https://api.drand.sh", "https://drand.cloudflare.com")


def corpus() -> list[str]:
    return [(FIXTURES / f).read_text() for f in ("corpus-a.txt", "corpus-b.txt")]


def test_l1_file_validates_and_checks() -> None:
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    assert load_document(ROOT / "levels/L1.yaml", registry)[0] == "level/1"
    level = load_level(ROOT)
    assert [r.id for r in level.rungs] == ["llama-4-maverick", "llama-3.1-8b"]
    assert level.rung("llama-3.1-8b").workloads == {"sash": "l1-l31-8b-p512-o512"}
    assert check_level(ROOT, level) == []


def test_check_frozen_refuses_a_draft() -> None:
    """A draft (frozen null, a control's revision null) fails the frozen check; the committed
    Level 1, frozen with every value pinned, passes it."""
    level = load_level(ROOT)
    assert check_level(ROOT, level, frozen=True) == []
    rung = level.rungs[1]
    source = rung.controls[-1].source
    assert source is not None
    control = dataclasses.replace(
        rung.controls[-1], source=dataclasses.replace(source, revision=None)
    )
    draft = dataclasses.replace(
        level,
        frozen=None,
        rungs=(level.rungs[0], dataclasses.replace(rung, controls=(*rung.controls[:-1], control))),
    )
    problems = check_level(ROOT, draft, frozen=True)
    assert "frozen is null: the level is a draft" in problems
    assert sum("smaller-model revision is null" in p for p in problems) == 1


def test_cli_check_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    assert main(["level", "check"]) == 0
    assert main(["level", "check", "--frozen"]) == 0


def test_first_round_after_a_time() -> None:
    """PR-2: quicknet round r is produced at genesis + (r - 1) * 3 s; the round after a time
    strictly follows it."""
    genesis, period = CHAINS[QUICKNET]
    at_round_10 = dt.datetime.fromtimestamp(genesis + 9 * period, tz=dt.UTC)
    assert first_round_after(QUICKNET, at_round_10) == 11
    assert first_round_after(QUICKNET, at_round_10 + dt.timedelta(seconds=1)) == 11
    assert first_round_after("00" * 32, at_round_10) is None


def test_beacon_seed_is_first_8_bytes_big_endian() -> None:
    assert beacon_seed(RANDOMNESS) == 0xFE290BECA10872EF
    with pytest.raises(IProofsError):
        beacon_seed("fe29")


def test_beacon_window_is_corpus_window_with_the_beacon_seed() -> None:
    tokenizer = ToyTokenizer(FIXTURES / "tokenizer.json")
    got = beacon_window_v1(corpus(), tokenizer, 5, 8, RANDOMNESS)
    assert got == corpus_window_v1(corpus(), tokenizer, 5, 8, 0xFE290BECA10872EF)


def test_rung_stream_prompts_then_kl_windows() -> None:
    level = load_level(ROOT)
    small = dataclasses.replace(
        level,
        request=dataclasses.replace(level.request, prompt_tokens=8),
        kl=Kl(texts=2, tokens=12),
    )
    rung = small.rung("llama-3.1-8b")  # 5 requests a session, 3 slots: 15 prompts
    texts = ["x" * 1000]
    stream = rung_stream(texts, RangeTokenizer(), small, rung, RANDOMNESS)
    prompts = rung_prompts(stream, small, rung)
    assert prompts == beacon_window_v1(texts, RangeTokenizer(), 15, 8, RANDOMNESS)
    kl = kl_texts(stream, small, rung)
    assert [len(w) for w in kl] == [12, 12]
    # one generator: the KL windows take draws 16 and 17 (RangeTokenizer: first id = offset)
    rng = random.Random(0xFE290BECA10872EF)
    draws = [rng.random() for _ in range(17)]
    assert [w[0] for w in kl] == [math.floor(r * (1000 - 12 + 1)) for r in draws[15:]]


def test_slot_prompts() -> None:
    prompts = [[i] for i in range(6)]
    assert slot_prompts(prompts, 1, 2) == [[0], [1]]
    assert slot_prompts(prompts, 3, 2) == [[4], [5]]
    with pytest.raises(IProofsError):
        slot_prompts(prompts, 4, 2)
    with pytest.raises(IProofsError):
        slot_prompts(prompts, 0, 2)


def test_beacon_workload_takes_the_record() -> None:
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    wl = load_workload("l1-l31-8b-p512-o512", root=ROOT, registry=registry)
    assert generator_seed(wl, {"randomness": RANDOMNESS}) == 0xFE290BECA10872EF
    with pytest.raises(IProofsError) as e:
        generator_seed(wl, 7)
    assert e.value.kind is ErrorKind.CONFIG


def relay_answers(answers: dict[str, dict[str, object]]):  # type: ignore[no-untyped-def]
    def get(url: str) -> bytes:
        relay = next(r for r in answers if url.startswith(r))
        assert url == f"{relay}/{QUICKNET}/public/1000"
        return json.dumps(answers[relay]).encode()

    return get


ROUND = {"round": 1000, "randomness": RANDOMNESS, "signature": SIGNATURE}


def test_fetch_beacon_agreeing_relays() -> None:
    import datetime as dt  # noqa: PLC0415

    get = relay_answers({r: ROUND for r in RELAYS})
    record = fetch_beacon(1000, RELAYS, get, chain_hash=QUICKNET, fetched=dt.date(2026, 11, 10))
    stored = json.loads(
        (ROOT / "schema/beacon/examples/valid/quicknet-round-1000.json").read_text()
    )
    assert record == stored


def test_fetch_beacon_disagreeing_relays() -> None:
    other_sig = "ab" * 48
    other = {
        "round": 1000,
        "signature": other_sig,
        "randomness": hashlib.sha256(bytes.fromhex(other_sig)).hexdigest(),
    }
    get = relay_answers({RELAYS[0]: ROUND, RELAYS[1]: other})
    with pytest.raises(IProofsError) as e:
        fetch_beacon(1000, RELAYS, get, chain_hash=QUICKNET)
    assert e.value.kind is ErrorKind.INTEGRITY
    assert "relays disagree" in e.value.message


def test_fetch_beacon_bad_sha256() -> None:
    bad = dict(ROUND, randomness="00" * 32)
    get = relay_answers({r: bad for r in RELAYS})
    with pytest.raises(IProofsError) as e:
        fetch_beacon(1000, RELAYS, get, chain_hash=QUICKNET)
    assert e.value.kind is ErrorKind.INTEGRITY
    assert "is not sha256(signature)" in e.value.message


def test_fetch_beacon_wrong_round_or_one_relay() -> None:
    get = relay_answers({r: dict(ROUND, round=999) for r in RELAYS})
    with pytest.raises(IProofsError):
        fetch_beacon(1000, RELAYS, get, chain_hash=QUICKNET)
    with pytest.raises(IProofsError):
        fetch_beacon(1000, RELAYS[:1], relay_answers({RELAYS[0]: ROUND}), chain_hash=QUICKNET)
