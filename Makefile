# Same commands, same order as .github/workflows/ci.yml (checked by harness/tests/unit/test_ci_config.py).
.PHONY: ci
ci:
	uv sync --frozen
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict harness/src/iproofs harness/tests
	HYPOTHESIS_PROFILE=ci uv run pytest harness/tests -q
