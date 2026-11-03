# Inference Proofs

An open benchmark for provable inference: the same models, the same reference hardware, the same timing rules, and a plain statement of what each proof establishes.

Several open systems can now prove that a language model produced a given output. Each publishes its own numbers, on its own model, under its own timing rules, for its own claim, so nobody can compare them. This project measures them on equal terms, in the spirit of [Ethproofs](https://ethproofs.org/) for zkVM provers, with one addition that inference needs: a claim card beside every number.

**Status:** design phase. No harness code or results yet. Working name.

## First systems (v0.1)

| System | Repository | Native workload |
|---|---|---|
| SASH zk-inference-prover | [sg-ai-safety-hub/zk-inference-prover](https://github.com/sg-ai-safety-hub/zk-inference-prover) | Llama-3.1-8B, W8A8 |
| FlashProve | [anthropics/FlashProve](https://github.com/anthropics/FlashProve) | Llama 4 Maverick, 4-bit |

Both run on one NVIDIA H100 80 GB. More systems and common workloads follow (see the roadmap in the PRD).

## Principles

- **Claim first.** No number without a statement of what is proved, under which assumptions, and what a dishonest prover can still do.
- **Measure, do not rank.** Many axes, no single score, no leaderboard.
- **Reproduced or labelled.** Every number says whether it was reported by its authors, peer-reviewed, or reproduced independently.
- **Adversarial.** Every verifier faces the same negative controls.
- **Adapters, not forks.** Provers run unchanged at pinned commits.
- **Neutral.** Maintainers from several organisations, methodology by RFC, conflicts and sponsors disclosed, right of reply.

## Read

- [docs/PRD.md](docs/PRD.md): problem, users, scope, requirements, roadmap.
- [docs/SPEC.md](docs/SPEC.md): index of the specification corpus (`docs/spec/`), with an executive summary.
- [docs/roadmap/IMPLEMENTATION.md](docs/roadmap/IMPLEMENTATION.md): the implementation issue set by milestone.
- [rfcs/](rfcs/README.md): the normative decisions, open for comment.
- [AGENTS.md](AGENTS.md): rules for contributors and coding agents.

## Install

The harness is one Python package (`iproofs`, Python 3.12 or 3.13), managed with [uv](https://docs.astral.sh/uv/):

```
uv sync
uv run iproofs --version
```

Optional extras are installed only where they are needed: `--extra gpu` (NVML sampling on a GPU host), `--extra fetch` (model download) and `--extra prompts` (tokenizers).

## Build the site

The site is static HTML generated from frozen releases (`releases/*/index.json`, [RFC-0009 §Site](rfcs/0009-results-and-publication.md#site)); it is never committed. With the base install:

```
uv run iproofs site build            # writes site/_build/
uv run iproofs site build --out DIR  # or any other directory
```

Open `site/_build/index.html` in a browser; no script is needed. Templates are in [`site/templates/`](site/templates/). Until a release is frozen the site has only its home page.

## Contributing

Open an issue or a pull request; methodology changes go through an RFC ([RFC-0001](rfcs/0001-process-and-governance.md)). Sign off your commits (DCO). Prover teams who want their system included: open an issue with your repository and the workloads you support, then follow the adapter guide, [systems/README.md](systems/README.md).

## Licence

Code is licensed under Apache-2.0 ([LICENSE](LICENSE)). Specifications, data, results and reports are licensed under CC BY 4.0 ([LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt)).

The boundary is fixed by [RFC-0001](rfcs/0001-process-and-governance.md#governance-files) (INV-GOV-6):

- Code (Apache-2.0): `harness/`, `systems/*/` (except `claim.yaml`, `claims/`, `external.yaml` and `replies/`), `site/` templates, `schema/` and CI configuration.
- Documents and data (CC BY 4.0): `docs/`, `rfcs/`, `workloads/`, `reference/`, `results/`, `releases/`, `targets/`, `reports/`, and claim cards, external figures and replies.
- A file that fits neither list is code.
