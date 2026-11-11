from pathlib import Path

import pytest

from iproofs.model import DEFAULT_TIMEOUTS_S, ReferenceWorkload, System, load
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "schema/system/examples/valid"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_tree(ROOT / "schema")


def system(name: str, registry: SchemaRegistry) -> System:
    loaded = load(EXAMPLES / f"{name}.yaml", registry)
    assert isinstance(loaded, System)
    return loaded


def test_timeout_defaults_and_overrides(registry: SchemaRegistry) -> None:
    fake = system("fake", registry)
    assert fake.timeout("prove") == 60.0  # declared
    assert fake.timeout("commit") == DEFAULT_TIMEOUTS_S["commit"] == 14400.0
    flashprove = system("flashprove-shape", registry)
    assert [flashprove.timeout(s) for s in ("info", "setup", "commit", "prove", "verify")] == [
        60.0, 3600.0, 14400.0, 43200.0, 3600.0,
    ]  # fmt: skip


def test_reference_workloads_are_objects(registry: SchemaRegistry) -> None:
    ref = system("ref-serve-shape", registry)
    assert isinstance(ref.workloads[0], ReferenceWorkload)
    want = ("--tensor-parallel-size", "1", "--max-model-len", "4608", "--max-num-seqs", "1")
    assert ref.workloads[0].engine_args == want
    assert (ref.workloads[0].load_point, ref.workloads[0].gpus) == ("matched", 1)
    assert ref.workload_ids() == ("sash-l31-8b-c4096", "sash-l31-8b-c4096", "l1-l31-8b-p512-o512")
    assert system("fake", registry).workload_ids() == ("fake-tiny-ci",)
