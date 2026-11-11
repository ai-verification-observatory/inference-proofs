# Fake system

A CPU-only toy prover and verifier implementing the adapter contract `adapter/1` ([RFC-0005 §Reference implementations](../../rfcs/0005-adapter-contract.md#reference-implementations)). CI runs it end to end so the whole pipeline, including the negative controls, is tested without a GPU. It proves nothing about any model: the relation is a keyed hash over toy data.

## Subcommands

| Subcommand | What the fake does |
|---|---|
| `info` | reports `fake`, the upstream commit from `IPROOFS_FAKE_UPSTREAM` (set by the image build or the harness), workload `fake-tiny-ci`, profile `ci-cpu` |
| `setup` | nothing; `ready: true` |
| `commit` | `commitment_id = sha256` of the RFC-0012 model digest string of `/models`; no verifier or prover files |
| `prove` | per request: `body.bin = sha256(key, request)`, `tag.bin = HMAC-SHA256(key, request, claimed_output, body)`, released one by one through `/io/proofs/.tmp-<id>/` and an atomic rename, `IPROOFS_FAKE_DELAY_S` apart (default 0.05 s) |
| `verify` | recomputes the tag with the `commitment_id` the harness passes from its commit record; `accept` (exit 0), `reject` (exit 1, tag mismatch) or `invalid_call` (exit 2, a part missing or shorter than 32 bytes) |
| `perturb` | with `IPROOFS_FAKE_L1=1` only (RFC-0018 AD-5): copies `/models` to the job's `out_dir` with byte 0 of `weights.bin` raised by one, and returns that change |
| `mutate_reply` | with `IPROOFS_FAKE_L1=1` only (RFC-0018 AD-6): copies the proof to `out_dir` with one bit of `body.bin` flipped at the reply position mod 32; it decides nothing |

With `IPROOFS_FAKE_L1=1`, `info` lists `perturb` and `mutate_reply` in `optional_subcommands`, and `prove` renames `/io/marks/generation.start` and `generation.end` into place before its first proof (AD-4). A setup, commit or prove whose job names a `control` object (a level's C3 or P1) says in its warnings that it loaded W'.

The prover keys the HMAC with the commitment of the weights it actually loads, not with the `commitment_id` in its job file. Proving with weights other than the committed ones (control P1) therefore produces proofs the verifier rejects.

`claimed_output` is one token id: the first byte of `sha256` of the request, a deterministic function of the request.

## Values under `proofs` in system.yaml

- `granularity: request`: one proof per request.
- `tokens_covered: window`: one proof covers the request's prompt tokens.
- `steady_boundary: first_proof`, `incremental_proofs: true`: proofs are released one at a time during the call.
- `deterministic_proofs: true`: identical weights and requests give identical parts.

## Forbidden flags

`--unsound-skip-` is listed as forbidden. The prover exits non-zero if a job carries such a flag without `control: true` (RFC-0005 rule 4). In a control job the flag is accepted and logged to `/io/commands.jsonl`; the fake has no binding edge for it to remove.

## Model

`model/` holds 64 bytes of toy weights and a toy character vocabulary. They are test data under this repository's code licence, not model weights (AGENTS.md rule 8). `workloads/fake-tiny-ci.yaml` pins them by the commit of this repository that added them.

## Running in process

`IPROOFS_IO` and `IPROOFS_MODELS` map `/io` and `/models` to host directories, so the harness can run this file without a container. The image (`Dockerfile`) pins its base by digest. Build it with `systems/` as context and the commit `system.yaml` pins: `docker build --build-arg IPROOFS_FAKE_UPSTREAM=<commit> -f systems/fake/Dockerfile systems`. `IPROOFS_FAKE_FAULT` (`exit`, `sleep`, `escape`, `network`, as an environment variable or a build argument) makes `prove` misbehave for the integration tests in `harness/tests/integration/`; a measured run never sets it.
