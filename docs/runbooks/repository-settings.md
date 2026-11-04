# Repository settings

Settings that live on the hosting platform rather than in files. A maintainer applies them by hand and records any change in a pull request to this file ([RFC-0013 §CI workflow structure](../../rfcs/0013-validation-and-ci.md#ci-workflow-structure)).

## Branch protection on `main`

- Require a pull request before merging.
- Require status checks to pass, with the branch up to date. Required checks, from `.github/workflows/ci.yml`:
  - `lint-and-types`
  - `tests (3.12)`
  - `tests (3.13)` (each passes only after its three `test-shard` jobs pass and the combined coverage meets its floors; the shard jobs need not be required)
  - `validate`
  - `fake-e2e`
  - `dco`
  - `merge-guard` (from `.github/workflows/merge-guard.yml`, INV-GOV-4; it re-runs on each review)
- Do not allow force pushes or deletion of `main`.

## Actions

- Workflow permissions: read repository contents only. The `merge-guard` job also reads pull request reviews (`pull-requests: read`), and the nightly link check may open one issue (`issues: write`).
- Pull requests from forks get no secrets. No workflow uses a secret today.
- Every action is referenced by a full commit hash; `harness/tests/unit/test_ci_config.py` checks it.

## Security

- Private vulnerability reporting: enable once the repository is public ([SECURITY.md](../../SECURITY.md), #21).
