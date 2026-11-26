# Fake system

`systems/fake` is a CPU-only toy prover and verifier that implements the `adapter/1` contract ([RFC-0005 §Reference implementations](../../rfcs/0005-adapter-contract.md#reference-implementations)). CI runs it end to end to exercise the entire pipeline, including negative controls, without needing a GPU. It does not prove anything about a real model; the underlying check is simply a keyed hash over toy data.

## Subcommands

| Subcommand | What the fake does |
|---|---|
| `info` | Reports system name `fake`, the upstream commit from `IPROOFS_FAKE_UPSTREAM` (set at image build time or by the harness), workload `fake-tiny-ci`, and profile `ci-cpu`. |
| `setup` | Does nothing and returns `ready: true`. |
| `commit` | Sets `commitment_id` to the SHA-256 of the RFC-0012 model digest string for `/models`, with no verifier or prover files. |
| `prove` | For each request, writes `body.bin = sha256(key, request)` and `tag.bin = HMAC-SHA256(key, request, claimed_output, body)`, releasing each proof via `/io/proofs/.tmp-<id>/` and an atomic rename, spaced `IPROOFS_FAKE_DELAY_S` apart (default 0.05 s). |
| `verify` | Recomputes the tag using the `commitment_id` supplied by the harness from its commit record, returning `accept` (exit 0), `reject` (exit 1 on tag mismatch), or `invalid_call` (exit 2 if a part is missing or shorter than 32 bytes). |
| `perturb` | Available only when `IPROOFS_FAKE_L1=1` (RFC-0018 AD-5): copies `/models` to the job's `out_dir`, increments byte 0 of `weights.bin` by 1, and returns a record of that change. |
| `mutate_reply` | Available only when `IPROOFS_FAKE_L1=1` (RFC-0018 AD-6): copies the proof to `out_dir` and flips one bit of `body.bin` at the reply position mod 32; does not decide any verdict. |

When `IPROOFS_FAKE_L1=1` is set, `info` advertises `perturb` and `mutate_reply` in `optional_subcommands`, and `prove` atomically renames `/io/marks/generation.start` and `generation.end` into place before releasing its first proof (AD-4). If a `setup`, `commit`, or `prove` job includes a `control` object (such as Level 1's C3 or P1), it logs a warning noting that it loaded W'.

The prover keys the HMAC using the commitment of the weights it actually loads rather than the `commitment_id` passed in the job file. As a result, proving with different weights than the committed ones (control P1) produces proofs that the verifier rejects.

`claimed_output` is a single token ID equal to the first byte of `sha256` of the request, making it a deterministic function of the input.

## Values under `proofs` in system.yaml

- `granularity: request`: produces one proof per request.
- `tokens_covered: window`: each proof covers the request's prompt tokens.
- `steady_boundary: first_proof`, `incremental_proofs: true`: proofs are released incrementally, one at a time, while proving runs.
- `deterministic_proofs: true`: identical weights and requests always produce identical proof parts.

## Forbidden flags

`--unsound-skip-` is listed as a forbidden flag. If a job passes it without `control: true`, the prover exits non-zero (RFC-0005 rule 4). In a control job, the flag is accepted and logged to `/io/commands.jsonl`, though the fake prover has no real binding edge for it to disable.

## Model

The `model/` directory contains 64 bytes of toy weights and a toy character vocabulary. These are test fixtures under this repository's code licence rather than real model weights (AGENTS.md rule 8). `workloads/fake-tiny-ci.yaml` pins them to the commit in this repository that introduced them.

## Running in process

Setting `IPROOFS_IO` and `IPROOFS_MODELS` maps `/io` and `/models` to host directories, letting the harness run the entrypoint directly without a container. The container image (`Dockerfile`) pins its base image by digest; build it using `systems/` as the Docker context and the commit pinned in `system.yaml`: `docker build --build-arg IPROOFS_FAKE_UPSTREAM=<commit> -f systems/fake/Dockerfile systems`. For integration tests in `harness/tests/integration/`, setting `IPROOFS_FAKE_FAULT` (`exit`, `sleep`, `escape`, or `network`, via environment variable or build arg) forces `prove` to misbehave, and `setup-id` makes a commit over a restored setup return another commitment than the setup's; measured runs never set it. A setup run's commit keeps the commitment in `/io/state/commitment.txt`; given `setup_state` (`iproofs run --setup`), commit checks that file against the setup's commitment and does not read the weights again. `IPROOFS_FAKE_KERNELS=1` makes `commit` and `prove` report a one-kernel store (`kernels`), with one reply that rebuilt it, for the tests of run.json `kernels`.
