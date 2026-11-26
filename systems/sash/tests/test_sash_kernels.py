"""The kernel store on CPU: commit emits and builds once, the data-dependent families over their
bound; a restored setup is checked and nothing is made again; a reply builds only when its own
emission added a kernel, and says so; the phases are reported apart. Every upstream process is
stub_upstream.py, whose emitters keep a store as cudagen.rs does."""

import json
import re
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

PROMPT = list(range(128))
TOK = list(range(1000, 1064))
# every flag an emission may pass: headline-c4096.sh's shared flags and head flags,
# sequence-job.sh's pins, the stub plan's line flags and step 5's own options
UPSTREAM_FLAGS = {"--round", "--numbits", "--z-hi-bits", "--variants", "--head-groups",
                  "--tight-table", "--kmax", "--ao-rem-bits", "--fold-rem-bits", "--fold-alpha",
                  "--table-bits", "--witness", "--block", "--min-blocks", "--families",
                  "--out", "--gkr-key-tiles", "--gkr-dequant", "--gkr-residual-stream",
                  "--gkr-freivalds", "--gkr-attnout"}  # fmt: skip
FORM_FLAGS = {"--ao-acc-mag", "--ao-acc-prod", "--ao-acc-lo-bits"}


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    return load(tmp_path, monkeypatch)


def logged(adapter: ModuleType) -> list[dict[str, Any]]:
    path = adapter.host("/io/commands.jsonl")
    return [json.loads(ln) for ln in path.read_text().splitlines()]


def commands(adapter: ModuleType) -> list[list[str]]:
    return [c["argv"] for c in logged(adapter)]


def commit(adapter: ModuleType) -> dict[str, Any]:
    return run_step(adapter, "commit", model_dir="/models")


def prove(adapter: ModuleType, c: dict[str, Any], replies: int) -> dict[str, Any]:
    adapter.host("/io/prompts.jsonl").write_text((json.dumps(PROMPT) + "\n") * replies)
    return run_step(adapter, "prove", commitment_id=c["commitment_id"], model_dir="/models",
                    prover_files=c["prover_files"], prompts_file="/io/prompts.jsonl",
                    batch_size=1, batches=replies)  # fmt: skip


def phases(out: dict[str, Any]) -> dict[str, float]:
    return {p["name"]: p["seconds"] for p in out["phases"]}


def emitted(argvs: list[list[str]]) -> list[list[str]]:
    return [a for a in argvs if len(a) > 1 and a[1] in ("cudaemit", "genemit")]


def from_witness(argvs: list[list[str]]) -> list[list[str]]:
    """The emissions (a) to (c): a commitment line with the pins sequence-job.sh passes."""
    return [a for a in emitted(argvs) if "--witness" in a and not FORM_FLAGS & set(a)]


def synthetic(argvs: list[list[str]]) -> list[list[str]]:
    return [a for a in emitted(argvs) if "--witness" not in a]


def test_commit_emits_from_its_own_witness_and_builds_once(adapter: ModuleType) -> None:
    out = commit(adapter)
    argvs = commands(adapter)
    assert [a[0] for a in argvs].count("cargo") == 1
    emits = emitted(argvs)
    assert emits
    witnessed = [a for a in emits if "--witness" in a]
    assert all("/io/state/commit-witness/" in a[a.index("--witness") + 1] for a in witnessed)
    # every other emission lowers the synthetic segment, for the two data-dependent families
    assert {(a[1], a[a.index("--families") + 1]) for a in synthetic(argvs)} == {
        ("genemit", "zk_attn_out_eval"),
        ("genemit", "zk_dequant_eval"),
    }
    # every emission precedes the build and read a dump that was there (the stub refuses a
    # dump whose directory is gone), and the witness was gone when the build ran
    tools = [a[0] for a in argvs]
    assert max(i for i, a in enumerate(argvs) if a in emits) < tools.index("cargo")
    assert all(c["exit_code"] == 0 for c in logged(adapter) if c["argv"] in emits)
    cargo = adapter.host("/io/stub-cargo.jsonl").read_text().splitlines()
    assert [json.loads(ln) for ln in cargo] == [{"commit_witness": False}]
    assert adapter.host("/io/state/build/kernels.done").read_text() == adapter.store()[2]
    assert list(phases(out)) == ["witness", "model_roots", "kernels_emit", "kernels_build"]
    assert out["commitment_id"] == adapter.commitment_of(out["verifier_files"])
    c, g, key, shapes = adapter.store()
    assert {
        k: out["kernels"][k]
        for k in ("constraint_kernels", "generation_shapes", "build_key", "shape_set")
    } == {"constraint_kernels": c, "generation_shapes": g, "build_key": key, "shape_set": shapes}
    assert out["kernels"]["emitter_runs"] == len(emits)


def test_commit_emits_every_plan_line_and_widens_the_pins(adapter: ModuleType) -> None:
    """(a) the lines a reply emits, (b) every other plan line and the two pins sequence-job.sh
    passes, each widened only above its own value (the stub's pins: --ao-rem-bits 20, at the
    cap, and --fold-rem-bits 15); no flag upstream's drivers do not pass."""
    commit(adapter)
    emits = from_witness(commands(adapter))
    plan_witnesses = {a[a.index("--witness") + 1] for a in emits}
    # 3 blocks of 2 layers and 2 heads: every segment's own witness is emitted from
    assert len(plan_witnesses) == 3 * 2 + 2
    folds = sorted({adapter.pinned(a, "--fold-rem-bits") for a in emits})
    assert folds == [15, 16, 17, 18, 19]
    assert {adapter.pinned(a, "--ao-rem-bits") for a in emits} == {20}
    flags = {t for a in emits for t in a[2:] if t.startswith("--")}
    assert flags <= UPSTREAM_FLAGS


def test_reply_whose_emission_adds_nothing_does_not_build(adapter: ModuleType) -> None:
    """The reply's lines name its own witness directory, which v1.0's key hashed; the store's
    content is what decides now."""
    c = commit(adapter)
    before = len(commands(adapter))
    out = prove(adapter, c, replies=2)
    argvs = commands(adapter)[before:]
    assert "cargo" not in [a[0] for a in argvs]
    emits = emitted(argvs)
    dirs = {re.search(r"/io/state/(witness-\d+)/", a[a.index("--witness") + 1]) for a in emits}
    assert {m.group(1) for m in dirs if m} == {"witness-0", "witness-1"}
    assert phases(out)["kernels_build"] == 0
    assert (out["kernels"]["replies_built"], out["warnings"]) == (0, [])
    composed = [a for a in argvs if len(a) > 1 and a[1] == "compose-chunks"]
    assert len(composed) == 2
    assert {a[0] for a in composed} == {"/io/state/build/t-cuda/release/zk-prover"}


def test_reply_whose_emission_adds_a_kernel_builds_once(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = commit(adapter)
    shapes = adapter.store()
    before = len(commands(adapter))
    monkeypatch.setenv("IPROOFS_SASH_STUB_NEW", "f00dface")
    out = prove(adapter, c, replies=2)
    argvs = commands(adapter)[before:]
    tools = [a[0] for a in argvs]
    assert tools.count("cargo") == 1
    first_proof = next(i for i, a in enumerate(argvs) if len(a) > 1 and a[1] == "compose-chunks")
    assert tools.index("cargo") < first_proof  # built for the reply that needed it, before it
    after = adapter.store()
    assert (after[0] - shapes[0], after[1] - shapes[1]) == (1, 1)
    assert adapter.host("/io/state/build/kernels.done").read_text() == after[2]
    assert phases(out)["kernels_build"] > 0
    assert out["kernels"]["replies_built"] == 1
    assert out["kernels"]["build_key"] == after[2]
    [warning] = out["warnings"]
    assert warning.startswith("req-0: the reply's emission added 1 constraint kernels and 1 ")
    assert [p["proof_id"] for p in out["proofs"]] == ["req-0", "req-1"]


def test_prove_phases_apart(adapter: ModuleType) -> None:
    out = prove(adapter, commit(adapter), replies=1)
    assert list(phases(out)) == ["ids", "witness", "kernels_emit", "kernels_build", "prove"]


def test_prove_builds_when_no_build_was_installed(adapter: ModuleType) -> None:
    c = commit(adapter)
    adapter.host("/io/state/build/kernels.done").unlink()
    before = len(commands(adapter))
    prove(adapter, c, replies=1)
    assert [a[0] for a in commands(adapter)[before:]].count("cargo") == 1


def test_store_digest_keys_on_content_not_on_the_last_run(adapter: ModuleType) -> None:
    """cudagen.rs rewrites every store file byte for byte when no shape is new, except the two
    manifests, whose `source` (a witness path), `components` and new counts follow the last
    run; the install scripts read their `families`."""
    gen = adapter.host("/io/state/build/gen")
    gen.mkdir(parents=True)
    (gen / "shapes.json").write_text(
        json.dumps([["zk_row_eval", "a", {}], ["zk_key_eval", "b", {}]])
    )
    (gen / "gen_shapes.json").write_text(json.dumps([["zk_dequant_eval", "c", {}]]))
    (gen / "evaluate_zk_row_eval.cu").write_text("kernel")

    def manifest(source: str, new: int, families: list[str]) -> None:
        doc = {"source": source, "components": [{"component": source}], "families": families,
               "kernels": 2, "kernels_new_this_run": new}  # fmt: skip
        (gen / "manifest.json").write_text(json.dumps(doc))

    manifest("/io/state/witness-0/witness_B0_L0", 2, ["zk_row_eval", "zk_key_eval"])
    first = adapter.store()
    assert first[:2] == (2, 1)
    manifest("/io/state/witness-1/witness_B0_L0", 0, ["zk_row_eval", "zk_key_eval"])
    assert adapter.store() == first
    manifest("/io/state/witness-1/witness_B0_L0", 0, ["zk_row_eval"])
    assert adapter.store()[2] != first[2]
    manifest("/io/state/witness-0/witness_B0_L0", 2, ["zk_row_eval", "zk_key_eval"])
    (gen / "evaluate_zk_row_eval.cu").write_text("another kernel")
    assert adapter.store()[2] != first[2]


def test_a_store_with_no_kernel_stops_commit(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every emission refused: commit stops before the build rather than installing nothing."""
    monkeypatch.setattr(adapter, "emit", lambda *a, **k: (0, []))
    with pytest.raises(SystemExit, match="lines left 0 constraint kernels"):
        commit(adapter)
    assert "cargo" not in [a[0] for a in commands(adapter)]


def test_the_sweep_widens_each_line_from_the_pin_it_is_emitted_at(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared --ao-rem-bits 17 and a head pin of 12, which plan.py puts on the head lines
    after the shared one: the head lines are emitted at 12 and widened through 13..20, the
    layer lines at 17 and widened through 18..20, and no run reads a pin below its line's."""
    monkeypatch.setenv("IPROOFS_SASH_STUB_AO", "17")
    monkeypatch.setenv("IPROOFS_SASH_STUB_HEAD_AO", "12")
    commit(adapter)
    emits = from_witness(commands(adapter))
    head = [a for a in emits if "/head_B" in a[a.index("--witness") + 1]]
    layer = [a for a in emits if a not in head]
    assert {adapter.pinned(a, "--ao-rem-bits") for a in head} == set(range(12, 21))
    assert {adapter.pinned(a, "--ao-rem-bits") for a in layer} == set(range(17, 21))
    # on a head line the shared pin stays as it is; only the value the prover reads moves
    assert all(a[a.index("--ao-rem-bits") + 1] == "17" for a in head)


def test_refused_lowerings_are_recorded_and_commit_completes(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IPROOFS_SASH_STUB_EMIT_REFUSE", "--fold-rem-bits=18")
    commit(adapter)
    refused = [c for c in logged(adapter) if c["argv"] in emitted([c["argv"]]) and c["exit_code"]]
    assert refused
    assert {adapter.pinned(c["argv"], "--fold-rem-bits") for c in refused} == {18, 19}
    assert [a[0] for a in commands(adapter)].count("cargo") == 1
    err = capsys.readouterr().err
    assert re.search(r"--fold-rem-bits 16\.\.19 .*, \d+ refused", err)
    # each refusal is logged with the emitter's own message, not Rust's backtrace hint
    lines = [ln for ln in err.splitlines() if "  refused: " in ln]
    assert lines
    assert all(ln.endswith("--fold-rem-bits=18: the lowering is refused (stub)") for ln in lines)


def test_every_generation_shape_refused_stops_commit_before_the_build(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IPROOFS_SASH_STUB_EMIT_REFUSE", "genemit")
    with pytest.raises(SystemExit, match="generation shapes; every emission was refused"):
        commit(adapter)
    assert "cargo" not in [a[0] for a in commands(adapter)]


def test_a_reply_partly_refused_proves_on_the_store_it_has(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = commit(adapter)
    before = len(commands(adapter))
    monkeypatch.setenv("IPROOFS_SASH_STUB_EMIT_REFUSE", "genemit")
    out = prove(adapter, c, replies=1)
    runs = logged(adapter)[before:]
    gen = [r for r in runs if r["argv"][1:2] == ["genemit"]]
    assert gen
    assert all(r["exit_code"] == 1 for r in gen)
    assert "cargo" not in [r["argv"][0] for r in runs]
    assert [p["proof_id"] for p in out["proofs"]] == ["req-0"]


def test_the_shape_set_is_the_same_for_one_set_reached_in_two_orders(adapter: ModuleType) -> None:
    """cudagen.rs keeps shapes in first-seen order, so the build key differs; the shape set
    does not, and it changes when a shape does."""
    gen = adapter.host("/io/state/build/gen")
    gen.mkdir(parents=True)

    def shapes(*irs: int) -> tuple[int, int, str, str]:
        rows = [["zk_attn_out_eval", f"seen{i}", {"ops": [ir]}] for i, ir in enumerate(irs)]
        (gen / "gen_shapes.json").write_text(json.dumps(rows))
        (gen / "shapes.json").write_text(json.dumps([["zk_row_eval", "a", {"ops": []}]]))
        return adapter.store()  # type: ignore[no-any-return]

    x_then_y, y_then_x = shapes(1, 2), shapes(2, 1)
    assert x_then_y[2] != y_then_x[2]
    assert x_then_y[3] == y_then_x[3]
    assert x_then_y[3].startswith("sha256:")
    assert shapes(1, 3)[3] != x_then_y[3]


def test_a_point_below_the_synthetic_accumulator_takes_a_wider_high_limb(
    adapter: ModuleType,
) -> None:
    """The segment's accumulator is 16 bits. Magnitude lo 8, hi 4, rem 15: 8 + 4 < 16; hi 8
    would equal lo, hi 9 equals none of rem and lo, as 4 does not: hi 9. Magnitude lo 6, hi 4,
    rem 10: hi 10 would equal rem, so hi 11. Product lo 10, hi 4, rem 20: hi 6 equals none of
    rem, lo and 30 - lo = 20. Magnitude lo 4, hi 4: the high limb would have to equal the low
    one and reach 12, so the point stays (and is refused). Product lo 13, hi 4 already sums to
    17; the offset form keeps its own limbs."""
    point = adapter.synthetic_point
    assert point(("magnitude", 8, 4, 15, False)) == ("magnitude", 8, 9, 15, False)
    assert point(("magnitude", 6, 4, 10, False)) == ("magnitude", 6, 11, 10, False)
    assert point(("product", 10, 4, 20, True)) == ("product", 10, 6, 20, True)
    assert point(("magnitude", 4, 4, 12, False)) == ("magnitude", 4, 4, 12, False)
    assert point(("product", 13, 4, 17, False)) == ("product", 13, 4, 17, False)
    assert point(("offset", 8, 4, 15, False)) == ("offset", 8, 4, 15, False)


def test_the_attention_output_box_by_hand(adapter: ModuleType) -> None:
    """The full box (the fixture shrinks it for speed): acc_bits 1..26, e_hi 4..30, rem 10..20,
    acc_bits <= rem + 6. Three points by hand: 21 bits at e_hi 9 need 16 + 6 offset limbs, and
    1 + 22 + 9 = 32 > 31, so the magnitude form at 16 + 5, which fits (31); 20 bits at e_hi 5,
    rem 20: offset 16 + 5 (27 <= 31) and denp2 (11 + 20 > 30); 22 bits at e_hi 10: the
    magnitude window 1 + 16 + 6 + 10 = 33 > 31, so the product form."""
    adapter.AO_BOX = (range(1, 27), range(4, 31), range(10, 21))
    points = adapter.ao_points()
    assert len(points) == len(set(points)) == 494
    assert ("magnitude", 16, 5, 18, False) in points
    assert ("offset", 16, 5, 20, True) in points
    assert ("product", 16, 6, 18, False) in points
    # 26 bits need 16 + 11 offset limbs, which leave no e_hi >= 4 inside 31
    assert not [p for p in points if p[0] == "offset" and p[1:3] == (16, 11)]
    assert all(lo <= 16 and hi >= 4 and 10 <= rem <= 20 for _, lo, hi, rem, _ in points)
    assert adapter.ao_flags(("product", 16, 6, 18, False)) == [
        "--ao-acc-lo-bits",
        "16",
        "--ao-acc-hi-bits",
        "6",
        "--ao-rem-bits",
        "18",
        "--ao-acc-mag",
        "--ao-acc-prod",
    ]


def test_commit_sweeps_the_data_dependent_families(adapter: ModuleType) -> None:
    """(d) one cudaemit per attention-output form on the first layer line that admits it;
    (e) one synthetic genemit per point of the box; (f) one per fold pin up to 19."""
    commit(adapter)
    argvs = commands(adapter)
    forms = [a for a in emitted(argvs) if FORM_FLAGS & set(a) and "--witness" in a]
    assert {a[1] for a in forms} == {"cudaemit"}
    wanted = [["--ao-acc-mag"]] + [["--ao-acc-prod", "--ao-acc-lo-bits", str(lo)]
                                   for lo in adapter.AO_PROD_LO]  # fmt: skip

    def form(a: list[str]) -> list[str]:
        lo = (
            ["--ao-acc-lo-bits", a[a.index("--ao-acc-lo-bits") + 1]]
            if "--ao-acc-lo-bits" in a
            else []
        )
        return [t for t in a if t in ("--ao-acc-mag", "--ao-acc-prod")] + lo

    assert [form(a) for a in forms] == wanted
    assert all("/head_B" not in a[a.index("--witness") + 1] for a in forms)
    ao = [a for a in synthetic(argvs) if "zk_attn_out_eval" in a]
    assert [a[a.index("--ao-acc-lo-bits") : a.index("--families")] for a in ao] == [
        adapter.ao_flags(p)
        for p in dict.fromkeys(map(adapter.synthetic_point, adapter.ao_points()))
    ]
    folds = [a for a in synthetic(argvs) if "zk_dequant_eval" in a]
    assert [adapter.pinned(a, "--fold-rem-bits") for a in folds] == list(range(1, 20))
    assert all(a[2 : 2 + len(adapter.SYNTH.split())] == adapter.SYNTH.split() for a in ao + folds)


def test_a_form_refused_on_every_layer_line_is_taken_from_a_head_line(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IPROOFS_SASH_STUB_EMIT_REFUSE", "--ao-acc-mag@/witness_B")
    out = commit(adapter)
    mag = [c for c in logged(adapter) if "--ao-acc-mag" in c["argv"]
           and "--ao-acc-prod" not in c["argv"] and "--witness" in c["argv"]]  # fmt: skip
    assert [c["exit_code"] for c in mag] == [1] * 6 + [0]  # 3 blocks x 2 layers, then a head
    assert "/head_B" in mag[-1]["argv"][mag[-1]["argv"].index("--witness") + 1]
    assert out["kernels"]["refused"] == 0  # a form one line refuses and another admits is had


def restored(adapter: ModuleType, tmp_path: Path) -> dict[str, Any]:
    """A setup run's commit, then a fresh /io holding only the state it left, as the harness
    restores it."""
    out = commit(adapter)
    io = adapter.host("/io")
    shutil.copytree(io / "state", tmp_path / "saved", symlinks=True)
    shutil.rmtree(io)
    io.mkdir()
    shutil.copytree(tmp_path / "saved", io / "state", symlinks=True)
    return out


def reuse(adapter: ModuleType, out: dict[str, Any], **setup: str) -> dict[str, Any]:
    state = {"commitment_id": out["commitment_id"], "build_key": out["kernels"]["build_key"]}
    return run_step(adapter, "commit", model_dir="/models", setup_state={**state, **setup})


def test_commit_reuses_a_restored_setup_and_makes_nothing(
    adapter: ModuleType, tmp_path: Path
) -> None:
    fresh = restored(adapter, tmp_path)
    out = reuse(adapter, fresh)
    assert [a[0] for a in commands(adapter)] == ["nvidia-smi", "cuobjdump"]
    assert list(phases(out)) == ["setup_check"]
    for k in ("commitment_id", "verifier_files", "prover_files", "sizes", "kernels"):
        assert out[k] == fresh[k]
    before = len(commands(adapter))
    prove(adapter, out, replies=1)  # nothing new in the store: the restored binary proves
    assert "cargo" not in [a[0] for a in commands(adapter)[before:]]


@pytest.mark.parametrize(("damage", "message"), [
    ("verifier", "hash to"), ("marker", "built from"), ("binary", "has no"),
    ("key", "the setup names"), ("card", "carries no sm_80"), ("grid", "not this request's"),
])  # fmt: skip
def test_a_restored_setup_that_fails_its_check_stops_commit(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
    message: str,
) -> None:  # fmt: skip
    fresh = restored(adapter, tmp_path)
    state, setup = adapter.host("/io/state"), {}
    if damage == "verifier":
        (state / "model-roots.json").write_text("[]")
    elif damage == "marker":
        (state / "build/kernels.done").write_text("sha256:another")
    elif damage == "binary":
        (state / "build/t-cuda/release/zk-prover").unlink()
    elif damage == "key":
        setup = {"build_key": "sha256:another"}
    elif damage == "card":
        monkeypatch.setenv("IPROOFS_SASH_STUB_CAP", "8.0")
    elif damage == "grid":
        grid = json.loads((state / "grid.json").read_text())
        (state / "grid.json").write_text(json.dumps({**grid, "blocks": 4}))
        setup = {"commitment_id": adapter.commitment_of(fresh["verifier_files"])}
    with pytest.raises(SystemExit, match=message):
        reuse(adapter, fresh, **setup)
    ran = [a[0] for a in commands(adapter)] if adapter.host("/io/commands.jsonl").is_file() else []
    assert set(ran) <= {"nvidia-smi", "cuobjdump"}  # nothing extracted, derived, emitted, built
    assert not adapter.host("/io/state/commit-witness").exists()


C3 = {"id": "C3", "perturbation": {"tensor": "t", "index": 0, "old": "00", "new": "01",
                                   "unit": "u", "digest_w": "a", "digest_w_prime": "b",
                                   "digest_tool": None}}  # fmt: skip


def test_a_control_commit_makes_the_commitment_and_no_kernel(adapter: ModuleType) -> None:
    """A MODEL control's commit (W', RFC-0008 C3): witness and model roots, then no emission
    and no build, since no proof is made from its state."""
    out = run_step(adapter, "commit", model_dir="/models", control=C3)
    ran = commands(adapter)
    assert not emitted(ran)
    assert "cargo" not in [a[0] for a in ran]
    assert list(phases(out)) == ["witness", "model_roots"]
    assert "kernels" not in out
    assert out["commitment_id"] == adapter.commitment_of(out["verifier_files"])
    assert not adapter.host("/io/state/commit-witness").exists()


def test_a_control_commit_never_reuses_a_setup(adapter: ModuleType, tmp_path: Path) -> None:
    fresh = restored(adapter, tmp_path)
    control = {"id": "C3", "perturbation": {"tensor": "t", "index": 0, "old": "00", "new": "01",
                                            "unit": "u", "digest_w": "a", "digest_w_prime": "b",
                                            "digest_tool": None}}  # fmt: skip
    state = {"commitment_id": fresh["commitment_id"]}
    with pytest.raises(SystemExit, match="never a restored setup"):
        run_step(adapter, "commit", model_dir="/models", setup_state=state, control=control)
