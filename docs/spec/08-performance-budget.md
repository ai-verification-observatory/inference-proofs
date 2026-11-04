# 08. Performance budget

Status: Draft 0.1, part of the specification corpus indexed by [docs/SPEC.md](../SPEC.md). Normative decisions live in the RFCs under [rfcs/](../../rfcs/README.md); where this section and an Accepted RFC disagree, the RFC takes precedence.

This section sets the performance budgets of the benchmark's own software: the harness's measurement overhead, the CPU-only tooling (validation, derivation, site, CI), and the method for budgeting GPU time for a run campaign. It does not set targets for the measured provers; the project publishes no targets for systems (RFC-0009 §Targets). Every number below is a **target** (a budget the software must meet), not a measurement, and carries no grade or tier because it describes no run.

## Why budgets exist here

Two kinds of cost matter. The first is measurement interference: if the harness steals CPU time, memory bandwidth or scheduling slots from the job, it changes the numbers it reports. The second is contributor cost: if validation or CI is slow, people stop running it locally and errors reach `results/`. Both are bounded below, and each bound has a named check.

## Harness measurement overhead

Owner: [RFC-0011 §Measurement overhead budget](../../rfcs/0011-measurement-and-sampling.md#measurement-overhead-budget).

| Budget id | Item | Target | Checked by |
|---|---|---|---|
| B-OVH-CPU | sampler plus release watcher CPU use, at 20 Hz | at most 1 % of one logical CPU | GH-OVERHEAD (GPU host) |
| B-OVH-JITTER | sampler deadline lateness, p99 | at most 10 ms | ST-JITTER (self-test), GH-OVERHEAD |
| B-OVH-RATE | achieved sampling rate | at least 10 Hz, gaps above 150 ms on at most 5 % of a call | ST-SAMPLER; per-call `degraded` flag |
| B-OVH-RSS | harness resident memory during a call | at most 256 MiB | GH-OVERHEAD |
| B-OVH-WATCH | release time error | inotify: at most 5 ms; poll fallback: at most 10 ms plus scheduling delay | TC-WATCH-INOTIFY, TC-WATCH-POLL |
| B-OVH-TRACE | 1 Hz downsampled trace per call | within the 1 MiB per-file log cap for calls up to 6 hours | unit test on trace writer size |

Isolation rule: the harness pins itself to one logical CPU outside the prover and verifier CPU sets (RFC-0011 C-3, RFC-0006 §CPU and memory selection). Its overhead therefore never enters a job's cgroup counters, and B-OVH-CPU bounds interference through shared caches and memory bandwidth rather than through CPU time accounting.

Container start-up is not overhead of the harness: it is part of every adapter call and is reported (`info_seconds`, RFC-0004), not subtracted.

## CPU-only tooling

These steps must run on any developer machine and on hosted CI (AGENTS.md: CPU-only steps run anywhere). Reference machine for these targets: a hosted CI runner with 4 vCPUs and 16 GB memory, or a laptop of similar size.

| Budget id | Operation | Target |
|---|---|---|
| B-CI-TOTAL | all pull request gates of RFC-0013, wall time | at most 10 minutes |
| B-CI-UNIT | unit, property and schema-example tests, per shard on hosted CI ([07 §Sharding](07-testing-strategy.md#sharding)) | at most 3 minutes |
| B-CI-E2E | fake-system end-to-end run plus controls, and the `fake-broken` check | at most 2 minutes |
| B-VAL-TREE | `iproofs validate` over a tree of 1,000 run directories | at most 60 seconds |
| B-DERIVE-RUN | `iproofs derive --check` on one run directory | at most 50 ms |
| B-SITE | `iproofs site build` over 1,000 run directories | at most 60 seconds |
| B-FREEZE | `iproofs release freeze` over 1,000 run directories | at most 60 seconds |
| B-CLI-START | `iproofs --help` cold start | at most 500 ms (optional extras are imported lazily) |

Design consequences:

- Optional dependencies (`nvidia-ml-py`, `huggingface_hub`, `tokenizers`) are imported only inside the functions that need them, so CPU-only commands never load them (B-CLI-START).
- Schemas are compiled once per process (`jsonschema` validator objects cached by `$id`), not per file (B-VAL-TREE).
- `results/` grows append-only; validation on a pull request covers changed files plus cross-file checks that the change touches, and the full-tree validation runs on the default branch (RFC-0013), so pull request time does not grow with history.

## Run-campaign compute budget

A release needs GPU time for every configuration, repetition, negative control and reference row, and a third-party reproduction needs about as much again. Sponsors and runners need that estimate before the campaign starts (PRD §11, "proving runs are expensive").

Method (AGENTS.md rule 3: derived numbers are computed, not typed):

1. Inputs are the `external` quantities in `systems/<name>/external.yaml` (upstream figures with their upstream scope, RFC-0004 §Mapping from upstream scopes) and the workload shapes (RFC-0003).
2. `iproofs.derive.project_campaign(release: str, root: Path) -> CampaignProjection` computes, per configuration, projected GPU-seconds as repetitions × (projected `whole_wall` seconds for the shape) + projected commit seconds for one perturbed-weights commitment (control C3, once per workload) + projected prove seconds for prover-side controls P1 and P2 + projected reference-row seconds (RFC-0015). Setup is counted once per image per host.
3. Every output quantity has grade `projected`, names the formula id P-CAMPAIGN and lists its external inputs in `source.inputs`. Where an input is missing (for example `whole_wall` is not published upstream), the projection for that configuration is null with `null_reason: missing_input` and the gap is listed; nobody fills it by hand.
4. The projection is printed by `iproofs release plan RELEASE` and attached to the release's sponsorship request; it is never published as a result.

The command is [`iproofs release plan RELEASE [--repetitions N]`](../../harness/src/iproofs/cli.py) (default and minimum 3) and the code is `project_campaign` in [`derive.py`](../../harness/src/iproofs/derive.py). It reads the `external.yaml` metrics `whole_wall_seconds`, `commit_seconds` and `prove_session_seconds` of each system, and `prove_session_seconds` of the reference system `ref-serve` for the same workload. Each configuration also lists `missing` (the absent inputs) and `verify_seconds_per_proof_external` (the upstream `verify_single_thread_seconds` figure, or null).

Verifier-side controls C1 to C8 run on the CPU verifier profile (RFC-0008) and cost no GPU time; the projection reports their verify-seconds separately, from `external` verify figures.

## Profiling plan

- Harness hot paths (validation, derivation, site build, freeze) are profiled with the standard library `cProfile` on the 1,000-run synthetic tree generated by the test fixture `harness/tests/fixtures/synthetic_tree.py`. No profiling dependency is added.
- The synthetic tree generator is deterministic (fixed seed) so profiles compare across commits.
- Measurement overhead is profiled only on the GPU host, via GH-OVERHEAD (RFC-0011 §Testing Strategy), because it depends on NVML and the real scheduler.
- CI records each gate's wall time in the job summary, so drift is visible before a budget is breached. Every job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) has a hard timeout of twice its target; jobs with no gate-specific target use twice B-CI-TOTAL.
- The tooling benchmarks are [`harness/tests/bench/test_budgets.py`](../../harness/tests/bench/test_budgets.py) (B-VAL-TREE, B-DERIVE-RUN, B-CLI-START) over [`harness/tests/fixtures/synthetic_tree.py`](../../harness/tests/fixtures/synthetic_tree.py). They run on the default branch with `IPROOFS_BENCH=1`, fail at twice the target, and write each time and its target to the job summary.

## When a budget is exceeded

| Budget class | Response |
|---|---|
| Measurement overhead (B-OVH-*) on a host | the self-test fails and the host is refused (`environment`, exit 3) for B-OVH-JITTER and B-OVH-RATE; a GH-OVERHEAD failure for B-OVH-CPU or B-OVH-RSS blocks the release until fixed; per-call sampling gaps mark that call's GPU metrics `degraded: true` rather than failing it |
| CI gates (B-CI-*) | each CI job has a hard timeout of twice its target; a timeout fails the pull request; a gate between its target and the hard timeout passes, its time is shown in the job summary, and a maintainer opens an issue labelled `type:perf` |
| Tooling operations (B-VAL-TREE, B-DERIVE-RUN, B-SITE, B-FREEZE, B-CLI-START) | a benchmark test over the synthetic tree fails at twice the target on the default branch; a breach between target and twice the target is reported in the job summary |
| Campaign projection | if a projected configuration exceeds the sponsored GPU budget, the release plan drops repetitions only down to the minimum of three (RFC-0004 §Statistics); below that, the configuration is deferred and the release report says so |

Changing a target is a change to this document by pull request; changing a measurement mechanism to meet a target is a change to RFC-0011 and goes through RFC-0001.

## Cross-references

- [RFC-0004 §Statistics](../../rfcs/0004-metrics-timing-grades.md#statistics) for the repetition minimum.
- [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md) for profiles and CPU binding.
- [RFC-0011](../../rfcs/0011-measurement-and-sampling.md) for the sampler, watcher and self-test.
- [RFC-0013](../../rfcs/0013-validation-and-ci.md) for the CI gates timed here.
- [RFC-0015](../../rfcs/0015-reference-rows.md) for reference rows in the campaign projection.
