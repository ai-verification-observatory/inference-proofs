# Implementation tracker, 2026-11-03

Generated from the specification corpus in [pull request #1](https://github.com/ai-verification-observatory/inference-proofs/pull/1). Every implementable unit of work in [docs/SPEC.md](../SPEC.md), `docs/spec/` and `rfcs/` is filed below as one issue. Each issue is independently shippable as one pull request; cross-issue dependencies are listed in each issue body and summarised at the end of this file.

The research phase dropped several of these issues ([rfcs/README.md](../../rfcs/README.md#out-for-the-research-phase)). Status reflects the issue state when this file was generated; the issues are the live record.

## Milestone: v0.1-alpha

CPU-only foundations: schemas, serialization, derivation, validation, CI gates, fake systems, runner against the fake system, governance files.

| # | Title | Area | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|---|
| [#20](https://github.com/ai-verification-observatory/inference-proofs/issues/20) | governance: add MAINTAINERS, CONTRIBUTING, CODE_OF_CONDUCT and licence files | governance | p0 | m | RFC-0001 | open |
| [#21](https://github.com/ai-verification-observatory/inference-proofs/issues/21) | security: add SECURITY.md with reporting channel and control embargo rule | security | p0 | s | RFC-0001, RFC-0008 | open |
| [#24](https://github.com/ai-verification-observatory/inference-proofs/issues/24) | governance: run Last call for RFC-0001 to RFC-0015 and record outcomes | governance | p0 | s | RFC-0001 | open |
| [#30](https://github.com/ai-verification-observatory/inference-proofs/issues/30) | harness: scaffold the iproofs package with uv, hatchling, ruff, mypy and pytest | harness | p0 | s | RFC-0010, RFC-0012 | open |
| [#31](https://github.com/ai-verification-observatory/inference-proofs/issues/31) | schema: implement the canonical JSON writer and the YAML subset loader | schema | p0 | s | RFC-0012 | open |
| [#32](https://github.com/ai-verification-observatory/inference-proofs/issues/32) | schema: implement model, proof, corpus and prompt-set digest functions | schema | p0 | s | RFC-0012, RFC-0014 | open |
| [#33](https://github.com/ai-verification-observatory/inference-proofs/issues/33) | schema: implement the schema registry, schema-field dispatch and validation | schema | p0 | m | RFC-0012 | open |
| [#34](https://github.com/ai-verification-observatory/inference-proofs/issues/34) | schema: publish quantity/1 with vocabularies, identifiers and shared defs | schema | p0 | m | RFC-0012, RFC-0004 | open |
| [#35](https://github.com/ai-verification-observatory/inference-proofs/issues/35) | schema: implement frozen dataclass models and the schema drift test | schema | p0 | m | RFC-0012 | open |
| [#36](https://github.com/ai-verification-observatory/inference-proofs/issues/36) | schema: publish run/1 and manifest/1 schemas with examples | schema | p0 | m | RFC-0012, RFC-0004, RFC-0014 | open |
| [#37](https://github.com/ai-verification-observatory/inference-proofs/issues/37) | schema: publish release/1, release-index/1 and target/1 schemas | schema | p0 | s | RFC-0012, RFC-0009 | open |
| [#38](https://github.com/ai-verification-observatory/inference-proofs/issues/38) | schema: publish claim/1 schema with valid and invalid examples | schema | p0 | m | RFC-0002, RFC-0012 | open |
| [#39](https://github.com/ai-verification-observatory/inference-proofs/issues/39) | schema: implement claim card checks for sources, pins and forbidden flags | schema | p0 | m | RFC-0002 | open |
| [#43](https://github.com/ai-verification-observatory/inference-proofs/issues/43) | schema: publish workload/1 and corpus/1 schemas with examples | schema | p0 | m | RFC-0003, RFC-0012 | open |
| [#44](https://github.com/ai-verification-observatory/inference-proofs/issues/44) | workloads: implement the workload loader and its invariant checks | workloads | p0 | s | RFC-0003 | open |
| [#45](https://github.com/ai-verification-observatory/inference-proofs/issues/45) | workloads: implement the corpus-window/1 prompt generator | workloads | p0 | m | RFC-0003 | open |
| [#46](https://github.com/ai-verification-observatory/inference-proofs/issues/46) | harness: draw, record and replay per-job prompt seeds | harness | p0 | s | RFC-0003, RFC-0007 | open |
| [#50](https://github.com/ai-verification-observatory/inference-proofs/issues/50) | harness: compute timing scope seconds from recorded events | harness | p0 | m | RFC-0004 | open |
| [#51](https://github.com/ai-verification-observatory/inference-proofs/issues/51) | harness: count tokens covered per coverage kind and cross-check the adapter | harness | p0 | s | RFC-0004, RFC-0003 | open |
| [#52](https://github.com/ai-verification-observatory/inference-proofs/issues/52) | harness: implement repetition-level derived metrics with hand-computed tests | harness | p0 | m | RFC-0004 | open |
| [#53](https://github.com/ai-verification-observatory/inference-proofs/issues/53) | harness: implement D-STAT repetition statistics with failed counts | harness | p0 | s | RFC-0004 | open |
| [#54](https://github.com/ai-verification-observatory/inference-proofs/issues/54) | harness: implement iproofs derive --check with bit-exact comparison | harness | p0 | s | RFC-0004, RFC-0013 | open |
| [#57](https://github.com/ai-verification-observatory/inference-proofs/issues/57) | schema: publish adapter-job/1 and adapter-out/1 schemas with examples | schema | p0 | m | RFC-0005, RFC-0012 | open |
| [#58](https://github.com/ai-verification-observatory/inference-proofs/issues/58) | schema: publish system/1 and system-controls/1 schemas | schema | p0 | s | RFC-0005, RFC-0008, RFC-0015 | open |
| [#59](https://github.com/ai-verification-observatory/inference-proofs/issues/59) | security: validate adapter output paths, proof directories and size limits | security | p0 | s | RFC-0005 | open |
| [#60](https://github.com/ai-verification-observatory/inference-proofs/issues/60) | adapters: implement the fake CPU-only system with a keyed-hash verifier | adapters | p0 | m | RFC-0005, RFC-0008 | open |
| [#61](https://github.com/ai-verification-observatory/inference-proofs/issues/61) | adapters: implement fake-broken, a verifier that accepts every proof | adapters | p0 | s | RFC-0005, RFC-0008 | open |
| [#72](https://github.com/ai-verification-observatory/inference-proofs/issues/72) | reference: publish reference/1 schema and reference/v0.1.yaml | reference | p0 | s | RFC-0006, RFC-0012 | open |
| [#81](https://github.com/ai-verification-observatory/inference-proofs/issues/81) | results: implement iproofs reproduce compare with the tolerance rule | results | p0 | m | RFC-0007 | open |
| [#82](https://github.com/ai-verification-observatory/inference-proofs/issues/82) | results: compute effective tiers at release freeze | results | p0 | m | RFC-0007 | open |
| [#86](https://github.com/ai-verification-observatory/inference-proofs/issues/86) | controls: implement the seeded generator and proof selection | controls | p0 | s | RFC-0008 | open |
| [#87](https://github.com/ai-verification-observatory/inference-proofs/issues/87) | controls: implement shared verifier-side controls C1 to C8 | controls | p0 | m | RFC-0008 | open |
| [#88](https://github.com/ai-verification-observatory/inference-proofs/issues/88) | controls: implement honest twins, outcome classification and controls.json | controls | p0 | m | RFC-0008, RFC-0012 | open |
| [#89](https://github.com/ai-verification-observatory/inference-proofs/issues/89) | harness: wire the control suite into iproofs run and iproofs controls | harness | p0 | s | RFC-0008, RFC-0010 | open |
| [#92](https://github.com/ai-verification-observatory/inference-proofs/issues/92) | results: implement the run eligibility rule for releases | results | p0 | s | RFC-0014, RFC-0007 | open |
| [#93](https://github.com/ai-verification-observatory/inference-proofs/issues/93) | results: implement iproofs release freeze and the release index | results | p0 | m | RFC-0009 | open |
| [#98](https://github.com/ai-verification-observatory/inference-proofs/issues/98) | harness: implement ErrorKind, IProofsError and failure records | harness | p0 | s | RFC-0010 | open |
| [#99](https://github.com/ai-verification-observatory/inference-proofs/issues/99) | harness: implement the JSON Lines logger and the event catalogue | harness | p0 | s | RFC-0010 | open |
| [#100](https://github.com/ai-verification-observatory/inference-proofs/issues/100) | security: redact secrets and host identifiers from logs and records | security | p0 | m | RFC-0010, RFC-0006 | open |
| [#103](https://github.com/ai-verification-observatory/inference-proofs/issues/103) | harness: implement the iproofs CLI skeleton and exit-code mapping | harness | p0 | m | RFC-0010 | open |
| [#104](https://github.com/ai-verification-observatory/inference-proofs/issues/104) | harness: implement DockerRunner and InProcessRunner with isolation flags | harness | p0 | m | RFC-0010, RFC-0005 | open |
| [#105](https://github.com/ai-verification-observatory/inference-proofs/issues/105) | harness: implement JobSpec, run-id allocation and the job state machine | harness | p0 | l | RFC-0010 | open |
| [#106](https://github.com/ai-verification-observatory/inference-proofs/issues/106) | harness: write run directories atomically through staging and rename | harness | p0 | m | RFC-0010, RFC-0009 | open |
| [#107](https://github.com/ai-verification-observatory/inference-proofs/issues/107) | harness: implement the runner lock and crash recovery as failed jobs | harness | p0 | s | RFC-0010 | open |
| [#108](https://github.com/ai-verification-observatory/inference-proofs/issues/108) | harness: implement step timeouts, OOM detection and the fetch retry policy | harness | p0 | m | RFC-0010 | open |
| [#110](https://github.com/ai-verification-observatory/inference-proofs/issues/110) | measurement: record monotonic events and time container start separately | measurement | p0 | s | RFC-0011 | open |
| [#111](https://github.com/ai-verification-observatory/inference-proofs/issues/111) | measurement: implement the proof release watcher with inotify and polling | measurement | p0 | m | RFC-0011, RFC-0005 | open |
| [#112](https://github.com/ai-verification-observatory/inference-proofs/issues/112) | measurement: account proof, verifier download and prover keep bytes | measurement | p0 | s | RFC-0011 | open |
| [#118](https://github.com/ai-verification-observatory/inference-proofs/issues/118) | ci: add the workflow with required checks and gate G1 | ci | p0 | m | RFC-0013 | open |
| [#119](https://github.com/ai-verification-observatory/inference-proofs/issues/119) | ci: implement iproofs validate with gates G2, G3 and G5 | ci | p0 | l | RFC-0013 | open |
| [#120](https://github.com/ai-verification-observatory/inference-proofs/issues/120) | ci: implement gate G6, forbidden flags outside control jobs | ci | p0 | s | RFC-0013, RFC-0005 | open |
| [#121](https://github.com/ai-verification-observatory/inference-proofs/issues/121) | ci: implement gate G7, full commit hashes and digests | ci | p0 | s | RFC-0013, RFC-0014 | open |
| [#123](https://github.com/ai-verification-observatory/inference-proofs/issues/123) | security: implement gate G9, the secrets and identifiers scan | security | p0 | s | RFC-0013 | open |
| [#124](https://github.com/ai-verification-observatory/inference-proofs/issues/124) | ci: implement gate G10, fake and fake-broken end-to-end runs | ci | p0 | m | RFC-0013, RFC-0008 | open |
| [#130](https://github.com/ai-verification-observatory/inference-proofs/issues/130) | provenance: write manifest.json with everything needed to rerun | provenance | p0 | m | RFC-0014 | open |
| [#131](https://github.com/ai-verification-observatory/inference-proofs/issues/131) | security: pass the commitment to verify from the harness record only | security | p0 | s | RFC-0014, RFC-0005 | open |
| [#22](https://github.com/ai-verification-observatory/inference-proofs/issues/22) | docs: add CHANGELOG.md and the harness and benchmark release checklists | docs | p1 | s | RFC-0009 | open |
| [#25](https://github.com/ai-verification-observatory/inference-proofs/issues/25) | ci: validate MAINTAINERS.md rows and maintainer seat rules | ci | p1 | s | RFC-0001, RFC-0013 | open |
| [#40](https://github.com/ai-verification-observatory/inference-proofs/issues/40) | schema: implement claim_class grammar and wildcard matching | schema | p1 | s | RFC-0002 | open |
| [#41](https://github.com/ai-verification-observatory/inference-proofs/issues/41) | ci: enforce card_version increment and review reset on claim card edits | ci | p1 | s | RFC-0002, RFC-0013 | open |
| [#62](https://github.com/ai-verification-observatory/inference-proofs/issues/62) | docs: write the adapter author guide from the contract and the fake system | docs | p1 | s | RFC-0005 | open |
| [#80](https://github.com/ai-verification-observatory/inference-proofs/issues/80) | schema: publish review/1 and reproduction/1 schemas with examples | schema | p1 | s | RFC-0007, RFC-0012 | open |
| [#83](https://github.com/ai-verification-observatory/inference-proofs/issues/83) | harness: record runner identity and affiliation in the manifest | harness | p1 | s | RFC-0007, RFC-0014 | open |
| [#101](https://github.com/ai-verification-observatory/inference-proofs/issues/101) | harness: cap log files with head and tail retention | harness | p1 | s | RFC-0009, RFC-0010 | open |
| [#109](https://github.com/ai-verification-observatory/inference-proofs/issues/109) | ci: add the import-layer test that enforces module boundaries | ci | p1 | s | RFC-0010 | open |
| [#113](https://github.com/ai-verification-observatory/inference-proofs/issues/113) | measurement: add null readers for hosts without NVML or cgroup v2 | measurement | p1 | s | RFC-0011 | open |
| [#122](https://github.com/ai-verification-observatory/inference-proofs/issues/122) | ci: implement gate G8, the neutral-language lint | ci | p1 | s | RFC-0013 | open |
| [#125](https://github.com/ai-verification-observatory/inference-proofs/issues/125) | ci: implement gate G11, DCO sign-off on every commit | ci | p1 | s | RFC-0013, RFC-0001 | open |
| [#126](https://github.com/ai-verification-observatory/inference-proofs/issues/126) | ci: implement gate G12, relative link and anchor check | ci | p1 | s | RFC-0013 | open |
| [#23](https://github.com/ai-verification-observatory/inference-proofs/issues/23) | governance: add inclusion, opt-out and review objection issue templates | governance | p2 | s | RFC-0001, RFC-0007 | open |
| [#26](https://github.com/ai-verification-observatory/inference-proofs/issues/26) | ci: check RFC status lines against rfcs/README.md | ci | p2 | s | RFC-0001, RFC-0013 | open |
| [#27](https://github.com/ai-verification-observatory/inference-proofs/issues/27) | ci: check every tracked file maps to the code or data licence | ci | p2 | s | RFC-0001, RFC-0013 | open |
| [#102](https://github.com/ai-verification-observatory/inference-proofs/issues/102) | harness: implement stderr progress output and --quiet | harness | p2 | s | RFC-0010 | open |
| [#127](https://github.com/ai-verification-observatory/inference-proofs/issues/127) | ci: set job timeouts from the budget and add the synthetic tree benchmark | ci | p2 | m | RFC-0013 | open |
| [#129](https://github.com/ai-verification-observatory/inference-proofs/issues/129) | test: add the quarantine marker and the flaky-test release block | ci | p2 | s | RFC-0013 | open |

## Milestone: v0.1-beta

GPU path: measurement, model fetch, prompts, SASH and FlashProve adapters, reference rows, controls on real systems, first reported runs on prover-h100.

| # | Title | Area | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|---|
| [#49](https://github.com/ai-verification-observatory/inference-proofs/issues/49) | workloads: pin the four v0.1 workload files with revisions and digests | workloads | p0 | m | RFC-0003 | open |
| [#64](https://github.com/ai-verification-observatory/inference-proofs/issues/64) | adapters: build the SASH image at eb95bfa with pinned toolchains | adapters | p0 | m | RFC-0005, RFC-0014 | open |
| [#65](https://github.com/ai-verification-observatory/inference-proofs/issues/65) | adapters: map SASH commit, prove and verify with CPU fixture tests | adapters | p0 | l | RFC-0005 | open |
| [#67](https://github.com/ai-verification-observatory/inference-proofs/issues/67) | adapters: draft the SASH claim card from upstream docs at the pin | adapters | p0 | m | RFC-0002 | open |
| [#68](https://github.com/ai-verification-observatory/inference-proofs/issues/68) | adapters: build the FlashProve image at 9e2bdd8f with CUDA 13.2 and gcc 13 | adapters | p0 | m | RFC-0005, RFC-0014 | open |
| [#69](https://github.com/ai-verification-observatory/inference-proofs/issues/69) | adapters: map FlashProve commit, prove and verify with CPU fixture tests | adapters | p0 | l | RFC-0005 | open |
| [#71](https://github.com/ai-verification-observatory/inference-proofs/issues/71) | adapters: draft the FlashProve claim card from upstream docs at the pin | adapters | p0 | m | RFC-0002 | open |
| [#73](https://github.com/ai-verification-observatory/inference-proofs/issues/73) | measurement: implement the machine record with the identifier exclusions | measurement | p0 | m | RFC-0006 | open |
| [#74](https://github.com/ai-verification-observatory/inference-proofs/issues/74) | measurement: implement deterministic CPU selection on the GPU NUMA node | measurement | p0 | s | RFC-0006 | open |
| [#75](https://github.com/ai-verification-observatory/inference-proofs/issues/75) | measurement: implement profile conformance checks before every job | measurement | p0 | m | RFC-0006 | open |
| [#76](https://github.com/ai-verification-observatory/inference-proofs/issues/76) | harness: run verify in emulated verifier-cpu containers | harness | p0 | s | RFC-0006, RFC-0004 | open |
| [#114](https://github.com/ai-verification-observatory/inference-proofs/issues/114) | measurement: implement the parent-slice cgroup v2 reader | measurement | p0 | m | RFC-0011 | open |
| [#115](https://github.com/ai-verification-observatory/inference-proofs/issues/115) | measurement: implement the NVML sampler with gap tracking and busy check | measurement | p0 | m | RFC-0011 | open |
| [#116](https://github.com/ai-verification-observatory/inference-proofs/issues/116) | measurement: implement iproofs machine-record --selftest | measurement | p0 | m | RFC-0011, RFC-0006 | open |
| [#132](https://github.com/ai-verification-observatory/inference-proofs/issues/132) | provenance: implement iproofs fetch-model with per-file hash checks | provenance | p0 | m | RFC-0014, RFC-0003 | open |
| [#134](https://github.com/ai-verification-observatory/inference-proofs/issues/134) | provenance: build adapter images offline and record every input digest | provenance | p0 | m | RFC-0014, RFC-0005 | open |
| [#136](https://github.com/ai-verification-observatory/inference-proofs/issues/136) | reference: choose and pin the vLLM release and image digest | reference | p0 | s | RFC-0015 | open |
| [#137](https://github.com/ai-verification-observatory/inference-proofs/issues/137) | harness: support reference systems and --prompts-from in iproofs run | harness | p0 | s | RFC-0015, RFC-0010 | open |
| [#138](https://github.com/ai-verification-observatory/inference-proofs/issues/138) | reference: implement the ref-serve plain-serving adapter | reference | p0 | l | RFC-0015 | open |
| [#139](https://github.com/ai-verification-observatory/inference-proofs/issues/139) | reference: implement the ref-recompute adapter with the agreement check | reference | p0 | l | RFC-0015 | open |
| [#142](https://github.com/ai-verification-observatory/inference-proofs/issues/142) | results: record reported SASH runs on both workloads with controls | results | p0 | m | RFC-0009, RFC-0004, RFC-0008 | open |
| [#143](https://github.com/ai-verification-observatory/inference-proofs/issues/143) | results: record reported FlashProve runs on both workloads with controls | results | p0 | m | RFC-0009, RFC-0004, RFC-0008 | open |
| [#144](https://github.com/ai-verification-observatory/inference-proofs/issues/144) | results: record plain-serving and recompute rows for all four workloads | results | p0 | m | RFC-0015, RFC-0009 | open |
| [#47](https://github.com/ai-verification-observatory/inference-proofs/issues/47) | workloads: choose the corpus texts and commit corpus.yaml with digests | workloads | p1 | s | RFC-0003, RFC-0014 | open |
| [#48](https://github.com/ai-verification-observatory/inference-proofs/issues/48) | workloads: implement iproofs prompts build with pinned tokenizer files | workloads | p1 | m | RFC-0003 | open |
| [#56](https://github.com/ai-verification-observatory/inference-proofs/issues/56) | schema: publish external/1 and record SASH and FlashProve upstream figures | schema | p1 | s | RFC-0004, RFC-0012 | open |
| [#63](https://github.com/ai-verification-observatory/inference-proofs/issues/63) | adapters: confirm SASH grid geometry and segment release from upstream | adapters | p1 | s | RFC-0003, RFC-0005 | open |
| [#66](https://github.com/ai-verification-observatory/inference-proofs/issues/66) | controls: register SASH unsound-skip control jobs with binding checks | controls | p1 | m | RFC-0008, RFC-0005 | open |
| [#70](https://github.com/ai-verification-observatory/inference-proofs/issues/70) | controls: register FlashProve rejected-proofs examples as system controls | controls | p1 | s | RFC-0008 | open |
| [#77](https://github.com/ai-verification-observatory/inference-proofs/issues/77) | reference: pin the v0.1 NVIDIA driver and CUDA runtime | reference | p1 | s | RFC-0006 | open |
| [#90](https://github.com/ai-verification-observatory/inference-proofs/issues/90) | controls: implement perturbed commitments and prover-side controls P1, P2 | controls | p1 | m | RFC-0008 | open |
| [#91](https://github.com/ai-verification-observatory/inference-proofs/issues/91) | controls: load system-specific controls from controls.yaml | controls | p1 | m | RFC-0008 | open |
| [#117](https://github.com/ai-verification-observatory/inference-proofs/issues/117) | docs: write the GPU-host runbook for self-tests and campaign runs | docs | p1 | s | RFC-0011, RFC-0013 | open |
| [#133](https://github.com/ai-verification-observatory/inference-proofs/issues/133) | provenance: implement corpus fetch and digest verification | provenance | p1 | s | RFC-0014, RFC-0003 | open |
| [#140](https://github.com/ai-verification-observatory/inference-proofs/issues/140) | reference: enforce precision substitution rules in validation | reference | p1 | s | RFC-0015, RFC-0013 | open |
| [#128](https://github.com/ai-verification-observatory/inference-proofs/issues/128) | ci: report coverage and enforce branch thresholds on core modules | ci | p2 | s | RFC-0013 | open |
| [#141](https://github.com/ai-verification-observatory/inference-proofs/issues/141) | harness: implement iproofs release plan for the campaign compute budget | harness | p2 | m | RFC-0004 | open |

## Milestone: v0.1

Release: reviewed claim cards, peer review, third-party reproduction, site, report, 14-day review window, freeze.

| # | Title | Area | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|---|
| [#29](https://github.com/ai-verification-observatory/inference-proofs/issues/29) | governance: seat a maintainer from a second organisation (INV-GOV-1) | governance | p0 | m | RFC-0001 | open |
| [#42](https://github.com/ai-verification-observatory/inference-proofs/issues/42) | governance: obtain system maintainer review of the SASH and FlashProve cards | governance | p0 | s | RFC-0002, RFC-0001 | open |
| [#78](https://github.com/ai-verification-observatory/inference-proofs/issues/78) | reference: set the v0.1 price per GPU-hour from named providers | reference | p0 | s | RFC-0006 | open |
| [#84](https://github.com/ai-verification-observatory/inference-proofs/issues/84) | governance: run the cross-system peer review and file review records | governance | p0 | m | RFC-0007 | open |
| [#85](https://github.com/ai-verification-observatory/inference-proofs/issues/85) | governance: reproduce every v0.1 configuration with independent runners | governance | p0 | l | RFC-0007 | open |
| [#96](https://github.com/ai-verification-observatory/inference-proofs/issues/96) | site: generate system pages with the claim card before any number | site | p0 | l | RFC-0009, RFC-0002 | open |
| [#97](https://github.com/ai-verification-observatory/inference-proofs/issues/97) | site: generate cross-system tables by division, sponsors and conflicts pages | site | p0 | m | RFC-0009 | open |
| [#145](https://github.com/ai-verification-observatory/inference-proofs/issues/145) | docs: write and review the v0.1 release report | docs | p0 | m | RFC-0009 | open |
| [#146](https://github.com/ai-verification-observatory/inference-proofs/issues/146) | results: freeze v0.1 after the 14-day review window and publish | results | p0 | m | RFC-0009, RFC-0001, RFC-0007 | open |
| [#55](https://github.com/ai-verification-observatory/inference-proofs/issues/55) | harness: implement cross-row metrics for overhead, agreement and spread | harness | p1 | m | RFC-0004, RFC-0015 | open |
| [#94](https://github.com/ai-verification-observatory/inference-proofs/issues/94) | results: evaluate relying-party targets per row | results | p1 | m | RFC-0009, RFC-0002 | open |
| [#135](https://github.com/ai-verification-observatory/inference-proofs/issues/135) | provenance: archive one proof per configuration and verify digests.txt | provenance | p1 | m | RFC-0014, RFC-0009 | open |
| [#28](https://github.com/ai-verification-observatory/inference-proofs/issues/28) | ci: flag merges by maintainers with a declared interest in the system | ci | p2 | m | RFC-0001, RFC-0013 | open |
| [#79](https://github.com/ai-verification-observatory/inference-proofs/issues/79) | measurement: compare emulated and separate verifier hosts once | measurement | p2 | m | RFC-0006 | open |
| [#95](https://github.com/ai-verification-observatory/inference-proofs/issues/95) | results: validate right-of-reply files and the 300-word limit | results | p2 | s | RFC-0009 | open |

## Tracking Issues

- [#2](https://github.com/ai-verification-observatory/inference-proofs/issues/2) [Tracking] Governance and project files (10 children)
- [#3](https://github.com/ai-verification-observatory/inference-proofs/issues/3) [Tracking] Schemas, labelled quantities and serialization (8 children)
- [#4](https://github.com/ai-verification-observatory/inference-proofs/issues/4) [Tracking] Claim cards (5 children)
- [#5](https://github.com/ai-verification-observatory/inference-proofs/issues/5) [Tracking] Workloads, prompt corpus and prompt generation (7 children)
- [#6](https://github.com/ai-verification-observatory/inference-proofs/issues/6) [Tracking] Metrics, timing scopes and derivation (7 children)
- [#7](https://github.com/ai-verification-observatory/inference-proofs/issues/7) [Tracking] Adapter contract and fake systems (6 children)
- [#8](https://github.com/ai-verification-observatory/inference-proofs/issues/8) [Tracking] SASH zk-inference-prover adapter (5 children)
- [#9](https://github.com/ai-verification-observatory/inference-proofs/issues/9) [Tracking] FlashProve adapter (4 children)
- [#10](https://github.com/ai-verification-observatory/inference-proofs/issues/10) [Tracking] Reference hardware, machine record and cost basis (8 children)
- [#11](https://github.com/ai-verification-observatory/inference-proofs/issues/11) [Tracking] Evidence tiers, peer review and reproduction (6 children)
- [#12](https://github.com/ai-verification-observatory/inference-proofs/issues/12) [Tracking] Negative controls (6 children)
- [#13](https://github.com/ai-verification-observatory/inference-proofs/issues/13) [Tracking] Results, releases, targets and site (6 children)
- [#14](https://github.com/ai-verification-observatory/inference-proofs/issues/14) [Tracking] Harness runner, CLI, errors and logs (12 children)
- [#15](https://github.com/ai-verification-observatory/inference-proofs/issues/15) [Tracking] External measurement and resource sampling (8 children)
- [#16](https://github.com/ai-verification-observatory/inference-proofs/issues/16) [Tracking] Validation pipeline and CI gates (12 children)
- [#17](https://github.com/ai-verification-observatory/inference-proofs/issues/17) [Tracking] Provenance, pinning and artifact integrity (6 children)
- [#18](https://github.com/ai-verification-observatory/inference-proofs/issues/18) [Tracking] Reference rows: plain serving and recompute (5 children)
- [#19](https://github.com/ai-verification-observatory/inference-proofs/issues/19) [Tracking] v0.1 run campaign and release (6 children)

## Counts

| Milestone | Issues | p0 | p1 | p2 |
|---|---|---|---|---|
| v0.1-alpha | 75 | 56 | 13 | 6 |
| v0.1-beta | 37 | 23 | 12 | 2 |
| v0.1 | 15 | 9 | 3 | 3 |

| Area | Issues |
|---|---|
| adapters | 9 |
| ci | 17 |
| controls | 7 |
| docs | 4 |
| governance | 7 |
| harness | 23 |
| measurement | 11 |
| provenance | 5 |
| reference | 7 |
| results | 10 |
| schema | 15 |
| security | 5 |
| site | 2 |
| workloads | 5 |

## Cross-Cutting Dependencies

The issues below block five or more others; landing them first unblocks the most work. Every other dependency is listed in the issue bodies.

- [#34](https://github.com/ai-verification-observatory/inference-proofs/issues/34) blocks 13 issues (#35, #36, #37, #38, #43, #50, #56, #57, #58, #72, #80, #88, #119) because every schema and every stored number uses the labelled-quantity definitions (RFC-0012).
- [#118](https://github.com/ai-verification-observatory/inference-proofs/issues/118) blocks 11 issues (#25, #26, #27, #41, #122, #123, #125, #126, #127, #128, #129) because every gate needs the workflow that runs it.
- [#58](https://github.com/ai-verification-observatory/inference-proofs/issues/58) blocks 11 issues (#39, #51, #59, #60, #64, #68, #91, #105, #120, #134, #140) because adapters, controls, policy checks and tokens-covered counting read system.yaml.
- [#103](https://github.com/ai-verification-observatory/inference-proofs/issues/103) blocks 8 issues (#48, #54, #73, #81, #105, #119, #132, #141) because every user-facing command hangs off it.
- [#57](https://github.com/ai-verification-observatory/inference-proofs/issues/57) blocks 8 issues (#51, #59, #60, #65, #69, #87, #104, #120) because the runner, the fake systems, the real adapters and the controls all exchange adapter-job and adapter-out documents.
- [#119](https://github.com/ai-verification-observatory/inference-proofs/issues/119) blocks 8 issues (#93, #95, #120, #121, #124, #127, #128, #140) because every CI gate after G1 is a check inside iproofs validate.
- [#32](https://github.com/ai-verification-observatory/inference-proofs/issues/32) blocks 7 issues (#45, #60, #87, #112, #132, #133, #135) because workloads, proofs, corpus and archive all identify content by digest.
- [#105](https://github.com/ai-verification-observatory/inference-proofs/issues/105) blocks 7 issues (#46, #89, #106, #108, #130, #131, #137) because measurement, manifests, controls and reference rows plug into the job state machine.
- [#30](https://github.com/ai-verification-observatory/inference-proofs/issues/30) blocks 6 issues (#31, #32, #86, #98, #109, #118) because every module, test and CI job lives in the package it creates.
- [#20](https://github.com/ai-verification-observatory/inference-proofs/issues/20) blocks 5 issues (#23, #24, #25, #27, #29) because the governance checks, the Last call and the issue templates need MAINTAINERS.md, CONTRIBUTING.md and the licence files.
- [#44](https://github.com/ai-verification-observatory/inference-proofs/issues/44) blocks 5 issues (#45, #51, #105, #132, #140) because prompt generation, model fetch, tokens covered and the runner read workloads through it.
- [#130](https://github.com/ai-verification-observatory/inference-proofs/issues/130) blocks 5 issues (#83, #92, #142, #143, #144) because eligibility, tiers and every GPU run depend on a complete manifest.
