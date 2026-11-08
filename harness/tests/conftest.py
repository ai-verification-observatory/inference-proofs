import os

import pytest
from hypothesis import settings

# Deterministic property tests in CI (RFC-0013 §G1); select with HYPOTHESIS_PROFILE=ci.
settings.register_profile("ci", max_examples=200, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def shard_of(nodeids: list[str], shard: str) -> set[str]:
    """`i/n`: the tests of the i-th of n parts (docs/spec/07 §Sharding). Test files are dealt
    whole, most tests first (ties by path), each to the part with the fewest tests so far (the
    lowest index on a tie). So every test runs in exactly one shard, a file's module fixtures
    build in one shard only, and two parts differ by at most the tests of one file."""
    i, n = (int(x) for x in shard.split("/"))
    if not 1 <= i <= n:
        raise pytest.UsageError(f"IPROOFS_SHARD={shard!r}: need 1 <= i <= n")
    files: dict[str, list[str]] = {}
    for nodeid in sorted(nodeids):
        files.setdefault(nodeid.split("::", 1)[0], []).append(nodeid)
    parts: list[list[str]] = [[] for _ in range(n)]
    for path in sorted(files, key=lambda p: (-len(files[p]), p)):
        min(parts, key=len).extend(files[path])  # min returns the first of equal parts
    return set(parts[i - 1])


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
