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
from iproofs.model import SiteFacts
from iproofs.schema import SchemaRegistry
from iproofs.site import inputs
from iproofs.site.legacy import REPOSITORY, maintainer_rows, reply_html

# The figures each configuration prints: the overview columns, then More numbers (#320 §1).
FIGURES = ("tokens_covered_per_proof", "proof_bytes", "verify_seconds",
           "overhead_vs_serving_prove.session")  # fmt: skip
MORE = ("rate_prove.session", "cost_per_1k_tokens_prove.session", "commit_seconds",
        "verify_host_memory_peak_anon", "prove_gpu_memory_peak")  # fmt: skip
AGREEMENT = "agreement_rate"
NM1_KINDS = ("resource", "adapter")  # RFC-0015 NM-1, as `release._measurable` tests
LINK_REF = "main"  # #320 plan §1.1: no tracked file records the commit that merged index.json


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


def _left_out(config: dict[str, Any]) -> list[dict[str, Any]]:
    """S7: every listed run not counted, with its reasons and the run that replaced it."""
    out = []
    for entry in config["ineligible"]:
        reasons = [str(r) for r in entry["reasons"]]
        by = next((r.split(":", 1)[0].removeprefix("superseded by ") for r in reasons
                   if r.startswith("superseded by ")), None)  # fmt: skip
        out.append({"run_id": entry["run_id"], "reasons": reasons, "replaced_by": by})
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
    nm1 = not completed and bool(failed) and all(f["kind"] in NM1_KINDS for f in failed)
    return {
        "completed": completed,
        "failed": failed,
        "left_out": _left_out(config),
        "not_measurable": nm1,
        "records": {rid: f"{records[rid]['dir']}/run.json" for rid in config["runs"]},
    }


def property_controls(
    root: Path, criteria: inputs.Criteria, row: dict[str, Any], configuration: str
) -> dict[str, Any]:
    """OVR-7: per property, each mapped control's outcome in every run OVR-5 reads; the site
    lists, it never sets a state. With no criteria `release` no run is read (OVR-5); "not run"
    is a mapped control absent from a read run's controls.json. OVR-8 withholds the lists."""
    if row["pending"]:
        return {"withheld": True, "properties": {}}
    read = runs_read(root, criteria.release, row["id"], configuration)
    controls: dict[str, dict[str, Any]] = {}
    for run_dir in read:
        path = root / run_dir / "controls.json"
        doc = inputs.read_json(path) if path.is_file() else {"controls": []}
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
                                "passed": None if rec is None else rec["passed"]})  # fmt: skip
        out[prop] = {"mapped": mapped, "outcomes": entries}
    return {"withheld": False, "properties": out}


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
        "runs": _runs(config, records),
        "insufficient_repetitions": config["insufficient_repetitions"],
        "effective_tier": config["effective_tier"],
        "evidence": config["evidence"],
        "controls": index["controls"][position],
        "adapter_readme": f"{REPOSITORY}/blob/{LINK_REF}/systems/{config['system']}/README.md",
    }  # fmt: skip


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
    for c in configs:
        row = criteria.rows.get(c["system"])
        if c["kind"] == "prover" and row and row["source_class"] == "claim_card_at_pin":
            c["property_controls"] = property_controls(root, criteria, row, c["configuration"])
    replies = {
        str(system): str(reply_html((root / str(path)).read_text("utf-8")))
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
            "properties": list(criteria.properties),
            "rows": criteria.rows,
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
        "targets": index["targets"],
        "maintainers": maintainer_rows(root / "MAINTAINERS.md"),
    }


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
