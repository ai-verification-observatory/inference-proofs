# Changelog

All notable changes to the harness, the schemas and the methodology. Format: [Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/), plus a `Methodology` section for changes that need an RFC, each naming its RFC ([docs/spec/09-release-and-versioning.md §CHANGELOG discipline](docs/spec/09-release-and-versioning.md#changelog-discipline)).

Every pull request that changes the public API, a schema or the methodology adds an entry under `Unreleased`. Entries are plain statements of what changed. Any number in an entry carries its labels (AGENTS.md rule 2). CI does not check this file in v0.1; reviewers do.

## [Unreleased]

### Methodology

- RFC-0011: the calibration self-test of a hosted host (`machine-record --selftest --hosted`): the probe runs as a process, ST-CGROUP reads the container's own anon rise and CPU time, ST-OOM is not run (no memory limit can be set). Without it no hosted run could be eligible for a release (RFC-0014).
- RFC-0006 §Hosted execution: a prover profile may name a hosted runtime, a container the provider starts from the adapter image with the harness inside it; `iproofs run --hosted --gpu N` runs each step as a process of the image's ENTRYPOINT under the bound CPUs' affinity, as the adapter uid with no capabilities. The network, memory binding and limits are not isolated and are recorded so (`commands[].network: "provider"`). New profile `prover-h100-hosted` in `reference/v0.1.yaml` (driver 610.57.04); new checks PC-CPU-QUOTA and the hosted forms of PC-CGROUP, PC-RUNTIME and PC-MEM.
- RFC-0003: a workload may pin its tokenizer file from a second repository (`model.tokenizer_source`, with its own revision and sha256) when the weights' repository has none; `model.digest` still covers the weights only. `fetch-model` and the prompt builder fetch and check it alone.
- RFC-0015: vLLM v0.32.0 pinned for the reference rows (Q1) and teacher-forced argmax through `prompt_logprobs` (Q3); a reference loads only the workload's pinned files (PM-0) and may use the same bit widths in another number format (PM-4), so the SASH reference rows run FP8 W8A8 as a declared substitution (from #257).
- RFC-0009 Q1: archived proofs are stored in a public dataset repository on the Hugging Face Hub, at URIs pinned to the dataset commit.
- RFC-0006 Q1: the v0.1 price per GPU-hour is the median of Lambda, RunPod and CoreWeave on-demand H100 SXM list prices read on 2026-11-04, archived in `reference/v0.1.yaml`.
- RFC-0014 Q2: release images live in `ghcr.io/ai-verification-observatory/`, kept indefinitely.
- RFC-0001 to RFC-0015 added as Draft: governance, claim card, workloads, metrics and grades, adapter contract, reference hardware and cost, evidence tiers, negative controls, publication, runner, measurement, schemas, validation and CI, provenance, reference rows.

### Added

- `systems/flashprove/README.md` §Upstream's rejected proofs: FlashProve's `examples/rejected-proofs` at `9e2bdd8` listed row by row, and why none is registered as a system control (#70): upstream stores no altered proof (a script makes them from the synthetic `accepted-proof` examples), each set is checked against the example's own commitment ID, which the harness cannot regenerate (INV-CTRL-6, RFC-0008 Q4 default), and the examples' requests (r = 60, e = 64; r = 15, e = 47) and the clipped-gap `-policy` are not what the adapter's `verify` writes. No `controls.yaml` is added.
- GPU fixtures for `sash` and `flashprove` (`tests/fixtures/gpu/`): one commit, prove and verify of each on an H100, both verdicts `accept`; the two INV-ADAPTER-9 fixture tests run on them.
- `systems/flashprove/system.yaml`, pinning the FlashProve image built from `main` at `4f1a295`; no system maintainer is named (RFC-0001 §System inclusion: not reached, no consent recorded). The Maverick workloads list `flashprove`.
- `systems/sash/claim.yaml`: the SASH claim card (configuration `sound-defaults`, card_version 1), every field copied from upstream at `eb95bfa` with a source link or written as not stated; `reviewed_by` is empty until a SASH system maintainer reviews it (#67).
- `systems/flashprove/claim.yaml`: the draft FlashProve claim card, configuration `exact-match-cp-verify` (the C++ verifier the adapter's `verify` runs, exact-match policy), every field copied from upstream at `9e2bdd8` with a line-anchored link (RFC-0002, #71). Upstream states soundness for its Lean verifier only and claims no level for `cp_verify`; the card says so. `reviewed_by: []`: no FlashProve maintainer has been reached.
- `systems/sash/system.yaml`, pinning the SASH image built from `main` at `d713177`; no system maintainer is named (RFC-0001 §System inclusion: not reached, no consent recorded). The SASH workloads list `sash`.
- `systems/sash`: `commit`, `prove` and `verify` mapped onto upstream's recorded job script at `eb95bfa` (witness extraction, model roots, per-shape CUDA kernels, `compose-chunks`, `boundary-grid --verify`), with the forbidden-flag guard and CPU tests against stand-in programs (#65).
- GPU runs: `iproofs run --gpu N` binds the GPU and selects CPUs on its NUMA node (RFC-0006 §CPU and memory selection), and every step is sampled by NVML at 20 Hz with the cgroup counters read over the call (RFC-0011), so the resource metrics of a GPU run are measured. `machine-record --hosted` and the machine record's `container.execution`, `cpu.cgroup_quota_cpus` and `memory.cgroup_limit_bytes` (additive `manifest/1` and `reference/1` changes).
- `systems/flashprove`: `setup` runs upstream's fit (calibration set from the three files upstream names by sha256, weight sums, scales on the GPU, both published digests checked), and `commit`, `prove` and `verify` call `cp_commit`, `cp_prove` and `cp_verify` as upstream's own scripts do, with incremental release per batch and the forbidden-flag guard (#69).
- Workloads `fp-maverick-w1024-b1` and `fp-maverick-w1024-b24`: the public 4-bit Llama 4 Maverick files FlashProve names, every file hash, the model digest and the tokenizer from a second pinned source (RFC-0003).
- Workloads `sash-l31-8b-c4096` and `sash-l31-8b-c1024`: Llama-3.1-8B pinned at the revision SASH's runs name, every file hash and the model digest (RFC-0003).
- `web/`: a first dashboard for the platform (Next.js static export, deployable on Vercel) with the RFC-0009 pages: overview, release, native division with sorted views, systems, workloads, controls, targets, methodology, sponsors. Run values, controls, targets and reproductions are mock data, labelled on every number; upstream figures, the reference price and the RFC list are read from the repository at build time. G3 skips `web/` tool-written JSON and G8 covers the dashboard sources (RFC-0013 text updated).
- `ref-serve` and `ref-recompute` pin their pushed images, `ghcr.io/ai-verification-observatory/ref-serve` and `.../ref-recompute`, by manifest digest (RFC-0014 B7).
- `systems/sash`: the SASH adapter image (Dockerfile, inputs.lock) built by the RFC-0014 rules from upstream's own build at `eb95bfa`, with `info` and `setup`; `write_inputs.py` records an adapter's toolchain versions (B5).
- `systems/flashprove`: the FlashProve adapter image (Dockerfile, inputs.lock, hash-locked CUDA 13.2.2 packages) built by the RFC-0014 rules from upstream's build instructions at `9e2bdd8`, with `info` and `setup`.
- The `images` workflow: builds an adapter image from a clean checkout of `main` and pushes it to `ghcr.io/ai-verification-observatory/<system>`, printing the manifest digest (RFC-0014 B6, B7).
- The `iproofs` harness package (`harness/`), with `validate`, `derive`, `run` and `controls` commands.
- JSON Schemas under `schema/`, each with valid and invalid examples.
- The `fake` and `fake-broken` test systems, the `fake-tiny-ci` workload and the `ci-cpu` profile.
- Tree gates G2 to G7 and G9, and the G10 fake-system end-to-end job (RFC-0013).
- `review/1` and `reproduction/1` schemas with their models (RFC-0007).
- `iproofs prompts build WORKLOAD --seed SEED`: rebuild and digest a job's prompt set from the verified corpus and tokenizer file (RFC-0003).
- `iproofs fetch-model WORKLOAD`: weights fetched at the pinned revision into a read-only cache, every file and the model digest checked, rehashed at every job start (RFC-0014).
- `iproofs machine-record --selftest [--gpu INDEX] [--probe-image IMAGE_ID]`: the RFC-0011 calibration checks ST-CLOCK to ST-OOM, saved for the runner's manifests.
- `iproofs machine-record`: the RFC-0006 machine record from allowlisted probes; every run records it before `info` and checks it again after the last step (INV-MR-2).
- `iproofs run --runner HANDLE --runner-org ORG --affiliated SYSTEM`: the declared runner recorded in every manifest; `iproofs.release.is_unaffiliated` (RFC-0007 §Tiers).
- `iproofs archive upload`: uploads proof archives and the adapters' upstream inputs to the archive dataset, checks every stored digest and records the pinned archive URI in the manifest (RFC-0014, RFC-0009 Q1).
- `systems/ref-serve`: the plain-serving reference adapter (entrypoint, Dockerfile, inputs.lock, CPU tests on engine outputs captured on a GPU host) (RFC-0015).
- `systems/ref-recompute`: the recompute reference adapter, the ref-serve entrypoint with `reference_role: recompute` (teacher-forced argmax from prompt log-probabilities, one request at a time), with CPU tests on argmax tokens captured on a GPU host (RFC-0015).
- `iproofs reproduce compare ORIG_RUN REPRO_RUN`: eligibility, the tolerance rule, verdict and digest matching, and the `reproduction/1` record (RFC-0007).

### Changed

- `run/1` `proofs[]`: optional `request_index`, `claimed_output` and, for ref-recompute runs, `agreement`; `adapter-job/1`: optional `claims_file` on `prove`. The runner passes a source run's claims to a ref-recompute job and records the agreement counts as run metrics (RFC-0015 RC-1, RC-5).
- `system/1`: a reference system may pin its adapter image (`image`); release freeze applies the project-registry rule to reference runs too (RFC-0014 B7, RFC-0015).
- Release freeze refuses a prover run whose image is not in `ghcr.io/ai-verification-observatory/` (eligibility reason `image_not_in_project_registry`, RFC-0014 Q2 and B7; from #255).
- CI runs the unit tests in three shards per Python version and combines coverage in the `tests` jobs, whose check names are unchanged (docs/spec/07 §Sharding).
- `reference/1`: optional `cost.readings` (provider, URL, offer, list price, GPU count), from which validate recomputes the price (rule COST-1, RFC-0006 C3).
- `iproofs release freeze` refuses a reference file with no price or no date (RFC-0006 C6).

### Deprecated

### Removed

### Fixed

- `sash` declares a 21,600 s `verify` limit; the 3,600 s default stopped a job whose grid verification on 8 CPUs took longer.
- `sash` pins the image rebuilt from `main` at `aa3fbb2`: vendored crates readable by the adapter user (#283) and the program path mapped (#289).
- Hosted execution passes the adapter absolute `IPROOFS_IO` and `IPROOFS_MODELS` paths; with `--results results` they were relative, and FlashProve's fit, which runs upstream from its own directory, could not find `/io/fit`.
- `sash`: the program path of an upstream call is mapped like its arguments, so `prove` finds the CUDA build it made under `/io/state/build` when `/io` is mapped (hosted execution).
- G4: a derived quantity of a substituted reference row whose inputs are all absent (a reference row has no verify step) recomputes with the row's `precision_substituted` flag (RFC-0015 PM-2); the check had refused six real runs.
- `sash`: the image makes the vendored crates readable by all; `prove`'s CUDA build, run as the adapter user, failed on an owner-only file of the `fnv` crate.
- `flashprove`: `prove` unpacks the secret key directory with its recorded modes; `cp_prove` refused it (cp-isk) when the unpack gave its directories the default mode instead of 0700.
- `ref-serve` and `ref-recompute` pin images rebuilt from `main` with the `/tmp` engine caches (`ref-serve` at `2dacdc8`, `ref-recompute` at `d713177`).
- Hosted execution: the harness removes what the adapter uid left in `/tmp` before each call, as docker's per-call tmpfs would, so engine and compile caches do not carry from one repetition to the next (RFC-0006 §Hosted execution).
- `ref-serve` and `ref-recompute`: vLLM's JIT and compile caches go under `/tmp`, writable under a read-only root filesystem; the adapter user has no home, and engine start failed with EACCES on `~/.cache`. The pinned images predate this fix and are rebuilt by the images workflow.
- Gate G9 (SEC-5) no longer reads a requirement pin such as `nvidia-cublas==13.4.1.3` as an IPv4 address; any other match is still reported.
- Release eligibility read the pinned image from `system.yaml` at the image's own build commit, which can never hold that image's digest, so every pushed image was ineligible. It now reads the pin at the release commit and requires the build commit to be its ancestor (RFC-0014 §Eligibility, INV-DM-4 wording clarified).

### Security

- The commitment a verifier checks comes only from the harness's commit record (RFC-0014 §The commitment record).
