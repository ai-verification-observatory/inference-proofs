"""Every value the site prints, from the level file and the board file (RFC-0018 §Site).

`site_view(root, board=None)` returns plain JSON-able data for the `web/build.py` renderer. It
reads the newest Level 1 release's `board.json` (or the board file `board` names, for a
preview); with none, every rung of the level file is drawn as not run yet. No number is typed
or recomputed here (AGENTS.md rule 3): every figure is a `quantity/1` value as the board file
stores it, with the JSON Pointer it was read from. Pure apart from the reads in `inputs`.
"""

from pathlib import Path
from typing import Any

from iproofs.schema import SchemaRegistry
from iproofs.site import inputs
from iproofs.site.inputs import REPOSITORY

# RFC-0018 §The six checks, in the table's order (the entry gate; the glyph is the petals below)
CHECKS = ("run", "model", "prompt", "reply", "no_weight_file", "fidelity")
STATES = ("held", "failed", "undecided")
LINK_REF = "main"
# RFC-0018 §The glyph: the five petals, in the glyph's order (top to bottom)
PETALS = ("unforgeable", "weights_hidden", "faithful_model", "machine_checked", "no_trusted_party")
# §The glyph, step table: a petal's decided step, a word (GL-8; None: not decided), and the ink
# each step is drawn in
STEPS = ("green", "amber_upper", "amber_lower", "red", None)
STEP_STATE = {"green": "green", "amber_upper": "amber", "amber_lower": "amber", "red": "red",
              None: "hollow"}  # fmt: skip
RED_CAUSES = ("not_stated", "stated", "check_failed")
HOLLOW_CAUSES = ("not_read", "not_decided", "proof_build_not_run")
BASES = ("statement", "test")
# Machine-checked's scope card (MC-1 to MC-6): printed as recorded facts, it sets no state
SCOPE_ROWS = ("soundness", "zero_knowledge", "completeness")
SCOPE_COLS = ("protocol", "verifier_run", "prover_run")
SCOPE_VALUES = ("machine_checked", "paper", "tested", "not_stated")


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def figure(q: Any, pointer: str, board: str | None) -> dict[str, Any] | None:
    """A stored quantity as the pages print it, labels unchanged, with where it was read; None
    where the board holds none."""
    if not isinstance(q, dict):
        return None
    stats = q.get("stats") or None
    return {
        "value": q["value"],
        "unit": q["unit"],
        "scope": q["scope"],
        "grade": q["grade"],
        "tier": q["tier"],
        "null_reason": q["null_reason"],
        "n": stats["n"] if stats else None,
        "stats": stats,
        "formula": q["source"]["ref"],
        "source": f"{board}#{pointer}" if board else pointer,
    }


def _system(sid: str, facts: Any) -> dict[str, Any]:
    row = facts.rows.get(sid)
    return {
        "id": sid,
        "name": row.name if row is not None else sid,
        "licence": None if row is None or row.licence is None else
        {"name": row.licence.name, "url": row.licence.url},
    }  # fmt: skip


def _quotes(raw: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    return [{"text": q["text"], "url": q["url"]} for q in raw or []]


def _form(step: str | None, state: str, cause: str | None) -> str:
    """How an arm is drawn beside its ink: `cut` for amber in lesser part, `open` for a red the
    publisher's silence set (§The glyph, Q7); "" otherwise."""
    if step == "amber_lower":
        return "cut"
    if state == "red" and cause == "not_stated":
        return "open"
    return ""


def _formal(pid: str, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    card = raw["scope_card"]
    for r in SCOPE_ROWS:
        for c in SCOPE_COLS:
            if card[r][c]["value"] not in SCOPE_VALUES:
                raise inputs.config(f"petal {pid}: scope card {r}/{c} {card[r][c]['value']!r}")
    return {
        "stated_step": raw["stated_step"],
        "reach": raw["reach"],
        "tool": raw["tool"],
        "theorem": raw["theorem"],
        "theorem_url": raw["theorem_url"],
        "trusted_base": list(raw["trusted_base"]),
        "input_code_unverified": raw["input_code_unverified"],
        "scope_card": {r: {c: {"value": card[r][c]["value"],
                               "quotes": _quotes(card[r][c]["quotes"])}
                           for c in SCOPE_COLS} for r in SCOPE_ROWS},
    }  # fmt: skip


def _glyph(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """GL-5: the five petals as the board stores them, in RFC-0018's order, each with its step,
    its cause and the form its arm is drawn in. No count, total or order over petals (GL-8)."""
    if [p["id"] for p in raw] != list(PETALS):
        raise inputs.config(f"glyph petals {[p['id'] for p in raw]}, the site draws {PETALS}")
    out = []
    for p in raw:
        pid, step, state, cause = p["id"], p["step"], p["state"], p["cause"]
        if step not in STEPS or state != STEP_STATE[step]:
            raise inputs.config(f"petal {pid}: step {step!r}, state {state!r}")
        allowed = {"red": RED_CAUSES, "hollow": HOLLOW_CAUSES}.get(state, (None,))
        if cause not in allowed:
            raise inputs.config(f"petal {pid}: {state} with cause {cause!r}")
        if p["basis"] not in BASES:
            raise inputs.config(f"petal {pid}: basis {p['basis']!r}")
        # a fact the decision read carries a note: the reader's reading, not the publisher's words
        reading = p.get("reading", False)
        if not isinstance(reading, bool):
            raise inputs.config(f"petal {pid}: reading {reading!r}")
        visible = p.get("visible")
        out.append({"id": pid, "state": state, "step": step, "cause": cause,
                    "basis": p["basis"], "reading": reading, "reason": p["reason"],
                    "quotes": _quotes(p.get("quotes")),
                    "lowered_by": list(p["lowered_by"]), "form": _form(step, state, cause),
                    "formal": _formal(pid, p.get("formal")),
                    "visible": None if visible is None else
                    [{"item": v["item"], "tag": v["tag"], "quotes": _quotes(v["quotes"])}
                     for v in visible]})  # fmt: skip
    return out


def _checks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for cid in CHECKS:
        c = raw[cid]
        if c["state"] not in STATES:
            raise inputs.config(f"check {cid}: unknown state {c['state']!r}")
        out.append({"id": cid, "state": c["state"], "cause": c["cause"],
                    "note": c.get("note"), "evidence": list(c["evidence"])})  # fmt: skip
    return out


ROW_FIGURES = ("multiple", "session_multiple", "steady_gpu_seconds_per_reply",
               "steady_generation_gpu_seconds_per_reply", "steady_proving_gpu_seconds_per_reply",
               "generation_multiple", "proving_multiple",
               "session_gpu_seconds_per_reply", "steady_usd_per_reply", "session_usd_per_reply",
               "verify_seconds_per_reply", "proof_bytes_per_reply")  # fmt: skip


def _row(raw: dict[str, Any], at: str, board: str | None, rung: dict[str, Any]) -> dict[str, Any]:
    fid = raw.get("fidelity")
    return {
        "system": raw["system"],
        "rung": rung["id"],
        "workload": raw["workload"],
        "configuration": raw["configuration"],
        "commit": raw["commit"],
        "checks": _checks(raw["checks"]),
        "glyph": _glyph(raw["glyph"]),
        "passed": raw["passed"],
        "ranked": raw["ranked"],
        "position": raw["position"],
        "unranked_reason": raw["unranked_reason"],
        "figures": {k: figure(raw.get(k), f"{at}/{k}", board) for k in ROW_FIGURES},
        "sessions": [dict(s) for s in raw["sessions"]],
        "incomplete": [dict(s) for s in raw["incomplete_sessions"]],
        "replaced": [dict(s) for s in raw.get("replaced_sessions", [])],
        "fidelity": None if fid is None else {
            **{k: fid[k] for k in ("n", "mean_prefix", "p_above_bar", "p_below_bar", "kl_note")},
            "kl": figure(fid.get("kl"), f"{at}/fidelity/kl", board)},
        "security": raw.get("security"),
        # where the row's plain numbers (session values, mean prefix) are read from
        "record": f"{board}#{at}" if board else at,
    }  # fmt: skip


def _baseline(raw: dict[str, Any] | None, at: str, board: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    return {
        "serving": raw["serving"],
        "run_id": raw["run_id"],
        "gpus": raw["gpus"],
        "concurrency": raw["concurrency"],
        "cause": raw["cause"],
        "gpu_seconds_per_reply": figure(raw["gpu_seconds_per_reply"],
                                        f"{at}/gpu_seconds_per_reply", board),
        "usd_per_reply": figure(raw["usd_per_reply"], f"{at}/usd_per_reply", board),
    }  # fmt: skip


def _fidelity(raw: dict[str, Any] | None, at: str, board: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    return {
        "path": raw["path"],
        "record": f"{board}#{at}" if board else at,
        "bar": raw["bar"],
        "cause": raw["cause"],
        "controls": [{"id": c["id"], "kind": c["kind"], "status": c["status"],
                      "mean_prefix": c["mean_prefix"],
                      "kl": figure(c.get("kl"), f"{at}/controls/{i}/kl", board)}
                     for i, c in enumerate(raw["controls"])],
    }  # fmt: skip


def _rung(
    level_rung: dict[str, Any], raw: dict[str, Any] | None, at: str, board: str | None
) -> dict[str, Any]:
    """One rung: its head from the level file, its baseline, fidelity and rows from the board
    (none while it has not been run)."""
    rung = {
        "id": level_rung["id"],
        "model": level_rung["model"],
        "publisher": level_rung["publisher"],
        "parameters_total": level_rung["parameters_total"],
        "parameters_active": level_rung.get("parameters_active"),
        "requests_per_session": level_rung["requests_per_session"],
        # FI-1: the precision of the rung's fidelity reference (the KL column's head)
        "reference_dtype": level_rung["reference"]["dtype"],
        "systems_run": 0,
        "baseline": None,
        "fidelity": None,
        "rows": [],
    }
    if raw is None:
        return rung
    for key in (
        "model",
        "publisher",
        "parameters_total",
        "parameters_active",
        "requests_per_session",
    ):
        rung[key] = raw[key]
    rung["systems_run"] = raw["systems_run"]
    rung["baseline"] = _baseline(raw["baseline"], f"{at}/baseline", board)
    rung["fidelity"] = _fidelity(raw["fidelity"], f"{at}/fidelity", board)
    rung["rows"] = [_row(r, f"{at}/rows/{i}", board, rung) for i, r in enumerate(raw["rows"])]
    return rung


def _pages(rungs: list[dict[str, Any]]) -> None:
    """Each row's page: `/<system>`, or `/<system>-<rung>` for a system on more than one rung."""
    count: dict[str, int] = {}
    for rung in rungs:
        for row in rung["rows"]:
            count[row["system"]] = count.get(row["system"], 0) + 1
    for rung in rungs:
        for row in rung["rows"]:
            sid = row["system"]
            row["page"] = sid if count[sid] == 1 else f"{sid}-{rung['id']}"


def not_run(facts: Any, ran: set[str]) -> list[dict[str, Any]]:
    """SI-4: every system of the facts file with a reason and no row on the board, A to Z."""
    out = []
    for sid, row in facts.rows.items():
        if row.reason is None or sid in ran:
            continue
        if row.reason not in inputs.REASONS:
            raise inputs.config(f"{inputs.FACTS} {sid}: unknown reason {row.reason!r}")
        out.append({"id": sid, "name": row.name, "reason": row.reason})
    return sorted(out, key=lambda r: str(r["name"]).lower())


def site_view(root: Path, board: Path | None = None) -> dict[str, Any]:
    """The whole site's data (module docstring). `board`: a board file to render in place of the
    newest release's (a preview)."""
    registry = SchemaRegistry.from_tree(root / "schema")
    facts = inputs.load_facts(root, registry)
    level, level_digest = inputs.level(root)
    path = board if board is not None else inputs.newest_board(root)
    doc = inputs.board(path, registry) if path is not None else None
    # the board's own pointer prefix: a path in the tree, or the file's name for a preview
    shown = None
    if path is not None:
        try:
            shown = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            shown = path.name
    raw = {r["id"]: (i, r) for i, r in enumerate((doc or {}).get("rungs") or [])}
    if unknown := set(raw) - {r["id"] for r in level["rungs"]}:
        raise inputs.config(f"{shown}: rungs {sorted(unknown)} are not in {inputs.LEVEL}")
    rungs = []
    for lr in level["rungs"]:
        i, found = raw.get(lr["id"], (None, None))
        rungs.append(_rung(lr, found, f"/rungs/{i}", shown))
    _pages(rungs)
    ran = {row["system"] for r in rungs for row in r["rows"]}
    systems = {sid: _system(sid, facts) for sid in sorted(ran)}
    frontier = None
    if doc is not None and doc["frontier"] is not None:
        f = doc["frontier"]
        rung = next(r for r in rungs if r["id"] == f["rung"])
        frontier = {"rung": rung["id"], "model": rung["model"], "systems_run": f["systems_run"],
                    "rows": [next(row for row in rung["rows"] if row["system"] == s)
                             for s in f["rows"]]}  # fmt: skip
    request = (doc or {}).get("request") or level["request"]
    engine = inputs.engine(root)
    return {
        "repository": REPOSITORY,
        "link_ref": LINK_REF,
        "licence": facts.site.licence,
        "level": {
            "id": level["id"],
            "name": level["name"],
            "frozen": level.get("frozen"),
            "path": inputs.LEVEL,
            "digest": level_digest,
        },
        "release": None
        if doc is None
        else {
            "id": doc["release"],
            "date": doc["date"],
            "board": shown,
            "level_digest": doc["level_digest"],
        },
        "price": None
        if doc is None
        else {
            "basis": doc["price"]["basis"],
            "date": doc["price"]["date"],
            "usd_per_gpu_hour": figure(
                doc["price"]["usd_per_gpu_hour"], "/price/usd_per_gpu_hour", shown
            ),
        },
        "request": {
            "prompt_tokens": request["prompt_tokens"],
            "output_tokens": request["output_tokens"],
            "decoding": request["decoding"],
        },
        "engine": None
        if engine is None
        else {"name": engine.get("name"), "version": engine.get("version")},
        "checks": list(CHECKS),
        "petals": list(PETALS),
        "order_margin": level["order"]["margin"],
        # the level's constants the checks page words its rules with
        "constants": {
            "slots": level["sessions"]["slots"],
            "attempts_per_slot": level["sessions"]["attempts_per_slot"],
            "group_gap_s": level["steady"]["group_gap_s"],
            "plateau": level["baseline"]["plateau"],
            "ladder_top": max(level["baseline"]["ladder"]),
        },
        "frontier": frontier,
        "rungs": rungs,
        "systems": systems,
        "not_run": not_run(facts, ran),
        # the systems the level file names on a rung, run or not (their addresses redirect home
        # while they have no page)
        "planned": sorted({sid for r in level["rungs"] for sid in r.get("workloads") or {}}),
        # the Learn pages' words (web/learn/), None in a tree with none
        "learn": inputs.learn(root),
    }
