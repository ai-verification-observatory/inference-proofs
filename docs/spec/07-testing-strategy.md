# 07. Testing strategy

Status: Draft 0.1. CI gates that run these tests are defined in [RFC-0013](../../rfcs/0013-validation-and-ci.md). Specific test cases per mechanism are listed in each RFC's Testing Strategy section; this section fixes where tests live, what each layer must prove and the rules every test follows.

## Principles

1. **CPU first.** Everything except the GPU measurement path is testable on a laptop without a GPU (AGENTS.md working practice). GPU code is thin and isolated behind interfaces that have CPU fakes.
2. **Hand-computed truth.** Every derived metric ships with at least one test whose expected value was computed by hand and written in the test with the arithmetic in a comment (AGENTS.md working practice). The derivation code may not be used to produce its own expected values.
3. **Valid and invalid examples.** Every schema ships with examples that must pass and examples that must fail, each failing example naming the rule it breaks (RFC-0012).
4. **Every gate has a bad fixture.** A gate that passes everything is a failure; each gate's suite includes a fixture it must flag (RFC-0013).
5. **Determinism.** No test depends on wall-clock time, network, locale, hash seed or test order. Hypothesis runs derandomized in CI.
6. **Failures are data.** Tests for failure paths assert the failure record (kind, step, exit code, last lines), not only that an exception was raised.

## Layers

| Layer | Location | Runs where | Gate | What it proves |
|---|---|---|---|---|
| Unit | `harness/tests/unit/` | anywhere | G1 | pure functions: serialization, digests, quantities, derivations, statistics, mutations, redaction, CLI argument handling |
| Property | `harness/tests/property/` | anywhere | G1 | invariants over generated inputs |
| Schema examples | `schema/*/examples/{valid,invalid}/` | anywhere | G2 | schemas accept and reject what the RFCs say |
| Gate fixtures | `harness/tests/fixtures/gates/<gate>/` | anywhere | G1 | each gate flags its known-bad input |
| Adapter fixtures | `systems/<name>/tests/` | anywhere | G1 | the adapter maps stored upstream outputs to `adapter-out/1` correctly and maps every documented upstream exit code to the right verdict |
| Golden | `harness/tests/golden/` | anywhere | G1 | site HTML and release index bytes for a fixture release |
| Fake-system integration | `systems/fake`, `systems/fake-broken`, `harness/tests/integration/` | anywhere with Docker | G10 | the full job lifecycle, controls and record writing end to end |
| GPU runbook tests | `docs/runbooks/gpu-run.md`, `harness/tests/gpu/` | GPU host, by a person | none (pre-campaign checklist) | NVML sampling, cgroup reading, NUMA binding, real adapters on real hardware |

## Named suites and minimum cases

The list below is the floor; RFC Testing Strategy sections add cases.

### Unit

- `test_serialize.py`, `test_digest.py`, `test_yaml.py`, `test_quantity.py`, `test_ids.py`, `test_model_drift.py`: as listed in [RFC-0012 §Testing Strategy](../../rfcs/0012-schemas-and-serialization.md#testing-strategy).
- `test_derive_formulas.py`: one hand-computed case per RFC-0004 formula. Example form:

  ```python
  def test_cost_per_1k_tokens_hand_computed() -> None:
      # 2.0 s/token * 1000 tokens * 1 GPU * 3.60 USD/gpu_hour / 3600 s/h = 2.0 USD per 1k tokens
      assert derive.cost_per_1k_tokens(s_per_token=2.0, gpus=1, usd_per_gpu_hour=3.60) == 2.0
  ```

  Inputs are chosen so the hand result is exact in binary64, and the comment shows the arithmetic. The inputs are test fixtures, not measurements, and are never published.
- `test_derive_nulls.py`: every formula with a null or zero denominator returns `value: null` with the RFC-0004 `null_reason`, never NaN or infinity.
- `test_stats.py`: n = 0, 1, 2, 3; failed repetitions excluded from the mean and counted in `n_failed`; stdev null for n < 2; inputs ordered by repetition.
- `test_scopes.py`: `prove.steady` from release times `[10 s, 12 s, 15 s]` with tokens `[100, 100, 100]` gives 200 tokens over 5 s; one proof gives null with `fewer_than_two_proofs`; `whole_wall` starts at the commit call, not setup.
- `test_mutations.py`: each control C1 to C8 changes exactly what RFC-0008 says (C1 token becomes `(t+1) mod vocab_size`; C5 halves the largest part; C6 flips exactly one bit at the seeded offset; C7 swaps two proofs; C8 drops one part) and is deterministic for a seed.
- `test_redact.py`: every pattern of RFC-0013 G9 is removed from a log line; `test_redactor_and_scanner_share_patterns`.
- `test_errors.py`: each `ErrorKind` maps to the CLI exit code in RFC-0010; failure records carry at most 50 redacted last lines.
- `test_machine_record.py`: the record built on a fixture `/proc` and `/sys` tree contains exactly the RFC-0006 fields and none of the excluded ones.

### Property (Hypothesis)

- `test_roundtrip`, `test_digest_order_independent`, `test_fsum_order_independent` (RFC-0012).
- `test_rate_inverse`: for positive tokens and seconds, `seconds_per_token == 1 / tokens_per_second` is not asserted bitwise (it is not exact); instead both are computed from raw inputs and each equals its own formula. This guards against deriving one metric from another derived metric.
- `test_tolerance_symmetric_cases`: the RFC-0007 tolerance accepts identical means for any stdev and rejects means differing by more than both bounds.
- `test_target_least_favourable_case`: for any repetitions and threshold, `meets` under `<=` implies every repetition is at or below the threshold.
- `test_mutation_changes_digest`: every byte-level control mutation changes the proof digest.

### Adapter fixtures

Each adapter directory `systems/<name>/tests/` holds stored upstream outputs captured on a GPU host (small text outputs, exit codes, last lines; never weights, never large proofs) and tests that:

- `test_verdict_mapping`: every upstream exit code and final line documented for the pinned commit maps to the verdict the adapter README states (for FlashProve, the mapping in [RFC-0005](../../rfcs/0005-adapter-contract.md); for SASH, segment and grid outcomes).
- `test_out_json_valid`: the adapter's output builder produces `adapter-out/1` documents for each stored case.
- `test_forbidden_flags_guarded`: building a measured `prove` command never includes a forbidden flag; building a control command includes only the flag the control names.
- `test_dockerfile_rules`: B1 to B7 of [RFC-0014](../../rfcs/0014-provenance-and-integrity.md#adapter-image-build) hold for the Dockerfile.

### Golden

- `golden/site/`: HTML of every page type for a fixture release with two fake systems, one reference row, one superseded run, one failed repetition, one target and one reply. Assertions in [RFC-0009 §Testing Strategy](../../rfcs/0009-results-and-publication.md#testing-strategy). Golden files are regenerated only by `uv run pytest --update-golden` in a pull request that explains the diff.
- `golden/index/`: `index.json` for the same fixture release, byte for byte.

### Fake-system integration

On hosts without NVML or cgroup v2 (macOS, hosted CI), the `ci-cpu` profile selects null readers ([RFC-0011 §Portability](../../rfcs/0011-measurement-and-sampling.md#portability), `iproofs.measure.NullCgroupReader`): every GPU, host-memory and CPU metric of a fake run is null with `null_reason: not_applicable`, and the release watcher polls instead of using inotify. A GPU profile never falls back to them; without NVML it fails with kind `environment` (`harness/tests/unit/test_portable_readers.py`).

The G10 job of [RFC-0013 §G10](../../rfcs/0013-validation-and-ci.md#g10-fake-system-end-to-end), implemented in `harness/tests/integration/test_fake_e2e.py` and run by the `fake-e2e` job of [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). With `IPROOFS_REAL_DOCKER=1` (`make e2e`, and the `fake-e2e` job) the module builds the fake images and runs real containers; without it, `docker` is the stand-in CLI in `harness/tests/fixtures/fake-docker`, so the same tests run anywhere in the ordinary test job. Faults are injected through `IPROOFS_FAKE_FAULT` in the fake image (`exit`, `sleep`, `escape`, `network`). The module holds `test_e2e_fake_and_fake_broken` (rule `E2E-1`), plus:

- `test_failed_step_recorded`: an environment variable in the fake image makes `prove` exit 3; the run is `failed` with step `prove`, exit code 3 and last lines, and the directory validates.
- `test_timeout_recorded`: a fake `prove` that sleeps past its limit yields `ErrorKind.timeout`, the container is killed, the record is written.
- `test_path_traversal_rejected`: a fake `out.json` naming `../../etc/passwd` as a proof part yields `ErrorKind.adapter`.
- `test_commitment_from_record`: see RFC-0014.
- `test_network_none`: the fake adapter tries to open a socket during `prove` and records the failure; the test asserts the attempt failed. Real containers only.

### GPU runbook tests

Run by a person on the GPU host before every measurement campaign and recorded in the campaign log (not CI):

- `harness/tests/gpu/test_nvml_sampler.py`: sampler rate at least 10 Hz over 60 s, gap accounting, memory peak of a known allocation (a CUDA allocation of a fixed size made by the test container) within the sampling resolution.
- `test_cgroup_reader.py`: `memory.peak` and sampled `anon` for a container that allocates a known amount.
- `test_numa_binding.py`: the chosen cpuset lies on the GPU's NUMA node and prefers distinct physical cores.
- One full `fake` run on `prover-h100` and one short real job per adapter on the smallest workload, with controls.

## Determinism tests

- Byte-identical `index.json` and site output across two freezes in different directories (RFC-0009).
- Byte-identical prompt set for a given seed and corpus across two hosts (`test_prompts_deterministic` runs in CI against a small fixture corpus and fixture tokenizer).
- Fake system proof digests identical across runs with the same seed (`deterministic_proofs: true` in its `system.yaml`), which exercises the RFC-0007 digest comparison.

## Coverage

Line coverage target for `iproofs` excluding `iproofs.measure.nvml` and `iproofs.measure.cgroup`: 90 % (target, measured by `pytest --cov` in CI and reported, not enforced as a gate in v0.1). Branch coverage of `iproofs.derive`, `iproofs.controls` and `iproofs.validate`: 100 % (target, enforced by a coverage threshold in G1 from v0.1-beta), because these modules decide what is published.

## Flaky-test policy

A test that fails intermittently is a bug. The first failure opens an issue with the log; the test is fixed or quarantined within 7 days by marking it `@pytest.mark.quarantine` with the issue number, which CI runs but does not count as blocking. A quarantined test older than 30 days blocks the next harness release (docs/spec/09-release-and-versioning.md). Retrying a failing test automatically in CI is not allowed.
