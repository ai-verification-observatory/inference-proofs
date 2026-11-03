"""RFC-0014 §Model fetch and verification, against a local fake hub."""

import dataclasses
import io
import json
import shutil
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.log import JsonlLogger
from iproofs.model import Workload
from iproofs.runner import Runner, retry_fetch
from iproofs.schema import SchemaRegistry
from iproofs.workloads import ensure_model, load_workload

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
TOY = ROOT / "systems/fake/model"
TOKEN = "hf_" + "t" * 34  # a token-shaped placeholder, never a real one


def hub_workload() -> Workload:
    """fake-tiny-ci, as if its toy weights were on a public hub."""
    wl = load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)
    source = dataclasses.replace(wl.model.source, hub="huggingface", path=None, repo="org/toy")
    return dataclasses.replace(wl, model=dataclasses.replace(wl.model, source=source))


class Hub:
    """Serves the toy model files; `extra`, `drop` and `corrupt` misbehave."""

    def __init__(self, extra: bool = False, drop: bool = False, corrupt: bool = False) -> None:
        self.extra, self.drop, self.corrupt = extra, drop, corrupt
        self.calls: list[tuple[str, str, list[str], str | None]] = []

    def __call__(
        self, repo: str, revision: str, files: list[str], into: Path, token: str | None
    ) -> None:
        self.calls.append((repo, revision, files, token))
        for name in files[1:] if self.drop else files:
            data = (TOY / name).read_bytes()
            (into / name).write_bytes(data + b"x" if self.corrupt and name == files[-1] else data)
        (into / ".cache").mkdir()  # the hub client's own bookkeeping is not a model file
        if self.extra:
            (into / "README.md").write_text("not in the workload's list\n")


def test_fetch_verify_and_reuse(tmp_path: Path) -> None:
    hub = Hub()
    path = ensure_model(hub_workload(), tmp_path, download=hub, token=TOKEN)
    wl = hub_workload()
    assert path == tmp_path / "models" / wl.model.digest.removeprefix("sha256:")
    assert hub.calls == [("org/toy", wl.model.revision, [f.path for f in wl.model.files], TOKEN)]
    assert not any(p.stat().st_mode & 0o222 for p in [path, *path.iterdir()])  # read-only
    assert ensure_model(wl, tmp_path, download=hub) == path  # rehashed, not fetched again
    assert len(hub.calls) == 1


@pytest.mark.parametrize("hub", [Hub(extra=True), Hub(drop=True), Hub(corrupt=True)])
def test_extra_missing_or_mismatching_file_rejected(tmp_path: Path, hub: Hub) -> None:
    with pytest.raises(IProofsError) as e:
        ensure_model(hub_workload(), tmp_path, download=hub)
    assert e.value.kind is ErrorKind.INTEGRITY
    assert [p.name for p in (tmp_path / "models").iterdir()] == []  # the temporary dir is gone


def test_extra_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match=r"unexpected \['README.md'\]"):
        ensure_model(hub_workload(), tmp_path, download=Hub(extra=True))


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match="missing"):
        ensure_model(hub_workload(), tmp_path, download=Hub(drop=True))


def test_cache_rehash_detects_change_and_quarantines(tmp_path: Path) -> None:
    path = ensure_model(hub_workload(), tmp_path, download=Hub())
    weights = path / "weights.bin"
    weights.chmod(0o644)
    weights.write_bytes(b"\0" * 64)  # a changed file on the runner's disk
    with pytest.raises(IProofsError) as e:
        ensure_model(hub_workload(), tmp_path, download=Hub())
    assert e.value.kind is ErrorKind.INTEGRITY
    assert not path.exists()
    (moved,) = (tmp_path / "quarantine").iterdir()
    assert moved.name.startswith(path.name)  # kept for the runner to see, never refetched


def test_fetch_errors_retry(tmp_path: Path) -> None:
    failures = [IProofsError(ErrorKind.FETCH, "502"), IProofsError(ErrorKind.FETCH, "timeout")]
    hub = Hub()

    def flaky(*args: object) -> None:
        if failures:
            raise failures.pop(0)
        hub(*args)  # type: ignore[arg-type]

    retry = lambda op: retry_fetch(op, "model", sleep=lambda s: None)  # noqa: E731
    assert ensure_model(hub_workload(), tmp_path, download=flaky, retry=retry).is_dir()


def test_token_never_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hub = Hub()
    monkeypatch.setattr("iproofs.workloads.hub_download", hub)
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "cache"))
    runner = Runner(InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY), root=ROOT,
                    registry=REGISTRY)  # fmt: skip
    stream = io.StringIO()
    path = runner._models(hub_workload(), JsonlLogger(stream))
    assert path.is_dir()
    assert hub.calls[0][3] == TOKEN  # only the fetch call gets it
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [e["event"] for e in events] == ["integrity.model_rehash"]
    assert TOKEN not in stream.getvalue()
    assert not any(
        TOKEN in p.read_text(errors="ignore")
        for p in (tmp_path / "cache").rglob("*")
        if p.is_file()
    )
    shutil.rmtree(tmp_path / "cache", ignore_errors=True)
