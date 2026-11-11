# Same commands, same order as .github/workflows/ci.yml.
.PHONY: ci e2e
# Gate G10 with real containers (needs Docker); CI runs it as root in the fake-e2e job.
e2e:
	IPROOFS_REAL_DOCKER=1 uv run pytest harness/tests/integration -q -rs

ci:
	uv sync --frozen
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict harness/src/iproofs harness/tests
	HYPOTHESIS_PROFILE=ci uv run pytest harness/tests systems -q -n auto --dist loadfile --durations=20
	uv run iproofs validate --all
