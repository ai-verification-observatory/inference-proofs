# Repository settings

Settings that live on the hosting platform rather than in files. A maintainer applies them by hand and records any change in a pull request to this file ([RFC-0013 §CI workflow structure](../../rfcs/0013-validation-and-ci.md#ci-workflow-structure)).

## Branch protection on `main`

- Require a pull request before merging.
- Require status checks to pass, with the branch up to date. Required checks, from `.github/workflows/ci.yml`:
  - `lint-and-types`
  - `tests (3.12)`
  - `tests (3.13)`
  - `validate`
  - `fake-e2e` (once gate G10 lands, #124)
  - `dco` (once gate G11 lands, #125)
- Do not allow force pushes or deletion of `main`.

## Actions

- Workflow permissions: read repository contents only.
- Pull requests from forks get no secrets. No workflow uses a secret today.
- Every action is referenced by a full commit hash; `harness/tests/unit/test_ci_config.py` checks it.

## Security

- Private vulnerability reporting: enable once the repository is public ([SECURITY.md](../../SECURITY.md), #21).
