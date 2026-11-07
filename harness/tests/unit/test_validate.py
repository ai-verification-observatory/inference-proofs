import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs import cli
from iproofs.errors import ErrorKind, IProofsError
from iproofs.schema import SchemaRegistry
from iproofs.validate import repo_root, resolve
from iproofs.validate.tree import (
    g2_schema,
    g2_size,
    g2_xref,
    g5_labels,
    g8_language,
    tracked_files,
    validate_tree,
)

ROOT = Path(__file__).resolve().parents[3]
GATES = ROOT / "harness/tests/fixtures/gates"
RUN_DIR = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repository: the schemas, the fake system and its workload, the reference files."""
    for rel in [
        "schema",
        "systems/fake",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
    ]:
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.email=ci@example.org", "-c", "user.name=ci", "commit", "-qm", "base")
    return tmp_path


def place(repo: Path, fixture: str, target: str) -> None:
    dst = repo / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(GATES / fixture, dst)
    git(repo, "add", "-A")


def rules(repo: Path) -> set[tuple[str, str]]:
    return {(f.gate, f.rule) for f in validate_tree(repo)}


def write(repo: Path, rel: str, doc: object) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc) if rel.endswith(".json") else yaml.safe_dump(doc))
    return rel


def test_clean_repository_passes(repo: Path) -> None:
    assert validate_tree(repo) == []
    assert validate_tree(repo, base_ref="HEAD") == []  # APP-1 and CARD-* against itself


def test_outside_a_repository(tmp_path: Path) -> None:
    with pytest.raises(IProofsError) as e:
        tracked_files(tmp_path)
    assert e.value.kind == ErrorKind.ENVIRONMENT
    with pytest.raises(IProofsError):
        repo_root(tmp_path)
    assert resolve(tmp_path, "missing.json#/a") is None


def test_g2_claim_card_and_failing_example(repo: Path) -> None:
    card = "systems/fake/claim.yaml"
    shutil.copy(ROOT / "schema/claim/examples/valid/binding-edges.yaml", repo / card)
    (repo / "schema/system/examples/valid/broken.yaml").write_text('schema: "system/1"\n')
    found = g2_schema(repo, [card], SchemaRegistry.from_tree(repo / "schema"))
    assert sorted({(f.path, f.rule) for f in found}) == [
        ("schema", "EXAMPLE"),  # a valid example that fails its schema
        (card, "CLAIM-PIN"),  # the card goes through check_claim, not the plain schema load
        (card, "INV-CLAIM-3"),
    ]


def test_g2_site_facts(repo: Path) -> None:
    """RFC-0013 §G2 input: web/_data/facts.json validates against site-facts/1."""
    facts = "web/_data/facts.json"
    doc = json.loads((ROOT / "schema/site-facts/examples/valid/facts.json").read_text())
    write(repo, facts, doc)
    registry = SchemaRegistry.from_tree(repo / "schema")
    assert g2_schema(repo, [facts], registry) == []
    doc["rows"]["fake"]["name"] = 1
    write(repo, facts, doc)
    assert [(f.path, f.rule) for f in g2_schema(repo, [facts], registry)] == [(facts, "SCHEMA")]


def test_g2_xref_rules(repo: Path) -> None:
    run = "results/v0.1/fake/r"
    files = [
        write(repo, f"{run}/run.json", {"schema": "run/1", "workload": {"id": "fake-tiny-ci"},
                                        "system": "nope", "release": "v9", "profile": "nope"}),
        write(repo, f"{run}/manifest.json", {"runner": {"organisation": "Org A"}}),
        write(repo, f"{run}/reviews/a.json", {}),  # no reviewer: nothing to compare
        write(repo, f"{run}/reviews/b.json", {"reviewer": {"organisation": "Org B"}}),
        write(repo, "results/v0.1/fake/gone/reviews/c.json", {}),
        write(repo, "releases/v0.1/release.yaml", {"schema": "release/1", "reference_file":
                                                   "reference/v9.yaml", "runs": [f"{run}-gone"]}),
    ]  # fmt: skip
    assert [(f.path, f.rule, f.message) for f in g2_xref(repo, files)] == [
        ("releases/v0.1/release.yaml", "XREF-4", f"run {run}-gone does not exist"),
        ("releases/v0.1/release.yaml", "XREF-4", "reference file does not exist"),
        ("results/v0.1/fake/gone/reviews/c.json", "XREF-3", "names no existing run directory"),
        (f"{run}/run.json", "XREF-1", "unknown system nope"),
        (f"{run}/run.json", "XREF-1", "unknown profile nope"),
    ]


def test_g2_run_directory_size(repo: Path) -> None:
    rel = "results/v0.1/fake/r/logs/prover.log"  # logs are exempt from the per-file limit
    (repo / rel).parent.mkdir(parents=True)
    with (repo / rel).open("wb") as f:
        f.truncate(10 * 1024 * 1024 + 1)
    assert [(f.path, f.rule) for f in g2_size(repo, [rel])] == [("results/v0.1/fake/r", "SIZE-1")]


def test_g5_ratio_scope_and_tier(repo: Path) -> None:
    rel = "results/v0.1/fake/r/run.json"
    q = {"value": 1.0, "unit": "ratio", "grade": "derived", "tier": "reported"}
    rate = f"{rel}#/metrics/rate"
    metrics = {
        "rate": {**q, "unit": "token/s", "grade": "measured", "scope": "steady"},
        "ratio_bad": {**q, "scope": "end_to_end", "source": {"inputs": [rate]}},
        "ratio_ok": {**q, "scope": "steady", "source": {"inputs": [rate]}},
        "ratio_bare": {**q, "source": {"inputs": []}},
        "verified": {**q, "unit": "s", "tier": "verified"},
    }
    write(repo, rel, {"metrics": metrics})
    assert [(f.rule, f.pointer, f.message) for f in g5_labels(repo, [rel])] == [
        ("LBL-1", "/metrics/ratio_bad/scope", "scope must be steady"),
        ("LBL-3", "/metrics/verified/tier", "tier must be reported in run.json"),
    ]


def test_g8_skips_undecodable_file(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "docs/blob.md").write_bytes(b"\xff\xfe")
    assert g8_language(repo, ["docs/blob.md"]) == []


def test_g2_unknown_workload(repo: Path) -> None:
    place(repo, "G2/run-unknown-workload.json", f"{RUN_DIR}/run.json")
    assert ("G2", "XREF-1") in rules(repo)


def test_g2_rate_without_scope(repo: Path) -> None:
    place(repo, "G2/run-rate-without-scope.json", f"{RUN_DIR}/run.json")
    found = [f for f in validate_tree(repo) if f.rule == "SCHEMA"]
    assert any(f.message.startswith("/metrics/rate_prove.steady:") for f in found)


def test_g3_not_canonical(repo: Path) -> None:
    place(repo, "G3/not-canonical.json", "workloads/extra.json")
    assert ("G3", "FMT-1") in rules(repo)


def test_g5_bare_float(repo: Path) -> None:
    place(repo, "G5/manifest-bare-float.json", f"{RUN_DIR}/manifest.json")
    found = [f for f in validate_tree(repo) if f.rule == "LBL-4"]
    assert [f.pointer for f in found] == ["/machine/gpu_clock_mhz"]


def test_g2_size_limit(repo: Path) -> None:
    big = repo / "workloads/blob.bin"
    with big.open("wb") as f:
        f.truncate(5 * 1024 * 1024 + 1)
    git(repo, "add", "-A")
    assert ("G2", "SIZE-1") in rules(repo)


def test_failure_output_sorted_and_formatted(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    place(repo, "G3/not-canonical.json", "workloads/b.json")
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    place(repo, "G2/run-unknown-workload.json", f"{RUN_DIR}/run.json")
    monkeypatch.chdir(repo)
    assert cli.main(["validate"]) == 1
    out = capsys.readouterr()
    lines = out.out.splitlines()
    assert lines == sorted(lines, key=lambda line: (line.split()[0], line.split()[1].encode()))
    line_re = r"^G\d+ \S+ [A-Z0-9-]+: .+$"
    assert all(re.match(line_re, line) for line in lines), lines
    fmt = [line for line in lines if " FMT-1:" in line]
    assert [line.split()[1] for line in fmt] == ["workloads/a.json", "workloads/b.json"]
    assert re.search(r"validate: \d+ failures in \d+ files", out.err)


def test_format_json_fields(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    monkeypatch.chdir(repo)
    assert cli.main(["validate", "--format", "json"]) == 1
    [item] = json.loads(capsys.readouterr().out)
    assert set(item) == {"gate", "path", "pointer", "line", "rule", "message", "hint"}
    assert item["hint"] == "run iproofs fmt workloads/a.json"


def test_fmt_fixes_format(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    monkeypatch.chdir(repo)
    assert cli.main(["fmt", "workloads/a.json"]) == 0
    assert cli.main(["validate"]) == 0


def test_fmt_is_hidden(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert " fmt" not in capsys.readouterr().out


def test_repository_validates() -> None:
    """The repository itself passes every tree gate (warnings do not fail a gate). CRIT-8 needs
    the git objects of the commits the criteria file's reference quotes cite: a shallow clone
    reports them as environment errors, which this test sets apart and skips on, with the reason
    printed, once every other finding is checked (RFC-0016 §Testing Strategy). The validate CI
    jobs fetch full history, so there CRIT-8 runs."""
    shallow = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    failing = [f for f in validate_tree(ROOT) if not f.warning]
    missing = [
        f
        for f in failing
        if shallow == "true" and f.rule == "CRIT-8" and f.kind is ErrorKind.ENVIRONMENT
    ]
    assert [f.line() for f in failing if f not in missing] == []
    if missing:
        pytest.skip(f"shallow clone: {len(missing)} CRIT-8 quotes cite commits not in this clone "
                    "(fetch-depth: 0 runs them)")  # fmt: skip
