"""Every value the site prints, computed from the frozen release (RFC-0009 §Site, #320).

`site_view(root)` returns plain JSON-able data for the `web/build.py` renderer: no number is
typed or recomputed here (AGENTS.md rule 3). A figure carries its stored value, unit, scope,
grade, tier, null reason, statistics, formula id and the JSON Pointer of its record in the
release index; its sort key is the stored value in its base unit (S4). Pure apart from the
reads in `inputs`.
"""

import math
from pathlib import Path
from typing import Any

from iproofs.controls import CONTROL_PROPERTY, runs_read
from iproofs.derive import STEADY_RULE, formula_of
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import SiteFacts
from iproofs.release import REASONS
from iproofs.schema import SchemaRegistry
from iproofs.serving import SHORT_STEADY
from iproofs.site import inputs
from iproofs.site.inputs import REPOSITORY

# The figures each configuration prints: the overview columns, then More numbers (#320 §1).
FIGURES = ("tokens_covered_per_proof", "proof_bytes", "verify_seconds",
           "overhead_vs_production_prove.steady",
           "overhead_vs_production_warm")  # fmt: skip
OVERHEAD = "overhead_vs_production_prove.steady"  # RFC-0004 INV-DERIVE-9, the headline
WARM = "overhead_vs_production_warm"  # RFC-0004 INV-DERIVE-11: no steady scope of its own
# RFC-0004 D-SPAB-S, prover seconds per active weight bit per token: the overview shows the steady
# figure, or the session figure where the steady one is null (owner decision of 2026-11-09)
PER_BIT = ("seconds_per_active_weight_bit_token_prove.steady",
           "seconds_per_active_weight_bit_token_prove.session")  # fmt: skip
# RFC-0004 D-BPAB and D-VSPAB: proof size and check time on the same basis, for the overview
PER_BIT_SIZE = ("proof_bytes_per_active_weight_bit_token",
                "verify_seconds_per_active_weight_bit_token")  # fmt: skip
MORE = ("rate_prove.session", "cost_per_1k_tokens_prove.session", "commit_seconds",
        "verify_host_memory_peak_anon", "prove_gpu_memory_peak")  # fmt: skip
# what production serving measured, the baseline every overhead divides by (RFC-0015 SRV-6)
SERVING = ("gpu_seconds_per_token_prove.steady", "rate_prove.steady",
           "cost_per_1k_tokens_prove.steady")  # fmt: skip
AGREEMENT = "agreement_rate"
# RFC-0016 §States: the states a contradicting outcome turns to `no` (OVR-4)
CONTRADICTABLE = ("yes", "partly")
LINK_REF = "main"  # #320 plan §1.1: no tracked file records the commit that merged index.json


def _config(message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"site: {message}")


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def figure(
    index_path: str,
    position: int,
    statistics: dict[str, Any],
    metric: str,
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """One stored statistic as the pages print it, labels unchanged (S2, S3, S4). `formula`
    is the statistic's own id (D-STAT or a release row); `repetition_formula` the id of the
    per-repetition quantity it summarises, when that one is derived (for example D-TPP)."""
    q = statistics.get(metric)
    if q is None:  # not recorded in these runs
        return {"metric": metric, "recorded": False, "value": None, "sort_key": None}
    value = q["value"]
    return {
        "metric": metric,
        "recorded": True,
        "value": value,
        "unit": q["unit"],
        "scope": q["scope"],
        "grade": q["grade"],
        "tier": q["tier"],
        "null_reason": q["null_reason"],
        "stats": q.get("stats"),
        "formula": formula_of(q)[0],
        "repetition_formula": _repetition_formula(q, records),
        "source": f"{index_path}#/configurations/{position}/statistics/{_escape(metric)}",
        "sort_key": None if value is None else float(value),
        "pairs": q.get("pairs"),  # an overhead's prover and serving run counts and range
        "runs": input_runs(q),  # the runs its source inputs read
    }


def input_runs(q: dict[str, Any]) -> list[str]:
    """The run ids a statistic's source inputs read, in their order, each once: a run's own
    `run.json` or its entry in the index's `freeze_derived`."""
    out: list[str] = []
    for ref in q["source"].get("inputs") or []:
        file, _, pointer = str(ref).partition("#")
        if file.endswith("/run.json"):
            rid = file.rsplit("/", 2)[-2]
        elif pointer.startswith("/freeze_derived/"):
            rid = pointer.split("/")[2]
        else:
            continue
        if rid not in out:
            out.append(rid)
    return out


def _repetition_formula(q: dict[str, Any], records: dict[str, dict[str, Any]]) -> str | None:
    for ref in q["source"].get("inputs") or []:
        file, _, pointer = str(ref).partition("#")
        rec = records.get(file.rsplit("/", 2)[-2]) if file.endswith("/run.json") else None
        stored = (
            inputs.maybe(rec["run"], "metrics", pointer.removeprefix("/metrics/")) if rec else None
        )
        if isinstance(stored, dict) and stored.get("grade") == "derived":
            return formula_of(stored)[0]
    return None


def _record(records: dict[str, dict[str, Any]], rid: str | None, name: str) -> str | None:
    """A listed run's record file (`run.json` or `controls.json`), as a path in the tree."""
    rec = records.get(str(rid)) if rid is not None else None
    return None if rec is None else f"{rec['dir']}/{name}"


def _left_out(config: dict[str, Any], records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """S7: every listed run not counted, with its reasons, its record and the run that replaced
    it (with that run's record)."""
    out = []
    for entry in config["ineligible"]:
        reasons = [str(r) for r in entry["reasons"]]
        by = next((r.split(":", 1)[0].removeprefix("superseded by ") for r in reasons
                   if r.startswith("superseded by ")), None)  # fmt: skip
        out.append({"run_id": entry["run_id"], "reasons": reasons, "replaced_by": by,
                    "reason_words": [REASONS.get(r, r) for r in reasons],
                    "record": _record(records, entry["run_id"], "run.json"),
                    "replaced_by_record": _record(records, by, "run.json")})  # fmt: skip
    return out


def _runs(config: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Kept runs: completed and failed, each failure with kind, step, exit code, last line."""
    failed = []
    completed = []
    for rid in config["runs"]:
        rec = records[rid]
        run = rec["run"]
        if run["status"] == "completed":
            completed.append(rid)
            continue
        failure = run["failure"] or {}
        lines = failure.get("last_lines") or []
        failed.append({
            "run_id": rid,
            "kind": failure.get("kind"),
            "step": failure.get("step"),
            "exit_code": failure.get("exit_code"),
            "last_line": lines[-1] if lines else None,
            "record": f"{rec['dir']}/run.json",
        })  # fmt: skip
    return {
        "completed": completed,
        "failed": failed,
        "left_out": _left_out(config, records),
        "records": {rid: f"{records[rid]['dir']}/run.json" for rid in config["runs"]},
    }


def property_controls(
    root: Path,
    criteria: inputs.Criteria,
    row: dict[str, Any],
    configuration: str,
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """OVR-7: per property, each mapped control's outcome in every run OVR-5 reads; the site
    lists, it never sets a state. With no criteria `release` no run is read (OVR-5); "not run"
    is a mapped control absent from a read run's controls.json, or a read run with none. Each
    run read carries its `run.json` and, when it has one, its `controls.json`. A run of the
    rendered release is read from `records`; only a run of an earlier
    release is read again from disk."""
    read = runs_read(root, criteria.release, str(row["card"]["system"]), configuration)
    held = {rec["dir"]: rec["controls"] for rec in records.values()}
    controls: dict[str, dict[str, Any]] = {}
    where: dict[str, str] = {}  # run id -> its controls.json, for a run that has one
    dirs: dict[str, str] = {}
    for run_dir in read:
        dirs[run_dir.rsplit("/", 1)[1]] = run_dir
        path = root / run_dir / "controls.json"
        if run_dir in held:
            doc = held[run_dir]
        else:
            doc = inputs.read_json(path) if path.is_file() else None
        if doc is not None:
            where[run_dir.rsplit("/", 1)[1]] = f"{run_dir}/controls.json"
        doc = doc or {"controls": []}
        controls[run_dir.rsplit("/", 1)[1]] = {str(c["id"]): c for c in doc["controls"]}
    out: dict[str, Any] = {}
    for prop in criteria.order:
        mapped = sorted(c for c, p in CONTROL_PROPERTY.items() if p == prop)
        entries: list[dict[str, Any]] = []
        for cid in mapped:
            if criteria.release is None:
                entries.append({"control": cid, "run_id": None, "outcome": "no_run_read"})
            for rid, found in controls.items():
                rec = found.get(cid)
                entries.append({"control": cid, "run_id": rid,
                                "outcome": "not_run" if rec is None else rec["outcome"],
                                "expected": None if rec is None else rec["expected"],
                                "passed": None if rec is None else rec["passed"],
                                "note": None if rec is None else rec.get("note"),
                                "record": None if rec is None else where[rid]})  # fmt: skip
        contradicted = [{"control": str(x["control"]), "run_id": str(x["run_id"]),
                         "record": where.get(str(x["run_id"]))}
                        for x in row["cells"][prop]["contradicted_by"]]  # fmt: skip
        out[prop] = {"mapped": mapped, "outcomes": entries, "contradicted": contradicted}
    runs = [{"run_id": rid, "record": f"{d}/run.json", "controls": where.get(rid)}
            for rid, d in dirs.items()]  # fmt: skip
    return {"properties": out, "runs": runs}


def _system_controls(
    root: Path, config: dict[str, Any], records: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """RFC-0008 §System-specific controls the system registers (`controls.yaml`), each with
    its outcome in every completed kept run that recorded it, as stored."""
    path = root / "systems" / config["system"] / "controls.yaml"
    registered = inputs.read_yaml(path).get("controls") or [] if path.is_file() else []
    out = []
    for control in registered:
        outcomes = []
        for rid in config["runs"]:
            found = records[rid]["controls"] or {"controls": []}
            rec = next((c for c in found["controls"] if c["id"] == control["id"]), None)
            if rec is not None:
                outcomes.append({"run_id": rid, "outcome": rec["outcome"],
                                 "expected": rec["expected"], "passed": rec["passed"]})  # fmt: skip
        if outcomes:
            out.append({"id": control["id"], "kind": control["kind"],
                        "source": control.get("source"),
                        "flags": list(control.get("control_flags") or []),
                        "outcomes": outcomes})  # fmt: skip
    return out


def _verifier(
    reference: dict[str, Any], config: dict[str, Any], records: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """The verifier profile the configuration's kept runs recorded (`manifest.json`
    `profile.verifier`, RFC-0006): the CPU count the `verify` scope ran on. Kept runs that
    name different verifier profiles stop the build: one CPU count could not label them."""
    named = {inputs.maybe(records[r]["manifest"], "profile", "verifier") for r in config["runs"]}
    if len(named) > 1:
        raise _config(f"{config['system']} on {config['workload']['id']}: kept runs name "
                      f"verifier profiles {sorted(map(str, named))}")  # fmt: skip
    name = next(iter(named), None)
    cpu = inputs.maybe(reference, "profiles", name, "cpu", "logical_cpus") if name else None
    return {"profile": name, "logical_cpus": cpu}


def _controls_of(index: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """The configuration's `index.controls[]` entry, by system, workload and profile (the entry
    names no configuration, RFC-0009 §Release record); exactly one must match."""
    key = (config["system"], config["workload"], config["profile"])
    found = [c for c in index["controls"] if (c["system"], c["workload"], c["profile"]) == key]
    if len(found) > 1 and len(index["controls"]) == len(index["configurations"]):
        # two load points of one serving configuration share the key; the release writes
        # controls[] in configuration order, so take the entry at the configuration's position
        at = next(i for i, c in enumerate(index["configurations"]) if c is config)
        found = [index["controls"][at]]
    if len(found) != 1:
        raise _config(f"{len(found)} controls entries for {config['system']} on "
                      f"{config['workload']['id']} ({config['profile']}); the index names no "
                      "configuration in `controls[]`")  # fmt: skip
    entry: dict[str, Any] = found[0]
    return entry


def _not_read(system: dict[str, Any]) -> set[str]:
    """RFC-0008 §Parts the verifier reads: the parts the system declares its verify step does
    not read (`proofs.verify_reads.not_read`)."""
    return {
        str(x["part"]) for x in inputs.maybe(system, "proofs", "verify_reads", "not_read") or []
    }


def _parts_not_read(rec: dict[str, Any] | None, not_read: set[str]) -> list[str] | None:
    """The parts an accepted control record tampered with, when every accepted trial of it
    mutated a part the system declares verify does not read; None otherwise. RFC-0008's
    amendment of 2026-11-09: such a trial tests nothing (a gap in the control design, not a
    finding against the system)."""
    trials = [t for t in (rec or {}).get("trials") or [] if t.get("outcome") == "accepted"]
    parts = {str((t.get("mutation") or {}).get("part")) for t in trials}
    return sorted(parts) if trials and parts <= not_read else None


def _accepted(
    config: dict[str, Any], records: dict[str, dict[str, Any]], not_read: set[str]
) -> list[dict[str, Any]]:
    """Every `accepted` control record of the kept runs, as stored, so the tally can say which
    control each accepted outcome is and against which expected set (RFC-0008 §Reporting)."""
    out = []
    for rid in config["runs"]:
        for rec in (records[rid]["controls"] or {"controls": []})["controls"]:
            if rec["outcome"] == "accepted":
                out.append({"control": rec["id"], "run_id": rid, "source": rec["source"],
                            "expected": rec["expected"], "passed": rec["passed"],
                            "not_read": _parts_not_read(rec, not_read)})  # fmt: skip
    return out


def _unexpected(
    entry: dict[str, Any],
    records: dict[str, dict[str, Any]],
    not_read: set[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """RFC-0008 §Reporting: every outcome outside its control's expected set
    (`index.controls[].outside_expected`), with the control's stored record in full and the path
    of the `controls.json` that holds it; an accepted record on parts verify does not read names
    them, and the same control's outcome in the configuration's other kept runs."""
    out = []
    for x in entry["outside_expected"]:
        rid = str(x["run_id"])
        found = (records[rid]["controls"] or {"controls": []}) if rid in records else None
        rec = next((c for c in (found or {"controls": []})["controls"]
                    if c["id"] == x["control_id"]), None)  # fmt: skip
        parts = _parts_not_read(rec, not_read) if x["outcome"] == "accepted" else None
        others = []
        for other in config["runs"] if parts else []:
            held = records[other]["controls"] if other != rid else None
            same = next((c for c in (held or {"controls": []})["controls"]
                         if c["id"] == x["control_id"]), None)  # fmt: skip
            if same is not None:
                others.append({"run_id": other, "outcome": same["outcome"],
                               "record": _record(records, other, "controls.json"),
                               "parts_not_read": [str(p["part"]) for p in
                                                  same.get("parts_not_read") or []]})  # fmt: skip
        out.append({"control": x["control_id"], "run_id": rid, "outcome": x["outcome"],
                    "record": _record(records, rid, "controls.json"), "stored": rec,
                    "not_read": parts, "others": others})  # fmt: skip
    return out


def _card(root: Path, index: dict[str, Any], system: str, configuration: str | None) -> Any:
    """S1 item 2: the card the index names for the configuration, its digest and body."""
    found = [c for c in index["claim_cards"]
             if c["system"] == system and c["configuration"] == configuration]  # fmt: skip
    if not found:
        return None
    card = dict(found[0])
    body = inputs.read_yaml(root / card["path"])
    card |= {
        "body": body,
        "upstream": body.get("upstream"),
        "link": f"{REPOSITORY}/blob/{LINK_REF}/{card['path']}",
    }  # fmt: skip
    return card


def _configuration(
    root: Path,
    index: dict[str, Any],
    position: int,
    systems: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    facts: SiteFacts,
) -> dict[str, Any]:
    config = index["configurations"][position]
    system = systems[config["system"]]
    wl = inputs.read_yaml(root / f"workloads/{config['workload']['id']}.yaml")
    reference = inputs.read_yaml(root / str(index["reference"]["file"]))
    gpu = inputs.maybe(reference, "profiles", config["profile"], "gpu") or {}
    stats = config["statistics"]
    index_path = f"releases/{index['release']}/index.json"
    digest = wl["model"]["digest"]
    model = facts.models.get(digest)
    controls = _controls_of(index, config)
    not_read = _not_read(system)
    accepted = _accepted(config, records, not_read)
    if len(accepted) != controls["counts"]["accepted"]:  # the index and its runs disagree
        raise _config(f"{config['system']} on {wl['id']}: the index counts "
                      f"{controls['counts']['accepted']} accepted controls, its runs record "
                      f"{len(accepted)}")  # fmt: skip
    return {
        "position": position,
        "system": config["system"],
        "configuration": config["configuration"],
        "kind": system["kind"],
        "reference_role": system.get("reference_role"),
        "workload": {
            "id": wl["id"], "version": wl["version"], "division": wl["division"],
            "phase": wl["phase"], "shape": wl["shape"], "precision": wl["precision"],
            "model": {"digest": digest, "name": None if model is None else model.name,
                      "parameters": wl["model"]["parameters"]},
            "record": f"workloads/{wl['id']}.yaml",
        },
        "profile": config["profile"],
        "gpu": {"model": gpu.get("model"), "count": gpu.get("count"),
                "short": facts.gpus.get(str(gpu.get("model")))},
        "card": _card(root, index, config["system"], config["configuration"]),
        "figures": {m: figure(index_path, position, stats, m, records)
                    for m in (*FIGURES, *PER_BIT, *PER_BIT_SIZE, *MORE, *SERVING)},
        "per_bit_metric": per_bit_metric(stats),
        "agreement": figure(index_path, position, stats, AGREEMENT, records),
        "overhead_metric": overhead_metric(config),
        "overhead_words": overhead_words(
            config.get("overhead_conditions"), stats, overhead_metric(config),
            None if model is None else dict(model.precision_words or {})),
        "runs": _runs(config, records),
        "insufficient_repetitions": config["insufficient_repetitions"],
        "controls": controls,
        # the runs the counts are over: each kept run that recorded its controls
        "control_runs": [{"run_id": rid, "record": _record(records, rid, "controls.json")}
                         for rid in config["runs"] if records[rid]["controls"]],
        "accepted": accepted,
        "unexpected": _unexpected(controls, records, not_read, config),
        "system_controls": _system_controls(root, config, records),
        "verifier": _verifier(reference, config, records),
        "price": _price(reference, config["profile"], str(index["reference"]["file"])),
        "steady_boundary": config.get("steady_boundary"),
        "overhead_runs": _overhead_runs(index, config, records, int(wl["shape"]["batch_size"])),
        # what sets a completed run's steady scope apart, from its own records: a statistic
        # that leaves a run out says why
        "run_why": {rid: why for rid in config["runs"]
                    if records[rid]["run"]["status"] == "completed"
                    and (why := _steady_why(records[rid]))},
        "load_point": config.get("load_point"),
        "adapter_readme": f"{REPOSITORY}/blob/{LINK_REF}/systems/{config['system']}/README.md",
    }  # fmt: skip


# why a completed run of either side joins no pair of an overhead (RFC-0004 INV-DERIVE-2), read
# from its records; the pages word each id
JOIN_WHY = ("first_proof_boundary", "one_batch", "short_steady", "sizing_capture", "other_prompts")


def _join_why(
    rec: dict[str, Any], batch: int, joined: set[str], serving: bool = False
) -> str | None:
    """Why a completed run is in no pair of an overhead, from its own records: recorded with the
    first-proof boundary at a batch size above 1 (INV-SCOPE-5), a serving run of one batch (no
    steady scope to divide by), a steady scope under 60 s or a sizing capture (RFC-0015 SRV-1),
    or prompts of no joined prover run (INV-DERIVE-2 (f)); None where its records show none."""
    manifest, warnings = rec["manifest"], rec["run"].get("warnings") or []
    if batch > 1 and inputs.maybe(manifest, "workload", "steady_rule") != STEADY_RULE:
        return "first_proof_boundary"
    if serving and inputs.maybe(manifest, "workload", "batches_per_session_run") == 1:
        return "one_batch"
    if SHORT_STEADY in warnings:
        return "short_steady"
    if inputs.maybe(manifest, "workload", "sizing_capture") is True:
        return "sizing_capture"
    if manifest.get("prompts_from") is not None and manifest["prompts_from"] not in joined:
        return "other_prompts"
    return None


def _steady_why(rec: dict[str, Any]) -> str | None:
    """What its own records say of a completed run's steady scope: one batch (none), under 60 s,
    or a sizing capture (RFC-0015 SRV-1); None for none of these."""
    manifest, warnings = rec["manifest"], rec["run"].get("warnings") or []
    if inputs.maybe(manifest, "workload", "batches_per_session_run") == 1:
        return "one_batch"
    if SHORT_STEADY in warnings:
        return "short_steady"
    if inputs.maybe(manifest, "workload", "sizing_capture") is True:
        return "sizing_capture"
    return None


def _overhead_runs(
    index: dict[str, Any], config: dict[str, Any], records: dict[str, dict[str, Any]], batch: int
) -> dict[str, Any]:
    """RFC-0004 INV-DERIVE-2, per overhead statistic with a value: the runs its pairs join on each
    side, read from its source inputs, each with its `run.json`; and every other completed run
    of the two configurations it divides, with why it joins none (`_join_why`)."""
    conditions = config.get("overhead_conditions") or {}
    out: dict[str, Any] = {}
    # (statistic, the serving configuration it divides by, that side's batch size; high load: > 1);
    # the warm figure divides by the matched serving configuration's steady scope (INV-DERIVE-11)
    sides = (
        ("overhead_vs_production_prove.steady", "serving_configuration", batch),
        (WARM, "serving_configuration", batch),
        ("overhead_vs_production_high_prove.steady", "high_configuration", 2),
    )
    for metric, key, at in sides:
        q = config["statistics"].get(metric)
        pointer = conditions.get(key)
        if not isinstance(q, dict) or q.get("value") is None or not isinstance(pointer, str):
            continue
        serving = index["configurations"][int(pointer.rsplit("/", 1)[1])]
        ids = input_runs(q)  # a run's run.json, or its entry in the index's freeze_derived
        mine = [r for r in ids if r in config["runs"]]
        theirs = [r for r in ids if r in serving["runs"]]
        left = []
        for side, runs, size in (
            ("system", config["runs"], batch),
            ("serving", serving["runs"], at),
        ):
            for rid in runs:
                if rid in ids or records[rid]["run"]["status"] != "completed":
                    continue
                left.append({"run_id": rid, "side": side,
                             "record": _record(records, rid, "run.json"),
                             "why": _join_why(records[rid], size, set(mine),
                                              serving=side == "serving")})  # fmt: skip
        out[metric] = {
            "system": [{"run_id": r, "record": _record(records, r, "run.json")} for r in mine],
            "serving": [{"run_id": r, "record": _record(records, r, "run.json")} for r in theirs],
            "left": left,
        }
    return out


def _price(reference: dict[str, Any], profile: str, path: str) -> dict[str, Any] | None:
    """RFC-0006 C1, C7: the GPU-hour price that costs a row on `profile` (the profile's `cost`
    basis in `costs`, else the file's `cost`), with its date, providers and pointer."""
    basis = inputs.maybe(reference, "profiles", profile, "cost")
    doc = inputs.maybe(reference, "costs", basis) if basis else reference.get("cost")
    price = inputs.maybe(doc, "price_per_gpu_hour_usd", "value") if doc else None
    if price is None or not isinstance(doc, dict):
        return None
    pointer = f"/costs/{basis}" if basis else "/cost"
    return {"usd_per_gpu_hour": price, "date": doc.get("date"),
            "providers": len(doc.get("providers") or []), "basis": doc.get("basis"),
            "file": path, "pointer": pointer}  # fmt: skip


def _num(x: float) -> str:
    """A number as the pages print it: four significant digits, thousands separated (S4); the
    record keeps the stored value."""
    if x == 0:
        return "0"
    places = 3 - math.floor(math.log10(abs(x)))
    return f"{x:,.{places}f}" if places >= 0 else f"{round(x, places):,.0f}"


def _count(n: object, one: str, many: str | None = None) -> str:
    """A count with its noun, singular for 1 ("1 batch", "5,016 prompts"); "not recorded"."""
    if not isinstance(n, int):
        return "not recorded"
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def _range(q: dict[str, Any]) -> str:
    pairs = q.get("pairs") or {}
    over = f"{pairs.get('n_system', 0)} \u00d7 {pairs.get('n_serving', 0)} pairs"
    if pairs.get("min") is None:
        return f"over {over}"
    return f"range {_num(pairs['min'])} to {_num(pairs['max'])} over {over}"


# engine names as their projects write them
ENGINE = {"vllm": "vLLM"}


def overhead_metric(config: dict[str, Any]) -> str:
    """RFC-0004 INV-DERIVE-10, -11: the statistic a system row shows as its overhead, as the
    release index's `overhead_headline` names it (release code chooses it: D-OVERHEAD-S, or
    D-OVERHEAD-WARM for a system with no steady scope); D-OVERHEAD-S at `prove.steady` for an
    index without that block."""
    headline = config.get("overhead_headline") or {}
    return str(headline.get("metric") or OVERHEAD)


def per_bit_metric(stats: dict[str, Any]) -> str:
    """The D-SPAB-S statistic the overview shows: `prove.steady`, or `prove.session` where the
    steady figure is null (a system with no steady scope); the cell names the scope it shows."""
    steady = stats.get(PER_BIT[0])
    has_steady = isinstance(steady, dict) and steady.get("value") is not None
    return PER_BIT[0] if has_steady else PER_BIT[1]


def overhead_words(
    conditions: dict[str, Any] | None,
    stats: dict[str, Any],
    metric: str = OVERHEAD,
    precision_words: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """RFC-0004 INV-DERIVE-9: the conditions line, the precision note and the high-load context
    of a system row's headline overhead `metric` (INV-DERIVE-10, -11), every value from the
    release index's `overhead_conditions` and the stored quantities; None
    without a value (nothing to qualify). Each fact once per plate (amendment of 2026-11-09):
    the scope is the plate's scope row (a warm figure's names both sides'), the runs and range
    its pairs row, the weight width the per-Gbit basis; the precisions are the note's alone."""
    q = stats.get(metric)
    if not conditions or not isinstance(q, dict) or q.get("value") is None:
        return None
    c = conditions
    model = c.get("serving_model") or {}
    engine = c["engine"]
    name = ENGINE.get(str(engine["name"]), str(engine["name"]))
    gpus, count = c["gpus"], c["prompt_count_run"]
    batch, per = c["batch"], c["batches_per_session"]
    warm = metric == WARM
    # the scope, n and range are the plate's own rows (its scope and pairs), the precisions the
    # note's, so not repeated here
    line = "; ".join([
        f"{_count(batch['matched'], 'request')} per batch on both sides, "
        f"{_count(per['system'], 'batch', 'batches')} for the prover and "
        f"{_count(per['serving_matched'], 'batch', 'batches')} for serving",
        f"prompts: the prover's {count['system']:,}, replayed"
        + ("" if not count.get("serving_matched") or count["serving_matched"] == count["system"]
           else f" (serving: the prover's {count['system']:,} plus "
                f"{count['serving_matched'] - count['system']:,} further windows of the same "
                "seeded generator)"),
        f"{name} {engine['version']}, {engine['interface'] or 'interface not recorded'},"
        f" {engine['settings']}",
        # warm (start-up outside the scope) is the scope row's; only a cold session says more
        "greedy decoding" + ("" if warm or c.get("warm", True)
                             else ", cold: engine and prover start-up inside the session"),
        f"{c['runtime']}",
        f"{gpus['system'] if gpus['system'] is not None else 'not recorded'} \u00d7 "
        f"{c['gpu_model']} for the prover, "
        f"{gpus['serving'] if gpus['serving'] is not None else 'not recorded'} for serving",
        "GPU-seconds only: CPU and host memory are not counted; the prover's GPU comes with its "
        "host's CPUs and memory (RFC-0006 C5)",
    ])  # fmt: skip
    note = (
        f"Proving the {c['proved_precision']} model costs {_num(float(q['value']))} times "
        f"serving {model.get('publisher', 'not stated')}'s "
        f"{model.get('precision', 'not stated')} release, in GPU-seconds per token."
    )
    proved = c["proved_precision"]
    said = (precision_words or {}).get(proved)
    served = f"{model.get('publisher', 'not stated')} {model.get('precision', 'not stated')}"
    per_batch = f"{_count(batch['matched'], 'request')} per batch"
    brief = (f"{proved}{f' ({said})' if said else ''} proved vs {served} served, "
             f"{name} {engine['version']}, {per_batch}")  # fmt: skip
    short = f"{proved} vs {model.get('precision', 'not stated')}"  # a phone's compact line
    out = {"conditions": line, "precision": note, "brief": brief, "short": short}
    # INV-DERIVE-11: no high-load figure pairs the prover's session with serving's steady scope
    scope = q.get("scope") or "prove.steady"
    high = None if warm else stats.get(f"overhead_vs_production_high_{scope}")
    if isinstance(high, dict) and high.get("value") is not None:
        extra = ""
        if count.get("serving_high") and count["serving_high"] > count["system"]:
            extra = (f"; the prover's {count['system']:,} prompts plus "
                     f"{count['serving_high'] - count['system']:,} further windows of the same "
                     "seeded generator")  # fmt: skip
        # at the headline's scope (INV-DERIVE-9), which the plate names
        on = gpus.get("serving_high")
        value = f"{_num(float(high['value']))}\u00d7 ({_range(high)})"
        out["high"] = (f"serving at {_count(batch['high'], 'request')} per batch, the prover at "
                       f"{batch['matched']:,}: {value}; "
                       f"{_count(per['serving_high'], 'batch', 'batches')} for serving on "
                       f"{on if on is not None else 'not recorded'} \u00d7 {c['gpu_model']}, "
                       f"{engine.get('settings_high') or 'settings not recorded'}"
                       f"{extra}.")  # fmt: skip
    return out


def site_view(root: Path) -> dict[str, Any]:
    """The whole site's data for the newest frozen release (module docstring)."""
    registry = SchemaRegistry.from_tree(root / "schema")
    release_id = inputs.newest_release(root)
    index = inputs.read_json(root / "releases" / release_id / "index.json")
    release = inputs.read_yaml(root / "releases" / release_id / "release.yaml")
    criteria = inputs.load_criteria(root)
    facts = inputs.load_facts(root, registry)
    systems = inputs.systems(root)
    records = inputs.run_records(root, [str(r) for r in release["runs"]])
    configs = [_configuration(root, index, i, systems, records, facts)
               for i in range(len(index["configurations"]))]  # fmt: skip
    present = {c["system"] for c in configs}

    def name(sid: str) -> str:
        return facts.rows[sid].name.lower() if sid in facts.rows else sid

    benchmarked = sorted({c["system"] for c in configs if c["kind"] == "prover"}, key=name)
    roles = {"serve": 0, "recompute": 1}

    def role(sid: str) -> int:
        return roles.get(str(systems[sid].get("reference_role")), len(roles))

    reference = sorted({c["system"] for c in configs if c["kind"] == "reference"}, key=role)
    public = [r for r, row in criteria.rows.items() if row["source_class"] == "public_sources"]
    listed = sorted((r for r in public if r not in present), key=name)
    inputs.check_facts(facts, criteria, [*benchmarked, *reference, *listed],
                       sorted({c["workload"]["model"]["digest"] for c in configs}))  # fmt: skip
    check_rows(criteria, release_id, configs)
    _serving_setups(index, configs)
    # a missing overhead names its baseline (RFC-0015 SRV-6): serving ran on the GPU model, or not
    served = {c["gpu"]["model"] for c in configs
              if c["reference_role"] == "serve" and c["runs"]["completed"]}  # fmt: skip
    for c in configs:
        c["serving_on_gpu"] = c["kind"] == "prover" and c["gpu"]["model"] in served
    for c in configs:
        row = criteria.rows.get(c["system"])
        if c["kind"] == "prover" and row and row["source_class"] == "claim_card_at_pin":
            c["property_controls"] = property_controls(root, criteria, row, c["configuration"],
                                                       records)  # fmt: skip
    rfcs = sorted(p.name for p in (root / "rfcs").glob("*.md"))
    return {
        "repository": REPOSITORY,
        "link_ref": LINK_REF,
        "release": {
            "id": release_id,
            "rfc_commit": release["rfc_commit"],
            "harness_version": release["harness_version"],
            "reference_file": release["reference_file"],
            "runs": [_listed(records[rid], rid) for rid in records],
            "superseded_runs": [dict(x) for x in release.get("superseded_runs") or []],
            "claim_cards": [dict(c) for c in index["claim_cards"]],
            "reference": index["reference"],
            "index": f"releases/{release_id}/index.json",
            "licence": facts.site.licence,
        },
        "rfcs": rfcs,
        "criteria": {
            "path": criteria.path,
            "sha256": criteria.sha256,
            "release": criteria.release,
            "order": list(criteria.order),
            "states": criteria.states,
            "properties": list(criteria.properties),
            "rows": criteria.rows,
            "pins": criteria.pins,
        },
        "facts": {
            "rows": {k: _facts_row(v) for k, v in facts.rows.items()},
            "models": {
                k: {"name": v.name, "precision_words": dict(v.precision_words or {})}
                for k, v in facts.models.items()
            },
        },
        "orders": {"benchmarked": benchmarked, "reference": reference, "not_benchmarked": listed},
        "configurations": configs,
        "targets": _targets(root, index),
    }


def _serving_setups(index: dict[str, Any], configs: list[dict[str, Any]]) -> None:
    """Each production-serving configuration an overhead divides by, with what it served, as
    the prover's `overhead_conditions` record it (RFC-0004 INV-DERIVE-9): the release served,
    the engine, the GPUs and the batch at its load point."""
    for raw in index["configurations"]:
        c = raw.get("overhead_conditions")
        if not c:
            continue
        model = c.get("serving_model") or {}
        for load, key, gpus in (("matched", "serving_configuration", "serving"),
                                ("high", "high_configuration", "serving_high")):  # fmt: skip
            point = c.get(key)
            if not point:
                continue
            position = int(str(point).rsplit("/", 1)[1])
            configs[position]["serving"] = {
                "load": load, "batch": c["batch"].get(load),
                "publisher": model.get("publisher"), "precision": model.get("precision"),
                "engine": ENGINE.get(str(c["engine"]["name"]), str(c["engine"]["name"])),
                "version": c["engine"]["version"], "gpus": c["gpus"].get(gpus),
            }  # fmt: skip


def _listed(rec: dict[str, Any], rid: str) -> dict[str, Any]:
    """One run the release lists, as the release page names it: id, system, workload, status,
    failure kind and record."""
    run = rec["run"]
    return {"run_id": rid, "system": run["system"], "workload": run["workload"]["id"],
            "profile": run["profile"], "status": run["status"],
            "failure": (run["failure"] or {}).get("kind"),
            "record": f"{rec['dir']}/run.json"}  # fmt: skip


def _targets(root: Path, index: dict[str, Any]) -> list[dict[str, Any]]:
    """§Targets: each target file the index evaluated, with its author and its results, in the
    index's order of results, grouped by file."""
    out: dict[str, dict[str, Any]] = {}
    for position, result in enumerate(index["targets"]):
        path = str(result["target"])
        if path not in out:
            doc = inputs.read_yaml(root / path)
            out[path] = {"path": path, "id": doc["id"], "author": doc["author"],
                         "date": doc["date"], "metric": doc["metric"],
                         "comparator": doc["comparator"], "threshold": doc["threshold"],
                         "rationale": doc.get("rationale"), "results": []}  # fmt: skip
        out[path]["results"].append({**result, "position": position})
    return list(out.values())


def check_rows(criteria: inputs.Criteria, release_id: str, configs: list[dict[str, Any]]) -> None:
    """What the site checks of the criteria file against the rendered release (these checks
    keep a stale file from being drawn):

    - the file names no release, or the rendered one (OVR-5: a file built for another release
      reads other runs);
    - each benchmarked configuration has the card row its card names (SRC-1), and that row is
      the system's (the renderer draws one glyph per system page), so a system runs one card
      configuration;
    - no state is drawn that a stored outcome contradicts (OVR-3, OVR-4): an `accepted` control
      outside its expected set (`index.controls[].outside_expected`), mapped to a property
      (OVR-2), on a configuration whose cell for that property is `yes`
      or `partly`, needs that control and run in the cell's `contradicted_by`. A file with no
      `release` reads no run (OVR-5), so it can name none: such an outcome stops the build until
      the file names the release.
    """
    if criteria.release is not None and criteria.release != release_id:
        raise _config(f"{criteria.path} is built for release {criteria.release!r}, the site "
                      f"renders {release_id!r} (RFC-0016 OVR-5)")  # fmt: skip
    cards: dict[str, set[str]] = {}
    for c in configs:
        if c["kind"] == "prover":
            cards.setdefault(c["system"], set()).add(str(c["configuration"]))
    for system, names in sorted(cards.items()):
        if len(names) > 1:
            raise _config(f"{system} runs {len(names)} card configurations {sorted(names)}; the "
                          "renderer draws one glyph per system page (RFC-0016 SRC-1)")  # fmt: skip
        (name,) = names
        rid = criteria.cards.get((system, name))
        if rid is None:
            raise _config(f"{criteria.path} has no card row for {system}/{name} (RFC-0016 SRC-1)")
        if rid != system:
            raise _config(f"{criteria.path} row {rid!r} holds the card of {system}; the renderer "
                          "keys a card row by its system")  # fmt: skip
    for c in configs:
        row = criteria.rows.get(c["system"])
        if c["kind"] != "prover" or row is None:
            continue
        for entry in c["controls"]["outside_expected"]:
            prop = CONTROL_PROPERTY.get(str(entry["control_id"]))
            if entry["outcome"] != "accepted" or prop is None:
                continue
            cell = row["cells"][prop]
            named = {(str(x["control"]), str(x["run_id"])) for x in cell["contradicted_by"]}
            if cell["state"] in CONTRADICTABLE and (entry["control_id"],
                                                    entry["run_id"]) not in named:  # fmt: skip
                raise _config(f"{c['system']}/{prop} is drawn {cell['state']!r}, but "
                              f"{entry['control_id']} was accepted outside its expected set in "
                              f"{entry['run_id']} and the cell's `contradicted_by` does not name "
                              "it (RFC-0016 OVR-4)")  # fmt: skip


def _facts_row(row: Any) -> dict[str, Any]:
    status = row.status
    licence = row.licence
    return {
        "name": row.name,
        "technique": row.technique,
        "kind_words": row.kind_words,
        "models": list(row.models or []),
        "code": row.code,
        "licence": None if licence is None else {"name": licence.name, "url": licence.url},
        "overview_workload": row.overview_workload,
        "status": None if status is None else {
            "state": status.state, "last_push": status.last_push, "source": status.source,
            "retrieved": status.retrieved, "quote": status.quote},
    }  # fmt: skip
