"""A deterministic fixture release for `iproofs release freeze` (RFC-0009).

`build(root, runs)` writes a repository with the fake system pinned to an image, `runs`
synthetic fake runs (fixtures/synthetic_tree.py) made eligible, a claim card and
`releases/v0.1/release.yaml`, committed with fixed author dates so every build gives the same
commit hashes and so the same `index.json` bytes. Of the runs, the second-to-last has a dirty
harness (ineligible) and the last is withdrawn in `superseded_runs`.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

from fixtures.synthetic_tree import generate
from iproofs.provenance import file_digest
from iproofs.serialize import write_json

ROOT = Path(__file__).resolve().parents[3]
COPY = ["schema", "systems/fake", "workloads/fake-tiny-ci.yaml", "reference",
        "harness/tests/fixtures/prompts"]  # fmt: skip
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "ab" * 32
GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2027-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2027-01-01T00:00:00Z",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}  # fmt: skip


def git(root: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    done = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, env=env)  # fmt: skip
    return done.stdout.strip()


def commit(root: Path, message: str, *paths: str) -> str:
    git(root, "add", *(paths or ("-A",)))
    git(root, "commit", "-qm", message, "--no-gpg-sign")
    return git(root, "rev-parse", "HEAD")


def build(root: Path, runs: int = 5) -> Path:
    for rel in COPY:
        src, dst = ROOT / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    system = yaml.safe_load((root / "systems/fake/system.yaml").read_text())
    repository, _, digest = IMAGE.partition("@")
    system["image"] = {"repository": repository, "digest": digest}
    (root / "systems/fake/system.yaml").write_text(yaml.safe_dump(system, sort_keys=False))
    git(root, "init", "-q", "-b", "main")
    adapter = commit(root, "adapter", "systems/fake/system.yaml")  # only it: a stable hash
    card = root / "systems/fake/claims/default.yaml"
    card.parent.mkdir(parents=True)
    card.write_text("# fixture claim card, read only for its digest\n")
    dirs = generate(root, runs)
    for i, d in enumerate(dirs):
        m = json.loads((d / "manifest.json").read_text())
        m["system"] |= {"adapter_commit": adapter, "claim_digest": file_digest(card),
                        "image": {"ref": IMAGE, "digest_kind": "manifest"}}  # fmt: skip
        m["proofs"][0]["archive"] = "https://archive.example.org/v0.1/fake.tar" if i == 0 else None
        m["harness"]["git_dirty"] = i == len(dirs) - 2
        write_json(d / "manifest.json", m)
    controls = (ROOT / "schema/controls/examples/valid/fake.json").read_text()
    (dirs[0] / "controls.json").write_text(controls.replace(
        "2026-11-20-fake-fake-tiny-ci-ci-cpu-1", dirs[0].name))  # fmt: skip
    release = yaml.safe_load((ROOT / "schema/release/examples/valid/v0.1.yaml").read_text())
    release |= {
        "runs": [d.relative_to(root).as_posix() for d in dirs],
        "superseded_runs": [{"run_id": dirs[-1].name, "reason": "wrong CPU binding"}],
        "claim_cards": [{"system": "fake", "configuration": "default", "card_version": 1,
                         "path": "systems/fake/claims/default.yaml",
                         "digest": file_digest(card)}],
        "replies": {"fake": "systems/fake/replies/v0.1.md"},
    }  # fmt: skip
    path = root / "releases/v0.1/release.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(release, sort_keys=False))
    commit(root, "runs")
    return path
