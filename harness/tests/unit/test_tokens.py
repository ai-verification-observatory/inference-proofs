import pytest

from iproofs.derive import honest_verdict_failure, tokens_metrics, tokens_per_proof
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Shape

FP_B24 = Shape(prompt_tokens=1024, output_tokens=1, batch_size=24, batches_per_session=5,
               context_window=1024)  # fmt: skip
SASH = Shape(prompt_tokens=4096, output_tokens=512, batch_size=1, batches_per_session=1,
             context_window=4607)  # fmt: skip
RUN = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json"


def test_tokens_window() -> None:
    """fp-maverick-w1024-b24 fixture shape: 1,024 tokens per proof, output 0."""
    assert tokens_per_proof("window", FP_B24, None, "p0") == (1024, 0)
    metrics = tokens_metrics([(1024, 0)] * 120, RUN)
    assert metrics["tokens_covered_total"]["value"] == 122880
    assert metrics["tokens_covered_steady"]["value"] == 121856
    assert metrics["tokens_covered_output"]["value"] == 0


def test_tokens_prompt_plus_output() -> None:
    """sash-l31-8b-c4096 fixture shape: 4,096 + 512 positions per proof."""
    assert tokens_per_proof("prompt_plus_output", SASH, None, "seq0") == (4096, 512)
    metrics = tokens_metrics([(4096, 512)], RUN)
    assert metrics["tokens_covered_total"]["value"] == 4608
    assert metrics["tokens_covered_prompt"]["value"] == 4096
    assert metrics["tokens_covered_steady"]["value"] == 0  # proofs 2..k, k = 1
    assert metrics["tokens_covered_total"]["unit"] == "token"
    assert metrics["tokens_covered_total"]["source"] == {"kind": "harness", "ref": f"{RUN}#/proofs"}


def test_tokens_mismatch_is_adapter_error() -> None:
    with pytest.raises(IProofsError) as e:
        tokens_per_proof("window", FP_B24, 1025, "p3")
    assert e.value.kind is ErrorKind.ADAPTER
    assert e.value.step == "prove"
    assert "adapter tokens_covered 1025 != harness count 1024" in e.value.message


def test_matching_adapter_count_accepted() -> None:
    assert tokens_per_proof("prompt_plus_output", SASH, 4608, "s") == (4096, 512)


@pytest.mark.parametrize("declared", [None, 0, 4609])
def test_declared_per_proof_bounds(declared: int | None) -> None:
    with pytest.raises(IProofsError, match=r"outside 1\.\.4608"):
        tokens_per_proof("declared_per_proof", SASH, declared, "s")


def test_declared_per_proof_split() -> None:
    assert tokens_per_proof("declared_per_proof", SASH, 4100, "s") == (4096, 4)
    assert tokens_per_proof("declared_per_proof", SASH, 100, "s") == (100, 0)


def test_honest_reject() -> None:
    """TC-HONEST-REJECT: one honest proof rejected fails the repetition at verify."""
    assert honest_verdict_failure({"p0": "accept", "p1": "accept"}) is None
    err = honest_verdict_failure({"p0": "accept", "p1": "reject", "p2": "no_verdict"})
    assert err is not None
    assert err.step == "verify"
    assert "{'p1': 'reject', 'p2': 'no_verdict'}" in err.message
