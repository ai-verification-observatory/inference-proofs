"""Synthetic Level 1 records for the checks and board tests (RFC-0018). Not results.

`Tree(root)` copies `levels/L1.yaml` into `root`, writes a price file and the
systems' forbidden flags, and holds the level as the tree read from the file. `session(...)`
writes one session's run directory in the shape the runner workstream records under a level
(`manifest.level`, `manifest.session.slot`, `verify-trace/<proof_id>.json`); `controls(...)`
builds a `controls.json` whose C1, C2, C3 and P1 trials the test chooses.
"""

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import yaml

from iproofs.controls import seeded_index
from iproofs.provenance import file_digest

ROOT = Path(__file__).resolve().parents[4]
RELEASE = "v1.0"
RUNG = "llama-3.1-8b"
SYSTEM = "sash"
WORKLOAD = "l1-l31-8b-p512-o512"
SEED = "0x0123456789abcdef"
OUTPUT = 512
NS = 1_000_000_000
REJECT = "rejected"


class Tree:
    """A repository holding only what `iproofs.checks` and `iproofs.board` read."""

    def __init__(self, root: Path) -> None:
        self.root = root
        for rel in ("levels/L1.yaml",):
            src, dst = ROOT / rel, root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
        (root / "reference").mkdir()
        (root / "reference/v1.0.yaml").write_text(yaml.safe_dump({"costs": {"h200": {
            "price_per_gpu_hour_usd": {
                "value": 3.6, "unit": "USD/gpu_hour", "scope": None, "grade": "asserted",
                "tier": "reported", "null_reason": None,
                "source": {"kind": "reference_file", "ref": "reference/v1.0.yaml#/costs/h200"}},
            "date": "2026-11-08"}}}))  # fmt: skip
        for system in ("sash", "flashprove", "other"):
            path = root / "systems" / system / "system.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(yaml.safe_dump({"forbidden_flags": ["--unsound-skip-"]}))
        self.level: dict[str, object] = yaml.safe_load((root / "levels/L1.yaml").read_text())
        self.digest = file_digest(root / "levels/L1.yaml")

    def add_system(self, rung: str, system: str, workload: str, stated: bool = True) -> None:
        """Put `system` on `rung` in the level tree (the file and its digest are unchanged)."""
        for r in self.level["rungs"]:  # type: ignore[attr-defined]
            if r["id"] == rung:
                r["workloads"][system] = workload
        systems = self.level["systems"]
        assert isinstance(systems, dict)
        systems[system] = {"security": {"stated": stated, "words": "w", "source": "s"},
                           "model_change": "c"}  # fmt: skip

    def run_dir(self, system: str, run_id: str) -> Path:
        return self.root / "results" / RELEASE / system / run_id


def trial(
    outcome: str, k: int, mutation: dict[str, object] | None = None, position: str | None = None
) -> dict[str, object]:
    """A trial as the runner records it under a level: `detail.twin`, and `detail.position`
    on C1 trials only."""
    detail: dict[str, object] = {"twin": {"verdict": "accept", "raw_exit_code": 0}}
    if position is not None:
        detail["position"] = position
    return {"seed_index": k, "mutation": mutation or {}, "verdict": None, "outcome": outcome,
            "raw_exit_code": 1, "raw_last_line": "", "seconds": 1.0, "detail": detail}  # fmt: skip


def interior(k: int) -> int:
    """CH-3: trial k's interior reply position."""
    return seeded_index(SEED, "C1-interior", k, OUTPUT - 2) + 1


def control(cid: str, trials: Sequence[dict[str, object]]) -> dict[str, object]:
    return {"id": cid, "side": "prover" if cid == "P1" else "verifier", "source": "shared",
            "expected": ["rejected"], "twin": {"verdict": "accept", "raw_exit_code": 0},
            "trials": list(trials), "outcome": "rejected", "passed": True,
            "note": None}  # fmt: skip


def controls(  # noqa: PLR0913 (one keyword per control a test varies)
    *,
    p1: Sequence[str] = (REJECT,) * 3,
    c3: Sequence[str] = (REJECT,) * 3,
    c2: Sequence[str] = (REJECT,) * 3,
    first: Sequence[str] = (REJECT,) * 3,
    last: Sequence[str] = (REJECT,) * 3,
    interior_: Sequence[str] = (REJECT,) * 3,
    interior_index: int | None = None,
    perturbed: str = "perturbed",
    omit: Sequence[str] = (),
) -> dict[str, object]:
    """A controls.json: each sequence holds the outcomes of trials k = 0, 1, ...; C1 holds its
    three positions as mutated indices (0, R - 1 and the seeded interior one)."""
    c1 = [
        *(trial(o, k, {"index": 0}, "first") for k, o in enumerate(first)),
        *(trial(o, k, {"index": OUTPUT - 1}, "last") for k, o in enumerate(last)),
        *(trial(o, k, {"index": interior(k) if interior_index is None else interior_index},
                "interior") for k, o in enumerate(interior_)),
    ]  # fmt: skip
    found = {
        "C1": control("C1", c1),
        "C2": control("C2", [trial(o, k, {"position": 3}) for k, o in enumerate(c2)]),
        "C3": control("C3", [trial(o, k) for k, o in enumerate(c3)]),
        "P1": control("P1", [trial(o, k) for k, o in enumerate(p1)]),
    }
    return {"schema": "controls/1", "control_seed": SEED,
            "perturbed_commitment": {"commitment_id": perturbed,
                                     "model_digest": "sha256:" + "cd" * 32},
            "controls": [c for cid, c in found.items() if cid not in omit]}  # fmt: skip


def trace(*, opened: Sequence[str] = (), failed: Sequence[str] = (),
          tool: str | None = "strace", gpu: bool = False,
          present: bool = False) -> dict[str, object]:  # fmt: skip
    """A verify-trace/1 record: `opened` model files read, `failed` model files whose open
    failed (ENOENT after removal)."""
    return {"schema": "verify-trace/1", "run_id": "r", "proof_id": "x", "mode": "hosted",
            "tool": tool, "trace": None,
            "opened": [{"path": p, "bytes": 1} for p in opened],
            "failed_opens": list(failed),
            "model_files_opened": [{"path": p, "ok": True} for p in opened]
            + [{"path": p, "ok": False} for p in failed],
            "gpu_devices_opened": [], "gpu_visible": gpu, "model_files_present": present,
            "model_files_removed": True}  # fmt: skip


def session(  # noqa: PLR0913 (one keyword per recorded field a test varies)
    tree: Tree,
    slot: int,
    k: int,
    *,
    system: str = SYSTEM,
    workload: str = WORKLOAD,
    n: int = 5,
    groups: Sequence[tuple[float, int]] = ((100, 1), (110, 1), (120, 1), (130, 1), (140, 1)),
    commit_start: float = 0.0,
    gpus: int = 1,
    failure: dict[str, object] | None = None,
    claimed: int = OUTPUT,
    control_doc: dict[str, object] | None = None,
    traces: dict[str, object] | None = None,
    argv: Sequence[str] = (),
    digest: str | None = None,
    day: int = 1,
    generation: tuple[float, float] | None = None,
) -> Path:
    """One session's run directory; `groups` lists (release second, replies) per group,
    requests numbered in release order, 1 ms apart inside a group."""
    run_id = f"2026-12-{day:02d}-{system}-{workload}-prover-h200-hosted-{k}"
    path = tree.run_dir(system, run_id)
    path.mkdir(parents=True)
    times = [int(t * NS) + i * 1_000_000 for t, size in groups for i in range(size)]
    proofs = [{"proof_id": f"req-{i}", "request_index": i, "release_mono_ns": t,
               "tokens_covered": 1024, "verdict": "accept", "claimed_output": [7] * claimed}
              for i, t in enumerate(times[:n])]  # fmt: skip
    metric = {"value": 2.0, "unit": "s/request", "scope": "verify", "grade": "derived",
              "tier": "reported", "null_reason": None,
              "source": {"kind": "derivation", "ref": "derive:D-VSPR@0.1.0",
                         "inputs": [f"{run_id}#/metrics/verify_seconds_total"]}}  # fmt: skip
    run = {"schema": "run/1", "run_id": run_id, "system": system, "control": False,
           "status": "failed" if failure else "completed", "failure": failure,
           "events": [{"event": "commit.start", "mono_ns": int(commit_start * NS)}],
           "proofs": [] if failure else proofs,
           "metrics": {"verify_seconds_per_request": metric}}  # fmt: skip
    if generation is not None:
        run["marks"] = [
            {"name": n, "mono_ns": int(t * NS)}
            for n, t in zip(("generation.start", "generation.end"), generation, strict=True)
        ]
    manifest = {"schema": "manifest/1", "run_id": run_id,
                "level": {"id": "L1", "digest": digest or tree.digest},
                "session": {"slot": slot},
                "workload": {"id": workload},
                "claim": {"configuration": "default"},
                "commitment": {"commitment_id": "honest"},
                "system": {"adapter_dirty": False, "upstream": {"commit": "a" * 40}},
                "machine": {"gpu": {"bound_indices": list(range(gpus))}},
                "commands": [{"step": "prove", "argv": ["prove", *argv],
                              "started_at": f"2026-12-{day:02d}T00:{k:02d}:00Z"}]}  # fmt: skip
    (path / "run.json").write_text(json.dumps(run))
    (path / "manifest.json").write_text(json.dumps(manifest))
    if control_doc is not None:
        (path / "controls.json").write_text(json.dumps({**control_doc, "run_id": run_id}))
    (path / "verify-trace").mkdir()
    for p in proofs if not failure else []:
        doc = trace() if traces is None else traces
        (path / "verify-trace" / f"{p['proof_id']}.json").write_text(json.dumps(doc))
    return path


def three_sessions(tree: Tree, **kw: object) -> list[Path]:
    """Slots 1 to 3, each complete; the first holds the controls."""
    doc = kw.pop("control_doc", controls())
    return [session(tree, s, s, control_doc=doc if s == 1 else None, **kw)  # type: ignore[arg-type]
            for s in (1, 2, 3)]  # fmt: skip


def fidelity(tree: Tree, rows: dict[str, dict[str, object]], bar: bool = True) -> Path:
    path = tree.root / "results" / RELEASE / "fidelity" / RUNG / "fidelity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, object] = {
           "schema": "fidelity/1", "level": {"id": "L1", "digest": tree.digest}, "rung": RUNG,
           "controls": [{"id": "q8_0", "kind": "honest", "mean_prefix": 480.0, "status": "ok",
                         "scores": [], "kl": None},
                        {"id": "q3_k_s", "kind": "damaged", "mean_prefix": 200.0, "status": "ok",
                         "scores": [], "kl": None}],
           "bar": {"control": "q3_k_s", "mean_prefix": 200.0} if bar else None,
           "rows": rows}  # fmt: skip
    path.write_text(json.dumps(doc))
    return path


def fidelity_row(state: str = "held", cause: str | None = None) -> dict[str, object]:
    return {"scores": [500] * 15, "mean_prefix": 500.0, "p_above_bar": 0.001,
            "p_below_bar": 0.999, "state": state, "cause": cause, "kl": None,
            "kl_note": "not measured"}  # fmt: skip
