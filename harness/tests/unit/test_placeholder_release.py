"""The placeholder frozen release the site is built from until v0.1 (fixtures/placeholder_release).

Every number below is a placeholder fixture value, not a result: the expected digits are the
ones the site's data snapshot printed before #320 (`web/_data/` at 39662bf), recomputed here by
hand from the fixture's raw values (module docstring of the fixture).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures import placeholder_release as ph
from iproofs.validate import check_derived

ROOT = Path(__file__).resolve().parents[3]
INDEX = "releases/v0.1/index.json"


def frozen(root: Path, *, extras: bool = False) -> dict[str, Any]:
    ph.build_placeholder(root, extras=extras)
    assert ph.freeze_tree(root) == 0  # the real gates G2 to G7 pass on the placeholder runs
    doc = json.loads((root / INDEX).read_text())
    assert isinstance(doc, dict)
    return doc


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("placeholder")
    frozen(root)
    return root


@pytest.fixture(scope="module")
def extras(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("placeholder-extras")
    frozen(root, extras=True)
    return root


def index(root: Path) -> dict[str, Any]:
    doc = json.loads((root / INDEX).read_text())
    assert isinstance(doc, dict)
    return doc


def config(doc: dict[str, Any], system: str, workload: str = ph.WORKLOAD,
           configuration: str | None = None) -> dict[str, Any]:  # fmt: skip
    found = [c for c in doc["configurations"] if c["system"] == system
             and c["workload"]["id"] == workload
             and (configuration is None or c["configuration"] == configuration)]  # fmt: skip
    assert len(found) == 1, (system, workload, configuration)
    out = found[0]
    assert isinstance(out, dict)
    return out


def test_four_configurations(tree: Path) -> None:
    doc = index(tree)
    got = sorted((c["system"], c["configuration"], c["workload"]["id"], c["profile"])
                 for c in doc["configurations"])  # fmt: skip
    assert got == [
        ("flashprove", "exact-match-cp-verify", ph.WORKLOAD, ph.PROFILE),
        ("ref-recompute", None, ph.WORKLOAD, ph.PROFILE),
        ("ref-serve", None, ph.WORKLOAD, ph.PROFILE),
        ("sash", "sound-defaults", ph.WORKLOAD, ph.PROFILE),
    ]


def test_two_freezes_byte_identical(tree: Path, tmp_path: Path) -> None:
    """CLI-4: the same inputs give the same index bytes, wherever the tree is built."""
    frozen(tmp_path)
    assert (tmp_path / INDEX).read_bytes() == (tree / INDEX).read_bytes()


def test_sash_failed_and_superseded(tree: Path) -> None:
    sash = config(index(tree), "sash")
    first = ph.run_id("sash", ph.WORKLOAD, 1)
    assert sash["ineligible"] == [{"run_id": first, "reasons": [
        f"superseded by {ph.run_id('sash', ph.WORKLOAD, 5)}: {ph.SASH_CORRECTION}"]}]  # fmt: skip
    assert ph.run_id("sash", ph.WORKLOAD, 2) in sash["runs"]  # the failed run is kept, counted
    assert sash["statistics"]["proof_bytes"]["stats"]["n_failed"] == 1
    failed = json.loads((tree / f"results/v0.1/sash/{ph.run_id('sash', ph.WORKLOAD, 2)}/run.json")
                        .read_text())["failure"]  # fmt: skip
    assert (failed["exit_code"], failed["last_lines"][-1]) == (1, ph.SASH_FAILURE["message"])


def test_tokens_covered_per_proof_statistics(tree: Path) -> None:
    """D-TPP through D-STAT: FlashProve's window rule counts the 1,024-token prompt; SASH's
    prompt_plus_output rule counts 1,024 + 1 on this shape (fixture values)."""
    doc = index(tree)
    for system, want, failed in (("flashprove", 1024.0, 0), ("sash", 1025.0, 1)):
        q = config(doc, system)["statistics"]["tokens_covered_per_proof"]
        assert q["value"] == want
        assert q["stats"] == {"n": 3, "n_failed": failed, "mean": want, "stdev": 0.0,
                              "min": want, "max": want}  # fmt: skip
        assert (q["unit"], q["scope"], q["grade"]) == ("token", None, "derived")


def test_agreement_null_not_measurable(tree: Path) -> None:
    """RFC-0015 NM-1: every ref-recompute run failed with `resource`."""
    doc = index(tree)
    for system in ("flashprove", "sash"):
        stats = config(doc, system)["statistics"]
        for metric in ("agreement_rate", "overhead_vs_serving_prove.session"):
            q = stats[metric]
            assert (q["value"], q["null_reason"]) == (None, "not_measurable_on_profile"), metric


def test_reference_all_failed(tree: Path) -> None:
    doc = index(tree)
    for system in ("ref-serve", "ref-recompute"):
        c = config(doc, system)
        assert c["statistics"] == {}
        assert c["insufficient_repetitions"] is True
        assert len(c["runs"]) == 3
    for n in (1, 2, 3):
        run = json.loads((tree / f"results/v0.1/ref-serve/{ph.run_id('ref-serve', ph.WORKLOAD, n)}"
                          "/run.json").read_text())  # fmt: skip
        assert run["failure"]["kind"] == "resource"
        assert run["failure"]["last_lines"] == []  # no invented log line


def test_ref_recompute_pairs_both_provers(tree: Path) -> None:
    sources = set()
    for n in (1, 2, 3):
        rid = ph.run_id("ref-recompute", ph.WORKLOAD, n)
        manifest = json.loads((tree / f"results/v0.1/ref-recompute/{rid}/manifest.json")
                              .read_text())  # fmt: skip
        sources.add(manifest["prompts_from"].split("-")[3])
    assert sources == {"flashprove", "sash"}


def test_placeholder_digits(tree: Path) -> None:
    """The figures keep the digits the site printed (4 significant digits, fixture values):
    FlashProve 18.78 MB, 3.120 s, 103.6 token/s, 0.01150 USD/1k, 2,411 s commit; SASH
    19.80 GB, 121.3 s, 0.8511 token/s, 1.400 USD/1k, 64.37 s commit."""
    doc = index(tree)
    want = {
        "flashprove": {"proof_bytes": "1.878e+07", "verify_seconds": "3.12",
                       "rate_prove.session": "103.6", "cost_per_1k_tokens_prove.session": "0.0115",
                       "commit_seconds": "2411"},
        "sash": {"proof_bytes": "1.98e+10", "verify_seconds": "121.3",
                 "rate_prove.session": "0.8511", "cost_per_1k_tokens_prove.session": "1.4",
                 "commit_seconds": "64.37"},
    }  # fmt: skip
    for system, metrics in want.items():
        stats = config(doc, system)["statistics"]
        assert {m: f"{stats[m]['value']:.4g}" for m in metrics} == metrics, system


def test_control_counts(tree: Path) -> None:
    """Today's tallies, stored per outcome (RFC-0008); SASH adds its accepted weakened prover."""
    counts = {c["system"]: c["counts"] for c in index(tree)["controls"]}
    assert counts["flashprove"] == {"rejected": 6, "accepted": 0, "no_verdict": 0,
                                    "invalid_call": 1, "void": 0, "not_applicable": 3,
                                    "error": 0, "prover_failed": 0}  # fmt: skip
    assert counts["sash"] == {"rejected": 5, "accepted": 1, "no_verdict": 0, "invalid_call": 1,
                              "void": 0, "not_applicable": 3, "error": 0,
                              "prover_failed": 1}  # fmt: skip
    assert all(c["outside_expected"] == [] for c in index(tree)["controls"])


def test_every_run_derives_clean(tree: Path) -> None:
    """G4: every derived value of every placeholder run recomputes from its inputs."""
    runs = sorted(tree.glob("results/v0.1/*/*/run.json"))
    assert len(runs) == 3 + 5 + 3 + 3
    for path in runs:
        assert check_derived(path, tree) == [], path


def test_tree_local_edit_only(tree: Path) -> None:
    """SASH joins the Maverick workload in the tree's copies only; the real files keep it out."""
    copy = yaml.safe_load((tree / f"workloads/{ph.WORKLOAD}.yaml").read_text())
    real = yaml.safe_load((ROOT / f"workloads/{ph.WORKLOAD}.yaml").read_text())
    assert "sash" in copy["systems"]
    assert "sash" not in real["systems"]
    sash = yaml.safe_load((tree / "systems/sash/system.yaml").read_text())
    assert ph.WORKLOAD in sash["workloads"]
    assert (tree / f"workloads/{ph.WORKLOAD}.yaml").read_text().startswith("# RFC-0003")


def test_deployed_build_has_no_extras(tree: Path) -> None:
    """No page of the deployed build puts words in a team's name: no reply, no target."""
    release = yaml.safe_load((tree / "releases/v0.1/release.yaml").read_text())
    assert release["replies"] == {}
    assert release["superseded_runs"] == []
    assert not (tree / "targets").exists()
    criteria = json.loads((tree / "web/_data/criteria.json").read_text())
    assert criteria == json.loads((ROOT / "web/_data/criteria.json").read_text())
    assert not (tree / "web/shots").exists()


def test_tree_copies_tracked_web_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only web/'s tracked files enter the tree: an untracked `.vercel/` or `.env` file, or an
    ignored picture, stays out (it would be committed into the tree's repository)."""
    repo = tmp_path / "repo"
    (repo / "web/og").mkdir(parents=True)
    (repo / "web/index.html").write_text("tracked")
    (repo / "web/shots").mkdir()
    (repo / "web/shots/a.png").write_text("tracked, skipped")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "web"], check=True)
    (repo / "web/.vercel").mkdir()
    (repo / "web/.vercel/project.json").write_text("untracked")
    (repo / "web/.env.local").write_text("untracked")
    (repo / "web/og/stray.png").write_text("untracked")
    monkeypatch.setattr(ph, "ROOT", repo)
    ph._copy_web(tmp_path / "out")
    got = sorted(p.relative_to(tmp_path / "out").as_posix()
                 for p in (tmp_path / "out").rglob("*") if p.is_file())  # fmt: skip
    assert got == ["index.html"]


def test_extras_cases(extras: Path) -> None:
    """Every extras case of the #320 plan §4 is in the index or the tree."""
    doc = index(extras)
    fp = config(doc, "flashprove", configuration="exact-match-cp-verify")
    reasons = {i["run_id"].rsplit("-", 1)[1]: i["reasons"] for i in fp["ineligible"]}
    assert reasons["101"] == ["harness_dirty"]
    assert reasons["102"][0].startswith("superseded: fixture")
    config(doc, "flashprove", ph.SECOND_WORKLOAD)  # a second workload on the same model
    # one card per system: a second card has no criteria row of its own until #318
    assert len([c for c in doc["claim_cards"] if c["system"] == "flashprove"]) == 1
    outside = {(c["system"], o["control_id"]) for c in doc["controls"]
               for o in c["outside_expected"]}  # fmt: skip
    assert outside == {("flashprove", "C1"), ("sash", "C2")}
    assert fp["evidence"]["reviews"]
    assert fp["evidence"]["reproductions"]
    assert fp["effective_tier"] == "reproduced"
    assert [t["target"] for t in doc["targets"]] == [ph.TARGET] * 2  # the two on its workload
    release = yaml.safe_load((extras / "releases/v0.1/release.yaml").read_text())
    assert release["replies"] == {"sash": ph.REPLY}
    assert "written by no SASH maintainer" in (extras / ph.REPLY).read_text()
    criteria = json.loads((extras / "web/_data/criteria.json").read_text())
    assert criteria["release"] == "v0.1"
    rows = {r["id"]: r for r in criteria["rows"]}
    assert rows["sash"]["disclosures"][0]["state"] == "pending"
    cell = rows["flashprove"]["cells"]["whole_output"]
    assert (cell["stated"], cell["state"]) == ("partly", "no")
    assert cell["contradicted_by"] == [{"control": "C1", "run_id": ph.run_id(
        "flashprove", ph.WORKLOAD, 1)}]  # fmt: skip


def test_repetitions_scale(tmp_path: Path) -> None:
    ph.build_placeholder(tmp_path, repetitions=4)
    assert len(list(tmp_path.glob("results/v0.1/flashprove/*"))) == 4
    assert len(list(tmp_path.glob("results/v0.1/sash/*"))) == 4 + 2  # failed, superseded
    with pytest.raises(ValueError, match="at least 1"):
        ph.build_placeholder(tmp_path / "none", repetitions=0)


def test_refuses_when_a_release_is_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """From #146 the site comes from `iproofs site build` at the root, not the placeholder."""
    (tmp_path / "releases/v0.1").mkdir(parents=True)
    (tmp_path / INDEX).write_text("{}\n")
    monkeypatch.setattr(ph, "ROOT", tmp_path)
    assert ph.main(["--site", str(tmp_path / "out")]) == 1
    assert "iproofs site build" in capsys.readouterr().err


# The site.yml build step, `PYTHONPATH=harness/tests uv run python <SITE_ARGS> web`, which
# test_site_command_runs runs and test_site_workflow_runs_this_command holds site.yml to.
SITE_ARGS = ("-m", "fixtures.placeholder_release", "--site")
# What the build reads, so a change to any of it runs site.yml: the placeholder tree's copies
# (`COPY`, the systems, web/), the release records, the harness and its fixtures, and the
# pytest plugin `uv run pytest web` loads (pyproject addopts).
SITE_INPUTS = {"systems/**", "workloads/**", "releases/**", "results/**", "targets/**",
               "harness/src/iproofs/**", "harness/tests/fixtures/**", "web/**",
               "harness/tests/quarantine_plugin.py", "pyproject.toml", "uv.lock",
               ".github/workflows/site.yml"}  # fmt: skip


def test_site_workflow_runs_this_command() -> None:
    """site.yml builds with the command test_site_command_runs runs, and runs on a change to
    any input of the build, on pull requests and on main alike."""
    doc = yaml.safe_load((ROOT / ".github/workflows/site.yml").read_text())
    on = doc.get("on", doc.get(True))  # YAML 1.1 reads the key `on` as true
    steps = doc["jobs"]["built"]["steps"]
    build = next(s for s in steps if "fixtures.placeholder_release" in s.get("run", ""))
    assert build["run"] == f"PYTHONPATH=harness/tests uv run python {' '.join(SITE_ARGS)} web"
    assert on["pull_request"]["paths"] == on["push"]["paths"]
    paths = set(on["push"]["paths"])
    # a top-level file by its name (MAINTAINERS.md), anything else by its top folder
    copied = {c if "/" not in c and (ROOT / c).is_file() else f"{c.split('/')[0]}/**"
              for c in ph.COPY}  # fmt: skip
    assert copied | SITE_INPUTS <= paths, sorted(copied | SITE_INPUTS - paths)


@pytest.mark.skipif(
    "def render(" not in (ROOT / "web/build.py").read_text(),
    reason="iproofs site build calls the web/build.py renderer from step B2 of #320",
)
def test_site_command_runs(tmp_path: Path) -> None:
    """The exact site.yml command, in a subprocess: exits 0 and writes index.html."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(ROOT / "harness/tests"), env.get("PYTHONPATH")) if p
    )
    out = tmp_path / "site"
    done = subprocess.run(
        [sys.executable, *SITE_ARGS, str(out)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=600,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    assert (out / "index.html").is_file()
