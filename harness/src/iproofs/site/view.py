"""Every value the site prints, computed from the frozen release (RFC-0009 §Site, #320).

`site_view(root)` returns plain JSON-able data for the `web/build.py` renderer: no number is
typed or recomputed here (AGENTS.md rule 3). A figure carries its stored value, unit, scope,
grade, tier, null reason, statistics, formula id and the JSON Pointer of its record in the
release index; its sort key is the stored value in its base unit (S4). Pure apart from the
reads in `inputs`.
"""

from pathlib import Path
from typing import Any

from iproofs.controls import CONTROL_PROPERTY, runs_read
from iproofs.derive import formula_of
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import SiteFacts
from iproofs.release import REASONS, not_measurable_on_profile
from iproofs.schema import SchemaRegistry
from iproofs.site import inputs
from iproofs.site.inputs import REPOSITORY, maintainer_rows
from iproofs.site.reply import reply_html

# The figures each configuration prints: the overview columns, then More numbers (#320 §1).
FIGURES = ("tokens_covered_per_proof", "proof_bytes", "verify_seconds",
           "overhead_vs_production_prove.steady",
           "overhead_vs_production_prove.session")  # fmt: skip
OVERHEAD = "overhead_vs_production_prove.steady"  # RFC-0004 INV-DERIVE-9, the headline
MORE = ("rate_prove.session", "cost_per_1k_tokens_prove.session", "commit_seconds",
        "verify_host_memory_peak_anon", "prove_gpu_memory_peak")  # fmt: skip
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
    }


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
    # RFC-0015 NM-1, by the freeze's own rule; the index does not mark it yet (#320 PR notes)
    nm1 = not_measurable_on_profile([(records[rid]["run"]["status"] == "completed",
                                      (records[rid]["run"]["failure"] or {}).get("kind"))
                                     for rid in config["runs"]])  # fmt: skip
    return {
        "completed": completed,
        "failed": failed,
        "left_out": _left_out(config, records),
        "not_measurable": nm1,
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
    run read carries its `run.json` and, when it has one, its `controls.json`. OVR-8 withholds
    the lists. A run of the rendered release is read from `records`; only a run of an earlier
    release is read again from disk."""
    if row["pending"]:
        return {"withheld": True, "properties": {}, "runs": []}
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
    return {"withheld": False, "properties": out, "runs": runs}


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
    if len(found) != 1:
        raise _config(f"{len(found)} controls entries for {config['system']} on "
                      f"{config['workload']['id']} ({config['profile']}); the index names no "
                      "configuration in `controls[]`")  # fmt: skip
    entry: dict[str, Any] = found[0]
    return entry


def _accepted(config: dict[str, Any], records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every `accepted` control record of the kept runs, as stored, so the tally can say which
    control each accepted outcome is and against which expected set (RFC-0008 §Reporting)."""
    out = []
    for rid in config["runs"]:
        for rec in (records[rid]["controls"] or {"controls": []})["controls"]:
            if rec["outcome"] == "accepted":
                out.append({"control": rec["id"], "run_id": rid, "source": rec["source"],
                            "expected": rec["expected"], "passed": rec["passed"]})  # fmt: skip
    return out


def _unexpected(entry: dict[str, Any], records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """RFC-0008 §Reporting: every outcome outside its control's expected set
    (`index.controls[].outside_expected`), with the control's stored record in full and the path
    of the `controls.json` that holds it."""
    out = []
    for x in entry["outside_expected"]:
        rid = str(x["run_id"])
        found = (records[rid]["controls"] or {"controls": []}) if rid in records else None
        rec = next((c for c in (found or {"controls": []})["controls"]
                    if c["id"] == x["control_id"]), None)  # fmt: skip
        out.append({"control": x["control_id"], "run_id": rid, "outcome": x["outcome"],
                    "record": _record(records, rid, "controls.json"), "stored": rec})  # fmt: skip
    return out


def _card(root: Path, index: dict[str, Any], system: str, configuration: str | None) -> Any:
    """S1 item 2: the card the index names for the configuration, its digest and body."""
    found = [c for c in index["claim_cards"]
             if c["system"] == system and c["configuration"] == configuration]  # fmt: skip
    if not found:
        return None
    card = dict(found[0])
    body = inputs.read_yaml(root / card["path"])
    reviewed = body.get("reviewed_by") or []
    card |= {
        "body": body,
        "upstream": body.get("upstream"),
        "reviewed": any(r.get("card_version") == card["card_version"] for r in reviewed
                        if isinstance(r, dict)),
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
    accepted = _accepted(config, records)
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
        "figures": {m: figure(index_path, position, stats, m, records) for m in (*FIGURES, *MORE)},
        "agreement": figure(index_path, position, stats, AGREEMENT, records),
        "overhead_metric": overhead_metric(config),
        "overhead_words": overhead_words(
            config.get("overhead_conditions"), stats, wl, overhead_metric(config)
        ),
        "runs": _runs(config, records),
        "insufficient_repetitions": config["insufficient_repetitions"],
        "effective_tier": config["effective_tier"],
        "evidence": config["evidence"],
        "controls": controls,
        "accepted": accepted,
        "unexpected": _unexpected(controls, records),
        "system_controls": _system_controls(root, config, records),
        "verifier": _verifier(reference, config, records),
        "adapter_readme": f"{REPOSITORY}/blob/{LINK_REF}/systems/{config['system']}/README.md",
    }  # fmt: skip


def _num(x: float) -> str:
    """A ratio as the pages print it: three significant figures, never rounded in the record."""
    return f"{x:,.3g}" if x < 1000 else f"{x:,.0f}"


def _range(q: dict[str, Any]) -> str:
    pairs = q.get("pairs") or {}
    if pairs.get("min") is None:
        return f"over {pairs.get('n_system', 0)} \u00d7 {pairs.get('n_serving', 0)} pairs"
    return (f"range {_num(pairs['min'])} to {_num(pairs['max'])} over {pairs['n_system']} \u00d7 "
            f"{pairs['n_serving']} pairs")  # fmt: skip


def _scoped(q: dict[str, Any]) -> str:
    return f"{q['scope']} scope" if q.get("scope") else "scope not recorded"


def overhead_metric(config: dict[str, Any]) -> str:
    """RFC-0004 INV-DERIVE-10: the statistic a system row shows as its overhead, as the release
    index's `overhead_headline` names it (release code chooses it); D-OVERHEAD-S at
    `prove.steady` for an index without that block."""
    headline = config.get("overhead_headline") or {}
    return str(headline.get("metric") or OVERHEAD)


def overhead_words(
    conditions: dict[str, Any] | None,
    stats: dict[str, Any],
    wl: dict[str, Any],
    metric: str = OVERHEAD,
) -> dict[str, str] | None:
    """RFC-0004 INV-DERIVE-9: the conditions line, the precision note and the high-load context
    of a system row's headline overhead `metric` (INV-DERIVE-10), every value from the release
    index's `overhead_conditions`, the stored quantities and the workload record; None without a
    value (nothing to qualify). A session figure says that start-up is inside it, on both sides."""
    q = stats.get(metric)
    if not conditions or not isinstance(q, dict) or q.get("value") is None:
        return None
    c = conditions
    model = c.get("serving_model") or {}
    engine = c["engine"]
    bits = (wl.get("precision") or {}).get("weight_bits") or {}
    gpus, n, count = c["gpus"], c["n"], c["prompt_count_run"]
    batch, per = c["batch"], c["batches_per_session"]

    def known(value: object) -> str:
        return "not recorded" if value is None else str(value)

    session = q.get("scope") == "prove.session"
    start = ("start-up included on both sides: the prover's from the start of its prove call, "
             "production serving's from the start of its engine, each to its last token"
             if session else "start-up excluded on both sides")  # fmt: skip
    line = "; ".join([
        f"{_scoped(q)} ({start})",
        f"{batch['matched']} requests a batch on both sides, {known(per['system'])} batches for "
        f"the prover and {known(per['serving_matched'])} for serving",
        f"prompts: the prover's {count['system']}, replayed"
        + ("" if not count.get("serving_matched") or count["serving_matched"] == count["system"]
           else f" (serving: the prover's {count['system']} plus "
                f"{count['serving_matched'] - count['system']} further windows of the same "
                "seeded generator)"),
        f"{engine['name']} {engine['version']}, {engine['interface'] or 'interface not recorded'},"
        f" {engine['settings']}",
        "greedy decoding, " + ("warm" if c.get("warm", True) else "cold: engine and prover "
                               "start-up inside the session"),
        f"{c['runtime']}",
        f"serving {model.get('publisher', 'not stated')}'s {model.get('precision', 'not stated')}"
        f" release; proving {c['proved_precision']}",
        f"{known(gpus['system'])} \u00d7 {c['gpu_model']} for the prover, "
        f"{known(gpus['serving'])} for serving",
        f"n = {n['system']} prover and {n['serving_matched']} serving repetitions, {_range(q)}",
        "GPU-seconds only: CPU and host memory are not counted; the prover's GPU comes with its "
        "host's CPUs and memory (RFC-0006 C5)",
    ])  # fmt: skip
    note = (
        f"Proving the {c['proved_precision']} model ({bits.get('bits')} bits per active weight, "
        f"{bits.get('basis')}) costs {_num(float(q['value']))} times ({_range(q)}) serving "
        f"{model.get('publisher', 'not stated')}'s {model.get('precision', 'not stated')} "
        f"release, in GPU-seconds per token, "
        f"{'per proving session with start-up' if session else 'steady'}, "
        f"at {batch['matched']} requests a batch."
    )
    out = {"conditions": line, "precision": note}
    high = stats.get(f"overhead_vs_production_high_{q.get('scope') or 'prove.steady'}")
    if isinstance(high, dict) and high.get("value") is not None:
        extra = ""
        if count.get("serving_high") and count["serving_high"] > count["system"]:
            extra = (f"; at high load: the prover's {count['system']} prompts plus "
                     f"{count['serving_high'] - count['system']} further windows of the same "
                     "seeded generator")  # fmt: skip
        out["high"] = (f"At {known(batch['high'])} requests a batch: "
                       f"{_num(float(high['value']))}\u00d7 ({_range(high)}); "
                       f"{_scoped(high)}; "
                       f"{known(per['serving_high'])} batches for serving on "
                       f"{known(gpus.get('serving_high'))} \u00d7 {c['gpu_model']}, "
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
    for c in configs:
        row = criteria.rows.get(c["system"])
        if c["kind"] == "prover" and row and row["source_class"] == "claim_card_at_pin":
            c["property_controls"] = property_controls(root, criteria, row, c["configuration"],
                                                       records)  # fmt: skip
    replies = {
        str(system): reply_html((root / str(path)).read_text("utf-8"))
        for system, path in sorted((release.get("replies") or {}).items())
    }
    rfcs = sorted(p.name for p in (root / "rfcs").glob("*.md"))
    return {
        "repository": REPOSITORY,
        "link_ref": LINK_REF,
        "release": {
            "id": release_id,
            "candidate": True,  # #320 plan §1.1: no tracked file records the publication yet
            "rfc_commit": release["rfc_commit"],
            "harness_version": release["harness_version"],
            "reference_file": release["reference_file"],
            "runs": [_listed(records[rid], rid) for rid in records],
            "superseded_runs": [dict(x) for x in release.get("superseded_runs") or []],
            "claim_cards": [dict(c) for c in index["claim_cards"]],
            "review_window": release["review_window"],
            "freeze_date": release["freeze_date"],
            "sponsors": release.get("sponsors") or [],
            "reference": index["reference"],
            "index": f"releases/{release_id}/index.json",
            "licence": facts.site.licence,
            "replies": replies,
        },
        "rfcs": rfcs,
        "criteria": {
            "path": criteria.path,
            "sha256": criteria.sha256,
            "release": criteria.release,
            "rfc": inputs.rfc_status(root, "0016"),
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
        "maintainers": maintainer_rows(root / "MAINTAINERS.md"),
    }


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
    """What the site checks of the criteria file against the rendered release (CRIT-13 in the
    validator recomputes the override from the stored files; these checks keep a stale file
    from being drawn):

    - the file names no release, or the rendered one (OVR-5: a file built for another release
      reads other runs);
    - each benchmarked configuration has the card row its card names (SRC-1), and that row is
      the system's (the renderer draws one glyph per system page), so a system runs one card
      configuration;
    - no state is drawn that a stored outcome contradicts (OVR-3, OVR-4): an `accepted` control
      outside its expected set (`index.controls[].outside_expected`), mapped to a property
      (OVR-2), on a configuration whose row is drawn and whose cell for that property is `yes`
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
        if c["kind"] != "prover" or row is None or not row["drawn"]:
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
        "status": None if status is None else {
            "state": status.state, "last_push": status.last_push, "source": status.source,
            "retrieved": status.retrieved, "quote": status.quote},
    }  # fmt: skip
