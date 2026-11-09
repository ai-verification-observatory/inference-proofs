# 10. Glossary

Status: Draft 0.2, 2026-11-03. Canonical vocabulary for the whole corpus. Every other document uses these terms with these meanings and defines no term of its own; a new term is added here in the same pull request that first uses it. Terms are in alphabetical order. The enumerated values of a vocabulary (scopes, grades, tiers, verdicts, outcomes, error kinds) are normative in the RFC named beside them; this file repeats them for reading convenience and the RFC wins on any difference.

This file quotes the neutral-language rule and its banned words, so it is on the allowlist of the language lint ([RFC-0013](../../rfcs/0013-validation-and-ci.md)).

## Terms

<a id="adapter"></a>**Adapter.** The directory `systems/<name>/` and the OCI image built from it that wraps one upstream prover, unchanged, behind the five subcommands of the adapter contract. An adapter translates; it never patches upstream source. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="adapter-contract"></a>**Adapter contract.** The versioned interface (`adapter/1`) between the harness and an adapter: subcommands `info`, `setup`, `commit`, `prove`, `verify`, each reading `/io/job.json` and writing `/io/out.json`. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="amortisation-horizon"></a>**Amortisation horizon.** The number of requests of a workload's shape over which commit time is spread when reporting amortised commit cost. v0.1 reports two horizons: 1 request and 1,000 requests. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="attested"></a>**Attested.** A statement vouched for by hardware or a signing party (for example a trusted execution environment report). Never used for a cryptographic proof. Contrast [proved](#proved).

<a id="benchmark-release"></a>**Benchmark release.** A frozen, named set of runs, reference file, RFC versions and reviewed claim cards, for example `v0.1`. Independent of harness package versions. [RFC-0009](../../rfcs/0009-results-and-publication.md), [09](09-release-and-versioning.md).

<a id="binding"></a>**Binding.** Whether a proof ties one edge of the computation (for example layer output to next layer input, or weights to commitment) to the statement. Each edge is `bound`, `unbound`, `absent` or `not_stated` on the claim card. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="bound"></a>**Bound.** Said of an edge of the computation that the verifier's acceptance constrains. A bound edge is part of what is proved.

<a id="claim-card"></a>**Claim card.** The machine-readable statement, per system configuration, of what an accepted proof establishes, under which assumptions, and what a dishonest prover can still do (`systems/<name>/claim.yaml`, or `systems/<name>/claims/<configuration>.yaml` when a system has several configurations; versioned by `card_version`). No number is published without one. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="claim-class"></a>**Claim class.** A short identifier for a family of relations that closed-division rows and targets filter on, for example greedy next-token exact match of a committed model. [RFC-0002](../../rfcs/0002-claim-card.md), [RFC-0003](../../rfcs/0003-workloads.md).

<a id="commitment"></a>**Commitment.** The value, produced by the `commit` step, that fixes the model weights a later proof refers to. The commitment the verifier checks against always comes from the harness's own record of the `commit` step, never from files shipped with a proof (AGENTS.md rule 6). [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="control"></a>**Control (negative control).** A deliberate tampering of a request, claimed output, commitment, proof or prover input, applied by the harness, whose expected outcome is rejection (or, for system-specific unbinding switches, a documented acceptance). Identified C1 to C8 (verifier side) and P1, P2 (prover side). [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="control-job"></a>**Control job.** A job run with `control: true`. Only control jobs may use a configuration that weakens a system's statement. A control job never produces a measured row.

<a id="control-outcome"></a>**Control outcome.** One of `rejected`, `accepted`, `no_verdict`, `invalid_call`, `void`, `not_applicable`, `prover_failed` (prover-side controls P1 and P2 only), `error`. A control passes when its outcome is in its expected set. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="corpus"></a>**Corpus (prompt corpus).** The fixed set of public-domain texts from which prompt sets are drawn, listed with source and digest in `workloads/prompts/corpus.yaml`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="criteria-file"></a>**Criteria file.** `web/_data/criteria.json` (schema `criteria/1`): the six [glyph properties](#glyph-property), the four [glyph states](#glyph-state) and one row per system, reference and public-source system, each cell with its state, our short reason and the quotes or sources read behind it. Checked under G2 by the rules `CRIT-1` to `CRIT-14`. [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#criteria-file-contract).

<a id="derived-metric"></a>**Derived metric.** A number computed by the derivation code from stored raw numbers by a formula with a stable identifier (for example `D-RATE-S`). Never typed by hand. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="digest"></a>**Digest.** A SHA-256 value written `sha256:<64 lowercase hex>`. Model, proof, corpus, prompt-set and image digests have exact byte definitions in [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="division"></a>**Division.** The comparability class of a row: `native` (a system's own workload; side by side, never head to head), `closed` (a common workload and a fixed claim class; rows compare directly), `open` (anything declared; shown separately). v0.1 has native workloads and one closed workload, `l31-8b-c1024` on Llama 3.1 8B, whose rows publish once two systems with its claim class run it (RFC-0003 Q7, default). [RFC-0003](../../rfcs/0003-workloads.md).

<a id="effective-tier"></a>**Effective tier.** The evidence tier of a run as computed at release freeze from its review and reproduction records, written to `releases/<release>/index.json`. The tier stored in `run.json` is always `reported`. [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md).

<a id="error-kind"></a>**Error kind.** The category of a recorded failure: `config`, `environment`, `integrity`, `fetch`, `adapter`, `timeout`, `resource`, `policy`, `internal`. A verdict is a result, never an error. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="evidence-tier"></a>**Evidence tier.** Who stands behind a number: `reported` (one runner, not yet checked), `peer-reviewed` (checked by someone from another organisation), `reproduced` (rerun by an unaffiliated runner within tolerance). Only reproduced numbers are called measured in prose. [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md).

<a id="fake-system"></a>**Fake system.** `systems/fake/`, a CPU-only toy prover and verifier implementing the adapter contract, with a verifier that rejects every shared control. Its twin `systems/fake-broken/` accepts everything; CI asserts the control suite flags it. Used for end-to-end tests without a GPU. [RFC-0005](../../rfcs/0005-adapter-contract.md), [07](07-testing-strategy.md).

<a id="forbidden-flag"></a>**Forbidden flag.** A command-line option listed in `system.yaml` `forbidden_flags` because it weakens the system's statement (for example SASH's `--unsound-skip-*` family). Allowed only in control jobs; CI fails any measured run that used one. [RFC-0005](../../rfcs/0005-adapter-contract.md), [RFC-0013](../../rfcs/0013-validation-and-ci.md).

<a id="glyph"></a>**Glyph.** The six-part figure the site draws for one row, one part per [glyph property](#glyph-property), each in one [glyph state](#glyph-state). There is no total, score, count or order over states, and properties carry no numbers. [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#what-the-glyph-is-not).

<a id="glyph-property"></a>**Glyph property.** One of six questions a glyph answers, in display order: Weights hidden (`weights_hidden`: does the checker learn nothing about the weights?), Model bound (`model_bound`: is each checked token tied to the committed weights?), Whole output checked (`whole_output`: does one check cover every output token of a request?), Formally verified (`formally_verified`: is the security argument for this configuration checked by a proof assistant?), Security level (`security_level`: is a soundness level stated for this configuration, and proven?) and No trusted party (`no_trusted_party`: does a check hold without trusting a chip maker, a setup ceremony or an honest party?). [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#properties).

<a id="glyph-state"></a>**Glyph state.** The answer a glyph gives to one property, one of four, unordered: `yes` (printed Yes), `partly` (Partly), `no` (No) and `not_stated` (Not stated). On a claim card row a state is stated by the system at its pin, read for the configuration the benchmark runs and not contradicted by the benchmark's negative controls; a recorded control the verifier accepted where RFC-0008 expects rejection sets `no` on the property the control map gives it. Silence is `not_stated`, never `no`. A state is a validated claim, not an audit result. [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#states).

<a id="grade"></a>**Grade.** How a number was obtained: `measured` (read by the harness from an artifact of this project's run), `derived` (computed by CI by a named formula), `projected` (from a named cost model), `external` (read from a public source at a pin), `asserted` (an input such as a price, with source and date). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="harness"></a>**Harness.** The Python package `iproofs` and its CLI: it resolves workloads, runs adapters in containers, measures from outside, applies controls, writes and validates run directories, freezes releases and builds the site. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="honest-twin"></a>**Honest twin.** The unmodified counterpart of a control, verified in the same control batch with the same image and profile. If the twin is not accepted the control is `void`, never counted as a rejection. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="job"></a>**Job.** One system, one workload, one shape, one repetition, on one machine. The unit the runner executes and records. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="machine-record"></a>**Machine record.** The hardware and software description of the host a job ran on, limited to the fields RFC-0006 lists. It excludes hostnames, network addresses, GPU UUIDs and serials, account names and instance identifiers. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="manifest"></a>**Manifest.** `manifest.json` in a run directory: image digest, upstream commit, workload and prompt digests, seed, machine record, command lines, provider, runner. Everything needed to rerun the job. [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="native-workload"></a>**Native workload.** A workload a system supports at its pinned commit without change, used in the native division. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="null-reason"></a>**Null reason.** The required explanation when a quantity's value is null: `not_externally_observable`, `fewer_than_two_proofs`, `not_applicable`, `step_failed`, `not_measurable_on_profile`, `missing_input`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="overhead"></a>**Overhead.** The prover's GPU-seconds per token on its profile over [production serving](#production-serving)'s GPU-seconds per token on its own (vLLM, the publisher's release precision, every weight in GPU memory, the fewest GPUs of the same model that hold it), same workload version, steady scope, matched load (`D-OVERHEAD-S`); at high load as context (`D-OVERHEAD-HIGH-S`). A system with no steady scope (SASH) shows the warm figure instead: its proving session, its start-up included, over production serving's steady scope, the engine already running as a provider's is (`D-OVERHEAD-WARM`, Draft); the session figure with start-up on both sides (`D-OVERHEAD-SESSION`) is computed and not shown. One of the two figures that compare provers across models; the other is [prover time per bit of active weights](#prover-time-per-bit). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md), [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="production-serving"></a>**Production serving.** The model served unproved as providers serve it: the pinned vLLM release with its defaults, the publisher's release precision, every weight in GPU memory, tensor parallel over the fewest GPUs of the proving system's GPU model that hold it, at two load points (the workload's batch size, `matched`, and a high-load batch, `high`). The baseline of the [overhead](#overhead). [RFC-0015](../../rfcs/0015-reference-rows.md) SRV-6.

<a id="profile"></a>**Profile.** A named machine specification in `reference/<release>.yaml`. v0.1 defines the reference `prover-h200`, its hosted form `prover-h200-hosted`, `prover-h100`, `prover-h100-hosted`, `verifier-cpu`, and the serving profiles `serving-h200x1-hosted` and `serving-h200x4-hosted` (RFC-0006 R6). Every row names its profile; nothing is compared across profiles without the profile in the row. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="proof"></a>**Proof.** In this project, the set of files (parts) that one `verify` call checks for one request, released atomically as `/io/proofs/<proof_id>/`. For a segment-grid system it is the set of segment proofs for one sequence plus whatever the grid check needs. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="proof-part"></a>**Proof part.** One file inside a proof directory. Controls C5, C6 and C8 operate on the parts the adapter declares its verify step reads (`system.yaml` `proofs.verify_reads`); `controls.json` lists each part not read with its reason. [RFC-0008](../../rfcs/0008-negative-controls.md#parts-the-verifier-reads).

<a id="prover-time-per-bit"></a>**Prover time per bit of active weights.** Prover seconds per token covered divided by the bits of weights one token uses, active parameters per token times [weight bits](#weight-bits) (`D-SPAB-S`, unit `s/bit_token`). Attention cost is not in the normaliser. Shown only with the claim cards. Proof size and check time have the same basis (`D-BPAB`, `B/bit_token`; `D-VSPAB`, `s/bit_token`); the site prints all three per token per Gbit of active weights (1e9 bits), in ms and kB. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="proved"></a>**Proved.** Said of a statement that a sound verifier's acceptance establishes under the claim card's stated assumptions. Never "provably safe". Contrast [attested](#attested), [sampled](#sampled).

<a id="quantity"></a>**Quantity (labelled quantity).** The only form in which a number is stored: `{value, unit, scope, grade, tier, source, null_reason}`. A statistic adds `stats: {n, n_failed, mean, stdev, min, max}`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="reference-row"></a>**Reference row.** A row produced by a reference system on the same workload as a proving row, so a proving cost reads against something: [production serving](#production-serving) (`systems/ref-serve`) and naive recompute (`systems/ref-recompute`). [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="relation"></a>**Relation.** The claim card's one-sentence statement of what is true when the verifier accepts. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="release-time"></a>**Release time.** The monotonic timestamp at which the harness observed a proof directory become visible under `/io/proofs/` by atomic rename. Timing scopes for proving are defined on release times. [RFC-0011](../../rfcs/0011-measurement-and-sampling.md).

<a id="relying-party"></a>**Relying party.** Someone who would act on a proof: a policy analyst, auditor, lab, government or standards body. Relying parties publish targets; the project publishes none.

<a id="repetition"></a>**Repetition.** One of at least three jobs run for the same system, workload, shape and profile. Statistics are computed over successful repetitions; failed ones are counted in `n_failed`.

<a id="reproduction"></a>**Reproduction.** A rerun of a run's configuration through the harness by a runner unaffiliated with the system's authors and the original runner, compared with the RFC-0007 tolerance and recorded in a reproduction record. [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md).

<a id="residual"></a>**Residual.** The claim card's list of what a cheating prover can still do while passing verification. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="row"></a>**Row.** The published aggregate of the repetitions of one configuration (system, workload, shape, profile), with its claim card, labels, controls and reference rows.

<a id="run-directory"></a>**Run directory.** `results/<release>/<system>/<run-id>/`, the append-only record of one job: `run.json`, `manifest.json`, `controls.json`, `verifier/`, `logs/`, `digests.txt`, and later `reviews/` and `reproductions/`. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="runner"></a>**Runner.** The person or organisation that executes jobs and signs off the run directory. The runner's affiliation is recorded and determines eligibility for review and reproduction.

<a id="sampled"></a>**Sampled.** Said of a guarantee obtained by checking a random subset of the computation (for example sampled recompute). A sampled guarantee is statistical, not cryptographic, and the claim card says so.

<a id="scope"></a>**Scope (timing scope).** The interval a time or rate covers: `setup`, `commit`, `prove.steady`, `prove.session`, `whole_wall`, `verify`, `verify.single_thread`, `primitive`. Every time-based number names exactly one. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="seed"></a>**Seed.** The 64-bit value from which a job's prompt offsets are drawn. Measured jobs draw a fresh seed from the operating system at job start and record it; reproductions replay recorded seeds and add at least one fresh seed. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="shape"></a>**Shape.** The size parameters of a workload: `prompt_tokens`, `output_tokens`, `batch_size`, `batches_per_session`, `context_window`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="system"></a>**System.** A prover (or a reference engine) measured by the benchmark, identified by a name matching `^[a-z][a-z0-9-]{1,31}$`, for example `sash`, `flashprove`, `ref-serve`.

<a id="system-maintainer"></a>**System maintainer.** A person a prover team names to own its adapter and claim card and to review every row about its system before publication. [RFC-0001](../../rfcs/0001-process-and-governance.md).

<a id="target"></a>**Target.** A threshold on a named metric for a claim class, published by a relying party under their own name in `targets/<author>/<id>.yaml`. Rows show `meets`, `does_not_meet` or `not_evaluable` per target. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="tokens-covered"></a>**Tokens covered.** The positions whose computation a proof binds, as declared by the claim card and the adapter and checked against the workload: for a prefill proof stating the next token, the window's positions; for a segment grid, the positions in the grid. The denominator of every per-token metric. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="unbound"></a>**Unbound.** Said of an edge of the computation that the verifier's acceptance does not constrain, either by design or because a switch disabled its check.

<a id="verdict"></a>**Verdict.** The adapter's normalisation of one `verify` call: `accept`, `reject`, `no_verdict`, `invalid_call`, always stored with the upstream verifier's raw exit code and last line. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="weight-bits"></a>**Weight bits.** The bits that store one weight of a workload's precision as proved, one number in the workload record with its source: computed from the pinned files when they hold the precision as proved (the mean storage bits per active weight from their tensor tables, block scales included, or file size when they hold every weight at one width), else as the precision's own documentation states it, with whether the statement covers all or part of the active weights. [RFC-0003](../../rfcs/0003-workloads.md#weight-bits).

<a id="workload"></a>**Workload.** A versioned definition (`workloads/<id>.yaml`) of a model by content digest, a precision, a prompt generator over the corpus, a shape, a decoding rule, a phase and a division. [RFC-0003](../../rfcs/0003-workloads.md).

## Neutral language

The project describes what was measured. Prose MUST NOT use "fastest", "best", "winner", "beats" or "provably safe" about a system, and MUST use proved, bound, attested and sampled with the meanings above. The lint word list is normative in [RFC-0013](../../rfcs/0013-validation-and-ci.md).
