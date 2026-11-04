"""RFC-0014 §Proof digests and archive with RFC-0009 Q1: uploads are checked against their
digests and the manifest records a URI pinned to the store's commit."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.archive import _download, upload_archives, upload_sources
from iproofs.errors import ErrorKind, IProofsError
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
COMMIT = "c" * 40


class MemoryStore:
    """A store kept in memory; `corrupt` makes every stored object read back wrong."""

    def __init__(self, corrupt: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.corrupt = corrupt

    def put(self, local: Path, path: str) -> str:
        self.objects[path] = local.read_bytes() + (b"x" if self.corrupt else b"")
        return COMMIT

    def sha256(self, path: str, revision: str) -> str | None:
        data = self.objects.get(path)
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def uri(self, path: str, revision: str) -> str:
        return f"https://store.example/{revision}/{path}"


@pytest.fixture(scope="module")
def stored(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """results/ with one completed fake run and its archived proof."""
    out = tmp_path_factory.mktemp("results")
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    runner.run(JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(out), "v0.1"))
    return out


@pytest.fixture
def results(stored: Path, tmp_path: Path) -> Path:
    shutil.copytree(stored, tmp_path / "results")
    return tmp_path / "results"


def manifest(results: Path) -> tuple[Path, dict[str, object]]:
    path = next(results.glob("v0.1/fake/*/manifest.json"))
    return path, json.loads(path.read_text())


def test_upload_records_pinned_uri(results: Path) -> None:
    store = MemoryStore()
    path, _ = manifest(results)
    assert upload_archives(results, store, REGISTRY) == [path.as_posix()]
    tar = next(results.glob(".archive/v0.1/fake/fake-tiny-ci/ci-cpu/*.tar"))
    key = tar.relative_to(results / ".archive").as_posix()
    assert store.objects[key] == tar.read_bytes()
    proofs = manifest(results)[1]["proofs"]
    assert isinstance(proofs, list)
    assert [p["archive"] for p in proofs if p["archive"]] == [
        f"https://store.example/{COMMIT}/{key}"
    ]
    assert upload_archives(results, store, REGISTRY) == []  # already archived: nothing to do


def test_changed_archive_refused(results: Path) -> None:
    tar = next(results.glob(".archive/**/*.tar"))
    tar.write_bytes(tar.read_bytes() + b"\0")
    before = manifest(results)[0].read_bytes()
    with pytest.raises(IProofsError) as err:
        upload_archives(results, MemoryStore(), REGISTRY)
    assert err.value.kind == ErrorKind.INTEGRITY
    assert manifest(results)[0].read_bytes() == before


def test_stored_object_checked(results: Path) -> None:
    before = manifest(results)[0].read_bytes()
    with pytest.raises(IProofsError, match="does not match"):
        upload_archives(results, MemoryStore(corrupt=True), REGISTRY)
    assert manifest(results)[0].read_bytes() == before


def adapter_repo(tmp_path: Path, digest: str) -> str:
    """A repository whose fake inputs.lock lists one input; returns its commit."""
    repo = tmp_path / "repo"
    (repo / "systems/fake").mkdir(parents=True)
    (repo / "systems/fake/inputs.lock").write_text(
        f"# comment\nsrc.tar.gz\thttps://example.org/src.tar.gz\t{digest}\n"
    )
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "lock", "--no-gpg-sign"], check=True)
    return subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip


def with_commit(results: Path, commit: str) -> None:
    path, doc = manifest(results)
    doc["system"]["adapter_commit"] = commit  # type: ignore[index]
    path.write_text(json.dumps(doc))


def test_sources_stored_next_to_proofs(results: Path, tmp_path: Path) -> None:
    data = b"upstream source"
    with_commit(results, adapter_repo(tmp_path, "sha256:" + hashlib.sha256(data).hexdigest()))
    store = MemoryStore()
    fetched = []

    def fetch(url: str, out: Path) -> None:
        fetched.append(url)
        out.write_bytes(data)

    assert upload_sources(tmp_path / "repo", results, store, fetch) == [
        f"https://store.example/{COMMIT}/v0.1/sources/fake/src.tar.gz"
    ]
    assert upload_sources(tmp_path / "repo", results, store, fetch) == []  # already stored
    assert fetched == ["https://example.org/src.tar.gz"]


def test_source_with_wrong_hash_refused(results: Path, tmp_path: Path) -> None:
    with_commit(results, adapter_repo(tmp_path, "sha256:" + "0" * 64))
    with pytest.raises(IProofsError, match=r"differs from inputs\.lock"):
        upload_sources(tmp_path / "repo", results, MemoryStore(),
                       lambda url, out: out.write_bytes(b"other"))  # fmt: skip


def test_download_needs_https(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match="not https"):
        _download("file:///etc/hosts", tmp_path / "x")


def test_cli_prints_changes(
    results: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from iproofs import archive, cli  # noqa: PLC0415

    store = MemoryStore()
    monkeypatch.setattr(archive, "HubStore", lambda repo, token: store)
    monkeypatch.chdir(ROOT)
    assert cli.main(["archive", "upload", "--results", str(results)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"inputs": [], "manifests": [manifest(results)[0].as_posix()]}  # fake: no inputs
