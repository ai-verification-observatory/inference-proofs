# Harness release

Checklist for a harness version (`harness-v<version>`), from [docs/spec/09-release-and-versioning.md §Release checklists](../spec/09-release-and-versioning.md#release-checklists). A harness version is independent of a benchmark release. Do every step in order; a step that fails stops the release.

1. All required checks are green on `main`, and no quarantined test is older than 30 days ([07-testing-strategy.md §Flaky-test policy](../spec/07-testing-strategy.md#flaky-test-policy)); `harness/tests/repo/test_quarantine.py` checks it.
2. The version is bumped in `pyproject.toml`, and the `Unreleased` section of [CHANGELOG.md](../../CHANGELOG.md) is moved under the new version with the date.
3. `uv build` produces a wheel and an sdist, and `uv run --isolated --with dist/*.whl iproofs --version` succeeds in a clean environment.
4. Tag `harness-v<version>` on the release commit.
5. The wheel is attached to the tag's release notes. The harness is not published to a package index ([09 §Decisions](../spec/09-release-and-versioning.md#decisions), Q1).
