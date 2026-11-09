"""RFC-0008 §Parts the verifier reads: C5, C6 and C8 choose only among the parts the adapter
declares its verify step reads; a declaration that does not fit the proof is refused.

The hand-made system below is shaped like FlashProve: a proof is `response.proof` and a 4-byte
`response.y`, and its verifier reads `response.proof` only (the claimed token comes from the
harness record). Byte values are test fixtures, not measurements.
"""

import hashlib
import json
import math
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from iproofs import controls as ctl
from iproofs.adapter import InProcessRunner
from iproofs.controls import EVERY_PART, HonestProof, PartsRead, VerifyCall, VerifyResult
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import System, Workload
from iproofs.runner import JobSpec, Runner, controls_for_run
from iproofs.schema import SchemaRegistry
from iproofs.serialize import load_yaml
from iproofs.workloads import load_workload

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
SEED = "0x0123456789abcdef"
COMMIT = "c" * 64
REASON = "verify writes the token file from claimed_output, the harness record"
READS = PartsRead("handmade", frozenset({"response.proof"}), (("response.y", REASON),))


@pytest.fixture(scope="module")
def workload() -> Workload:
    return load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)


def proof_bytes(request: tuple[int, ...], claimed: tuple[int, ...]) -> bytes:
    msg = repr((COMMIT, request, claimed)).encode()
    return hashlib.sha256(msg).digest() + hashlib.sha256(msg[::-1]).digest()


def honest_proofs(tmp: Path) -> tuple[list[HonestProof], dict[str, Path]]:
    proofs, dirs = [], {}
    for i in range(2):
        request, claimed = tuple(range(i, i + 8)), (5 + i,)
        d = tmp / "proofs" / f"req-{i}"
        d.mkdir(parents=True)
        (d / "response.proof").write_bytes(proof_bytes(request, claimed))
        (d / "response.y").write_bytes(claimed[0].to_bytes(4, "little"))
        proofs.append(HonestProof(f"req-{i}", request, claimed, "accept", i, 0))
        dirs[f"req-{i}"] = d
    return proofs, dirs


def reads_proof_only(call: VerifyCall) -> VerifyResult:
    """The hand-made verifier: it never opens `response.y`."""
    path = call.proof_dir / "response.proof"
    if not path.is_file():
        return VerifyResult("invalid_call", 4, "no proof", 0.0)
    ok = call.commitment_id == COMMIT and path.read_bytes() == proof_bytes(
        call.request, call.claimed_output
    )
    return VerifyResult("accept" if ok else "reject", 0 if ok else 1, "YES" if ok else "NO", 0.0)


def suite(tmp: Path, workload: Workload, reads: PartsRead) -> dict[str, dict[str, Any]]:
    proofs, dirs = honest_proofs(tmp)
    records = ctl.run_shared_controls(
        proofs,
        dirs,
        COMMIT,
        None,
        workload=workload,
        seed=SEED,
        verify=reads_proof_only,
        work=tmp / "mutations",
        reads=reads,
    )
    return {str(r["id"]): r for r in records}


def index(cid: str, k: int, m: int) -> int:
    """RFC-0008 §Seeds by hand: floor(r * m), r from random.Random("seed:cid:k")."""
    return math.floor(random.Random(f"{SEED}:{cid}:{k}").random() * m)


def test_c6_chooses_only_read_parts(tmp_path: Path) -> None:
    _, dirs = honest_proofs(tmp_path)
    src, target = dirs["req-0"], HonestProof("req-0", (), (), "accept", 0, 0)
    every = ["response.proof", "response.y"]  # sorted by name
    for s in range(ctl.C6_TRIALS):
        undeclared = ctl.c6(target, COMMIT, src, tmp_path / f"all-{s}", SEED, s)
        assert undeclared.mutation["part"] == every[index("C6", 2 * s, 2)]  # unchanged rule
        declared = ctl.c6(target, COMMIT, src, tmp_path / f"read-{s}", SEED, s, READS)
        assert declared.mutation["part"] == "response.proof"  # the read list, one entry
        size = (src / "response.proof").stat().st_size
        assert declared.mutation["bit_offset"] == index("C6", 2 * s + 1, size * 8)  # same seeds
        assert (declared.proof_dir / "response.y").read_bytes() == (src / "response.y").read_bytes()
    # with this seed the undeclared suite flips response.y in at least one trial
    assert any(index("C6", 2 * s, 2) == 1 for s in range(ctl.C6_TRIALS))


def test_c6_read_list_sorted_by_name(tmp_path: Path) -> None:
    _, dirs = honest_proofs(tmp_path)
    src = dirs["req-0"]
    (src / "a.bin").write_bytes(b"a" * 16)
    reads = PartsRead("handmade", frozenset({"a.bin", "response.proof"}), (("response.y", REASON),))
    target = HonestProof("req-0", (), (), "accept", 0, 0)
    for s in range(ctl.C6_TRIALS):
        call = ctl.c6(target, COMMIT, src, tmp_path / f"c6-{s}", SEED, s, reads)
        assert call.mutation["part"] == ["a.bin", "response.proof"][index("C6", 2 * s, 2)]


def test_c5_truncates_largest_read_part(tmp_path: Path) -> None:
    src = tmp_path / "p"
    src.mkdir()
    for name, data in {"a.bin": b"abcdefgh", "b.bin": b"12345678", "y.bin": b"y" * 100}.items():
        (src / name).write_bytes(data)
    target = HonestProof("p", (1,), (1,), "accept", 0, 0)
    assert ctl.c5(target, COMMIT, src, tmp_path / "all").mutation == {"part": "y.bin", "bytes": 50}
    reads = PartsRead("handmade", frozenset({"a.bin", "b.bin"}), (("y.bin", REASON),))
    call = ctl.c5(target, COMMIT, src, tmp_path / "read", reads)
    assert call.mutation == {"part": "a.bin", "bytes": 4}  # largest read part, tie by name
    assert (call.proof_dir / "y.bin").read_bytes() == b"y" * 100


def test_c8_drops_only_read_parts(tmp_path: Path) -> None:
    _, dirs = honest_proofs(tmp_path)
    target = HonestProof("req-0", (), (), "accept", 0, 0)
    call = ctl.c8(target, COMMIT, dirs["req-0"], tmp_path / "c8", SEED, READS)
    assert call.mutation == {"dropped": "response.proof"}
    assert call.parts == ("response.y",)  # the proof keeps a part
    undeclared = ctl.c8(target, COMMIT, dirs["req-0"], tmp_path / "c8-all", SEED)
    every = ["response.proof", "response.y"]
    assert undeclared.mutation == {"dropped": every[index("C8", 0, 2)]}


def test_c8_single_part_still_counts_every_part(tmp_path: Path) -> None:
    src = tmp_path / "p"
    src.mkdir()
    (src / "only.bin").write_bytes(b"x")
    reads = PartsRead("handmade", frozenset({"only.bin"}), ())
    with pytest.raises(ctl.NotApplicable, match="single part"):
        ctl.c8(
            HonestProof("p", (1,), (1,), "accept", 0, 0), COMMIT, src, tmp_path / "c8", SEED, reads
        )


def test_unread_part_finding_reproduced_then_closed(tmp_path: Path, workload: Workload) -> None:
    """Undeclared, some C6 trial flips response.y and is accepted (the 2026-11-09 finding);
    declared, every C5, C6 and C8 mutation reaches the verifier and is not accepted."""
    undeclared = suite(tmp_path / "all", workload, EVERY_PART)
    assert "accepted" in {t["outcome"] for t in undeclared["C6"]["trials"]}
    assert all("parts_not_read" not in r for r in undeclared.values())
    declared = suite(tmp_path / "read", workload, READS)
    for cid in ctl.PART_CONTROLS:
        record = declared[cid]
        assert record["passed"] is True, record
        assert {
            t["mutation"].get("part", t["mutation"].get("dropped")) for t in record["trials"]
        } == {"response.proof"}
        assert record["parts_not_read"] == [{"part": "response.y", "reason": REASON}]
    assert declared["C8"]["outcome"] == "invalid_call"
    assert all("parts_not_read" not in declared[c] for c in ("C1", "C2", "C3", "C4", "C7"))
    # the other controls are the same records either way
    for cid in ("C1", "C2", "C3", "C4", "C7"):
        assert declared[cid] == undeclared[cid]
    doc = ctl.controls_document(
        "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
        SEED,
        "iproofs-fake@sha256:" + "a" * 64,
        "ci-cpu",
        None,
        list(declared.values()),
    )
    assert REGISTRY.errors("controls/1", doc) == []
    assert doc["disclosure_pending"] is False


def counting(calls: list[VerifyCall]) -> ctl.Verifier:
    def verify(call: VerifyCall) -> VerifyResult:
        calls.append(call)
        return reads_proof_only(call)

    return verify


@pytest.mark.parametrize(
    ("reads", "message"),
    [
        (
            PartsRead(
                "handmade", frozenset({"response.proof", "proof.bin"}), (("response.y", REASON),)
            ),
            "names proof.bin, which proof req-0 does not have",
        ),
        (
            PartsRead("handmade", frozenset({"response.proof"}), (("gone.bin", REASON),)),
            "names gone.bin, which proof req-0 does not have",
        ),
        (
            PartsRead("handmade", frozenset({"response.proof"}), ()),
            "does not say whether verify reads response.y of proof req-0",
        ),
    ],
)
def test_declaration_that_does_not_fit_is_refused_before_any_call(
    tmp_path: Path, workload: Workload, reads: PartsRead, message: str
) -> None:
    proofs, dirs = honest_proofs(tmp_path)
    calls: list[VerifyCall] = []
    for only in (None, ["C1"]):  # whole suite or a part without C5, C6, C8
        with pytest.raises(IProofsError, match=message) as e:
            ctl.run_shared_controls(
                proofs,
                dirs,
                COMMIT,
                None,
                workload=workload,
                seed=SEED,
                verify=counting(calls),
                work=tmp_path / "mutations",
                only=only,
                reads=reads,
            )
        assert e.value.kind == ErrorKind.CONFIG
    assert calls == []
    assert not (tmp_path / "mutations").exists()


def system(verify_reads: object) -> System:
    tree = load_yaml(ROOT / "systems/flashprove/system.yaml")
    proofs = tree["proofs"]
    assert isinstance(proofs, dict)
    tree["proofs"] = {**proofs, "verify_reads": verify_reads}
    assert REGISTRY.errors("system/1", tree) == []
    return System.from_tree(tree)


def test_parts_read_from_system_yaml() -> None:
    declared = ctl.parts_read(system({"read": ["a.bin"], "not_read": [
        {"part": "z.bin", "reason": "z"}, {"part": "b.bin", "reason": "b"}]}))  # fmt: skip
    assert declared == PartsRead(
        "flashprove", frozenset({"a.bin"}), (("b.bin", "b"), ("z.bin", "z"))
    )
    assert declared.record() == [{"part": "b.bin", "reason": "b"}, {"part": "z.bin", "reason": "z"}]
    assert ctl.parts_read(system("all")) == PartsRead("flashprove")
    assert ctl.parts_read(None) == EVERY_PART


@pytest.mark.parametrize(
    "verify_reads",
    [
        {"read": ["a.bin"], "not_read": [{"part": "a.bin", "reason": "r"}]},
        {
            "read": ["a.bin"],
            "not_read": [{"part": "b.bin", "reason": "r"}, {"part": "b.bin", "reason": "s"}],
        },
    ],
)
def test_part_placed_twice_refused(verify_reads: object) -> None:
    with pytest.raises(IProofsError, match=r"places (a|b)\.bin twice") as e:
        ctl.parts_read(system(verify_reads))
    assert e.value.kind == ErrorKind.CONFIG


def test_shipped_declarations() -> None:
    """FlashProve reads response.proof and not response.y; SASH reads every part."""
    flashprove = ctl.parts_read(load_system("flashprove"))
    assert flashprove.read == frozenset({"response.proof"})
    assert [part for part, _ in flashprove.not_read] == ["response.y"]
    flashprove.check("req-0", ["response.proof", "response.y"])  # the parts prove writes
    assert ctl.parts_read(load_system("sash")).read is None
    assert load_system("sash").proofs.verify_reads == "all"  # type: ignore[union-attr]


def load_system(name: str) -> System:
    return System.from_tree(load_yaml(ROOT / f"systems/{name}/system.yaml"))


# ---------------------------------------------------------------- through `iproofs controls`

FAKE_ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
            "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
IMAGE = "local/in-process@sha256:" + "0" * 64


def fake_repo(tmp: Path) -> Path:
    r = tmp / "repo"
    copied = ("schema", "systems/fake", "systems/fake-broken", "workloads/fake-tiny-ci.yaml",
              "reference", "harness/tests/fixtures/prompts", "uv.lock",
              "pyproject.toml")  # fmt: skip
    for rel in copied:
        src, dst = ROOT / rel, r / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fake", "--no-gpg-sign"], check=True)
    return r


def fake_runner(r: Path, **kw: object) -> Runner:
    containers = InProcessRunner(r / "systems/fake/entrypoint", REGISTRY, env=FAKE_ENV)
    return Runner(containers, root=r, registry=REGISTRY, image=IMAGE, **kw)  # type: ignore[arg-type]


def declare(r: Path, verify_reads: object) -> None:
    path = r / "systems/fake/system.yaml"
    doc = load_yaml(path)
    proofs = doc["proofs"]
    assert isinstance(proofs, dict)
    doc["proofs"] = {**proofs, "verify_reads": verify_reads}
    path.write_text(json.dumps(doc))  # JSON is YAML


@pytest.fixture
def kept_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    r = fake_repo(tmp_path)
    monkeypatch.chdir(r)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(r / "results"), "v0.1")
    return r, fake_runner(r, keep_io=True).run(spec)


def test_controls_on_a_stored_run_read_the_declaration(kept_fake: tuple[Path, Path]) -> None:
    """A run made before the declaration, controlled after it (READ-5: a new record)."""
    r, run_dir = kept_fake
    assert json.loads((run_dir / "run.json").read_text())["status"] == "completed"
    declare(r, {"read": ["body.bin"], "not_read": [{"part": "tag.bin", "reason": REASON}]})
    doc = json.loads(controls_for_run(fake_runner(r), run_dir, seed=SEED).read_text())
    by_id = {c["id"]: c for c in doc["controls"]}
    for cid in ctl.PART_CONTROLS:
        trials = by_id[cid]["trials"]
        assert {t["mutation"].get("part", t["mutation"].get("dropped")) for t in trials} == {
            "body.bin"
        }
        assert by_id[cid]["parts_not_read"] == [{"part": "tag.bin", "reason": REASON}]
    assert REGISTRY.errors("controls/1", doc) == []


def test_controls_refused_when_a_declared_part_does_not_exist(
    kept_fake: tuple[Path, Path],
) -> None:
    r, run_dir = kept_fake
    declare(r, {"read": ["body.bin", "tag.bin", "proof.bin"],
                "not_read": [{"part": "note.bin", "reason": REASON}]})  # fmt: skip
    with pytest.raises(IProofsError, match=r"names note\.bin, proof\.bin, which proof") as e:
        controls_for_run(fake_runner(r), run_dir, seed=SEED)
    assert e.value.kind == ErrorKind.CONFIG
    assert not (run_dir / "controls.json").exists()
    log = (run_dir / "logs/harness.jsonl").read_text()
    assert '"event":"control.call"' not in log  # refused before any call
