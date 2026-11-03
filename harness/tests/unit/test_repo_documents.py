"""Every committed system and workload document loads and passes its loader checks."""

import hashlib
from pathlib import Path

import pytest

from iproofs.model import System, load
from iproofs.provenance import model_digest
from iproofs.schema import SchemaRegistry
from iproofs.workloads import load_workload

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
SYSTEMS = sorted((ROOT / "systems").glob("*/system.yaml"))
WORKLOADS = sorted((ROOT / "workloads").glob("*.yaml"))


@pytest.mark.parametrize("path", SYSTEMS, ids=lambda p: p.parent.name)
def test_system_documents_load(path: Path) -> None:
    system = load(path, REGISTRY)
    assert isinstance(system, System)
    assert system.name == path.parent.name


@pytest.mark.parametrize("path", WORKLOADS, ids=lambda p: p.stem)
def test_workload_documents_load(path: Path) -> None:
    wl = load_workload(path.stem, root=ROOT, registry=REGISTRY)
    if wl.model.source.hub == "repository":
        # in-repository test data: the pinned hashes match the files at the given path
        assert wl.model.source.path is not None
        model_dir = ROOT / wl.model.source.path
        for f in wl.model.files:
            assert hashlib.sha256((model_dir / f.path).read_bytes()).hexdigest() == f.sha256
        assert model_digest(model_dir) == wl.model.digest
