import os

import pytest
from hypothesis import settings

# Deterministic property tests in CI (RFC-0013 §G1); select with HYPOTHESIS_PROFILE=ci.
settings.register_profile("ci", max_examples=200, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def shard_of(nodeids: list[str], shard: str) -> set[str]:
    """`i/n`: the i-th of n interleaved parts of the sorted node ids (docs/spec/07 §Sharding),
    so every test runs in exactly one shard and the parts differ in size by at most one."""
    i, n = (int(x) for x in shard.split("/"))
    if not 1 <= i <= n:
        raise pytest.UsageError(f"IPROOFS_SHARD={shard!r}: need 1 <= i <= n")
    return set(sorted(nodeids)[i - 1 :: n])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    shard = os.environ.get("IPROOFS_SHARD")  # set by the CI test-shard job only
    if not shard:
        return
    keep = shard_of([item.nodeid for item in items], shard)
    config.hook.pytest_deselected(items=[item for item in items if item.nodeid not in keep])
    items[:] = [item for item in items if item.nodeid in keep]


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
