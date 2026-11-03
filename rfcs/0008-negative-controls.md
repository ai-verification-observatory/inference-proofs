# RFC-0008: Negative controls

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0005

## Summary

A shared set of tampering tests that every system's verifier faces, plus each system's own. Each row reports which controls were rejected. Each control has an honest twin that must be accepted, so a broken control cannot pass for a strong verifier.

## Motivation

Speed is only half the result. A proof system is useful when its verifier rejects what it should. Both first systems ship their own rejection tests (FlashProve's `examples/rejected-proofs`; SASH's `--unsound-skip-*` switches, which unbind one edge each and are meant to show what each binding buys). A shared suite lets readers see the same attacks applied to every system.

## Specification

### Shared controls (verifier side, applied to an honest proof)

| ID | Control | Expected |
|---|---|---|
| C1 | change the claimed output token | reject |
| C2 | change one prompt token in the request | reject |
| C3 | verify against a different commitment of the same architecture | reject |
| C4 | replay a valid proof for a different request | reject |
| C5 | truncate the proof | reject or invalid_call |
| C6 | flip one byte at a seeded random offset in the proof (repeated with several seeds) | reject or invalid_call |
| C7 | swap two proofs within a batch | reject |
| C8 | drop one segment or sub-proof, where the proof has parts | reject |

### Shared controls (prover side)

| ID | Control | Expected |
|---|---|---|
| P1 | commit to weights W, prove with weights W' differing in one tensor | the honest prover fails or the verifier rejects |
| P2 | prove with a different precision or quantisation than committed | as P1 |

### System-specific controls

Each adapter MAY register controls from its upstream suite. SASH's unsound switches are registered with the expected verdict "accept", and the control passes only if the run's binding report marks the corresponding edge unbound: the point is to show the switch is honest, not that the verifier catches it.

### Honest twins

Each control job runs its honest twin first, on the same request. If the twin is not accepted, the control is void and is reported as void, not as a rejection.

### Reporting

Per row: controls run, rejected, accepted, `no_verdict`, `invalid_call`, void. An accepted control where rejection was expected is printed in the row in full and triggers a private report to the system maintainers before publication (each system's security policy is followed).

## Rationale and alternatives

Fuzzing the proof format was considered and kept to seeded byte flips for v0.1; a structured mutation suite needs each system's format specification and is a later RFC.

## Open questions

1. Controls that target the binding between proof and served traffic, once any system claims it.
2. An embargo period for an accepted control.
