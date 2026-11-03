"""Release freeze, effective tiers, review and reproduction records (RFC-0009, RFC-0007).

`compare` implements `iproofs reproduce compare` (RFC-0007 §Eligibility, §Tolerance,
§Verdict and digest matching). It reads run directories as stored and writes one
`reproduction/1` record; it computes no number other than the tolerance terms.
"""

import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json

# RFC-0007 §Tolerance: compared metric ids, in record order.
COMPARED = (
    "rate_prove.steady",
    "rate_prove.session",
    "whole_wall_seconds",
    "commit_seconds",
    "verify_seconds",
    "verify_single_thread_seconds",
    "prove_gpu_memory_peak",
    "prove_host_memory_peak_anon",
    "proof_bytes",
)
RELATIVE = 0.10
SIGMAS = 3.0
MIN_REPLAYED = 3
UNAFFILIATED = frozenset({"none", "independent", "individual"})  # RFC-0001 §Roles rule 3


def tolerance(
    m_o: float, s_o: float, n_o: int, m_r: float, s_r: float, n_r: int
) -> tuple[float, float, bool]:
    """(bound, difference, within) in binary64, unrounded (RFC-0007 §Tolerance)."""
    bound = max(RELATIVE * abs(m_o), SIGMAS * math.sqrt(s_o**2 / n_o + s_r**2 / n_r))
    difference = abs(m_r - m_o)
    return bound, difference, difference <= bound


@dataclass(frozen=True, slots=True)
class RunView:
    """One stored run directory: run.json, manifest.json and controls.json if present."""

    path: Path
    run: dict[str, object]
    manifest: dict[str, object]
    controls: dict[str, object] | None

    @classmethod
    def read(cls, path: Path) -> "RunView":
        try:
            run = json.loads((path / "run.json").read_text())
            manifest = json.loads((path / "manifest.json").read_text())
        except FileNotFoundError as e:
            raise IProofsError(ErrorKind.CONFIG, f"{path} is not a run directory") from e
        controls_file = path / "controls.json"
        controls = json.loads(controls_file.read_text()) if controls_file.is_file() else None
        return cls(path, run, manifest, controls)

    def get(self, doc: str, *keys: str) -> object:
        node: object = self.run if doc == "run" else self.manifest
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
        return node

    @property
    def run_id(self) -> str:
        return str(self.run["run_id"])

    @property
    def ok(self) -> bool:
        return self.run.get("status") == "completed"

    @property
    def seed(self) -> object:
        return self.get("manifest", "workload", "prompt_seed")

    def key(self) -> tuple[object, ...]:
        """RFC-0007: one configuration is (system, configuration, workload, profile, image)."""
        return (
            self.run.get("system"),
            self.get("manifest", "claim", "configuration"),
            self.get("manifest", "workload", "id"),
            self.get("manifest", "workload", "version"),
            self.get("manifest", "profile", "prover"),
            self.get("manifest", "system", "image", "ref"),
        )

    def verdicts(self) -> Counter[str]:
        proofs = self.run.get("proofs")
        return (
            Counter(str(p["verdict"]) for p in proofs if isinstance(p, dict))
            if isinstance(proofs, list)
            else Counter()
        )

    def control_outcomes(self) -> dict[str, str] | None:
        if self.controls is None:
            return None
        entries = self.controls.get("controls")
        assert isinstance(entries, list)
        return {str(c["id"]): str(c["outcome"]) for c in entries}

    def proof_digests(self) -> list[str]:
        proofs = self.manifest.get("proofs")
        return (
            sorted(str(p["digest"]) for p in proofs if isinstance(p, dict))
            if isinstance(proofs, list)
            else []
        )


def group(run: RunView) -> list[RunView]:
    """The run and every sibling with the same configuration key and the same runner."""
    runner = run.get("manifest", "runner", "handle")
    siblings = sorted(p for p in run.path.parent.iterdir() if (p / "run.json").is_file())
    views = [run if p == run.path else RunView.read(p) for p in siblings]
    return [
        v for v in views if v.key() == run.key() and v.get("manifest", "runner", "handle") == runner
    ]


def _organisation(runner: Mapping[str, object]) -> str:
    org = str(runner.get("organisation", "")).strip().lower()
    return f"individual:{runner.get('handle')}" if org in UNAFFILIATED | {"", "undeclared"} else org


def is_unaffiliated(
    runner: Mapping[str, object],
    system: str,
    original_runner: Mapping[str, object] | None,
    maintainers: Iterable[str],
) -> bool:
    """RFC-0007 §Tiers: the runner's organisation is not a system maintainer's of `system`,
    nor the original runner's, and `affiliated_systems` does not list the system.
    `maintainers` are the organisations of the system's maintainers in MAINTAINERS.md."""
    if str(runner.get("organisation", "")).strip().lower() in {"", "undeclared"}:
        return False  # an affiliation nobody declared is not an absence of one
    org = _organisation(runner)
    systems = runner.get("affiliated_systems")
    return (
        org not in {o.strip().lower() for o in maintainers}
        and (original_runner is None or org != _organisation(original_runner))
        and system not in (systems if isinstance(systems, list) else [])
    )


def _stats(values: Sequence[float]) -> dict[str, object]:
    n = len(values)
    return {
        "mean": statistics.mean(values) if n else None,
        "stdev": statistics.stdev(values) if n >= 2 else None,
        "n": n,
    }


def _comparison(
    metric: str, originals: Sequence[RunView], replays: Sequence[RunView]
) -> dict[str, object] | None:
    quantities = [
        q for r in (*originals, *replays) if isinstance(q := r.get("run", "metrics", metric), dict)
    ]
    if not quantities:
        return None  # the metric does not exist for this configuration

    def values(runs: Iterable[RunView]) -> list[float]:
        out = []
        for r in runs:
            v = r.get("run", "metrics", metric, "value")
            if isinstance(v, int | float) and not isinstance(v, bool):
                out.append(float(v))
        return out

    o, r = _stats(values(originals)), _stats(values(replays))
    bound: float | None = None
    difference: float | None = None
    within: bool | None = None
    if o["n"] and r["n"]:
        # with fewer than two values a group has no sample stdev; its statistical term is 0
        bound, difference, within = tolerance(
            float(o["mean"]),  # type: ignore[arg-type]
            float(o["stdev"] or 0.0),  # type: ignore[arg-type]
            int(o["n"]),  # type: ignore[call-overload]
            float(r["mean"]),  # type: ignore[arg-type]
            float(r["stdev"] or 0.0),  # type: ignore[arg-type]
            int(r["n"]),  # type: ignore[call-overload]
        )
    elif o["n"] or r["n"]:
        within = False  # null in one set and not the other fails
    return {
        "metric": metric,
        "unit": quantities[0]["unit"],
        "scope": quantities[0]["scope"],
        "original": o,
        "reproduction": r,
        "bound": bound,
        "difference": difference,
        "within": within,
    }


def _same(runs: Sequence[RunView], *path: str) -> bool:
    return len({json.dumps(r.get(*path), sort_keys=True) for r in runs}) == 1


def _different_machine(orig: RunView, repro: RunView) -> bool:
    """RFC-0007 §Eligibility 2: the provider or the run date differs, and the CPU binding."""
    date = (orig.run_id[:10], repro.run_id[:10])
    provider = (orig.get("manifest", "provider"), repro.get("manifest", "provider"))
    binding = [r.get("manifest", "machine", "cpu", "bound_prover") for r in (orig, repro)]
    elsewhere = date[0] != date[1] or provider[0] != provider[1]
    return elsewhere and binding[0] is not None and binding[0] != binding[1]


def compare(
    orig: Path,
    repro: Path,
    *,
    deterministic_proofs: bool,
    maintainer_organisations: Iterable[str],
) -> dict[str, object]:
    """The `reproduction/1` record for the configuration of `orig` reproduced by `repro`."""
    originals, reproductions = group(RunView.read(orig)), group(RunView.read(repro))
    seeds = {r.seed: r for r in originals if r.ok}
    replays = [r for r in reproductions if r.ok and r.seed in seeds]
    fresh = [r for r in reproductions if r.seed not in seeds]
    everyone = [*originals, *reproductions]
    o_runner = originals[0].get("manifest", "runner")
    r_runner = reproductions[0].get("manifest", "runner")
    assert isinstance(r_runner, dict)
    system = originals[0].run.get("system")
    eligibility: dict[str, object] = {
        "same_release": _same(everyone, "manifest", "release"),
        "same_image_digest": _same(everyone, "manifest", "system", "image", "ref"),
        "same_workload_digests": all(
            _same(everyone, "manifest", "workload", k)
            for k in ("id", "version", "file_digest", "corpus_digest", "model")
        ),
        "same_profile": _same(everyone, "manifest", "profile", "prover")
        and _same(everyone, "manifest", "profile", "verifier"),
        "different_machine": all(_different_machine(originals[0], r) for r in reproductions),
        "clean_build": not any(
            r.get("manifest", "harness", "git_dirty")
            or r.get("manifest", "system", "adapter_dirty")
            for r in everyone
        ),
        "repetitions": len(replays),
    }
    assert isinstance(o_runner, dict)
    unaffiliated = is_unaffiliated(r_runner, str(system), o_runner, maintainer_organisations)
    eligible = (
        all(v is True for k, v in eligibility.items() if k != "repetitions")
        and len(replays) >= MIN_REPLAYED
        and bool(fresh)
        and unaffiliated
    )
    # INV-TIER-5: verdicts and control outcomes per replayed seed; fresh seeds, verdicts only
    original_controls = next(
        (oc for r in originals if (oc := r.control_outcomes()) is not None), None
    )
    verdicts_match = all(
        r.verdicts() == seeds[r.seed].verdicts()
        and (
            r.control_outcomes() is None
            or seeds[r.seed].control_outcomes() is None
            or r.control_outcomes() == seeds[r.seed].control_outcomes()
        )
        for r in replays
    ) and all(
        set(r.verdicts()) <= {"accept"}
        and r.ok
        and (r.control_outcomes() is None or r.control_outcomes() == original_controls)
        for r in fresh
    )
    matched = (
        all(r.proof_digests() == seeds[r.seed].proof_digests() for r in replays)
        if deterministic_proofs
        else None
    )
    comparisons = [
        c for m in COMPARED if (c := _comparison(m, [r for r in originals if r.ok], replays))
    ]
    if not eligible:
        outcome = "ineligible"
    elif not verdicts_match or matched is False or any(c["within"] is False for c in comparisons):
        outcome = "outside_tolerance"
    else:
        outcome = "within_tolerance"
    return {
        "schema": "reproduction/1",
        "original_run_ids": [r.run_id for r in originals],
        "reproduction_run_ids": [r.run_id for r in reproductions],
        "runner": {
            "handle": r_runner.get("handle"),
            "organisation": r_runner.get("organisation"),
            "affiliated_systems": list(r_runner.get("affiliated_systems") or []),
        },
        "eligibility": eligibility,
        "comparisons": comparisons,
        "verdicts_match": verdicts_match,
        "digests": {"required": deterministic_proofs, "matched": matched},
        "fresh_seed_runs": [r.run_id for r in fresh],
        "outcome": outcome,
    }


def write_reproduction(orig: Path, record: dict[str, object], registry: SchemaRegistry) -> Path:
    """`<original-run-dir>/reproductions/<repro-run-id>.json`, validated before it is written."""
    errors = registry.errors("reproduction/1", record)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"reproduction record is invalid: {errors[0]}")
    ids = record["reproduction_run_ids"]
    assert isinstance(ids, list)
    path = orig / "reproductions" / f"{ids[0]}.json"
    if path.exists():
        raise IProofsError(ErrorKind.CONFIG, f"{path} exists; records are append-only")
    path.parent.mkdir(exist_ok=True)
    write_json(path, record)
    return path
