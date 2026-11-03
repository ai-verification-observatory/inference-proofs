import os

import pytest
from hypothesis import settings

# Deterministic property tests in CI (RFC-0013 §G1); select with HYPOTHESIS_PROFILE=ci.
settings.register_profile("ci", max_examples=200, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="rewrite the golden files under harness/tests/golden/ from this run",
    )


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    """Golden files change only through `uv run pytest --update-golden`."""
    return bool(request.config.getoption("--update-golden"))
