"""Proof archive upload (RFC-0014 §Proof digests and archive, RFC-0009 Q1).

Each configuration's archived proof, and the upstream inputs its adapter fetched, are uploaded
to the project's archive dataset before the results pull request. Every stored object is
checked against its digest, and the run's `manifest.proofs[].archive` gets a URI pinned to the
dataset commit, so the bytes behind a URI never change. Results are append-only (APP-1), so this
runs on the GPU host before the run directory is committed.
"""

import json
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json

ARCHIVE_REPO = "ai-verification-observatory/inference-proofs-archive"


class Store(Protocol):
    def put(self, local: Path, path: str) -> str:
        """Upload `local` to `path`; returns the 40-hex commit that holds it."""
        ...

    def sha256(self, path: str, revision: str) -> str | None:
        """Hex sha256 of the object at `path` and `revision`, or None if there is none."""
        ...

    def uri(self, path: str, revision: str) -> str: ...


@dataclass(frozen=True, slots=True)
class HubStore:
    """A public dataset repository on the Hugging Face Hub (RFC-0009 Q1)."""

    repo: str = ARCHIVE_REPO
    token: str | None = None

    def put(self, local: Path, path: str) -> str:
        from huggingface_hub import HfApi  # noqa: PLC0415 (optional extra, INV-ARCH-6)

        info = HfApi(token=self.token).upload_file(
            path_or_fileobj=str(local), path_in_repo=path, repo_id=self.repo,
            repo_type="dataset", commit_message=f"Archive {path}",
        )  # fmt: skip
        return str(info.oid)

    def sha256(self, path: str, revision: str) -> str | None:
        from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415

        api = HfApi(token=self.token)
        found = api.get_paths_info(self.repo, [path], revision=revision, repo_type="dataset")
        if not found:
            return None
        lfs = getattr(found[0], "lfs", None)
        if lfs is not None:
            return str(lfs.sha256)
        with tempfile.TemporaryDirectory() as tmp:  # a small file is stored without LFS
            local = hf_hub_download(self.repo, path, repo_type="dataset", revision=revision,
                                    local_dir=tmp, token=self.token)  # fmt: skip
            return file_digest(Path(local)).removeprefix("sha256:")

    def uri(self, path: str, revision: str) -> str:
        return f"https://huggingface.co/datasets/{self.repo}/resolve/{revision}/{path}"


def _integrity(message: str) -> IProofsError:
    return IProofsError(ErrorKind.INTEGRITY, message)


def _put_checked(store: Store, local: Path, path: str, digest: str) -> str:
    """Upload, then read the stored object's digest back; returns the pinned URI."""
    commit = store.put(local, path)
    if store.sha256(path, commit) != digest.removeprefix("sha256:"):
        raise _integrity(f"{path}: the stored object does not match {digest}")
    return store.uri(path, commit)


def _run_dir(results: Path, release: str, system: str, tar: Path) -> Path:
    runs = [d for d in (results / release / system).iterdir() if tar.name.startswith(d.name + "-")]
    if len(runs) != 1:
        raise IProofsError(ErrorKind.CONFIG, f"{tar}: no single run directory matches its name")
    return runs[0]


def upload_archives(results: Path, store: Store, registry: SchemaRegistry) -> list[str]:
    """Upload every proof archive under `results/.archive/` whose manifest has no URI yet, and
    record the URI. Returns the manifest paths it changed."""
    changed = []
    base = results / ".archive"
    for tar in sorted(base.glob("*/*/*/*/*.tar")):
        release, system, _workload, _profile = tar.parent.relative_to(base).parts
        run_dir = _run_dir(results, release, system, tar)
        proof_id = tar.name.removeprefix(run_dir.name + "-").removesuffix(".tar")
        lines = dict(
            line.split("\t", 1) for line in (run_dir / "digests.txt").read_text().splitlines()
        )
        digest = lines.get(f"archive/{proof_id}.tar")
        if digest is None:
            raise _integrity(f"{run_dir}/digests.txt has no line for archive/{proof_id}.tar")
        if file_digest(tar) != digest:
            raise _integrity(f"{tar} differs from its digests.txt line {digest}")
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        entry = next((p for p in manifest["proofs"] if p["proof_id"] == proof_id), None)
        if entry is None:
            raise IProofsError(ErrorKind.CONFIG, f"{manifest_path} lists no proof {proof_id}")
        if entry["archive"]:
            continue
        entry["archive"] = _put_checked(store, tar, tar.relative_to(base).as_posix(), digest)
        if errors := registry.errors("manifest/1", manifest):
            raise IProofsError(ErrorKind.INTERNAL, f"{manifest_path}: {errors[0]}")
        write_json(manifest_path, manifest)
        changed.append(manifest_path.as_posix())
    return changed


def _download(url: str, out: Path) -> None:
    if not url.startswith("https://"):
        raise IProofsError(ErrorKind.CONFIG, f"inputs.lock URL {url!r} is not https")
    with urllib.request.urlopen(url, timeout=60) as response, out.open("wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)


def _lock_at(root: Path, commit: str, system: str) -> list[tuple[str, str, str]]:
    """`systems/<system>/inputs.lock` at the adapter commit: (name, url, digest) rows."""
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:systems/{system}/inputs.lock"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if shown.returncode != 0:
        raise IProofsError(ErrorKind.CONFIG, f"no systems/{system}/inputs.lock at {commit}")
    rows = [line.split("\t") for line in shown.stdout.splitlines() if line and line[0] != "#"]
    if any(len(r) != 3 for r in rows):
        raise IProofsError(ErrorKind.CONFIG, f"systems/{system}/inputs.lock: malformed line")
    return [(r[0], r[1], r[2]) for r in rows]


def upload_sources(
    root: Path,
    results: Path,
    store: Store,
    fetch: Callable[[str, Path], object] = _download,
) -> list[str]:
    """RFC-0014 Q3: the upstream inputs of each archived configuration's adapter, stored next to
    the proofs at `<release>/sources/<system>/<name>`, each checked against inputs.lock before
    and after upload. Returns the URIs it uploaded; inputs already stored are skipped."""
    done = []
    base = results / ".archive"
    seen = set()
    for tar in sorted(base.glob("*/*/*/*/*.tar")):
        release, system = tar.parent.relative_to(base).parts[:2]
        run_dir = _run_dir(results, release, system, tar)
        commit = json.loads((run_dir / "manifest.json").read_text())["system"]["adapter_commit"]
        for name, url, digest in _lock_at(root, str(commit), system):
            path = f"{release}/sources/{system}/{name}"
            if path in seen or store.sha256(path, "main") == digest.removeprefix("sha256:"):
                continue
            seen.add(path)
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / name
                fetch(url, local)
                if file_digest(local) != digest:
                    raise _integrity(f"{url} differs from inputs.lock {digest}")
                done.append(_put_checked(store, local, path, digest))
    return done
