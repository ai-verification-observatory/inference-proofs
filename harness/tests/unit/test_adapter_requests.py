"""RFC-0017 INV-REQ-2: the proofs of one request claim exactly the workload's output tokens."""

import dataclasses
from typing import Any

import pytest

from iproofs.adapter import check_requests
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import AdapterOut, ProofEntry


def out(*claims: tuple[int, int]) -> AdapterOut:
    """A `prove` out.json holding one proof per (request index, claimed tokens)."""
    proofs = tuple(
        ProofEntry(proof_id=f"p{i}", request_index=request, parts=(), claimed_output=(7,) * n)
        for i, (request, n) in enumerate(claims)
    )
    blank: dict[str, Any] = {f.name: None for f in dataclasses.fields(AdapterOut)}
    return AdapterOut(**(blank | {"proofs": proofs}))


def test_claimed_tokens_per_request_must_match_the_shape() -> None:
    check_requests(out((0, 64)), 64)  # one proof a request (both v0.1 systems)
    check_requests(out((0, 1), (1, 1)), 1)
    check_requests(out((0, 40), (0, 24)), 64)  # two proofs of one request
    with pytest.raises(IProofsError) as e:
        check_requests(out((0, 64), (1, 63)), 64)
    assert (e.value.kind, e.value.step) == (ErrorKind.ADAPTER, "prove")
    assert "{1: 63}" in e.value.message
