"""Release freeze, eligibility, effective tiers, review and reproduction records (RFC-0009,
RFC-0007, RFC-0014).

`compare` implements `iproofs reproduce compare` (RFC-0007 §Eligibility, §Tolerance,
§Verdict and digest matching). It reads run directories as stored and writes one
`reproduction/1` record; it computes no number other than the tolerance terms.
"""

import datetime as dt
import functools
import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from iproofs import __version__
from iproofs.derive import (
    Input,
    QuantityTree,
    agreement_rate,
    freeze_values,
    overhead,
    provider_spread,
    statistic,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import ReferenceFile, Release, Workload, load
from iproofs.provenance import file_digest
from iproofs.quantity import (
    NullReason,
    Scope,
    Tier,
    claim_class_matches,
    lowest_tier,
    parse_claim_class,
)
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json
from iproofs.workloads import asserted_inputs, serving_system, workload_file

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
        # RFC-0007 rule 1: ids, versions, model and corpus digests. The file digest is not
        # compared: a descriptive field (RFC-0003 WB-4, weight bits) changes it, not the inputs
        "same_workload_digests": all(
            _same(everyone, "manifest", "workload", k)
            for k in ("id", "version", "corpus_digest", "model")
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


# ---------------------------------------------------------------- eligibility (RFC-0014)

# B7 (RFC-0014 Q2): every release image lives here, a reference adapter's included; the
# engine image a reference adapter builds FROM is a base image, pinned by digest.
PROJECT_REGISTRY = "ghcr.io/ai-verification-observatory/"

# Stable reason strings, shown by the release index and the site.
REASONS = {
    "other_release": "the run belongs to another release",
    "manifest_invalid": "the manifest fails manifest/1 (a pin is not in full form)",
    "self_test_failed": "the host's calibration self-test did not pass",
    "nonconforming_host": "the host did not conform to the profile",
    "claim_card_not_listed": "the run's claim card is not the one the release lists",
    "harness_dirty": "the harness tree was dirty",
    "adapter_dirty": "the adapter tree was dirty or unknown",
    "image_digest_kind_config": "the image is pinned by config digest, not manifest digest",
    "image_differs_from_system_yaml": "the image is not the one system.yaml pins at the release "
    "commit, or was not built from that commit's history",
    "image_not_in_project_registry": "the image is not in the project's container registry",
    "no_archived_proof": "the configuration has no archived proof URI",
}


def eligibility(
    run_dir: Path,
    release: Release,
    root: Path,
    registry: SchemaRegistry,
    archived: Collection[tuple[object, ...]] | None = None,
) -> tuple[bool, list[str]]:
    """RFC-0014 §Eligibility of one stored run for `release`: (eligible, reason codes from
    REASONS, in that order). Reads only the run's documents, the release record, the listed
    runs' manifests, and system.yaml at the run's adapter commit and at the release commit."""
    run = RunView.read(run_dir)
    m, system = run.manifest, run.get("manifest", "system")
    assert isinstance(system, dict)
    claim = m.get("claim")
    pinned = _system_at(root, str(system.get("adapter_commit")), str(system.get("name"))) or {}
    head = _head(root)  # the release commit
    reference = pinned.get("kind") == "reference"  # RFC-0015: no claim card, no proofs (REF-2)
    cards = {(c.system, c.configuration, c.card_version, c.digest) for c in release.claim_cards}
    failed = {
        "other_release": m.get("release") != release.release,
        "manifest_invalid": bool(registry.errors("manifest/1", m)),
        "self_test_failed": run.get("manifest", "self_test", "passed") is not True,
        "nonconforming_host": run.get("manifest", "harness", "nonconforming") is not False,
        "claim_card_not_listed": not reference
        and (
            not isinstance(claim, dict)
            or (
                claim.get("system"),
                claim.get("configuration"),
                claim.get("card_version"),
                system.get("claim_digest"),
            )
            not in cards
        ),
        "harness_dirty": run.get("manifest", "harness", "git_dirty") is not False,
        "adapter_dirty": system.get("adapter_dirty") is not False,
        "image_digest_kind_config": run.get("manifest", "system", "image", "digest_kind")
        != "manifest",
        "image_differs_from_system_yaml": _pinned_image(root, head, str(system.get("name")))
        != run.get("manifest", "system", "image", "ref")
        or not _is_ancestor(root, str(system.get("adapter_commit")), head),
        "image_not_in_project_registry": not str(
            run.get("manifest", "system", "image", "ref")
        ).startswith(PROJECT_REGISTRY),
        "no_archived_proof": not reference
        and run.key()
        not in (archived if archived is not None else archived_configurations(release, root)),
    }
    reasons = [code for code in REASONS if failed[code]]
    return not reasons, reasons


def _head(root: Path) -> str:
    done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=False)  # fmt: skip
    return done.stdout.strip() if done.returncode == 0 else "HEAD"


@functools.cache
def _is_ancestor(root: Path, adapter_commit: str, head: str) -> bool:
    """The image was built from a commit of the history being released."""
    done = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", adapter_commit, head],
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


@functools.cache
def _system_at(root: Path, adapter_commit: str, name: str) -> dict[str, object] | None:
    """systems/<name>/system.yaml at the run's adapter commit, or None when git has none."""
    import yaml  # noqa: PLC0415

    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{adapter_commit}:systems/{name}/system.yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    doc = yaml.safe_load(shown.stdout) if shown.returncode == 0 else None
    return doc if isinstance(doc, dict) else None


def _pinned_image(root: Path, head: str, name: str) -> str | None:
    """`repository@digest` (or a reference engine's image) of system.yaml at the release
    commit `head`. An image cannot carry its own digest, so the commit it was built from never
    pins it; the pin is a later commit, and the build commit must be its ancestor."""
    doc = _system_at(root, head, name) or {}
    engine = doc.get("engine")
    image = doc.get("image") or (engine.get("image") if isinstance(engine, dict) else None)
    if isinstance(image, dict):
        return f"{image.get('repository')}@{image.get('digest')}"
    return image if isinstance(image, str) else None


def archived_configurations(release: Release, root: Path) -> set[tuple[object, ...]]:
    """RFC-0014: configuration keys of the release's runs that record an archive URI."""
    found = set()
    for listed in release.runs:
        if (root / listed / "manifest.json").is_file():
            run = RunView.read(root / listed)
            proofs = run.manifest.get("proofs")
            if isinstance(proofs, list) and any(
                isinstance(p, dict) and p.get("archive") for p in proofs
            ):
                found.add(run.key())
    return found


# ---------------------------------------------------------------- freeze (RFC-0009)

MIN_WINDOW_DAYS = 14
OUTCOME_COUNTS = ("rejected", "accepted", "no_verdict", "invalid_call", "void",
                  "not_applicable", "error", "prover_failed")  # fmt: skip


def _fail(message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"release freeze: {message}")


def _check_cost_bases(reference: ReferenceFile, name: str) -> None:
    """RFC-0006 C6 and C7: every cost basis of the reference file has a price and a date."""
    for basis in (reference.cost, *(reference.costs or {}).values()):
        if not basis.price_per_gpu_hour_usd.value or not basis.date:
            raise _fail(f"{name} has no price or no date (RFC-0006 C6)")


def freeze(
    release_id: str,
    root: Path,
    registry: SchemaRegistry,
    gates: Callable[[list[str]], list[str]],
    maintainers: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, object]:
    """RFC-0009 §Freeze algorithm, steps 1 to 9. `gates` runs G2 to G7 over repository paths
    and returns the failing lines; `maintainers` maps a system to its maintainers'
    organisations (MAINTAINERS.md). Returns the `release-index/1` document; nothing is
    written and no clock is read, so the same inputs give the same bytes."""
    read: list[Path] = []
    path = root / "releases" / release_id / "release.yaml"
    if not path.is_file():
        raise _fail(f"no {path.relative_to(root)}")
    release = load(path, registry)  # step 1
    if not isinstance(release, Release) or release.release != release_id:
        raise _fail(f"{path.relative_to(root)} is not release {release_id}")
    reference = load(root / release.reference_file, registry)  # validates the reference file
    assert isinstance(reference, ReferenceFile)
    _check_cost_bases(reference, release.reference_file)
    read += [path, root / release.reference_file]
    runs = {}
    for listed in release.runs:
        run = RunView.read(root / listed)
        for doc in ("run", "manifest"):
            errors = registry.errors(f"{doc}/1", getattr(run, doc))
            if errors:
                raise _fail(f"{listed}/{doc}.json: {errors[0]}")
        runs[run.run_id] = run
        read += [
            p
            for n in ("run", "manifest", "controls")
            if (p := root / listed / f"{n}.json").is_file()
        ]
        read += sorted(
            [*(root / listed).glob("reviews/*.json"), *(root / listed).glob("reproductions/*.json")]
        )
    for card in release.claim_cards:
        if not (root / card.path).is_file() or file_digest(root / card.path) != card.digest:
            raise _fail(f"claim card {card.path} does not match its listed digest")
        read.append(root / card.path)
    failing = gates([*release.runs, path.relative_to(root).as_posix()])  # step 2
    if failing:
        raise _fail(f"gates failed: {failing[0]}")
    window = release.review_window  # step 3
    opens, closes = dt.date.fromisoformat(window.opens), dt.date.fromisoformat(window.closes)
    if (closes - opens).days < MIN_WINDOW_DAYS:
        raise _fail(
            f"review window {window.opens} to {window.closes} is under {MIN_WINDOW_DAYS} days"
        )
    if dt.date.fromisoformat(release.freeze_date) <= closes:
        raise _fail(f"freeze_date {release.freeze_date} is not after {window.closes}")
    excluded = _excluded(release, runs, root, registry)  # step 4
    late = _Late(root, registry, release.release)
    configurations, controls, contexts = _configurations(runs, excluded, maintainers or {}, late)
    _require_closed(root, release, contexts)
    _release_rows(  # step 5, release rows
        release.release, contexts, _reference_roles(root), _serving(root, contexts)
    )
    targets = _targets(root, registry, release, contexts, read)  # step 8
    digests = sorted(file_digest(p) for p in read)
    index: dict[str, object] = {
        "schema": "release-index/1",
        "release": release.release,
        "reference": {
            "file": release.reference_file,
            "digest": file_digest(root / release.reference_file),
        },
        "claim_cards": [
            {
                "system": c.system,
                "configuration": c.configuration,
                "card_version": c.card_version,
                "path": c.path,
                "digest": c.digest,
            }
            for c in release.claim_cards
        ],
        "configurations": configurations,
        "controls": controls,
        "targets": targets,
        "inputs_digest": "sha256:"
        + hashlib.sha256("".join(f"{d}\n" for d in digests).encode()).hexdigest(),
    }
    if late.values:  # RFC-0004 Q3
        index["freeze_derived"] = dict(late.values)
    return index


def _excluded(
    release: Release, runs: Mapping[str, RunView], root: Path, registry: SchemaRegistry
) -> dict[str, list[str]]:
    """run id -> reasons: superseded runs (RFC-0009 §Corrections) and ineligible runs."""
    out: dict[str, list[str]] = {
        s.run_id: [f"superseded: {s.reason}"] for s in release.superseded_runs
    }
    for run in runs.values():
        replaces = run.run.get("replaces")
        if isinstance(replaces, dict):
            out.setdefault(str(replaces["run_id"]), []).append(
                f"superseded by {run.run_id}: {replaces['reason']}"
            )
    archived = archived_configurations(release, root)
    for run_id, run in runs.items():
        ok, reasons = eligibility(run.path, release, root, registry, archived)
        if not ok:
            out.setdefault(run_id, []).extend(reasons)
    return out


MIN_CLOSED_SYSTEMS = 2  # RFC-0003 §Choosing common workloads and Q7 (default)


def closed_workload_failures(
    classes: Mapping[str, str | None], rows: Iterable[tuple[str, str, str | None]]
) -> list[str]:
    """RFC-0003 §Choosing common workloads and Q7 (default): a closed workload's rows enter a
    release only when at least `MIN_CLOSED_SYSTEMS` distinct proving systems run it under a
    claim card of its exact class. `classes` maps each closed workload a proving configuration
    of the release ran to its `claim_class`; `rows` holds (workload id, proving system, its
    card's `claim_class`, None without a card) per proving configuration with at least one
    kept completed run. Returns the failing lines, a card of another class first, then each
    workload short of systems, in workload id order."""
    systems: dict[str, set[str]] = {wid: set() for wid in classes}
    out = []
    for wid, system, card_class in sorted(rows, key=lambda r: (r[0], r[1])):
        if wid not in classes:
            continue
        if card_class is None or str(parse_claim_class(card_class)) != classes[wid]:
            out.append(f"{system} on closed workload {wid} has claim class {card_class!r}, "
                       f"not {classes[wid]!r} (RFC-0003 §Divisions)")  # fmt: skip
            continue
        systems[wid].add(system)
    for wid in sorted(classes):
        if len(systems[wid]) < MIN_CLOSED_SYSTEMS:
            ran = ", ".join(sorted(systems[wid])) or "none"
            out.append(f"closed workload {wid} has completed runs of {len(systems[wid])} proving "
                       f"system(s) with claim class {classes[wid]!r} ({ran}); its rows enter "
                       f"a release once {MIN_CLOSED_SYSTEMS} do (RFC-0003 Q7)")  # fmt: skip
    return out


def _closed_inputs(
    root: Path, release: Release, contexts: Sequence["_Context"]
) -> tuple[dict[str, str | None], list[tuple[str, str, str | None]]]:
    """The inputs of `closed_workload_failures` from the workload files, the release's claim
    cards and the configurations' kept runs."""
    import yaml  # noqa: PLC0415

    cards = {(c.system, c.configuration): root / c.path for c in release.claim_cards}
    classes: dict[str, str | None] = {}
    rows = []
    for ctx in contexts:
        if not ctx.kept or any(r.run.get("system_kind") != "prover" for r in ctx.kept):
            continue
        wid = str(ctx.where["workload"]["id"])  # type: ignore[index]
        path = root / "workloads" / f"{wid}.yaml"
        wl = yaml.safe_load(path.read_text()) if path.is_file() else None
        if not isinstance(wl, dict) or wl.get("division") != "closed":
            continue
        classes[wid] = wl.get("claim_class")
        if not any(r.ok for r in ctx.kept):
            continue
        card_path = cards.get((str(ctx.where["system"]), str(ctx.configuration)))
        card = yaml.safe_load(card_path.read_text()) if card_path else None
        card_class = card.get("claim_class") if isinstance(card, dict) else None
        rows.append((wid, str(ctx.where["system"]), str(card_class) if card_class else None))
    return classes, rows


def _require_closed(root: Path, release: Release, contexts: Sequence["_Context"]) -> None:
    """Stops the freeze on the first line `closed_workload_failures` returns (RFC-0003 Q7)."""
    closed = closed_workload_failures(*_closed_inputs(root, release, contexts))
    if closed:
        raise _fail(closed[0])


def _repetition_order(run: RunView) -> tuple[str, int]:
    """Run ids end in a sequence number: order by date and that number, not as text."""
    head, _, n = run.run_id.rpartition("-")
    return (run.run_id[:10], int(n) if n.isdigit() else 0) if head else (run.run_id, 0)


def _configurations(
    runs: Mapping[str, RunView],
    excluded: Mapping[str, list[str]],
    maintainers: Mapping[str, Sequence[str]],
    late: "_Late",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list["_Context"]]:
    groups: dict[tuple[object, ...], list[RunView]] = {}
    for run in runs.values():
        key = (run.run.get("system"), run.get("manifest", "claim", "configuration"),
               run.get("manifest", "workload", "id"), run.get("manifest", "workload", "version"),
               run.get("manifest", "profile", "prover"))  # fmt: skip
        groups.setdefault(key, []).append(run)
    configurations, controls, contexts = [], [], []
    for group_key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        system, configuration, workload, version, profile = group_key
        members = sorted(groups[group_key], key=_repetition_order)
        kept = [r for r in members if r.run_id not in excluded]
        reviews = {r.run_id: run_records(r, "reviews") for r in kept}
        repros = {r.run_id: run_records(r, "reproductions") for r in kept}
        every_repro = [doc for found in repros.values() for _, doc in found]
        tiers = {  # step 6: only records present at freeze count
            r.run_id: effective_tier(r, [d for _, d in reviews[r.run_id]], every_repro,
                                     maintainers.get(str(system), ()))
            for r in kept
        }  # fmt: skip
        where = {
            "system": system,
            "workload": {"id": workload, "version": version},
            "profile": profile,
        }
        configurations.append({
            **where,
            "configuration": configuration,
            "runs": [r.run_id for r in kept],
            "ineligible": [{"run_id": r.run_id, "reasons": excluded[r.run_id]}
                           for r in members if r.run_id in excluded],
            "insufficient_repetitions": sum(r.ok for r in kept) < MIN_REPLAYED,
            "statistics": (stats := _statistics(kept, tiers, late)),
            "effective_tier": str(lowest_tier(list(tiers.values()))) if tiers else "reported",
            "evidence": {  # INV-TIER-7: outside_tolerance records are listed too
                "reviews": [path for r in kept for path, _ in reviews[r.run_id]],
                "reproductions": [path for r in kept for path, _ in repros[r.run_id]],
            },
        })  # fmt: skip
        controls.append({**where, **_control_summary(kept)})
        contexts.append(_Context(where, configuration, kept, tiers, stats, late))
    return configurations, controls, contexts


class _Late:
    """RFC-0004 Q3: values a freeze evaluates for runs stored before their formula existed,
    written to index.json `freeze_derived` and pointed at from there."""

    def __init__(self, root: Path, registry: SchemaRegistry, release: str) -> None:
        self.root, self.registry, self.release = root, registry, release
        self.values: dict[str, dict[str, QuantityTree]] = {}
        self._workloads: dict[str, Workload] = {}

    def workload_inputs(self, run: RunView) -> tuple[Input, Input]:
        """The workload record's asserted inputs at the release commit, as (pointer, quantity);
        missing inputs when the record now holds another version than the run's."""
        wid = str(run.get("run", "workload", "id"))
        if wid not in self._workloads:  # the record only, not the loader's cross-file rules
            wl = load(workload_file(self.root, wid), self.registry)
            if not isinstance(wl, Workload):
                raise _fail(f"workloads/{wid}.yaml is not a workload record")
            self._workloads[wid] = wl
        wl = self._workloads[wid]
        same = wl.version == run.get("run", "workload", "version")
        inputs, out = asserted_inputs(wl), []
        for name in ("active_parameters_per_token", "weight_bits"):
            q = inputs[name]
            source = q["source"]
            assert isinstance(source, dict)
            out.append((str(source["ref"]), q if same else None))
        return out[0], out[1]

    def evaluate(self, run: RunView) -> dict[str, QuantityTree]:
        params, bits = self.workload_inputs(run)
        values = freeze_values(
            run.run["metrics"],  # type: ignore[arg-type]
            run_json=f"{_rel(run)}/run.json",
            harness_version=__version__,
            active_parameters=params,
            weight_bits=bits,
            reference=run.run.get("system_kind") == "reference",
        )
        if values:
            self.values[run.run_id] = values
        return values

    def pointer(self, run: RunView, metric: str) -> str:
        return f"releases/{self.release}/index.json#/freeze_derived/{run.run_id}/{metric}"


def _statistics(
    kept: Sequence[RunView], tiers: Mapping[str, Tier], late: _Late
) -> dict[str, object]:
    """D-STAT per metric over completed repetitions, in repetition order (INV-DERIVE-1);
    failed repetitions count in n_failed. Each input carries its effective tier, so the
    statistic's tier is the lowest of them (INV-TIER-6). A run stored before a formula of
    FREEZE_FORMULAS existed gets its value at freeze (RFC-0004 Q3), so it stays in n."""
    done = [r for r in kept if r.ok]
    failed = [f"{_rel(r)}/run.json#/failure" for r in kept if not r.ok]
    evaluated = {r.run_id: late.evaluate(r) for r in done}
    _same_inputs(done, evaluated, late)
    metrics = sorted(
        {m for r in done for m in r.run["metrics"]}  # type: ignore[attr-defined]
        | {m for values in evaluated.values() for m in values}
    )
    out: dict[str, object] = {}
    for metric in metrics:
        inputs = _metric_inputs(done, metric, tiers, late)
        out[metric] = statistic(inputs, failed, __version__)
    return out


def _same_inputs(
    done: Sequence[RunView], evaluated: Mapping[str, Mapping[str, QuantityTree]], late: _Late
) -> None:
    """RFC-0003 WB-4: one configuration's repetitions share the workload's asserted inputs; a
    change of weight bits or parameter count is a new workload version."""
    used: dict[str, tuple[object, object]] = {}
    for r in done:
        recorded = r.run.get("inputs")
        if isinstance(recorded, dict):
            params, bits = recorded["active_parameters_per_token"], recorded["weight_bits"]
        elif any(name.startswith("seconds_per_active") for name in evaluated[r.run_id]):
            (_, params), (_, bits) = late.workload_inputs(r)
        else:
            continue
        used[r.run_id] = (
            None if params is None else params["value"],
            None if bits is None else bits["value"],
        )
    if len(set(used.values())) > 1:
        raise _fail(
            "RFC-0003 WB-4: repetitions of one configuration have different workload inputs"
            f" (active parameters per token, weight bits): {dict(sorted(used.items()))}"
        )


def _metric_inputs(
    done: Sequence[RunView], metric: str, tiers: Mapping[str, Tier], late: _Late | None = None
) -> list[tuple[str, Mapping[str, object] | None]]:
    """(pointer, quantity with its effective tier) per completed repetition that has `metric`,
    stored in its run.json or evaluated at freeze (`late`, RFC-0004 Q3)."""
    inputs: list[tuple[str, Mapping[str, object] | None]] = []
    for r in done:
        stored: dict[str, dict[str, object]] = r.run["metrics"]  # type: ignore[assignment]
        if metric in stored:
            tier = str(quantity_tier(r, metric, tiers[r.run_id]))
            inputs.append(
                (f"{_rel(r)}/run.json#/metrics/{metric}", {**stored[metric], "tier": tier})
            )
        elif late is not None and metric in late.values.get(r.run_id, {}):
            q = late.values[r.run_id][metric]
            tier = str(quantity_tier(r, metric, tiers[r.run_id], q=q))
            inputs.append((late.pointer(r, metric), {**q, "tier": tier}))
    return inputs


def _rel(run: RunView) -> str:
    """The run directory as a repository path: results/<release>/<system>/<run-id>."""
    return "/".join(run.path.parts[-4:])


def _control_summary(kept: Sequence[RunView]) -> dict[str, object]:
    counts = dict.fromkeys(OUTCOME_COUNTS, 0)
    outside = []
    for run in kept:
        for c in (run.controls or {}).get("controls") or []:  # type: ignore[attr-defined]
            counts[str(c["outcome"])] += 1
            if c["passed"] is False:
                outside.append(
                    {"run_id": run.run_id, "control_id": c["id"], "outcome": c["outcome"]}
                )
    return {"counts": counts, "outside_expected": outside}


# ---------------------------------------------------------------- effective tiers (RFC-0007)


def clean_build(run: RunView) -> bool:
    """INV-TIER-4: harness and adapter trees recorded clean."""
    return (
        run.get("manifest", "harness", "git_dirty") is False
        and run.get("manifest", "system", "adapter_dirty") is False
    )


def effective_tier(
    run: RunView,
    reviews: Sequence[Mapping[str, object]],
    repros: Sequence[Mapping[str, object]],
    maintainers: Iterable[str],
) -> Tier:
    """RFC-0007 §Effective tier at release freeze, with RFC-0009 step 6's added condition
    (the reproducer's organisation differs from the original runner's, inside
    `is_unaffiliated`). `maintainers` are the organisations of the system's maintainers."""
    metrics = run.run.get("metrics")
    grades = [q.get("grade") for q in metrics.values()] if isinstance(metrics, dict) else []
    if grades and all(g == "external" for g in grades):  # imported upstream figures
        return Tier.REPORTED
    if not clean_build(run):
        return Tier.REPORTED
    runner = run.get("manifest", "runner")
    original = runner if isinstance(runner, dict) else {}
    system, maintainers = str(run.run.get("system")), list(maintainers)
    if any(
        r.get("outcome") == "within_tolerance"
        and run.run_id in (r.get("original_run_ids") or [])  # type: ignore[operator]
        and is_unaffiliated(r.get("runner") or {}, system, original, maintainers)  # type: ignore[arg-type]
        for r in repros
    ):
        return Tier.REPRODUCED
    if any(
        v.get("outcome") == "approved"
        and v.get("run_id") == run.run_id
        and _organisation(v.get("reviewer") or {}) != _organisation(original)  # type: ignore[arg-type]
        for v in reviews
    ):
        return Tier.PEER_REVIEWED
    return Tier.REPORTED


def quantity_tier(
    run: RunView,
    metric: str,
    run_tier: Tier,
    seen: frozenset[str] = frozenset(),
    q: Mapping[str, object] | None = None,
) -> Tier:
    """RFC-0007 rules 1 and 2: a measured quantity takes its run's tier; a derived one the
    lowest tier of its inputs (INV-TIER-6), where an input outside this run's measured or
    derived quantities (an asserted price, a projected or external figure) is `reported`.
    `q` is a value evaluated at freeze (RFC-0004 Q3) in place of the stored one."""
    if q is None:
        q = run.run["metrics"][metric]  # type: ignore[index]
    assert q is not None
    grade = q.get("grade")
    if grade == "measured":
        return run_tier
    if grade != "derived" or metric in seen:
        return Tier(str(q.get("tier", "reported"))) if grade == "external" else Tier.REPORTED
    tiers = []
    source = q.get("source")
    for ref in (source.get("inputs") if isinstance(source, Mapping) else None) or []:
        file, _, pointer = str(ref).partition("#")
        name = pointer.removeprefix("/metrics/")
        mine = file.endswith(f"{run.run_id}/run.json") and pointer.startswith("/metrics/")
        tiers.append(quantity_tier(run, name, run_tier, seen | {metric}) if mine
                     and name in run.run["metrics"] else Tier.REPORTED)  # type: ignore[operator]  # fmt: skip
    return lowest_tier(tiers) if tiers else Tier.REPORTED


def run_records(run: RunView, kind: str) -> list[tuple[str, dict[str, object]]]:
    """(repository path, document) of a run's reviews/ or reproductions/ records."""
    return [(f"{_rel(run)}/{kind}/{p.name}", json.loads(p.read_text()))
            for p in sorted((run.path / kind).glob("*.json"))]  # fmt: skip


# ---------------------------------------------------------------- targets (RFC-0009)


@dataclass(frozen=True)
class _Context:
    """What target evaluation needs of one configuration."""

    where: dict[str, object]
    configuration: object
    kept: list[RunView]
    tiers: dict[str, Tier]
    statistics: dict[str, object]
    late: "_Late | None" = None


def evaluate_target(
    target: Mapping[str, object], inputs: Sequence[tuple[str, Mapping[str, object] | None]]
) -> tuple[str, str | None, Mapping[str, object] | None]:
    """RFC-0009 §Targets rules 1 and 2 over one configuration's completed repetitions:
    (result, reason, least favourable quantity). `<=` compares the maximum, `>=` the minimum,
    `==` every repetition; a missing, null or differently labelled metric is not evaluable."""
    threshold = target["threshold"]
    assert isinstance(threshold, Mapping)
    if not inputs:
        return "not_evaluable", "metric missing", None
    for ref, q in inputs:
        if q is None or q.get("value") is None:
            return "not_evaluable", f"metric null in {ref}", None
        for label in ("unit", "scope"):
            if q.get(label) != threshold.get(label):
                return ("not_evaluable", f"{label} {q.get(label)} differs from the threshold's "
                        f"{threshold.get(label)}", None)  # fmt: skip
    limit = float(threshold["value"])
    values = [(float(q["value"]), q) for _, q in inputs if q is not None]  # type: ignore[arg-type]
    if target["comparator"] == "<=":
        worst, ok = max(values, key=lambda v: v[0]), all(v <= limit for v, _ in values)
    elif target["comparator"] == ">=":
        worst, ok = min(values, key=lambda v: v[0]), all(v >= limit for v, _ in values)
    else:
        worst, ok = max(values, key=lambda v: abs(v[0] - limit)), all(v == limit for v, _ in values)
    return ("meets" if ok else "does_not_meet"), None, worst[1]


def _dig(doc: object, dotted: str) -> object:
    for key in dotted.split("."):
        doc = doc.get(key) if isinstance(doc, Mapping) else None
    return doc


def _targets(
    root: Path, registry: SchemaRegistry, release: Release, contexts: Sequence[_Context],
    read: list[Path],
) -> list[dict[str, object]]:  # fmt: skip
    """Step 8: every applicable target per configuration, in target path order. A target
    applies when its claim-class pattern matches the configuration's claim card, every
    `applies_to` key matches the card, and its `profile`, if set, is the row's prover or
    verifier profile (RFC-0009 rule 3: otherwise it is not shown)."""
    import yaml  # noqa: PLC0415

    cards = {(c.system, c.configuration): root / c.path for c in release.claim_cards}
    out = []
    for path in sorted(root.glob("targets/*/*.yaml")):
        errors = registry.errors("target/1", yaml.safe_load(path.read_text()))
        if errors:
            raise _fail(f"{path.relative_to(root)}: {errors[0]}")
        target = yaml.safe_load(path.read_text())
        read.append(path)
        for ctx in contexts:
            card_path = cards.get((str(ctx.where["system"]), str(ctx.configuration)))
            card = yaml.safe_load(card_path.read_text()) if card_path else None
            profiles = {
                ctx.where["profile"],
                *(r.get("manifest", "profile", "verifier") for r in ctx.kept),
            }
            applies = (
                isinstance(card, dict)
                and isinstance(card.get("claim_class"), str)
                and claim_class_matches(target["claim_class"], card["claim_class"])
                and all(_dig(card, k) == v for k, v in (target.get("applies_to") or {}).items())
                and target.get("profile") in (None, *profiles)
            )
            if not applies:
                continue
            done = [r for r in ctx.kept if r.ok]
            result, reason, worst = evaluate_target(
                target, _metric_inputs(done, target["metric"], ctx.tiers, ctx.late)
            )
            mean = ctx.statistics.get(target["metric"]) if worst else None
            out.append({**ctx.where, "target": path.relative_to(root).as_posix(),
                        "result": result, "reason": reason, "mean": mean,
                        "least_favourable": dict(worst) if worst else None})  # fmt: skip
    return out


# ---------------------------------------------------------------- release rows (RFC-0004)


def _reference_roles(root: Path) -> dict[str, str]:
    """system -> `reference_role` (serve, recompute) of every reference system.yaml."""
    import yaml  # noqa: PLC0415

    roles = {}
    for path in sorted(root.glob("systems/*/system.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        if doc.get("kind") == "reference" and doc.get("reference_role"):
            roles[path.parent.name] = str(doc["reference_role"])
    return roles


NM1_KINDS = ("resource", "adapter")


def not_measurable_on_profile(attempts: Sequence[tuple[bool, object]]) -> bool:
    """RFC-0015 NM-1 over a configuration's kept attempts, each (completed, failure kind): true
    when there is at least one and every one failed with `resource` or `adapter`. The freeze
    and the site (`iproofs.site.view`) both call it, so the rule has one copy."""
    return bool(attempts) and all(not ok and kind in NM1_KINDS for ok, kind in attempts)


def _measurable(ctx: "_Context") -> bool:
    """RFC-0015 NM-1: not measurable when every attempt failed with `resource` or `adapter`."""
    return not not_measurable_on_profile(
        [(r.ok, r.get("run", "failure", "kind")) for r in ctx.kept]
    )


def _serving(root: Path, contexts: Sequence["_Context"]) -> dict[str, str | None]:
    """workload id -> the plain-serving system its workload file names (RFC-0015 SRV-7)."""
    import yaml  # noqa: PLC0415

    found: dict[str, str | None] = {}
    for ctx in contexts:
        wid = str(ctx.where["workload"]["id"])  # type: ignore[index]
        if wid not in found:
            path = workload_file(root, wid)
            doc = yaml.safe_load(path.read_text()) if path.is_file() else None
            systems = doc.get("systems") if isinstance(doc, dict) else None
            found[wid] = serving_system(root, [str(s) for s in systems or ()])
    return found


def _release_rows(
    release: str,
    contexts: Sequence["_Context"],
    roles: Mapping[str, str],
    serving: Mapping[str, str | None],
) -> None:
    """Adds to each configuration's statistics the release-level rows of RFC-0004:
    D-PROVIDER-SPREAD per rate, and for system rows D-OVERHEAD-S against the row of the
    plain-serving system the workload names (`serving`, SRV-7) and D-AGREE against the
    ref-recompute runs that replayed its prompts."""
    index = f"releases/{release}/index.json#/configurations"
    for ctx in contexts:
        done = [r for r in ctx.kept if r.ok]
        rates = [m for m in sorted(ctx.statistics) if m.startswith("rate_")]
        for m in rates:
            by_provider: dict[str, list[tuple[str, Mapping[str, object] | None]]] = {}
            for r in done:
                by_provider.setdefault(str(r.get("manifest", "provider")), []).extend(
                    _metric_inputs([r], m, ctx.tiers, ctx.late)
                )
            if any(by_provider.values()):
                ctx.statistics[f"provider_spread_{m[5:]}"] = provider_spread(
                    by_provider, Scope(m[5:]), __version__
                )
        if str(ctx.where["system"]) in roles:
            continue
        _overheads(index, ctx, contexts, serving, rates)
        _agreement(ctx, contexts, roles)


def _overheads(index: str, ctx: "_Context", contexts: Sequence["_Context"],
               serving: Mapping[str, str | None], rates: Sequence[str]) -> None:  # fmt: skip
    """INV-DERIVE-2: join on workload id and version and profile (phase and batch size are
    the workload version's); a row of the workload's plain-serving system (SRV-7: the one its
    `systems` names, never another serve-role system) that does not join gives
    `not_applicable`."""
    wl = ctx.where["workload"]
    named = serving.get(str(wl["id"]))  # type: ignore[index]
    serve = [(i, c) for i, c in enumerate(contexts)
             if named is not None and str(c.where["system"]) == named
             and c.where["workload"]["id"] == wl["id"]]  # type: ignore[index]  # fmt: skip
    if not serve:
        return
    same = (wl, ctx.where["profile"])
    joins = [(i, c) for i, c in serve if (c.where["workload"], c.where["profile"]) == same]
    i, ref = (joins or serve)[0]
    mine = contexts.index(ctx)
    for m in rates:
        q = ref.statistics.get(m)
        ctx.statistics[f"overhead_vs_serving_{m[5:]}"] = overhead(
            (f"{index}/{i}/statistics/{m}", q if isinstance(q, Mapping) else None),
            (f"{index}/{mine}/statistics/{m}", ctx.statistics[m]),  # type: ignore[arg-type]
            Scope(m[5:]),
            joined=bool(joins),
            measurable=_measurable(ref),
            version=__version__,
        )


def _agreement(ctx: "_Context", contexts: Sequence["_Context"], roles: Mapping[str, str]) -> None:
    """RFC-0015 RC-5: the ref-recompute runs whose prompts came from this configuration's runs."""
    mine = {r.run_id for r in ctx.kept}
    paired = [c for c in contexts if roles.get(str(c.where["system"])) == "recompute"
              and any(r.get("manifest", "prompts_from") in mine for r in c.kept)]  # fmt: skip
    if not paired:
        return
    agree: list[tuple[str, Mapping[str, object] | None]] = []
    disagree: list[tuple[str, Mapping[str, object] | None]] = []
    for c in paired:
        runs = [r for r in c.kept if r.ok and r.get("manifest", "prompts_from") in mine]
        agree += _metric_inputs(runs, "agreement_positions", c.tiers)
        disagree += _metric_inputs(runs, "disagreement_positions", c.tiers)
    if not agree:  # every paired run failed: the inputs are their failure records (INV-QTY-8)
        agree = [(f"{_rel(r)}/run.json#/failure", None) for c in paired for r in c.kept
                 if not r.ok and r.get("manifest", "prompts_from") in mine]  # fmt: skip
    out = agreement_rate(
        agree, disagree, measurable=all(_measurable(c) for c in paired), version=__version__
    )
    if out["null_reason"] == NullReason.MISSING_INPUT and not disagree:
        out["null_reason"] = str(NullReason.STEP_FAILED)
    ctx.statistics["agreement_rate"] = out
