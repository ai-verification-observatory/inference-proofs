"""Release freeze and run eligibility (RFC-0009, RFC-0014). Every quantity keeps the tier its
run recorded (`reported`); no review or reproduction record changes it during research."""

import functools
import hashlib
import json
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from iproofs import __version__
from iproofs.derive import (
    STEADY_RULE,
    Input,
    QuantityTree,
    agreement_rate,
    freeze_values,
    overhead,
    overhead_formula,
    provider_spread,
    statistic,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import ReferenceFile, Release, ServingModel, ServingProfile, Workload, load
from iproofs.provenance import file_digest
from iproofs.quantity import (
    NullReason,
    Scope,
    claim_class_matches,
    parse_claim_class,
)
from iproofs.schema import SchemaRegistry
from iproofs.serving import SHORT_STEADY
from iproofs.workloads import asserted_inputs, serving_system, workload_file

MIN_REPLAYED = 3  # fewer completed repetitions mark a configuration insufficient


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


# ---------------------------------------------------------------- eligibility (RFC-0014)

# Stable reason strings, shown by the release index and the site.
REASONS = {
    "other_release": "the run belongs to another release",
    "manifest_invalid": "the manifest fails manifest/1 (a pin is not in full form)",
    "self_test_failed": "the host's calibration self-test did not pass",
    "claim_card_not_listed": "the run's claim card is not the one the release lists",
    "harness_dirty": "the harness tree was dirty",
    "adapter_dirty": "the adapter tree was dirty or unknown",
}


def eligibility(
    run_dir: Path,
    release: Release,
    root: Path,
    registry: SchemaRegistry,
) -> tuple[bool, list[str]]:
    """RFC-0014 §Eligibility of one stored run for `release`: (eligible, reason codes from
    REASONS, in that order). Reads only the run's documents, the release record and
    system.yaml at the run's adapter commit."""
    run = RunView.read(run_dir)
    m, system = run.manifest, run.get("manifest", "system")
    assert isinstance(system, dict)
    claim = m.get("claim")
    pinned = _system_at(root, str(system.get("adapter_commit")), str(system.get("name"))) or {}
    reference = pinned.get("kind") == "reference"  # RFC-0015: no claim card, no proofs (REF-2)
    cards = {(c.system, c.configuration, c.card_version, c.digest) for c in release.claim_cards}
    failed = {
        "other_release": m.get("release") != release.release,
        "manifest_invalid": bool(registry.errors("manifest/1", m)),
        "self_test_failed": run.get("manifest", "self_test", "passed") is not True,
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
    }
    reasons = [code for code in REASONS if failed[code]]
    return not reasons, reasons


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


# ---------------------------------------------------------------- freeze (RFC-0009)

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
) -> dict[str, object]:
    """RFC-0009 §Freeze algorithm. `gates` runs G2 to G7 over repository paths and returns the
    failing lines. Returns the `release-index/1` document; nothing is written and no clock is
    read, so the same inputs give the same bytes."""
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
    for card in release.claim_cards:
        if not (root / card.path).is_file() or file_digest(root / card.path) != card.digest:
            raise _fail(f"claim card {card.path} does not match its listed digest")
        read.append(root / card.path)
    failing = gates([*release.runs, path.relative_to(root).as_posix()])  # step 2
    if failing:
        raise _fail(f"gates failed: {failing[0]}")
    excluded = _excluded(release, runs, root, registry)
    late = _Late(root, registry, release.release, (reference, release.reference_file))
    configurations, controls, contexts = _configurations(runs, excluded, late)
    _require_closed(root, release, contexts)
    _release_rows(
        release.release, contexts, _reference_roles(root), _Serving(root, registry, reference)
    )
    targets = _targets(root, registry, release, contexts, read)
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
    for run_id, run in runs.items():
        ok, reasons = eligibility(run.path, release, root, registry)
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
    late: "_Late",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list["_Context"]]:
    groups: dict[tuple[object, ...], list[RunView]] = {}
    for run in runs.values():
        key = (run.run.get("system"), run.get("manifest", "claim", "configuration"),
               run.get("manifest", "workload", "id"), run.get("manifest", "workload", "version"),
               run.get("manifest", "profile", "prover"),
               run.get("manifest", "workload", "load_point"))  # fmt: skip  # SRV-1
        groups.setdefault(key, []).append(run)
    configurations, controls, contexts = [], [], []
    for group_key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        system, configuration, workload, version, profile, load_point = group_key
        members = sorted(groups[group_key], key=_repetition_order)
        kept = [r for r in members if r.run_id not in excluded]
        where = {
            "system": system,
            "workload": {"id": workload, "version": version},
            "profile": profile,
        }
        configurations.append({
            **where,
            **({"load_point": load_point} if load_point is not None else {}),
            "configuration": configuration,
            "runs": [r.run_id for r in kept],
            "ineligible": [{"run_id": r.run_id, "reasons": excluded[r.run_id]}
                           for r in members if r.run_id in excluded],
            "insufficient_repetitions": sum(r.ok for r in kept) < MIN_REPLAYED,
            "statistics": (stats := _statistics(kept, late)),
            **({"steady_boundary": FIRST_PROOF_BOUNDARY} if late.first_proof_boundary(kept)
               else {}),
        })  # fmt: skip
        controls.append({**where, **_control_summary(kept)})
        contexts.append(_Context(where, configuration, kept, stats, late,
                                 None if load_point is None else str(load_point),
                                 configurations[-1]))  # fmt: skip
    return configurations, controls, contexts


class _Late:
    """RFC-0004 Q3: values a freeze evaluates for runs stored before their formula existed,
    written to index.json `freeze_derived` and pointed at from there."""

    def __init__(
        self,
        root: Path,
        registry: SchemaRegistry,
        release: str,
        reference: tuple[ReferenceFile, str] | None = None,
    ) -> None:
        self.root, self.registry, self.release = root, registry, release
        self.reference = reference  # the reference file and its path, for D-GSPT-S
        self.values: dict[str, dict[str, QuantityTree]] = {}
        self._workloads: dict[str, Workload] = {}

    def gpu_count(self, run: RunView) -> Input | None:
        """RFC-0004 Q3 for D-GSPT-S: the profile's `gpu.count` in the reference file at the
        release commit, as an asserted input; None for a CPU-only profile (no GPU count, so no
        D-GSPT-S) or without a reference file."""
        if self.reference is None:
            return None
        reference, path = self.reference
        name = str(run.get("run", "profile"))
        gpu = getattr(reference.profiles.get(name), "gpu", None)
        if gpu is None:
            return None
        ref = f"{path}#/profiles/{name}/gpu/count"
        return (ref, {"value": gpu.count, "unit": "count", "scope": None, "grade": "asserted",
                      "tier": "reported", "source": {"kind": "reference_file", "ref": ref},
                      "null_reason": None})  # fmt: skip

    def workload(self, wid: str) -> Workload:
        """The workload record at the release commit (the record only, not the loader's
        cross-file rules)."""
        if wid not in self._workloads:
            wl = load(workload_file(self.root, wid), self.registry)
            if not isinstance(wl, Workload):
                raise _fail(f"workloads/{wid}.yaml is not a workload record")
            self._workloads[wid] = wl
        return self._workloads[wid]

    def first_proof_boundary(self, runs: Sequence[RunView]) -> bool:
        """RFC-0004 INV-SCOPE-5: a completed run at batch size b > 1 that records no steady
        rule keeps the first-proof boundary of runs recorded before 2026-11-09 (APP-1)."""
        for r in runs:
            if not r.ok or r.get("manifest", "workload", "steady_rule") == STEADY_RULE:
                continue
            size = r.get("manifest", "workload", "batch_size_run")
            if not isinstance(size, int):
                size = self.workload(str(r.get("run", "workload", "id"))).shape.batch_size
            if size > 1:
                return True
        return False

    def workload_inputs(self, run: RunView) -> tuple[Input, Input]:
        """The workload record's asserted inputs at the release commit, as (pointer, quantity);
        missing inputs when the record now holds another version than the run's."""
        wl = self.workload(str(run.get("run", "workload", "id")))
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
            gpu_count=self.gpu_count(run),
        )
        if values:
            self.values[run.run_id] = values
        return values

    def pointer(self, run: RunView, metric: str) -> str:
        return f"releases/{self.release}/index.json#/freeze_derived/{run.run_id}/{metric}"


def _statistics(kept: Sequence[RunView], late: _Late) -> dict[str, object]:
    """D-STAT per metric over completed repetitions, in repetition order (INV-DERIVE-1);
    failed repetitions count in n_failed. A run stored before a formula of FREEZE_FORMULAS
    existed gets its value at freeze (RFC-0004 Q3), so it stays in n."""
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
        inputs = _metric_inputs(done, metric, late)
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
        elif any("per_active_weight_bit" in name for name in evaluated[r.run_id]):
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
    done: Sequence[RunView], metric: str, late: _Late | None = None
) -> list[tuple[str, Mapping[str, object] | None]]:
    """(pointer, quantity) per completed repetition that has `metric`, stored in its run.json
    or evaluated at freeze (`late`, RFC-0004 Q3)."""
    inputs: list[tuple[str, Mapping[str, object] | None]] = []
    for r in done:
        stored: dict[str, dict[str, object]] = r.run["metrics"]  # type: ignore[assignment]
        if metric in stored:
            inputs.append((f"{_rel(r)}/run.json#/metrics/{metric}", stored[metric]))
        elif late is not None and metric in late.values.get(r.run_id, {}):
            inputs.append((late.pointer(r, metric), late.values[r.run_id][metric]))
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


# ---------------------------------------------------------------- targets (RFC-0009)


@dataclass(frozen=True)
class _Context:
    """What target evaluation needs of one configuration."""

    where: dict[str, object]
    configuration: object
    kept: list[RunView]
    statistics: dict[str, object]
    late: "_Late | None" = None
    load_point: str | None = None  # RFC-0015 SRV-1, production-serving configurations
    entry: dict[str, object] | None = None  # the index configuration, for overhead_conditions


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
                target, _metric_inputs(done, target["metric"], ctx.late)
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


def _release_rows(
    release: str,
    contexts: Sequence["_Context"],
    roles: Mapping[str, str],
    serving: "_Serving | None" = None,
) -> None:
    """Adds to each configuration's statistics the release-level rows of RFC-0004:
    D-PROVIDER-SPREAD per rate, and for system rows D-OVERHEAD-S and D-OVERHEAD-HIGH-S against
    the production-serving system the workload names (RFC-0015 SRV-7, INV-DERIVE-2) and D-AGREE
    against the ref-recompute runs that replayed its prompts."""
    index = f"releases/{release}/index.json#/configurations"
    for ctx in contexts:
        done = [r for r in ctx.kept if r.ok]
        rates = [m for m in sorted(ctx.statistics) if m.startswith("rate_")]
        for m in rates:
            by_provider: dict[str, list[tuple[str, Mapping[str, object] | None]]] = {}
            for r in done:
                by_provider.setdefault(str(r.get("manifest", "provider")), []).extend(
                    _metric_inputs([r], m, ctx.late)
                )
            if any(by_provider.values()):
                ctx.statistics[f"provider_spread_{m[5:]}"] = provider_spread(
                    by_provider, Scope(m[5:]), __version__
                )
        if str(ctx.where["system"]) in roles:
            continue
        if serving is not None:
            _overheads(index, ctx, contexts, serving)
        _agreement(ctx, contexts, roles)


class _Serving:
    """What the overhead join reads at the release commit (RFC-0004 INV-DERIVE-2): the
    serve-role system each workload names, its system.yaml, the serving record that names the
    workload, and the reference file's profiles."""

    def __init__(self, root: Path, registry: SchemaRegistry, reference: ReferenceFile) -> None:
        from iproofs.serving import load_records  # noqa: PLC0415

        self.root, self.registry, self.reference = root, registry, reference
        self.records = load_records(root, registry)
        self._named: dict[str, str | None] = {}

    def named(self, workload: str) -> str | None:
        """SRV-7: the one serve-role system the workload's `systems` names."""
        import yaml  # noqa: PLC0415

        if workload not in self._named:
            path = workload_file(self.root, workload)
            doc = yaml.safe_load(path.read_text()) if path.is_file() else None
            systems = doc.get("systems") if isinstance(doc, dict) else None
            self._named[workload] = serving_system(self.root, [str(x) for x in systems or ()])
        return self._named[workload]

    def system(self, name: str) -> dict[str, object]:
        import yaml  # noqa: PLC0415

        path = self.root / "systems" / name / "system.yaml"
        doc = yaml.safe_load(path.read_text()) if path.is_file() else None
        return doc if isinstance(doc, dict) else {}

    def record(self, workload: str) -> "ServingModel | None":
        found = [r for r in self.records.values() if workload in r.workloads]
        return found[0] if len(found) == 1 else None

    def pairs(self, serving_profile: object, system_profile: object) -> bool:
        """INV-DERIVE-2 (c): a serving profile whose `pairs_with` lists the system's profile."""
        found = self.reference.profiles.get(str(serving_profile))
        return isinstance(found, ServingProfile) and str(system_profile) in found.pairs_with

    def gpus(self, profile: object) -> int | None:
        found = self.reference.profiles.get(str(profile))
        gpu = getattr(found, "gpu", None)
        return None if gpu is None else int(gpu.count)

    def gpu_model(self, profile: object) -> str | None:
        gpu = getattr(self.reference.profiles.get(str(profile)), "gpu", None)
        return None if gpu is None else str(gpu.model)

    def runtime(self, profile: object) -> str:
        found = self.reference.profiles.get(str(profile))
        runtime = getattr(found, "container_runtime", None)
        return "hosted" if getattr(runtime, "kind", None) == "hosted" else "docker host"

    def workload(self, workload: str) -> Workload:
        doc = load(workload_file(self.root, workload), self.registry)
        assert isinstance(doc, Workload)
        return doc


FIRST_PROOF_BOUNDARY = "first-proof boundary (before 2026-11-09)"  # INV-SCOPE-5, APP-1


def _steady_rule(run: RunView, batch: int) -> bool:
    """INV-SCOPE-5: a run at batch size b > 1 joins only if it records the batch-membership
    rule (a run recorded before 2026-11-09 keeps the first-proof boundary, APP-1)."""
    return batch <= 1 or run.get("manifest", "workload", "steady_rule") == STEADY_RULE


def _strings(value: object) -> list[str]:
    return [str(x) for x in value] if isinstance(value, list) else []


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _overheads(index: str, ctx: "_Context", contexts: Sequence["_Context"],  # noqa: PLR0915
               serving: _Serving) -> None:  # fmt: skip
    """RFC-0004 INV-DERIVE-2: D-OVERHEAD-S (matched load), D-OVERHEAD-HIGH-S (high load) and
    D-OVERHEAD-WARM (the prover's `prove.session` over matched serving's `prove.steady`,
    INV-DERIVE-11) of one system configuration, in GPU-seconds per token, its
    `overhead_headline` (INV-DERIVE-10, -11) and the headline's `overhead_conditions`
    (INV-DERIVE-9). Absent when the workload names no serve-role system.

    The matched join takes the smallest GPU count with a joinable run; the high load joins
    only at that same profile."""
    wl = ctx.where["workload"]
    assert isinstance(wl, Mapping)
    named = serving.named(str(wl["id"]))
    if named is None:
        return
    record = serving.record(str(wl["id"]))
    system_doc = serving.system(named)
    engine = system_doc.get("engine") if isinstance(system_doc.get("engine"), dict) else {}
    assert isinstance(engine, dict)
    batch = serving.workload(str(wl["id"])).shape.batch_size
    mine = {r.run_id for r in ctx.kept}
    mine_index = contexts.index(ctx)
    tried = [c for c in contexts if str(c.where["system"]) == named
             and c.where["workload"] == wl]  # fmt: skip
    paired = [c for c in tried if serving.pairs(c.where["profile"], ctx.where["profile"])]
    keyed = [c for c in paired if any(_serving_keys(r, record, engine) for r in c.kept)]

    def point(c: _Context) -> str:
        return c.load_point or "matched"

    def joinable(c: _Context) -> list[RunView]:
        """(e) the pinned engine and model, (f) paired by prompts, SRV-1's 60 s minimum,
        INV-SCOPE-5's rule, and no sizing capture (SRV-1: it sizes the session only)."""
        size = batch if point(c) == "matched" else 2  # a high-load batch is above 1 (SRV-1)
        return [r for r in c.kept if r.ok and _serving_keys(r, record, engine)
                and r.get("manifest", "prompts_from") in mine
                and SHORT_STEADY not in _strings(r.get("run", "warnings"))
                and r.get("manifest", "workload", "sizing_capture") is not True
                and _steady_rule(r, size)]  # fmt: skip

    chosen: dict[str, tuple[int, _Context, list[RunView]] | None] = {}
    reasons: dict[str, NullReason] = {}
    candidates = sorted(
        (serving.gpus(c.where["profile"]) or 0, contexts.index(c), runs) for c in keyed
        if point(c) == "matched" and (runs := joinable(c))
    )  # fmt: skip
    if candidates:
        _, i, runs = candidates[0]
        chosen["matched"] = (i, contexts[i], runs)
        at = contexts[i]
        high = sorted((contexts.index(c), runs) for c in keyed
                      if point(c) == "high" and c.where["profile"] == at.where["profile"]
                      and (runs := joinable(c)))  # fmt: skip
        if high:
            chosen["high"] = (high[0][0], contexts[high[0][0]], high[0][1])
        elif any(point(c) == "high" and joinable(c) for c in keyed):
            reasons["high"] = NullReason.NOT_APPLICABLE  # another placement than the headline's
        else:
            reasons["high"] = NullReason.MISSING_INPUT
    else:
        why = NullReason.NOT_APPLICABLE if tried and not keyed else NullReason.MISSING_INPUT
        reasons["matched"] = reasons["high"] = why
    done = [r for r in ctx.kept if r.ok]
    conforming = [r for r in done if _steady_rule(r, batch)]
    if done and not conforming:  # every system run keeps the first-proof boundary (APP-1)
        reasons["matched"] = reasons["high"] = NullReason.NOT_APPLICABLE
    steady_metric = f"gpu_seconds_per_token_{Scope.PROVE_STEADY}"
    steady = _metric_inputs(conforming or done, steady_metric, ctx.late)
    if steady:
        for at_load, key in (("matched", "overhead_vs_production"),
                             ("high", "overhead_vs_production_high")):  # fmt: skip
            found = chosen.get(at_load)
            serve_in = [] if found is None else _metric_inputs(found[2], steady_metric,
                                                               found[1].late)  # fmt: skip
            ctx.statistics[f"{key}_{Scope.PROVE_STEADY}"] = overhead(
                steady, serve_in, Scope.PROVE_STEADY, high=at_load == "high",
                reason=reasons.get(at_load), version=__version__,
            )  # fmt: skip
    scope = headline_scope(steady)
    warm = scope is Scope.PROVE_SESSION  # no steady scope of its own: the warm figure
    session = _metric_inputs(conforming or done, f"gpu_seconds_per_token_{Scope.PROVE_SESSION}",
                             ctx.late)  # fmt: skip
    if warm and session:  # INV-DERIVE-11: the prover's session over warm serving's steady scope
        found = chosen.get("matched")
        warm_in = [] if found is None else _metric_inputs(found[2], steady_metric, found[1].late)
        ctx.statistics[WARM] = overhead(session, warm_in, Scope.PROVE_SESSION, warm=True,
                                        reason=reasons.get("matched"),
                                        version=__version__)  # fmt: skip
    key = WARM if warm else f"overhead_vs_production_{scope}"
    headline = ctx.statistics.get(key)
    if ctx.entry is None or not isinstance(headline, dict):
        return
    ctx.entry["overhead_headline"] = {
        "metric": key,
        "formula": overhead_formula(scope, warm=warm),
        "scope": str(scope),
        "serving_scope": str(Scope.PROVE_STEADY),
        "start_up": "prover_only" if warm else "excluded",
    }
    if headline["value"] is not None:
        ctx.entry["overhead_conditions"] = _conditions(
            index, ctx, mine_index, chosen, record, engine, serving, Scope.PROVE_STEADY
        )


# INV-SCOPE-2 and -3: the null reasons of a system that has no steady scope of its own
NO_STEADY = frozenset({NullReason.NOT_EXTERNALLY_OBSERVABLE, NullReason.FEWER_THAN_TWO_PROOFS})
WARM = "overhead_vs_production_warm"  # RFC-0004 INV-DERIVE-11, D-OVERHEAD-WARM


def headline_scope(steady: Sequence[tuple[str, Mapping[str, object] | None]]) -> Scope:
    """RFC-0004 INV-DERIVE-10, -11: the prover's scope in a system row's headline overhead.
    `prove.steady` (D-OVERHEAD-S), unless the system has no steady scope: every successful
    repetition's `gpu_seconds_per_token_prove.steady` is null with `not_externally_observable`
    or `fewer_than_two_proofs` (SASH, RFC-0004 Q2), or none records it. Then `prove.session`:
    the headline is D-OVERHEAD-WARM, the prover's session (its start-up included) over warm
    serving's steady scope. A steady figure null for a join reason (no paired serving run,
    another profile) stays the headline, with that reason."""
    values = [q for _, q in steady if q is not None]
    if values and any(q.get("value") is not None or q.get("null_reason") not in NO_STEADY
                      for q in values):  # fmt: skip
        return Scope.PROVE_STEADY
    return Scope.PROVE_SESSION


def _serving_keys(
    run: RunView, record: "ServingModel | None", engine: Mapping[str, object]
) -> bool:
    """INV-DERIVE-2 (e): the run served the record's model digest with the engine image the
    release's system.yaml pins (a re-pinned engine never pools with the old one)."""
    if record is None:
        return False
    digest = run.get("manifest", "serving_model", "digest")
    image = run.get("manifest", "engine", "image")
    return digest == record.model.digest and image == engine.get("image")


def _conditions(
    index: str,
    ctx: "_Context",
    mine: int,
    chosen: Mapping[str, tuple[int, "_Context", list[RunView]] | None],
    record: "ServingModel | None",
    engine: Mapping[str, object],
    serving: _Serving,
    serving_scope: Scope = Scope.PROVE_STEADY,
) -> dict[str, object]:
    """RFC-0004 INV-DERIVE-9: the conditions of the headline overhead (INV-DERIVE-10, -11),
    every value read from records (the runs' manifests, the serving record, the system and
    workload files, the reference file); the site prints its strings from this block and types
    none. `warm` is true when serving's start-up is outside the serving scope (`prove.steady`):
    a steady headline, or a warm one (INV-DERIVE-11, the prover's session over serving's steady
    scope)."""
    wl = ctx.where["workload"]
    assert isinstance(wl, Mapping)
    matched, high = chosen.get("matched"), chosen.get("high")
    workload_doc = serving.workload(str(wl["id"]))
    shape = workload_doc.shape
    sys_gpus = serving.gpus(ctx.where["profile"])

    def run_field(found: tuple[int, "_Context", list[RunView]] | None, *keys: str) -> object:
        if found is None or not found[2]:
            return None
        values = {json.dumps(found[2][0].get(*keys))} | {json.dumps(r.get(*keys)) for r in found[2]}
        return found[2][0].get(*keys) if len(values) == 1 else None

    def settings(found: tuple[int, "_Context", list[RunView]] | None) -> str | None:
        """SRV-3: the chosen configuration's own allowlisted options, with their values."""
        if found is None:
            return None
        doc = serving.system(str(found[1].where["system"]))
        gpus = serving.gpus(found[1].where["profile"])
        point = found[1].load_point or "matched"
        entries = doc.get("workloads")
        args = next((list(e.get("engine_args") or []) for e in _items(entries)
                     if isinstance(e, dict) and e.get("id") == wl["id"]
                     and (e.get("load_point") or "matched") == point
                     and e.get("gpus") in (None, gpus)), None)  # fmt: skip
        if args is None:
            return None
        flags = iter(args)
        pairs = [f"{a} {b}" for a, b in zip(flags, flags, strict=False)]
        return "engine defaults except " + ", ".join(pairs) if pairs else "engine defaults"

    interface = run_field(matched, "manifest", "engine", "interface")
    serve_profile = None if matched is None else matched[1].where["profile"]
    high_profile = None if high is None else high[1].where["profile"]
    bits = workload_doc.precision.weight_bits
    return {
        "serving_configuration": None if matched is None else f"{index}/{matched[0]}",
        "high_configuration": None if high is None else f"{index}/{high[0]}",
        "engine": {"name": str(engine.get("name", "")) or "not stated",
                   "version": str(engine.get("version", "")) or "not stated",
                   "interface": None if interface is None else str(interface),
                   "image_digest": None if not engine.get("image") else str(engine["image"]),
                   "settings": settings(matched) or "not recorded",
                   "settings_high": settings(high),
                   "max_num_batched_tokens": {
                       "matched": _int(run_field(matched, "manifest", "engine", "observed",
                                                 "max_num_batched_tokens")),
                       "high": _int(run_field(high, "manifest", "engine", "observed",
                                              "max_num_batched_tokens"))}},
        "decoding": "greedy",
        "warm": serving_scope is not Scope.PROVE_SESSION,
        "runtime": serving.runtime(ctx.where["profile"]),
        "serving_model": None if record is None else {
            "id": record.id, "version": record.version, "digest": record.model.digest,
            "publisher": record.publisher.name, "precision": record.precision.name,
            "release_statement": _statement(record)},
        "proved_precision": workload_doc.precision.proved,
        "weight_bits": None if bits is None or bits.bits is None
        else f"workloads/{wl['id']}.yaml#/precision/weight_bits",
        "gpus": {"system": sys_gpus,
                 "serving": serving.gpus(serve_profile) if serve_profile else None,
                 "serving_high": serving.gpus(high_profile) if high_profile else None},
        "gpu_model": serving.gpu_model(ctx.where["profile"]),
        "profiles": {"system": str(ctx.where["profile"]),
                     "serving": None if serve_profile is None else str(serve_profile),
                     "serving_high": None if high_profile is None else str(high_profile)},
        "batch": {"matched": shape.batch_size,
                  "high": _int(run_field(high, "manifest", "workload", "batch_size_run"))},
        "batches_per_session": {
            "system": shape.batches_per_session,
            "serving_matched": _int(run_field(matched, "manifest", "workload",
                                              "batches_per_session_run")),
            "serving_high": _int(run_field(high, "manifest", "workload",
                                           "batches_per_session_run"))},
        "prompt_count_run": {
            "system": shape.batch_size * shape.batches_per_session,
            "serving_matched": _int(run_field(matched, "manifest", "workload", "prompt_count_run")),
            "serving_high": _int(run_field(high, "manifest", "workload", "prompt_count_run"))},
        "n": {"system": sum(r.ok for r in ctx.kept),
              "serving_matched": 0 if matched is None else len(matched[2]),
              "serving_high": 0 if high is None else len(high[2])},
    }  # fmt: skip


def _statement(record: "ServingModel") -> str:
    said = record.precision.release_statement
    return said if isinstance(said, str) else said.quote


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


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
        agree += _metric_inputs(runs, "agreement_positions")
        disagree += _metric_inputs(runs, "disagreement_positions")
    if not agree:  # every paired run failed: the inputs are their failure records (INV-QTY-8)
        agree = [(f"{_rel(r)}/run.json#/failure", None) for c in paired for r in c.kept
                 if not r.ok and r.get("manifest", "prompts_from") in mine]  # fmt: skip
    out = agreement_rate(agree, disagree, version=__version__)
    if out["null_reason"] == NullReason.MISSING_INPUT and not disagree:
        out["null_reason"] = str(NullReason.STEP_FAILED)
    ctx.statistics["agreement_rate"] = out
