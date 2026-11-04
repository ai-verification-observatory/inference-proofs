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
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from fixtures.synthetic_tree import generate
from iproofs.provenance import file_digest
from iproofs.serialize import write_json

ROOT = Path(__file__).resolve().parents[3]
COPY = ["schema", "systems/fake", "workloads/fake-tiny-ci.yaml", "reference",
        "harness/tests/fixtures/prompts", "site/templates"]  # fmt: skip
IMAGE = "ghcr.io/ai-verification-observatory/iproofs-fake@sha256:" + "ab" * 32
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
    reply = root / "systems/fake/replies/v0.1.md"
    reply.parent.mkdir(parents=True)
    reply.write_text("The fake system is test data; its numbers mean nothing.\n")
    path = root / "releases/v0.1/release.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(release, sort_keys=False))
    commit(root, "runs")
    return path


CARD = """# fixture claim card for the site golden files
claim_class: "next-token/exact-match/committed-weights"
coverage: {phase: "prefill"}
relation: "not stated"
"""
MAINTAINERS = """# Maintainers

| Handle | Role | Organisation | Systems maintained | Declared interests | Since |
|---|---|---|---|---|---|
| example-a | maintainer | Example Lab A | none | none | 2027-01-01 |
| example-b | system maintainer | Example Lab B | fake-broken | builds fake-broken | 2027-01-01 |
"""
TARGET = """schema: "target/1"
id: "session-under-2s"
author: {name: "Example Lab", affiliation: "Example Lab"}
date: "2027-01-10"
metric: "prove_session_seconds"
comparator: "<="
threshold:
  value: 2
  unit: "s"
  scope: "prove.session"
  grade: "asserted"
  tier: "reported"
  source: {kind: "reference_file", ref: "targets/example-lab/session-under-2s.yaml#/threshold"}
  null_reason: null
claim_class: "*/exact-match/*"
rationale: "A fixture target for the site golden files."
"""


def clone(src: Path, system: str, run_id: str, edit: Callable[[dict[str, Any]], None]) -> Path:
    """Copy a run directory to `system` under a new run id, then edit its manifest."""
    dst = src.parents[1] / system / run_id
    dst.mkdir(parents=True)
    old = f"results/v0.1/{src.parent.name}/{src.name}"
    for name in ("run.json", "manifest.json"):
        text = (src / name).read_text().replace(old, f"results/v0.1/{system}/{run_id}")
        doc = json.loads(text.replace(src.name, run_id))
        doc["system"] = system if name == "run.json" else doc["system"]
        if name == "manifest.json":
            doc["system"]["name"] = system
            edit(doc)
        write_json(dst / name, doc)
    return dst


def build_rich(root: Path) -> Path:
    """The site fixture: `build` plus a second fake system, a ref-serve reference row, a
    failed repetition, a target and claim cards with a claim class."""
    broken_image, ref_image = (IMAGE.replace("ab" * 32, x * 32) for x in ("cd", "ef"))
    broken_system = yaml.safe_load((ROOT / "systems/fake-broken/system.yaml").read_text())
    repository, _, digest = broken_image.partition("@")
    broken_system["image"] = {"repository": repository, "digest": digest}
    ref_system = yaml.safe_load(
        (ROOT / "schema/system/examples/valid/ref-serve-shape.yaml").read_text())  # fmt: skip
    ref_system["engine"]["image"] = ref_image
    ref_system["workloads"] = [{"id": "fake-tiny-ci", "precision_used": "int8",
                                "precision_substitution": None, "engine_args": []}]  # fmt: skip
    path = build(root, card_text=CARD,
                 systems={"fake-broken": broken_system, "ref-serve": ref_system})  # fmt: skip
    adapter = git(root, "rev-list", "--max-parents=0", "HEAD")
    card = root / "systems/fake-broken/claims/default.yaml"
    card.parent.mkdir(parents=True)
    card.write_text(CARD.replace("fixture claim card", "fixture claim card of fake-broken"))
    fake = sorted((root / "results/v0.1/fake").iterdir())

    def broken(m: dict[str, Any]) -> None:
        m["system"] |= {"adapter_commit": adapter, "claim_digest": file_digest(card), "image": {
            "ref": broken_image, "digest_kind": "manifest"}}  # fmt: skip
        m["claim"]["system"] = "fake-broken"

    def ref(m: dict[str, Any]) -> None:
        m["system"] |= {"adapter_commit": adapter, "claim_digest": None, "image": {
            "ref": ref_image, "digest_kind": "manifest"}}  # fmt: skip
        m["claim"] = None

    added = [clone(src, "fake-broken", src.name.replace("fake-fake", "fake-broken-fake"), broken)
             for src in fake[:3]]  # fmt: skip
    added += [clone(src, "ref-serve", src.name.replace("fake-fake", "ref-serve-fake"), ref)
              for src in fake[:3]]  # fmt: skip
    failed = fake[0].parent / "2026-11-08-fake-fake-tiny-ci-ci-cpu-6"
    failed.mkdir()
    run = json.loads((ROOT / "schema/run/examples/valid/failed-repetition.json").read_text())
    text = json.dumps(run).replace("2026-11-20-fake-fake-tiny-ci-ci-cpu-2", failed.name)
    write_json(failed / "run.json", json.loads(text))
    manifest = json.loads(
        (fake[0] / "manifest.json").read_text().replace(fake[0].name, failed.name)
    )
    manifest["proofs"][0]["archive"] = None
    write_json(failed / "manifest.json", manifest)
    target = root / "targets/example-lab/session-under-2s.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(TARGET)
    release = yaml.safe_load(path.read_text())
    release["runs"] += [d.relative_to(root).as_posix() for d in [*added, failed]]
    release["claim_cards"].append({"system": "fake-broken", "configuration": "default",
                                   "card_version": 1, "path": card.relative_to(root).as_posix(),
                                   "digest": file_digest(card)})  # fmt: skip
    path.write_text(yaml.safe_dump(release, sort_keys=False))
    (root / "MAINTAINERS.md").write_text(MAINTAINERS)
    commit(root, "rich release")
    return path
