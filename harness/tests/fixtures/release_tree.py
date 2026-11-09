"""A deterministic fixture release for `iproofs release freeze` (RFC-0009).

`build(root, runs)` writes a repository with the fake system pinned to an image, `runs`
synthetic fake runs (fixtures/synthetic_tree.py) made eligible, a claim card and
`releases/v0.1/release.yaml`, committed with fixed author dates so every build gives the same
commit hashes and so the same `index.json` bytes. Of the runs, the second-to-last has a dirty
harness (ineligible) and the last is withdrawn in `superseded_runs`.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from fixtures.repo import commit, git
from fixtures.synthetic_tree import generate
from iproofs.provenance import file_digest
from iproofs.serialize import write_json

ROOT = Path(__file__).resolve().parents[3]
COPY = ["schema", "systems/fake", "workloads/fake-tiny-ci.yaml", "reference",
        "harness/tests/fixtures/prompts"]  # fmt: skip
IMAGE = "ghcr.io/ai-verification-observatory/iproofs-fake@sha256:" + "ab" * 32
__all__ = ["build", "commit", "git"]  # tests import commit and git from here


def build(
    root: Path,
    runs: int = 5,
    card_text: str | None = None,
    systems: dict[str, dict[str, Any]] | None = None,
) -> Path:
    for rel in COPY:
        src, dst = ROOT / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    system = yaml.safe_load((root / "systems/fake/system.yaml").read_text())
    repository, _, digest = IMAGE.partition("@")
    system["image"] = {"repository": repository, "digest": digest}
    (root / "systems/fake/system.yaml").write_text(yaml.safe_dump(system, sort_keys=False))
    for name, doc in (systems or {}).items():
        (root / f"systems/{name}").mkdir(parents=True, exist_ok=True)
        (root / f"systems/{name}/system.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    git(root, "init", "-q", "-b", "main")
    pinned = ["systems/fake/system.yaml", *(f"systems/{n}/system.yaml" for n in systems or {})]
    adapter = commit(root, "adapter", *pinned)  # a root commit of these files only: stable
    card = root / "systems/fake/claims/default.yaml"
    card.parent.mkdir(parents=True)
    card.write_text(card_text or "# fixture claim card, read only for its digest\n")
    dirs = generate(root, runs)
    for i, d in enumerate(dirs):
        m = json.loads((d / "manifest.json").read_text())
        m["system"] |= {"adapter_commit": adapter, "claim_digest": file_digest(card),
                        "image": {"ref": IMAGE, "digest_kind": "manifest"}}  # fmt: skip
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
    }  # fmt: skip
    path = root / "releases/v0.1/release.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(release, sort_keys=False))
    commit(root, "runs")
    return path
