# 10. Glossary

Canonical vocabulary for the whole corpus. Every other document uses these terms with these meanings and defines no term of its own; a new term is added here in the same pull request that first uses it. Terms are in alphabetical order. The enumerated values of a vocabulary (scopes, grades, tiers, verdicts, outcomes, error kinds) are normative in the RFC named beside them; this file repeats them for reading convenience and the RFC wins on any difference.

This file quotes the neutral-language rule and its banned words, so it is on the allowlist of the language lint ([RFC-0013](../../rfcs/0013-validation-and-ci.md)).

The site's Learn glossary ([`web/learn/glossary.md`](../../web/learn/glossary.md), served at `/glossary`) restates these terms in plain words for readers, with these meanings, and this file wins on any difference. It also explains the field's general terms that this corpus uses without defining them (soundness, zero knowledge, security level, trusted setup, prover, verifier, witness).

## Terms

<a id="adapter"></a>**Adapter.** The directory `systems/<name>/` and the OCI image built from it that wraps one upstream prover, unchanged, behind the five subcommands of the adapter contract. An adapter translates; it never patches upstream source. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="adapter-contract"></a>**Adapter contract.** The versioned interface (`adapter/1`) between the harness and an adapter: subcommands `info`, `setup`, `commit`, `prove`, `verify`, each reading `/io/job.json` and writing `/io/out.json`. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="amortisation-horizon"></a>**Amortisation horizon.** The number of requests of a workload's shape over which commit time is spread when reporting amortised commit cost. v0.1 reports two horizons: 1 request and 1,000 requests. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="attested"></a>**Attested.** A statement vouched for by hardware or a signing party (for example a trusted execution environment report). Never used for a cryptographic proof. Contrast [proved](#proved).

<a id="benchmark-release"></a>**Benchmark release.** A frozen, named set of runs, reference file, RFC versions and claim cards by digest, for example `v0.1`. Independent of harness package versions. [RFC-0009](../../rfcs/0009-results-and-publication.md), [09](09-release-and-versioning.md).

<a id="binding"></a>**Binding.** Whether a proof ties one edge of the computation (for example layer output to next layer input, or weights to commitment) to the statement. Each edge is `bound`, `unbound`, `absent` or `not_stated` on the claim card. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="bound"></a>**Bound.** Said of an edge of the computation that the verifier's acceptance constrains. A bound edge is part of what is proved.

<a id="check"></a>**Check.** One of the six tests of Level 1 the benchmark runs on a row: Run, Model, Prompt, Reply, No weight file, Fidelity. Each ends held, failed or undecided (with a cause: system limit, not run, not resolved, not reproduced). Passing all six is the entry gate to a position; they are not the glyph. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="claim-card"></a>**Claim card.** The machine-readable statement, per system configuration, of what an accepted proof establishes, under which assumptions, and what a dishonest prover can still do (`systems/<name>/claim.yaml`, or `systems/<name>/claims/<configuration>.yaml` when a system has several configurations; versioned by `card_version`). No number is published without one. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="claim-class"></a>**Claim class.** A short identifier for a family of relations that closed-division rows and targets filter on, for example greedy next-token exact match of a committed model. [RFC-0002](../../rfcs/0002-claim-card.md), [RFC-0003](../../rfcs/0003-workloads.md).

<a id="commitment"></a>**Commitment.** The value, produced by the `commit` step, that fixes the model weights a later proof refers to. The commitment the verifier checks against always comes from the harness's own record of the `commit` step, never from files shipped with a proof (AGENTS.md rule 6). [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="control"></a>**Control (negative control).** A deliberate tampering of a request, claimed output, commitment, proof or prover input, applied by the harness, whose expected outcome is rejection (or, for system-specific unbinding switches, a documented acceptance). Identified C1 to C8 (verifier side) and P1, P2 (prover side). [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="control-job"></a>**Control job.** A job run with `control: true`. Only control jobs may use a configuration that weakens a system's statement. A control job never produces a measured row.

<a id="control-outcome"></a>**Control outcome.** One of `rejected`, `accepted`, `no_verdict`, `invalid_call`, `void`, `not_applicable`, `prover_failed` (prover-side controls P1 and P2 only), `error`. A control passes when its outcome is in its expected set. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="corpus"></a>**Corpus (prompt corpus).** The fixed set of public-domain texts from which prompt sets are drawn, listed with source and digest in `workloads/prompts/corpus.yaml`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="criteria-file"></a>**Criteria file.** `web/_data/criteria.json` (schema `criteria/1`): the six [glyph properties](#glyph-property), the four [glyph states](#glyph-state) and one row per system, reference and public-source system, each cell with its state, our short reason and the quotes or sources read behind it. Checked under G2 by its schema. [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#criteria-file-contract).

<a id="derived-metric"></a>**Derived metric.** A number computed by the derivation code from stored raw numbers by a formula with a stable identifier (for example `D-RATE-S`). Never typed by hand. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="digest"></a>**Digest.** A SHA-256 value written `sha256:<64 lowercase hex>`. Model, proof, corpus, prompt-set and image digests have exact byte definitions in [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="division"></a>**Division.** The comparability class of a row: `native` (a system's own workload; side by side, never head to head), `closed` (a common workload and a fixed claim class; rows compare directly), `open` (anything declared; shown separately). v0.1 has native workloads and one closed workload, `l31-8b-c1024` on Llama 3.1 8B, whose rows publish once two systems with its claim class run it (RFC-0003 Q7). [RFC-0003](../../rfcs/0003-workloads.md).

<a id="error-kind"></a>**Error kind.** The category of a recorded failure: `config`, `environment`, `integrity`, `fetch`, `adapter`, `timeout`, `resource`, `policy`, `internal`. A verdict is a result, never an error. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="evidence-tier"></a>**Evidence tier.** Who stands behind a number. Every stored number is at tier `reported` (one runner, not yet checked); `peer-reviewed` and `reproduced` are reserved. [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md).

<a id="fake-system"></a>**Fake system.** `systems/fake/`, a CPU-only toy prover and verifier implementing the adapter contract, with a verifier that rejects every shared control. Its twin `systems/fake-broken/` accepts everything; CI asserts the control suite flags it. Used for end-to-end tests without a GPU. [RFC-0005](../../rfcs/0005-adapter-contract.md), [07](07-testing-strategy.md).

<a id="forbidden-flag"></a>**Forbidden flag.** A command-line option listed in `system.yaml` `forbidden_flags` because it weakens the system's statement (for example SASH's `--unsound-skip-*` family). Allowed only in control jobs; CI fails any measured run that used one. [RFC-0005](../../rfcs/0005-adapter-contract.md), [RFC-0013](../../rfcs/0013-validation-and-ci.md).

<a id="frontier"></a>**Frontier.** The largest rung, by total parameters, on which at least one row passed; the site's headline. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="glyph"></a>**Glyph.** The five-petal figure the site draws for a row we ran: how close the system is to a perfect prover, one [glyph property](#glyph-property) per petal, each in one [glyph state](#glyph-state). It never moves a position. From Level 1, [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph); before it, six documentation properties ([RFC-0016](../../rfcs/0016-glyph-properties-and-states.md)).

<a id="glyph-property"></a>**Glyph property.** One of five petals, in display order: Unforgeable (`unforgeable`), Weights hidden (`weights_hidden`), Faithful model (`faithful_model`), Any model (`any_model`), Only the verifier trusted (`no_trusted_party`). The first two and the last are read from the publisher's statements at the pin (`systems/<name>/properties.yaml`) and lowered by failed checks; Faithful model and Any model are measured. [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph).

<a id="glyph-state"></a>**Glyph state.** One petal's answer: green (the property holds in full), amber (in part), red (not at all, not stated, or broken by a failed check), hollow (a measured petal not yet decided). [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph).

<a id="grade"></a>**Grade.** How a number was obtained: `measured` (read by the harness from an artifact of this project's run), `derived` (computed by CI by a named formula), `projected` (from a named cost model), `external` (read from a public source at a pin), `asserted` (an input such as a price, with source and date). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="harness"></a>**Harness.** The Python package `iproofs` and its CLI: it resolves workloads, runs adapters in containers, measures from outside, applies controls, writes and validates run directories, freezes releases and builds the site. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="honest-twin"></a>**Honest twin.** The unmodified counterpart of a control, verified in the same control batch with the same image and profile. If the twin is not accepted the control is `void`, never counted as a rejection. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="job"></a>**Job.** One system, one workload, one shape, one repetition, on one machine. The unit the runner executes and records. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="level"></a>**Level.** A frozen definition of the benchmark: rungs, request, checks, order rule and constants, in `levels/L<k>.yaml`. A change of rule is a new level file. Releases under Level 1 are `v1.<n>`. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="machine-record"></a>**Machine record.** The hardware and software description of the host a job ran on, limited to the fields RFC-0006 lists. It excludes hostnames, network addresses, GPU UUIDs and serials, account names and instance identifiers. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="manifest"></a>**Manifest.** `manifest.json` in a run directory: image digest, upstream commit, workload and prompt digests, seed, machine record, command lines, provider, runner. Everything needed to rerun the job. [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="multiple"></a>**Multiple.** Steady GPU-seconds per further proved reply over the serving baseline's GPU-seconds per reply at full load, on one rung. The ranked figure of Level 1. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="native-workload"></a>**Native workload.** A workload a system supports at its pinned commit without change, used in the native division. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="null-reason"></a>**Null reason.** The required explanation when a quantity's value is null: `not_externally_observable`, `fewer_than_two_proofs`, `not_applicable`, `step_failed`, `not_measurable_on_profile`, `missing_input`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="overhead"></a>**Overhead.** The prover's GPU-seconds per token on its profile over [production serving](#production-serving)'s GPU-seconds per token on its own (vLLM, the publisher's release precision, every weight in GPU memory, the fewest GPUs of the same model that hold it), same workload version, steady scope, matched load (`D-OVERHEAD-S`); at high load as context (`D-OVERHEAD-HIGH-S`). A system with no steady scope (SASH) shows the warm figure instead: its proving session, its start-up included, over production serving's steady scope, the engine already running as a provider's is (`D-OVERHEAD-WARM`). One of the two figures that compare provers across models; the other is [prover time per bit of active weights](#prover-time-per-bit). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md), [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="passed"></a>**Passed.** Said of a system on a rung when all six checks are held. Never said of a model. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="production-serving"></a>**Production serving.** The model served unproved as providers serve it: the pinned vLLM release with its defaults, the publisher's release precision, every weight in GPU memory, tensor parallel over the fewest GPUs of the proving system's GPU model that hold it, at two load points (the workload's batch size, `matched`, and a high-load batch, `high`). The baseline of the [overhead](#overhead). [RFC-0015](../../rfcs/0015-reference-rows.md) SRV-6.

<a id="profile"></a>**Profile.** A named machine specification in `reference/<release>.yaml`. v0.1 defines the reference `prover-h200`, its hosted form `prover-h200-hosted`, `prover-h100`, `prover-h100-hosted`, `verifier-cpu`, and the serving profiles `serving-h200x1-hosted` and `serving-h200x4-hosted` (RFC-0006 R6). Every row names its profile; nothing is compared across profiles without the profile in the row. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="proof"></a>**Proof.** In this project, the set of files (parts) that one `verify` call checks for one request, released atomically as `/io/proofs/<proof_id>/`. For a segment-grid system it is the set of segment proofs for one sequence plus whatever the grid check needs. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="proof-part"></a>**Proof part.** One file inside a proof directory. Controls C5, C6 and C8 operate on the parts the adapter declares its verify step reads (`system.yaml` `proofs.verify_reads`); `controls.json` lists each part not read with its reason. [RFC-0008](../../rfcs/0008-negative-controls.md#parts-the-verifier-reads).

<a id="proved"></a>**Proved.** Said of a statement that a sound verifier's acceptance establishes under the claim card's stated assumptions. Never "provably safe". Contrast [attested](#attested), [sampled](#sampled).

<a id="prover-time-per-bit"></a>**Prover time per bit of active weights.** Prover seconds per token covered divided by the bits of weights one token uses, active parameters per token times [weight bits](#weight-bits) (`D-SPAB-S`, unit `s/bit_token`). Attention cost is not in the normaliser. Shown only with the claim cards. Proof size and check time have the same basis (`D-BPAB`, `B/bit_token`; `D-VSPAB`, `s/bit_token`); the site prints all three per token per Gbit of active weights (1e9 bits), in ms and kB. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="quantity"></a>**Quantity (labelled quantity).** The only form in which a number is stored: `{value, unit, scope, grade, tier, source, null_reason}`. A statistic adds `stats: {n, n_failed, mean, stdev, min, max}`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="reference-row"></a>**Reference row.** A row produced by a reference system on the same workload as a proving row, so a proving cost reads against something: [production serving](#production-serving) (`systems/ref-serve`) and naive recompute (`systems/ref-recompute`). [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="relation"></a>**Relation.** The claim card's one-sentence statement of what is true when the verifier accepts. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="release-time"></a>**Release time.** The monotonic timestamp at which the harness observed a proof directory become visible under `/io/proofs/` by atomic rename. Timing scopes for proving are defined on release times. [RFC-0011](../../rfcs/0011-measurement-and-sampling.md).

<a id="relying-party"></a>**Relying party.** Someone who would act on a proof: a policy analyst, auditor, lab, government or standards body. Relying parties publish targets; the project publishes none.

<a id="repetition"></a>**Repetition.** One of at least three jobs run for the same system, workload, shape and profile. Statistics are computed over successful repetitions; failed ones are counted in `n_failed`.

<a id="request"></a>**Request.** One prompt and the output tokens the verifier is given for it; `requests_count` counts them. Its shape is P prompt tokens, N output tokens checked and W tokens covered. The unit a reader compares: every per-request figure is printed with P and N. [RFC-0017](../../rfcs/0017-requests-tasks-and-tested-states.md).

<a id="residual"></a>**Residual.** The claim card's list of what a cheating prover can still do while passing verification. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="row"></a>**Row.** The published aggregate of the repetitions of one configuration (system, workload, shape, profile), with its claim card, labels, controls and reference rows.

<a id="run-directory"></a>**Run directory.** `results/<release>/<system>/<run-id>/`, the append-only record of one job: `run.json`, `manifest.json`, `controls.json`, `verifier/`, `logs/`, and `digests.txt`. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="rung"></a>**Rung.** One open-weights model of a level, with its serving baseline, its fidelity reference and the workloads run on it. Rows are ranked inside a rung, never across rungs. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="runner"></a>**Runner.** The person or organisation that executes jobs and signs off the run directory. The runner's declared affiliation may be recorded in the manifest.

<a id="sampled"></a>**Sampled.** Said of a guarantee obtained by checking a random subset of the computation (for example sampled recompute). A sampled guarantee is statistical, not cryptographic, and the claim card says so.

<a id="scope"></a>**Scope (timing scope).** The interval a time or rate covers: `setup`, `commit`, `prove.steady`, `prove.session`, `whole_wall`, `verify`, `verify.single_thread`, `primitive`. Every time-based number names exactly one. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="seed"></a>**Seed.** The 64-bit value from which a job's prompt offsets are drawn. Measured jobs draw a fresh seed from the operating system at job start and record it; `--prompts-from` replays a run's recorded seeds. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="session"></a>**Session.** One cold-start job of Level 1: setup, commit, then prove on the rung's N requests. Three complete sessions count, one per slot. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="shape"></a>**Shape.** The size parameters of a workload: `prompt_tokens`, `output_tokens`, `batch_size`, `batches_per_session`, `context_window`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="slot"></a>**Slot.** One of a rung's three session positions; slot k proves prompts (k-1)N to kN-1 of the rung's prompt set, and a failed session is rerun in the same slot. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="system"></a>**System.** A prover (or a reference engine) measured by the benchmark, identified by a name matching `^[a-z][a-z0-9-]{1,31}$`, for example `sash`, `flashprove`, `ref-serve`.

<a id="target"></a>**Target.** A threshold on a named metric for a claim class, published by a relying party under their own name in `targets/<author>/<id>.yaml`. Rows show `meets`, `does_not_meet` or `not_evaluable` per target. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="task"></a>**Task.** A request shape with a decoding rule, named `p<P>-o<N>`. Rows of one task may share a table and a sort for their per-request figures; rows of different tasks never do. [RFC-0017](../../rfcs/0017-requests-tasks-and-tested-states.md).

<a id="tokens-covered"></a>**Tokens covered.** The positions whose computation a proof binds, as declared by the claim card and the adapter and checked against the workload: for a prefill proof stating the next token, the window's positions; for a segment grid, the positions in the grid. The denominator of every per-token metric. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="unbound"></a>**Unbound.** Said of an edge of the computation that the verifier's acceptance does not constrain, either by design or because a switch disabled its check.

<a id="verdict"></a>**Verdict.** The adapter's normalisation of one `verify` call: `accept`, `reject`, `no_verdict`, `invalid_call`, always stored with the upstream verifier's raw exit code and last line. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="weight-bits"></a>**Weight bits.** The bits that store one weight of a workload's precision as proved, one number in the workload record with its source: computed from the pinned files when they hold the precision as proved (the mean storage bits per active weight from their tensor tables, block scales included, or file size when they hold every weight at one width), else as the precision's own documentation states it, with whether the statement covers all or part of the active weights. [RFC-0003](../../rfcs/0003-workloads.md#weight-bits).

<a id="workload"></a>**Workload.** A versioned definition (`workloads/<id>.yaml`) of a model by content digest, a precision, a prompt generator over the corpus, a shape, a decoding rule, a phase and a division. [RFC-0003](../../rfcs/0003-workloads.md).

## Neutral language

The project describes what was measured. Prose MUST NOT use "fastest", "best", "winner", "beats" or "provably safe" about a system, and MUST use proved, bound, attested and sampled with the meanings above. The lint word list is normative in [RFC-0013](../../rfcs/0013-validation-and-ci.md).
