import ast
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.workloads import corpus_window_v1, write_prompt_set
from toy_tokenizer import RangeTokenizer, ToyTokenizer

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "harness/tests/fixtures/prompts"
GOLDEN = ROOT / "harness/tests/golden/corpus-window-v1-seed0-count3-L8.jsonl"
GOLDEN_DIGEST = "sha256:18a52238a4354a29e6334e6cb3b41559a043e1bbf16688e2b93baded0723eb58"
# Computed with random.Random(2**64 - 1).random() on CPython 3.12.16 and 3.15.2: identical.
OFFSETS_SEED_MAX = [21, 335, 210, 609]


def corpus() -> list[str]:
    return [(FIXTURES / f).read_text() for f in ("corpus-a.txt", "corpus-b.txt")]


def test_generator_golden(tmp_path: Path) -> None:
    prompts = corpus_window_v1(corpus(), ToyTokenizer(FIXTURES / "tokenizer.json"), 3, 8, 0)
    out = tmp_path / "prompts.jsonl"
    digest = write_prompt_set(out, prompts)
    assert out.read_bytes() == GOLDEN.read_bytes()
    assert digest == GOLDEN_DIGEST


def test_generator_stable_across_python() -> None:
    # CI runs this module on Python 3.12 and 3.13 against the same golden offsets.
    prompts = corpus_window_v1(["x" * 1000], RangeTokenizer(), 4, 10, 2**64 - 1)
    assert [p[0] for p in prompts] == OFFSETS_SEED_MAX


def test_generator_seed_sensitivity() -> None:
    a = corpus_window_v1(["x" * 10_000], RangeTokenizer(), 5, 16, 0)
    b = corpus_window_v1(["x" * 10_000], RangeTokenizer(), 5, 16, 1)
    assert a != b


def test_corpus_too_short() -> None:
    with pytest.raises(IProofsError) as e:
        corpus_window_v1(["abc"], RangeTokenizer(), 1, 4, 0)
    assert e.value.kind is ErrorKind.CONFIG
    assert "corpus shorter than prompt length: 3 tokens < 4" in e.value.message


def test_texts_joined_by_single_lf() -> None:
    seen: list[str] = []

    class Spy(RangeTokenizer):
        def encode(self, sequence: str, *, add_special_tokens: bool):  # type: ignore[no-untyped-def]
            seen.append(sequence)
            return super().encode(sequence, add_special_tokens=add_special_tokens)

    corpus_window_v1(["ab", "cd"], Spy(), 1, 2, 0)
    assert seen == ["ab\ncd"]


def test_generator_only_random_method() -> None:
    """RFC-0003 rule 1: only Random(seed).random() is called in the generator module."""
    tree = ast.parse((ROOT / "harness/src/iproofs/workloads.py").read_text())
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = {"randrange", "randint", "choice", "choices", "shuffle", "sample", "getrandbits",
                 "uniform", "randbytes"}  # fmt: skip
    assert not called & forbidden
    assert "random" in called
