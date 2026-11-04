import json
import subprocess
from pathlib import Path

import pytest

from iproofs.log import patterns
from iproofs.log.redact import Redactor
from iproofs.validate import tree
from iproofs.validate.tree import scan_text, validate_tree
from secret_samples import DIR, RULES, sample

ROOT = Path(__file__).resolve().parents[3]

# Every RFC-0006 machine record field, with values of the form a real H100 host reports.
MACHINE = {
    "gpu": {
        "model": "NVIDIA H100 80GB HBM3",
        "count_visible": 8,
        "memory_total_mib": 81559,
        "bound_index": 0,
        "numa_node": 0,
        "driver_version": "560.35.03",
        "cuda_driver_api": "12.6",
    },
    "cpu": {
        "model": "AMD EPYC 9654 96-Core Processor",
        "sockets": 2,
        "physical_cores": 192,
        "logical_cpus": 384,
        "smt_active": True,
        "bound_prover": [0, 1, 2, 3, 4, 5, 6, 7],
        "bound_verifier": [8, 9, 10, 11, 12, 13, 14, 15],
        "bound_verifier_single": [8],
    },
    "numa": {"nodes": 2, "bound_mems": [0]},
    "memory": {"total_bytes": 1622567096320, "available_bytes_at_start": 1588012875776},
    "disk": {"type": "nvme", "free_bytes_at_start": 3200000000000},
    "os": {"id": "ubuntu", "version_id": "22.04"},
    "kernel": {"release": "6.8.0-45-generic"},
    "container": {
        "docker_engine": "27.3.1",
        "cgroup_driver": "systemd",
        "cgroup_version": "2",
        "nvidia_container_toolkit": "1.16.2",
    },
    "provider": "example-cloud",
    "verifier_host": "same_as_prover",
}


@pytest.mark.parametrize("rule", RULES)
def test_fixture_rejected_with_its_rule(rule: str) -> None:
    rel = f"harness/tests/fixtures/secrets/{rule}.txt"
    assert [f.rule for f in scan_text(sample(rule), rel)] == [rule]


def test_named_fixture_directory_reports_every_rule() -> None:
    found = validate_tree(ROOT, only=[str(DIR.relative_to(ROOT))])
    assert sorted({f.rule for f in found if f.gate == "G9"}) == sorted(RULES)


def test_allowlist_skipped_in_a_repository_scan(tmp_path: Path) -> None:
    for rel in ["harness/tests/fixtures/secrets/SEC-5.txt", "docs/leak.md"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(f"reach {sample('SEC-5')}\n")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    found = [(f.path, f.rule) for f in validate_tree(tmp_path) if f.gate == "G9"]
    assert found == [("docs/leak.md:1", "SEC-5")]


def test_machine_record_example_passes() -> None:
    """RFC-0006 machine record fields never match a G9 pattern; no exception is needed."""
    text = json.dumps({"schema": "manifest/1", "machine": MACHINE}, indent=2)
    assert scan_text(text, "results/x/manifest.json") == []


@pytest.mark.parametrize(
    "line",
    [
        "harness/tests/unit/test_cli.py::test_validate PASSED",  # pytest node id
        '"ts": "2026-11-03T10:15:02.118Z"',  # clock time
        '"sha256": "ab01cd02"',
        '"driver_version": "560.35.03.01"',  # four groups inside a version field
        "nvidia-cublas==13.4.1.3 \\",  # a pip requirement pin
    ],
)
def test_not_secrets(line: str) -> None:
    assert scan_text(line, "x") == []


def test_address_after_other_operator_still_found() -> None:
    addr = ".".join(["10", "1", "2", "3"])  # built here so the repository scan (G9) passes
    assert [f.rule for f in scan_text(f"host={addr}", "x")] == ["SEC-5"]
    assert [f.rule for f in scan_text(f"pkg>={addr}", "x")] == ["SEC-5"]


def test_redactor_and_scanner_share_patterns() -> None:
    assert vars(tree)["PATTERNS"] is patterns.PATTERNS is Redactor.patterns
