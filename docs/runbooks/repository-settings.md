# Repository settings

Settings that live on the hosting platform rather than in files. They are applied by hand, and any change is recorded in a pull request to this file ([RFC-0013 §CI workflow structure](../../rfcs/0013-validation-and-ci.md#ci-workflow-structure)).

## Branch protection on `main`

- Require a pull request before merging.
- Requiring the jobs of `.github/workflows/ci.yml` to pass is optional.
- Do not allow force pushes or deletion of `main`.

## Actions

- Workflow permissions: read repository contents only.
- Pull requests from forks get no secrets. No workflow uses a secret today.
- Every action is referenced by a full commit hash.

## Security

- Private vulnerability reporting: enable once the repository is public ([SECURITY.md](../../SECURITY.md)).
