# RFC-0014: Provenance, pinning and artifact integrity

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0003, RFC-0005, RFC-0006, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every row the benchmark publishes must be rerunnable by a stranger and must be checkable against the exact inputs that produced it. This RFC fixes how inputs are pinned (commits, images, models, prompt corpora, toolchains), how adapter images are built, how weights are fetched and verified before any container sees them, what `manifest.json` records, how the harness keeps the commitment that the verifier checks against (AGENTS.md rule 6), how proofs are digested, and which supply-chain threats the design answers. Signed result files are left as an open question with a default of unsigned for v0.1.

## Motivation

[RFC-0007 §Motivation](0007-evidence-tiers-and-reproduction.md#motivation) records why provenance matters for the first two systems: FlashProve's performance page states that its measuring scripts are not in the repository and that a reader cannot check the figures against the run records; SASH publishes run manifests, but its headline manifest records that the producing prover tree was dirty. A benchmark has to do better than both, for its own runs.

The draft specification said "pin everything" and "the commitment the verifier checks against comes from the harness's own record". Neither said how. Concrete cases this RFC must handle:

- An adapter Dockerfile clones `main` of an upstream repository; a rebuild a month later measures different code under the same row label.
- A weight file on the model host is replaced under the same revision name; a run silently proves a different model.
- A prover writes a commitment file next to its proof, and a buggy adapter passes that file to the verifier; a forged proof with a matching forged commitment is accepted.
- A stranger cannot rerun a row because the image digest it names was never pushed.

## Goals

- Every input to a measured job is identified by an immutable reference: a 40-hex commit hash, an OCI digest, or a SHA-256 file or tree digest (RFC-0012 §Digests).
- No container sees weights, prompts or verifier keys whose digests have not been checked by the harness first.
- `manifest.json` alone, plus public sources, is enough to rerun the job.
- The commitment the verifier checks against is the one the harness recorded at the `commit` step, never one read from prover output.
- A stranger can obtain every image a release names.

## Non-Goals

- Bit-reproducible image builds. A rerun uses the same image digest, not a rebuild. Rebuild reproducibility is desirable and is recorded when it holds, but not required in v0.1.
- Cryptographic attestation of the runner's host (TEE or measured boot). Open question Q1.
- Auditing upstream code for backdoors. The benchmark pins and records; it does not certify (PRD §5).
- Hosting weights. Weights are never redistributed (AGENTS.md rule 8).

## Proposed Design

### Pin rules

| Input | Pin form | Where recorded | Checked by |
|---|---|---|---|
| Upstream source | full 40-hex commit hash | `system.yaml` `upstream.commit`, Dockerfile `ARG UPSTREAM_COMMIT`, `claim.yaml` | G7 `PIN-1` |
| Upstream source archive | `sha256:` of the source tarball the build fetched | `info` output `image_inputs`, manifest | harness at `info` |
| Base images | `<repo>@sha256:<digest>` | Dockerfile `FROM` | G7 `PIN-2` |
| Adapter image | `<registry>/<repo>@sha256:<manifest digest>` | `system.yaml` `image`, manifest | harness before every job |
| Toolchains | exact versions | Dockerfile, adapter README | G7 `PIN-5` |
| Language dependencies | lockfile with hashes (Cargo.lock with `--locked`, pip `--require-hashes`, uv.lock) | inside the image, digest in `image_inputs` | build fails on mismatch |
| Model | source, 40-hex revision, per-file digests, model digest | `workloads/<id>.yaml` | harness at resolve, G7 `PIN-3` |
| Tokenizer | part of the model file set | as above | as above |
| Prompt corpus | per-file digest and corpus digest | `workloads/prompts/corpus.yaml` | harness at resolve |
| Prompt set | prompt seed and prompt set digest | manifest | harness after materialising |
| Harness | version, git commit, dirty flag, `uv.lock` digest | manifest | harness at start |
| Host software | driver, CUDA runtime, container runtime, NVIDIA Container Toolkit versions | machine record (RFC-0006), reference file | harness against `reference/<release>.yaml` |
| CI actions | full commit hash | workflow files | G7 |

Abbreviated hashes, branch names, tags without digests and version ranges are rejected wherever a pin is required. Tags MAY appear next to a digest as information.

### Adapter image build

Each `systems/<name>/Dockerfile` follows these rules (RFC-0005 owns the adapter layout; this RFC owns the build rules):

1. **B1 Base by digest.** Every `FROM` names a digest.
2. **B2 Fetch stage.** One stage named `fetch` downloads every external input: the upstream source at the pinned commit (`ADD https://github.com/<org>/<repo>.git#<commit>` or a tarball with `ADD --checksum=sha256:<hex>`), and dependency sources through lockfiles that carry hashes. Every download is verified against a digest written in the repository (`systems/<name>/inputs.lock`, one line per input: `<name>\t<url>\tsha256:<hex>`).
3. **B3 Offline after fetch.** Every `RUN` in later stages uses `RUN --network=none`. A build step that needs network outside the fetch stage is a defect in the adapter.
4. **B4 No source changes.** The build applies no patch and runs no `sed` or equivalent over upstream source (AGENTS.md rule 1). Build flags are those the upstream documentation names.
5. **B5 Inputs record.** The final image contains `/opt/iproofs/inputs.json`, written by the build, listing every input `{name, url, digest}` and the toolchain versions. The `info` subcommand returns it as `image_inputs`.
6. **B6 Clean tree.** The build context is a clean checkout of this repository at a commit; `info` reports `adapter_commit` (this repository's commit) baked in at build time through a build argument. A build from a dirty tree sets `adapter_dirty: true`, and such an image is not eligible for a release (see §Eligibility).
7. **B7 Publication.** Images that a hosted provider pulls are pushed to the project's container registry, `ghcr.io/ai-verification-observatory/` (Q2), and referenced by manifest digest.

Local images that are not pushed (the fake systems in CI, adapter development) are referenced by their image ID and recorded with `image.digest_kind: "config"`; pushed images record `image.digest_kind: "manifest"`. Both kinds may enter a release during the research phase.

Development install, generic form (amendment of 2026-11-09; first written for the unmerged `ref-serve-gguf` branch, commit `d842275`). When an adapter's own image is not yet pullable by a hosted provider, a development run may start from the public engine image its Dockerfile is built `FROM`, and install the adapter into that container from the checkout the job runs: the files the Dockerfile copies, at its paths, and the inputs of its `inputs.lock`, each checked by its digest (`systems/<name>/dev_install.py`, on the shared `systems/_dev/install.py`; `ref-serve` is the first user, docs/runbooks/hf-jobs.md). Such a run records `image.ref` as `local/<the engine image's pull reference>`, with that reference's registry digest, and `image.digest_kind: "config"`. Here the digest names the engine image, not the image ID of a local build. It is the reference the job command names, which the container cannot read back; the install checks what it can: the image's own `FROM`, the engine's version, the bound GPUs, and the engine environment against the image's `ENV`. The adapter is identified by `system.adapter_commit` (the checkout's commit) and by the `image_inputs` entries of the install: the engine image by digest, and the adapter files at that commit with their sha256. A development install is never eligible for a release (`digest_kind` is `config`), and it never claims a digest of the adapter's image. RFC-0006 §Hosted execution admits it beside a local build named with `--image`.

### Model fetch and verification

`iproofs fetch-model WORKLOAD` and the `resolved` state of every job (RFC-0010) run the same procedure:

```python
def ensure_model(workload: Workload, cache: Path) -> VerifiedModel:
    """Return a read-only directory whose file set and digests equal workload.model.
    Raises IProofsError(kind=integrity) on any mismatch, kind=fetch after 3 failed attempts."""
```

1. Target directory: `$IPROOFS_CACHE/models/<model digest hex>/`. `IPROOFS_CACHE` defaults to `~/.cache/iproofs`.
2. If absent, download with `huggingface_hub.snapshot_download(repo_id=source, revision=<40-hex>, allow_patterns=<exact file list>)` into a temporary sibling directory. Fetch errors retry per RFC-0010 (3 attempts, backoff 2 s, 8 s, 32 s).
3. Hash every file. The file set MUST equal the workload's list exactly: a missing file, an extra file or a digest mismatch is `ErrorKind.integrity`, and the temporary directory is deleted.
4. Compute the model digest (RFC-0012) and compare with `workload.model.digest`.
5. Rename into place, then remove write permission from every file and directory.
6. At the start of every job, rehash every file in the cache directory and recompare. This costs time outside every timed scope; the duration is logged as the diagnostic event `integrity.model_rehash` in `logs/harness.jsonl` and is not a published number. A cache entry that fails the rehash is moved to `$IPROOFS_CACHE/quarantine/` and the job fails with `ErrorKind.integrity`; it does not silently refetch, because a changed file on a runner's disk is an event the runner must see.

Gated models: the runner accepts the model licence with their own account. The token is read only from the environment variable `HF_TOKEN`, passed to the fetch call, never written to any file, log or record, and never passed into an adapter container (docs/spec/06-security.md).

The model directory is mounted read-only at `/models` in `commit` and `prove` containers and never in `verify` containers. The reference systems ([RFC-0015](0015-reference-rows.md)) skip `commit` and `verify`; `ref-recompute` reads the weights in its `prove` step, which is where its recompute work is timed.

Production-serving weights (amendment of 2026-11-09, RFC-0015 SRV-6). A serving record `workloads/serving/<id>.yaml` (`serving-model/1`) pins an ungated copy of the publisher's release: source repository and revision, and per file the path, sha256, bytes, storage (`git` or `lfs`) and the publisher's git blob id at its pinned revision. Two files with equal git blob ids are equal byte for byte: for a small file the blob id hashes the bytes, and for an LFS file it hashes the pointer, which holds the sha256 and the size. The model digest is that of RFC-0012 over the pinned files.
- SM-1 (offline, CI, CPU): for every `storage: lfs` file, the git blob id of the pointer built from `sha256` and `bytes` equals `publisher_blob`. A file whose recomputed id differs fails G1.
- SM-2 (`iproofs fetch-model --serving RECORD`): the procedure above over the record's files, into `$IPROOFS_CACHE/models/<model digest hex>/`. Every downloaded file's sha256 and size equal the record; every `storage: git` file's git blob id (`sha1("blob <n>\0" + bytes)`) equals `publisher_blob`; the model digest is recomputed. Any mismatch is `config`, and no job runs. A file with `source: publisher` is fetched from the publisher's repository with the runner's token (`HF_TOKEN` in that one command's environment). `--no-weights DIR` fetches every file but the `.safetensors` weights into DIR, each checked the same way, so the engine's tokenizer load can be tried before the weights are fetched (RFC-0015 Q7).
- SM-3 (`iproofs serving check-mirror RECORD`, network, when a record lands and before each campaign): it reads both tree listings at the pinned revisions and requires the mirror's blob id, the publisher's blob id and `publisher_blob` to be equal for every pinned file, and prints the result for the campaign log. `iproofs serving pin RECORD` writes the file list from the same two listings and refuses any file whose blob ids differ.

The serving model is mounted read-only at `/models` in the `prove` container of a `reference_role: serve` job, in place of the workload's files.

### Corpus fetch

`workloads/prompts/corpus.yaml` lists each corpus file with `id`, `source_url`, `licence` and `sha256` (RFC-0003). The harness downloads each file into `$IPROOFS_CACHE/corpus/<digest hex>`, checks the digest, and computes the corpus digest. Any mismatch is `ErrorKind.integrity`. Prompt materialisation (RFC-0003) reads only verified corpus files.

### The commitment record

AGENTS.md rule 6: the commitment the verifier checks comes from the harness record, never from files sent with a proof.

1. After `commit` exits 0, the harness validates `out.json` and copies each file in `verifier_files[]` and `prover_files[]` from the commit container's `/io` into a harness-owned store `<job tmp>/commitment/`, which no later container mounts read-write.
2. It records in `manifest.json` under `commitment`: `commitment_id` (string, as returned), and for each verifier and prover file `{name, digest, bytes}`.
3. For `prove`, the harness mounts `commitment/prover/` read-only and passes `commitment_id` and the prover file names in `job.json`.
4. For every `verify` call, the harness creates a fresh `/io` containing only: `job.json`, a read-only copy of `commitment/verifier/` whose file digests it rechecks against the manifest immediately before the call, the request, the claimed output, and the proof's part files. `commitment_id` in `job.json` is copied from the manifest, not from `prove` output.
5. If `prove`'s `out.json` contains any key named `commitment_id` or any file whose digest equals a recorded verifier file, the harness records a `policy` warning in the run log and in `run.json` `warnings[]`; it does not fail the run, because some systems may legitimately echo the identifier, but the verify call still uses only the recorded commitment.
6. Control C3 (RFC-0008) supplies a different recorded commitment through the same path, which is the only way a commitment other than the job's own reaches a verifier.

### manifest.json

`schema/manifest/1.schema.json`. Everything needed to rerun, and nothing that identifies the host beyond RFC-0006's machine record.

```json
{
  "schema": "manifest/1",
  "run_id": "2026-12-02-sash-sash-l31-8b-c4096-prover-h100-1",
  "release": "v0.1",
  "control": false,
  "harness": {"version": "0.1.0", "git_commit": "<40 hex>", "git_dirty": false, "lock_digest": "sha256:...", "nonconforming": false},
  "runner": {"handle": "<declared handle>", "organisation": "<organisation>", "affiliated_systems": []},
  "claim": {"system": "sash", "configuration": "default", "card_version": 1},
  "provider": "<declared provider name>",
  "system": {
    "name": "sash",
    "system_manifest_digest": "sha256:...", "claim_digest": "sha256:...",
    "upstream": {"repo": "sg-ai-safety-hub/zk-inference-prover", "commit": "eb95bfa887299d1637550228d42086c27cbb2b3b"},
    "adapter_commit": "<40 hex>", "adapter_dirty": false,
    "image": {"ref": "<registry>/<repo>@sha256:...", "digest_kind": "manifest"},
    "image_inputs": [{"name": "upstream-source", "url": "...", "digest": "sha256:..."}]
  },
  "workload": {
    "id": "sash-l31-8b-c4096", "version": 1, "file_digest": "sha256:...",
    "model": {"source": "...", "revision": "<40 hex>", "digest": "sha256:..."},
    "corpus_digest": "sha256:...", "prompt_seed": "0x1f2e3d4c5b6a7988", "prompt_set_digest": "sha256:..."
  },
  "profile": {"prover": "prover-h100", "verifier": "verifier-cpu", "verifier_host": "same_as_prover",
              "reference_file": "reference/v0.1.yaml", "reference_digest": "sha256:..."},
  "machine": {"...": "RFC-0006 machine record"},
  "self_test": {"passed": true, "checks": [{"name": "ST-SAMPLER", "passed": true}, {"name": "ST-CGROUP", "passed": true}, {"name": "ST-WATCH", "passed": true}, {"name": "ST-NVML", "passed": true}]},
  "commands": [
    {"step": "commit", "argv": ["docker", "run", "..."], "cpuset": "0-23", "mems": "0", "gpus": "device=0",
     "network": "none", "started_at": "2026-12-02T09:14:03Z", "exit_code": 0}
  ],
  "commitment": {"commitment_id": "...", "verifier_files": [{"name": "...", "digest": "sha256:...", "bytes": 0}],
                 "prover_files": [{"name": "...", "digest": "sha256:...", "bytes": 0}]},
  "proofs": [{"proof_id": "...", "digest": "sha256:...", "parts": [{"name": "...", "digest": "sha256:...", "bytes": 0}],
              "archive": null}],
  "warnings": []
}
```

`runner.affiliated_systems` lists every system whose authors the runner is affiliated with, as the runner declares it. `self_test` is the result of the machine self-test, which runs on the host before its first run of a release and before each run campaign (RFC-0011), not before every job: `iproofs machine-record --selftest` keeps the host's latest result in `results/.selftest.json`, and the runner copies it into every manifest when the same harness version took it (otherwise `self_test` is `{passed: false, checks: []}` and the run is ineligible). Check names are the RFC-0011 ids (`ST-CLOCK` to `ST-OOM`). A failed self-test or profile check is recorded (`harness.nonconforming: true`) and refuses nothing; `--allow-nonconforming` is accepted and changes nothing. A run with a failed self-test is ineligible for a release. `claim` names the claim card in force by `card_version`. For reference systems `commitment` is `null` and `proofs` lists their outputs as recorded by RFC-0015. `bytes` values are structural integers; the sizes as metrics are quantities in `run.json`. `prompt_seed` is a 64-bit value written as `0x` plus 16 lowercase hex digits, a string, so JSON readers without 64-bit integers cannot corrupt it. `argv` is recorded after redaction (environment values are never in argv; the harness passes secrets only through the fetch call, which runs in the harness process).

### Proof digests

- Every proof directory gets a proof digest (RFC-0012) as soon as the harness sees its rename. The digest goes into `manifest.proofs[]` and `digests.txt` (`<proof_id>\t<digest>` per line, sorted by proof id bytes).
- The harness rechecks the proof digest immediately before each `verify` call and each control mutation, so a proof changed on disk between prove and verify is detected (`ErrorKind.integrity`).
- No proof bytes are committed to git (RFC-0009 §Storage). Proofs are kept by digest and MAY be deleted from the runner's disk after controls complete. The optional `manifest.proofs[].archive` field (`{uri, digest, bytes}` or `null`) stays in `manifest/1`; no archive is required during the research phase.

### Eligibility

A run is eligible for a release (RFC-0009 freeze) only if it belongs to that release, every pin in the manifest is in full form (the manifest is valid `manifest/1`), `self_test.passed` is true, the claim card named in `claim` is the one the release lists (prover runs), `harness.git_dirty` is false and `system.adapter_dirty` is false. Reason codes: `other_release`, `manifest_invalid`, `self_test_failed`, `claim_card_not_listed`, `harness_dirty`, `adapter_dirty`. A run that fails eligibility stays in `results/` (append-only) and is shown, if at all, as ineligible with the reason. Upstream results with a dirty or unknown tree enter only as `external` quantities.

### Supply-chain threats and responses

| Threat | Response |
|---|---|
| Upstream force-push or deletion makes the pinned commit unavailable | The upstream source archive digest is recorded at build |
| Base image tag moved | `FROM` by digest (B1) |
| Dependency registry serves different bytes | Lockfiles with hashes; build fails |
| Harness dependency compromised | `uv.lock` with hashes, `uv sync --frozen`; dependency updates are their own pull requests with the lock diff reviewed |
| Malicious or careless adapter change | Review; container hardening (docs/spec/06-security.md); controls catch a verifier that accepts everything (RFC-0008) |
| Model host replaces a file under the same revision | Per-file digests checked on fetch and before every job |
| CI action compromised | Actions pinned by commit; `contents: read` permissions (RFC-0013) |
| Image registry loses an image | Manifests list digests; images are not garbage collected (registry retention set to keep tagged release images) |
| Commitment substituted through prover output | §The commitment record |

### Failure modes

| Failure | Response |
|---|---|
| Pinned upstream commit not fetchable at build | Build fails in `fetch` stage; adapter issue opened; no row |
| Model digest mismatch | `integrity`, job stops before any container runs; cache entry quarantined |
| Verifier file digest changed before verify | `integrity`, that verify call is not made; the job's verify step fails and is recorded |
| Image digest not pullable | `fetch` after retries; job fails at `image_ready` |
| `info` `upstream_commit` differs from `system.yaml` | `integrity`, job stops at `info` |
| Dirty harness tree | job runs and is recorded with `git_dirty: true`; ineligible for a release |

## Alternatives Considered

**Rebuild images for a rerun instead of reusing digests.** Considered because it tests the build as well as the run. Rejected as the requirement because GPU toolchain builds are rarely bit-reproducible (timestamps, compiler nondeterminism), so a rebuild mismatch would block reruns for reasons unrelated to the numbers.

**Trust the model cache after the first check.** Considered because rehashing about 200 GB of weights per job costs minutes. Rejected because the cost is outside timed scopes and small next to proving times, and a silent on-disk change would invalidate every subsequent row.

**Let the adapter read the commitment from its own commit output.** Considered because it is simpler for adapters. Rejected: it makes rule 6 depend on every adapter being correct; the harness-owned store makes it structural.

**Signed result files from the start.** Considered because signatures make results cheaper to trust (PRD open question 4). Deferred: a signature proves who wrote a file, not that the numbers are right, and key management for volunteer runners needs its own design. Q1.

## Drawbacks

- Image publication requires a registry the project controls and pays for, before the permanent home is settled.
- Rehashing weights adds minutes of wall time per job on the runner.
- The fetch-stage discipline (B2, B3) makes adapter Dockerfiles longer and slower to write than a plain `git clone && make`.
- Unsigned results mean a fabricating runner is not caught (docs/spec/06-security.md residual risks).

## Conflicts of Interest

None declared.

## Migration / Rollout

No adapters or results exist yet. Order: manifest schema and the commitment store with the fake systems (v0.1-alpha, since G10 exercises them), then model fetch and verification, build rules B1 to B7 in the SASH and FlashProve adapters, registry publication (v0.1-beta). The eligibility rule takes effect at the first freeze (v0.1).

Amendment of 2026-11-09 (owner decision, RFC-0015 SRV-6 production serving): §Model fetch gains SM-1 to SM-3 and the serving mount; the development-install paragraph is added in generic form. `harness/tests/unit/test_serving.py` covers SM-1 and SM-2 on fixtures.

## Testing Strategy

- `harness/tests/unit/test_fetch.py::test_extra_file_rejected`, `::test_missing_file_rejected`, `::test_digest_mismatch_quarantines`, `::test_cache_rehash_detects_change` (flip a byte in a cached fixture model, expect `integrity` and the quarantine move), `::test_token_never_logged` (set `HF_TOKEN`, run a fetch against a local fake hub, grep every written file for the token).
- `test_commitment.py::test_verify_io_contains_only_recorded_commitment` (fake adapter whose prove writes a forged `commitment_id` and a forged key file; assert the verify job's `/io` has the recorded ones and a warning is logged), `::test_verifier_file_changed_before_verify_fails`.
- `test_manifest.py::test_manifest_round_trip_valid` against the schema, `::test_failed_self_test_ineligible`, `::test_reference_run_has_null_commitment`, `::test_prompt_seed_is_hex_string`, `::test_dirty_harness_marks_ineligible`.
- `test_proof_digest.py::test_changed_part_detected_before_control`.
- Adapter build checks (per system, CPU only, in `systems/<name>/tests/`): `test_dockerfile_rules.py` parses the Dockerfile and asserts B1, B3 (every `RUN` outside `fetch` has `--network=none`) and that `inputs.lock` covers every `ADD` in the fetch stage.
- G10 end-to-end run asserts the manifest of each fake run validates and that `commitment` digests match the files used at verify.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31, or a later RFC): whether runners sign `run.json` and `manifest.json` (for example with a key bound to an attested runner), and with which scheme. Default for v0.1: unsigned.
- Resolved Q2: the default holds. Release images live in `ghcr.io/ai-verification-observatory/`, the container registry of the organisation that hosts the source. They are kept indefinitely: a digest that a release references is never deleted or overwritten, and lookups never go by tag. The engine image a reference adapter builds on (RFC-0015) is a base image pinned by digest at its publisher's registry (B1), like any `FROM`, and is not pushed again.

## References

- AGENTS.md rules 1, 6, 7 and 8, and working practice "Pin everything".
- [RFC-0003](0003-workloads.md), [RFC-0005](0005-adapter-contract.md), [RFC-0006](0006-reference-hardware-and-cost.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0009](0009-results-and-publication.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md).
- OCI Image Specification, image manifest and digests.
- Docker BuildKit `ADD --checksum` and `RUN --network`.
- SLSA build provenance levels, as background for the inputs record.
