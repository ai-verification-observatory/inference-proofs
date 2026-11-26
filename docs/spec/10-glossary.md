# 10. Glossary

This file is the canonical vocabulary for the entire specification corpus. Every other document uses these terms with the meanings defined here rather than introducing local definitions; any new term is added here in the same pull request that first introduces it. Entries are sorted alphabetically. Enumerated values (scopes, grades, tiers, verdicts, outcomes, and error kinds) are normative in the RFC cited for each entry; they are summarized here for convenience, and the RFC takes precedence if any discrepancy arises.

Because this document quotes the language rule and its banned words, it is explicitly allowlisted by the language lint ([RFC-0013](../../rfcs/0013-validation-and-ci.md)).

The website's Learn glossary ([`web/learn/glossary.md`](../../web/learn/glossary.md), served at `/glossary`) explains these same terms in accessible language for site visitors, while this file remains authoritative on any nuance. The web glossary also introduces general cryptographic and ML terms used across the corpus without local redefinition (such as soundness, zero knowledge, security level, trusted setup, prover, verifier, and witness).

## Terms

<a id="adapter"></a>**Adapter.** The directory `systems/<name>/` and its built OCI container image wrapping an upstream prover at a public pin behind the five subcommands of the adapter contract. Adapters translate inputs and outputs without patching upstream source code. A pin may reference a pull request against the publisher's repository; Level 1's SASH pin points to an unmerged pull request written by this project's owner (RFC-0018 SI-3). [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="adapter-contract"></a>**Adapter contract.** The versioned interface (`adapter/1`) between the harness and every adapter, consisting of five subcommands (`info`, `setup`, `commit`, `prove`, and `verify`) that each read `/io/job.json` and write `/io/out.json`. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="amortisation-horizon"></a>**Amortisation horizon.** The number of workload requests over which model commitment time is spread when calculating amortised commit cost. v0.1 reports horizons of 1 request and 1,000 requests. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="attested"></a>**Attested.** Describes a statement backed by hardware attestation or a trusted signing party (such as a trusted execution environment report). Never applied to a cryptographic proof; contrast [proved](#proved).

<a id="benchmark-release"></a>**Benchmark release.** A frozen, named snapshot of runs, a reference hardware file, RFC versions, and claim cards pinned by digest (for example, `v0.1`), versioned separately from harness package releases. [RFC-0009](../../rfcs/0009-results-and-publication.md), [09](09-release-and-versioning.md).

<a id="binding"></a>**Binding.** Whether a proof cryptographically links a specific edge of the computation (such as one layer's output to the next layer's input, or weights to a commitment) to the proved statement. Each edge is recorded as `bound`, `unbound`, `absent`, or `not_stated` on the claim card. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="bound"></a>**Bound.** Describes an edge of the computation constrained by verifier acceptance, meaning it is part of what the proof establishes.

<a id="check"></a>**Check.** One of the six Level 1 verification tests executed by the benchmark on each row: Run, Model, Prompt, Reply, Verify without weights, and Fidelity. Each check finishes as passed, failed, or not decided (stored as `held`, `failed`, or `undecided`; an undecided check records its cause: system limit, not run, not resolved, or not reproduced). Passing all six checks is required for a ranked position; checks are distinct from the five-petal glyph. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="claim-card"></a>**Claim card.** A machine-readable statement for a specific system configuration documenting what an accepted proof establishes, under what assumptions, and what a dishonest prover can still do (`systems/<name>/claim.yaml`, or `systems/<name>/claims/<configuration>.yaml` when a system has multiple configurations, versioned by `card_version`). No measurement is published without one. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="claim-class"></a>**Claim class.** A short identifier naming a family of proved relations used to group closed-division rows and relying-party targets, such as greedy next-token exact match against a committed model. [RFC-0002](../../rfcs/0002-claim-card.md), [RFC-0003](../../rfcs/0003-workloads.md).

<a id="completeness"></a>**Completeness.** The property that a verifier accepts an honest prover's proof of a true statement, except with a stated error probability. Of the three core cryptographic properties (soundness, zero knowledge, and completeness), completeness is the only one directly observable through testing; system pages display it as "tested by us on honest runs (N of N)", where N is the count of replies across counted sessions whose proofs were accepted. [RFC-0018](../../rfcs/0018-level-1-ladder.md#formally-verified-machine_checked) MC-6.

<a id="commitment"></a>**Commitment.** The value generated by the `commit` step that binds subsequent proofs to a specific set of model weights. The commitment passed to `verify` always comes from the harness's own record of `commit`, never from files bundled with a proof (AGENTS.md rule 6). [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="control"></a>**Control (negative control).** An intentional, harness-applied tampering of a request, claimed output, commitment, proof, or prover input whose expected outcome is rejection (or documented acceptance for system-specific soundness switches). Verifier-side controls are numbered C1 through C8, and prover-side controls are P1 and P2. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="control-job"></a>**Control job.** A job executed with `control: true`, or a verifier-side control check that the harness records as a control while passing `control: false` to the verifier ([RFC-0008](../../rfcs/0008-negative-controls.md) INV-CTRL-9). Weakening flags are allowed only inside control jobs, and control jobs never produce measured rows.

<a id="control-outcome"></a>**Control outcome.** One of `rejected`, `accepted`, `no_verdict`, `invalid_call`, `void`, `not_applicable`, `prover_failed` (prover-side controls P1 and P2 only), or `error`. A control passes when its outcome falls inside its expected set. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="corpus"></a>**Corpus (prompt corpus).** The fixed collection of public-domain texts from which prompt sets are sampled, pinned by source URL and digest in `workloads/prompts/corpus.yaml`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="criteria-file"></a>**Criteria file.** `web/_data/criteria.json`, the v0.1 glyph data file (schema `criteria/1`, removed on 2026-11-15 and preserved in git history at `b9dfa3e`). It stored the six [glyph properties](#glyph-property), four [glyph states](#glyph-state), and one row per measured, reference, and public-source system, recording each cell's state, rationale, and source citations, validated under Gate G2. [RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#criteria-file-contract).

<a id="criterion"></a>**Criterion.** A [glyph property](#glyph-property) as a system's page grades it: one row of its Criteria section, with its name, plain question, grade word, the first item missing for Met and its [track](#track) (titled Glyph until 2026-11-22; not the v0.1 [criteria file](#criteria-file)). [RFC-0018](../../rfcs/0018-level-1-ladder.md) SI-3, Q53.

<a id="derived-metric"></a>**Derived metric.** A metric computed deterministically by `iproofs.derive` from stored raw measurements using a named formula (such as `D-RATE-S`). Derived metrics are never typed manually. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="digest"></a>**Digest.** A SHA-256 hash formatted as `sha256:<64 lowercase hex>`. Exact byte constructions for model, proof, corpus, prompt-set, and container image digests are defined in [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="division"></a>**Division.** The comparability grouping of a row: `native` (a system's own supported workload, shown side by side rather than head to head), `closed` (a shared workload and fixed claim class where rows compare directly), or `open` (any declared setup, shown separately). v0.1 includes native workloads plus one closed workload, `l31-8b-c1024` on Llama 3.1 8B, which publishes once two systems in its claim class run it (RFC-0003 Q7). [RFC-0003](../../rfcs/0003-workloads.md).

<a id="error-kind"></a>**Error kind.** The closed category assigned to a recorded job failure: `config`, `environment`, `integrity`, `fetch`, `adapter`, `timeout`, `resource`, `policy`, or `internal`. A verification verdict is a normal result, never an error. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="evidence-tier"></a>**Evidence tier.** Indicates the level of verification behind a number. All currently stored measurements carry tier `reported` (executed by one runner and not yet externally reproduced); `peer-reviewed` and `reproduced` are reserved for future use. [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md).

<a id="fake-system"></a>**Fake system.** `systems/fake/`, a CPU-only toy prover and verifier implementing the adapter contract whose verifier rejects every shared negative control. Its counterpart `systems/fake-broken/` accepts everything so CI can confirm the control suite flags broken verifiers. Used for GPU-free end-to-end tests. [RFC-0005](../../rfcs/0005-adapter-contract.md), [07](07-testing-strategy.md).

<a id="fidelity-petal"></a>**Fidelity petal.** The glyph petal `faithful_model` (labelled "Faithful model" until 2026-11-15, "Close to the original" on 2026-11-15, and "Fidelity" since 2026-11-16). It grades how closely a row's proved replies match the model publisher's release based on FI-3's matched leading tokens against the midpoints of the rung's rerun, Q8_0, and Q4_K_M controls. It is distinct from the Fidelity figure (FI-10's teacher-forced top-token agreement), which sets no petal state, and from the Fidelity check, whose result it consumes. [RFC-0018](../../rfcs/0018-level-1-ladder.md#fidelity-faithful_model).

<a id="forbidden-flag"></a>**Forbidden flag.** Any CLI option declared in `system.yaml` under `forbidden_flags` because it weakens the system's cryptographic statement (such as SASH's `--unsound-skip-*` options). Permitted exclusively in control jobs; CI rejects any measured run whose command log includes one. [RFC-0005](../../rfcs/0005-adapter-contract.md), [RFC-0013](../../rfcs/0013-validation-and-ci.md).

<a id="frontier"></a>**Frontier.** The largest rung (by total parameter count) on which at least one system has passed all checks. The board file records it; the ladder runs largest model first and no longer badges it (2026-11-23, RFC-0018 Q54). [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="glyph"></a>**Glyph.** The five-petal visual summary rendered on the site for each benchmarked row, showing how close the system comes to an ideal prover with one [glyph property](#glyph-property) per petal and one [glyph state](#glyph-state) each. Petals are never aggregated into a numeric score and never affect ranking positions. From Level 1 onward, glyphs follow [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph); earlier releases used six documentation-based properties ([RFC-0016](../../rfcs/0016-glyph-properties-and-states.md)).

<a id="glyph-property"></a>**Glyph property.** One of five petals, in drawing order: Integrity (`unforgeable`), Confidentiality (`weights_hidden`), Fidelity (`faithful_model`), Formally verified (`machine_checked`), and Trust assumptions (`no_trusted_party`), using these display labels since 2026-11-16 (RFC-0018 Q37). The four statement petals are computed by `iproofs.glyph` from quoted facts transcribed from the publisher's documentation at the pinned commit (`systems/<name>/properties.yaml`, schema `properties/2`) and downgraded if any check listed in RFC-0018 GL-2 fails. Fidelity is measured empirically by our fidelity run using matched leading tokens rather than the teacher-forced Fidelity figure. [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph).

<a id="glyph-state"></a>**Glyph state.** The outcome assigned to a single petal, stored as a named step (never a number) and displayed in plain terms since 2026-11-16 (RFC-0018 Q37): Met (`green`), Mostly met (`amber_upper`), Partly met (`amber_lower`), Not met / Failed / Not stated (`red`, distinguished by cause), or Not decided (null, rendered hollow). Colour names control rendering only and are never printed as text. A red petal records its cause: `stated` (Not met: explicitly stated not to hold, or stated facts fall short of Partly met), `check_failed` (Failed: our check or recorded proof build failed), or `not_stated` (Not stated: upstream documentation is silent, drawn as a red outline). A hollow petal also states its cause: documentation not yet reviewed, Fidelity check undecided or unrecorded, or awaiting a completed build of the publisher's machine-checked proof. When a petal relies on a fact carrying an interpretive `note` ([read as](#read-as)), the UI flags that the state rests on our reading rather than an explicit sentence and caps the grade at Mostly met (RFC-0018 GL-10). Every petal also displays its next step: what is needed to reach the next tier and who needs to act (GL-11). States follow each property's decision table, taking the first matching rule. [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph).

<a id="grade"></a>**Grade.** Indicates how a number was produced: `measured` (observed by the harness during a benchmark run), `derived` (recomputed in CI via a named formula), `projected` (estimated by a named cost model), `external` (transcribed from a pinned public source), or `asserted` (an external input such as reference GPU pricing, accompanied by source and date). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="harness"></a>**Harness.** The `iproofs` Python package and CLI that resolves workloads, drives containerised adapters, records external measurements, runs negative controls, writes and validates run directories, freezes releases, and builds the static website. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="honest-twin"></a>**Honest twin.** The unmodified control counterpart verified alongside a mutated control in the same batch using the same image and profile. If the verifier does not accept the honest twin, the control is marked `void` and never counted as a valid rejection. [RFC-0008](../../rfcs/0008-negative-controls.md).

<a id="job"></a>**Job.** A single execution of one system on one workload, shape, and repetition on one machine; the atomic unit executed and recorded by the runner. [RFC-0010](../../rfcs/0010-harness-runner.md).

<a id="level"></a>**Level.** A frozen benchmark specification defining rungs, the fixed request, verification checks, ranking order rule, and constants in `levels/L<k>.yaml`. Changing any rule creates a new level file. Releases under Level 1 are numbered `v1.<n>`. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="machine-record"></a>**Machine record.** The hardware and software profile of the host that executed a job, restricted to the allowlisted fields in RFC-0006. It omits hostnames, network addresses, GPU UUIDs and serial numbers, account names, and cloud instance IDs. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="manifest"></a>**Manifest.** The `manifest.json` file stored inside every run directory, capturing the image digest, upstream commit, workload and prompt digests, seed, machine record, command lines, provider, and runner metadata needed to reproduce the job. [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

<a id="multiple"></a>**Multiple.** Steady-state GPU-seconds per additional proved reply divided by the serving baseline's GPU-seconds per reply at full load on the same rung. This is the single ranked metric of Level 1. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="native-workload"></a>**Native workload.** A workload supported by a system at its pinned commit without modification, used in the `native` division. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="null-reason"></a>**Null reason.** The mandatory explanation accompanying any quantity whose value is null: `not_externally_observable`, `fewer_than_two_proofs`, `not_applicable`, `step_failed`, `not_measurable_on_profile`, `missing_input`, or `setup_reused`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="overhead"></a>**Overhead.** The ratio of a prover's GPU-seconds per token on its hardware profile to [production serving](#production-serving)'s GPU-seconds per token on its own profile (vLLM running the publisher's release precision with all weights in GPU memory across the fewest GPUs of the same model that fit), measured on the same workload version in steady scope at matched load (`D-OVERHEAD-S`), with high load reported for context (`D-OVERHEAD-HIGH-S`). Systems without an observable steady scope (such as SASH) instead report the warm overhead: the prover's full proving session (including start-up) divided by production serving's steady scope with the engine already warm (`D-OVERHEAD-WARM`). Overhead is one of two metrics that compare provers across different models, alongside [prover time per bit of active weights](#prover-time-per-bit). [RFC-0004](../../rfcs/0004-metrics-timing-grades.md), [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="passed"></a>**Passed.** Describes a system row on a rung when all six Level 1 checks pass (stored as `held`). A row with zero failures and at least one undecided check is labelled "not passed yet". "Passed" applies only to system rows, never to a model. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="production-serving"></a>**Production serving.** Unproved inference served the way production providers run it: the pinned vLLM release with default settings, the publisher's release precision, all weights resident in GPU memory, and tensor parallelism across the fewest GPUs of the prover's GPU model that hold the weights, measured at two load points (`matched`, matching the workload batch size, and `high`, a high-load batch). Serves as the denominator for [overhead](#overhead). [RFC-0015](../../rfcs/0015-reference-rows.md) SRV-6.

<a id="profile"></a>**Profile.** A named machine specification defined in `reference/<release>.yaml`. v0.1 declares `prover-h200`, `prover-h200-hosted`, `prover-h100`, `prover-h100-hosted`, `verifier-cpu`, and the serving profiles `serving-h200x1-hosted` and `serving-h200x4-hosted` (RFC-0006 R6). Every row names its profile, and rows on different profiles are never compared without displaying their profiles. [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md).

<a id="proof"></a>**Proof.** The collection of files (parts) verified together by one `verify` call for one request, released atomically under `/io/proofs/<proof_id>/`. In segment-grid provers, one proof encompasses all segment proofs for a sequence along with any auxiliary grid-check files. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="proof-part"></a>**Proof part.** An individual file inside a proof directory. Controls C5, C6, and C8 mutate only parts that the adapter declares its verifier reads (`system.yaml` `proofs.verify_reads`), and `controls.json` lists every unread part along with the reason. [RFC-0008](../../rfcs/0008-negative-controls.md#parts-the-verifier-reads).

<a id="proved"></a>**Proved.** Describes a statement established by a sound verifier's acceptance under the assumptions listed on its claim card. Never phrased as "provably safe"; contrast [attested](#attested) and [sampled](#sampled).

<a id="prover-time-per-bit"></a>**Prover time per bit of active weights.** Prover seconds per covered token divided by the active weight bits read per token (active parameters per token multiplied by [weight bits](#weight-bits); `D-SPAB-S`, unit `s/bit_token`). Attention computation is not included in this normaliser, and the metric is displayed only alongside claim cards. Proof size and verification time have analogous normalised forms (`D-BPAB` in `B/bit_token` and `D-VSPAB` in `s/bit_token`); on the site, all three are shown per token per Gbit (1e9 bits) of active weights in ms and kB. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="quantity"></a>**Quantity (labelled quantity).** The sole schema representation for stored measurements: `{value, unit, scope, grade, tier, source, null_reason}`. Aggregated statistics extend this with `stats: {n, n_failed, mean, stdev, min, max}`. [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

<a id="read-as"></a>**Read as.** Indicates a glyph petal whose evaluation depended on a fact carrying a `note` (`reading: true`), meaning the state relies on our interpretation of the publisher's documentation rather than a direct statement. The UI displays the underlying quotes and caps the petal at Mostly met across all rows; the name of a cryptographic construction is never treated as an explicit claim. [RFC-0018](../../rfcs/0018-level-1-ladder.md#the-glyph) GL-10, AGENTS.md rule 9.

<a id="reference-row"></a>**Reference row.** A baseline measurement produced by a reference system on the same workload as a prover row to contextualize proving cost: [production serving](#production-serving) (`systems/ref-serve`) and naive recompute (`systems/ref-recompute`). [RFC-0015](../../rfcs/0015-reference-rows.md).

<a id="relation"></a>**Relation.** The one-sentence statement on a claim card describing what is guaranteed to hold whenever the verifier accepts a proof. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="release-time"></a>**Release time.** The monotonic timestamp recorded when the harness detects a proof directory appearing under `/io/proofs/` via atomic rename. Proving timing scopes are computed from release times. [RFC-0011](../../rfcs/0011-measurement-and-sampling.md).

<a id="relying-party"></a>**Relying party.** Anyone who depends on a proof to make decisions, such as a policy analyst, auditor, AI lab, government agency, or standards body. Relying parties publish targets under their own names; the benchmark itself does not set targets.

<a id="repetition"></a>**Repetition.** One of at least three executions of the same system, workload, shape, and profile. Summary statistics aggregate successful repetitions while failed ones are counted in `n_failed`.

<a id="request"></a>**Request.** One prompt paired with the output tokens submitted to the verifier, counted by `requests_count`. Its shape is defined by P prompt tokens, N checked output tokens, and W covered tokens. Every per-request metric is displayed alongside P and N so readers can compare requests directly. [RFC-0017](../../rfcs/0017-requests-tasks-and-tested-states.md).

<a id="residual"></a>**Residual.** The list on a claim card describing what a dishonest prover can still do while passing verification. [RFC-0002](../../rfcs/0002-claim-card.md).

<a id="row"></a>**Row.** The published summary aggregating all repetitions of a single configuration (system, workload, shape, and profile), together with its claim card, labels, control outcomes, and reference rows.

<a id="run-directory"></a>**Run directory.** `results/<release>/<system>/<run-id>/`, the append-only directory recording one job: `run.json`, `manifest.json`, `controls.json`, `verifier/`, `logs/`, and `digests.txt`. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="rung"></a>**Rung.** One open-weights model in a level, paired with its serving baseline, fidelity reference, and workloads. Passed systems are ranked only within a rung, never across rungs. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="runner"></a>**Runner.** The individual or organisation executing benchmark jobs and submitting run directories. Runners may declare their affiliation in the manifest.

<a id="sampled"></a>**Sampled.** Describes a guarantee obtained by checking a random subset of computation (such as sampled recomputation). Sampled guarantees are statistical rather than cryptographic, and claim cards state this explicitly.

<a id="scope"></a>**Scope (timing scope).** The time interval covered by a duration or throughput metric: `setup`, `commit`, `prove.steady`, `prove.session`, `whole_wall`, `verify`, `verify.single_thread`, or `primitive`. Every time-based quantity specifies exactly one scope. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="scope-card"></a>**Scope card.** The table of facts displayed under the five criteria on a system's page, one click down, showing whether the publisher states soundness, zero knowledge, and completeness as machine-checked, proved on paper, tested, or not stated across three targets: the protocol, the verifier code we run, and the prover code we run, with supporting quotes. It provides context and does not set a petal state on its own. [RFC-0018](../../rfcs/0018-level-1-ladder.md#formally-verified-machine_checked).

<a id="seed"></a>**Seed.** The 64-bit integer used to sample prompt offsets from the corpus. Measured jobs draw a fresh seed from the OS at startup and record it in the manifest; `--prompts-from` replays a previous run's recorded seeds. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="soundness-error"></a>**Soundness error.** The publisher-stated probability that a verifier accepts a proof of a false statement for a specified verifier and proof unit, often parameterized by the adversary's hash queries `q` (for example, FlashProve's `q/2^124 + 2^-101` for its Lean verifier). The Integrity petal (subtitled "soundness") grades this bound, noting any conditions that limit its coverage of our run before citing the bound itself. No equivalent bit-security figure is derived from it (RFC-0018 Q9). [RFC-0018](../../rfcs/0018-level-1-ladder.md#integrity-unforgeable).

<a id="session"></a>**Session.** One cold-start Level 1 job executing `setup`, `commit`, and `prove` over the rung's N requests. Three completed sessions (one per slot) count toward the board. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="shape"></a>**Shape.** The workload dimensions: `prompt_tokens`, `output_tokens`, `batch_size`, `batches_per_session`, and `context_window`. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="slot"></a>**Slot.** One of a rung's three session positions. Slot `k` proves prompts `(k-1)N` through `kN-1` of the rung's prompt set, and any failed session is rerun in the same slot. [RFC-0018](../../rfcs/0018-level-1-ladder.md).

<a id="system"></a>**System.** A prover or reference engine evaluated by the benchmark, named with an identifier matching `^[a-z][a-z0-9-]{1,31}$` (for example, `sash`, `flashprove`, or `ref-serve`).

<a id="target"></a>**Target.** A threshold on a named metric within a claim class, authored by a relying party in `targets/<author>/<id>.yaml`. Each row is evaluated as `meets`, `does_not_meet`, or `not_evaluable` against every target. [RFC-0009](../../rfcs/0009-results-and-publication.md).

<a id="task"></a>**Task.** A combination of request shape and decoding rule, named `p<P>-o<N>`. Rows sharing a task may appear in the same table and be sorted by per-request figures; rows from different tasks never share a table. [RFC-0017](../../rfcs/0017-requests-tasks-and-tested-states.md).

<a id="teacher-forced-agreement"></a>**Teacher-forced agreement.** A non-gating fidelity metric displayed beside the matched-prefix check (shown on the site as a percentage mean labelled "Fidelity", SI-9). An engine is fed the prompt followed by the reference reply, and its score for that prompt is how many of the 512 reply positions match the reference token as its top prediction (unit `agreeing positions`), always conditioning on reference tokens rather than its own outputs. For prover rows, this figure is "computed by the system's own code on the reference reply, not by the proved computation"; the board distinguishes positions covered by a proof on that text from positions produced solely by the system's code (FI-16). [RFC-0018 FI-10 to FI-15](../../rfcs/0018-level-1-ladder.md#teacher-forced-agreement-and-kl-amended-2026-11-13-fi-10-to-fi-15).

<a id="tokens-covered"></a>**Tokens covered.** The number of token positions whose computation a proof binds, declared by the claim card and adapter and verified against the workload (for example, the window size for a next-token prefill proof, or all positions in a segment grid). Used as the denominator for all per-token metrics. [RFC-0004](../../rfcs/0004-metrics-timing-grades.md).

<a id="track"></a>**Track.** The three grades Partly met, Mostly met and Met drawn as cells on a [criterion](#criterion)'s row, lowest first: the grades it holds solid in its ink, each other one holding one open square per item `to_met` lists for it; opened, each square becomes its numbered item in words. [RFC-0018](../../rfcs/0018-level-1-ladder.md) SI-3, GL-11, Q53.

<a id="unbound"></a>**Unbound.** Describes an edge of the computation not constrained by verifier acceptance, whether by design or because a weakening switch turned off its check.

<a id="verdict"></a>**Verdict.** The normalised outcome of a single `verify` call (`accept`, `reject`, `no_verdict`, or `invalid_call`), always recorded alongside the upstream verifier's raw exit code and final output line. [RFC-0005](../../rfcs/0005-adapter-contract.md).

<a id="weight-bits"></a>**Weight bits.** The average number of bits storing one weight in the workload's proved precision, recorded in the workload definition with its source. When the pinned files store the proved precision directly, this is computed from their tensor tables (mean storage bits per active weight including block scales, or derived from file size when all weights share a single width); otherwise it is taken from the precision's documentation, noting whether the figure covers all or part of the active weights. [RFC-0003](../../rfcs/0003-workloads.md#weight-bits).

<a id="workload"></a>**Workload.** A versioned YAML definition (`workloads/<id>.yaml`) fixing a model by content digest, precision, prompt generator over the corpus, shape, decoding rule, phase, and division. [RFC-0003](../../rfcs/0003-workloads.md).

<a id="zero-knowledge"></a>**Zero knowledge.** The property that a verifier's view can be simulated without access to the witness (here, the model weights). Because the exact definition matters, the site reports it precisely as stated by the publisher: honest-verifier versus arbitrary verifier, perfect/statistical/computational, random-oracle versus standard model, and per request versus per batch. The Confidentiality petal reports this form, compares what one proof covers against the row's batch size, and states whether the programs we actually run are covered. [RFC-0018](../../rfcs/0018-level-1-ladder.md#confidentiality-weights_hidden).

## Neutral language

Benchmark documentation reports what was measured and avoids promotional claims. Prose MUST NOT describe any system as "fastest", "best", "winner", "beats", or "provably safe", and MUST use proved, bound, attested, and sampled with the exact definitions above. The normative banned-word lint list is defined in [RFC-0013](../../rfcs/0013-validation-and-ci.md).
