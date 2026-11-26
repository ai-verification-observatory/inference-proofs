"""Every value the site prints, from the level file and the board file (RFC-0018 §Site).

`site_view(root, board=None)` returns plain JSON-able data for the `web/build.py` renderer. It
reads the newest Level 1 release's `board.json` (or the board file `board` names, for a
preview); with none, every rung of the level file is drawn as not run yet. No number is typed
or recomputed here (AGENTS.md rule 3): every figure is a `quantity/1` value as the board file
stores it, with the JSON Pointer it was read from. Pure apart from the reads in `inputs`.
"""

import math
from pathlib import Path
from typing import Any

from iproofs.release import REASONS
from iproofs.schema import SchemaRegistry
from iproofs.site import inputs, system
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
SCOPE_VALUES = ("machine_checked", "paper", "tested", "not_stated", "does_not_apply")


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
        # the board's own words on how it was taken or why it is none (CO-9: "no split: ...")
        "note": q.get("note"),
    }


def _system(sid: str, facts: Any, root: Path) -> dict[str, Any]:
    row = facts.rows.get(sid)
    # the publisher's repository, as the claim card pins it (`upstream.repo`)
    card = root / "systems" / sid / "claim.yaml"
    doc = inputs.read_yaml(card) if card.is_file() else {}
    up = doc.get("upstream")
    sources = doc.get("sources") or {}
    return {
        "id": sid,
        "name": row.name if row is not None else sid,
        "licence": None if row is None or row.licence is None else
        {"name": row.licence.name, "url": row.licence.url},
        "repo": str(up["repo"]) if isinstance(up, dict) and up.get("repo") else None,
        # the claim card's links by field (`sources`), for the Stated security line's link
        "sources": {str(k): str(v) for k, v in sources.items()},
        # SI-3 (amended 2026-11-15): a row that runs a change to the publisher's code
        "pin": None if row is None or row.pin is None else
        {"pull": row.pin.pull, "url": row.pin.url, "merged": row.pin.merged,
         "by_owner": row.pin.by_owner, "upstream_commit": row.pin.upstream_commit,
         "upstream_outcome": row.pin.upstream_outcome, "record": row.pin.record},
        # the publisher's paper at the row's pinned commit (B5 of 2026-11-16), linked from the
        # band; a link at another commit stops the build
        "paper": _paper(sid, row.paper if row is not None else None, up),
        # CO-7 (amended 2026-11-15): how a generation phase of its own generates
        "generation": None if row is None or row.generation is None else
        {"words": row.generation.words, "quote": row.generation.quote,
         "url": row.generation.url},
    }  # fmt: skip


def _paper(sid: str, url: str | None, up: object) -> str | None:
    """The publisher's paper, a file of its repository at the commit the claim card pins: a link
    at any other commit would show another version of it than the one the row runs."""
    if url is None:
        return None
    commit = up.get("commit") if isinstance(up, dict) else None
    if not commit or f"/blob/{commit}/" not in url:
        raise inputs.config(f"{sid}: the paper {url} is not at the pinned commit {commit}")
    return url


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
    build = raw.get("build")
    if build is not None and build["status"] not in ("built", "failed", "stopped"):
        raise inputs.config(f"petal {pid}: proof build status {build['status']!r}")
    return {
        "build": build,
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
        # MC-7 and the scope card's bounds (amended 2026-11-15); absent from an older board
        "ceiling": raw.get("ceiling"),
        "scope_bounds": {r: None if not (raw.get("scope_bounds") or {}).get(r) else
                         {"text": raw["scope_bounds"][r]["text"],
                          "quotes": _quotes(raw["scope_bounds"][r]["quotes"])}
                         for r in SCOPE_ROWS},
        "conclusion": raw.get("conclusion"),
        "limits": [{"plain": str(i["plain"]), "quotes": _quotes(i["quotes"])}
                   for i in raw.get("limits") or []],  # amended 2026-11-17
        # each fact's own quotes, printed with it (amended 2026-11-17); absent from an older board
        "said": {k: {"quotes": _quotes(v.get("quotes")),
                     **({"plain": str(v["plain"])} if v.get("plain") else {})}
                 for k, v in (raw.get("said") or {}).items()},
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
                    "notes": [str(n) for n in p.get("notes") or []],  # GL-10: our reading
                    "quotes": _quotes(p.get("quotes")),
                    "sources": [{"path": d["path"], "url": d["url"]}
                                for d in p.get("sources_read") or []],
                    "lowered_by": list(p["lowered_by"]), "form": _form(step, state, cause),
                    "next": p.get("next"),  # GL-11 (amended 2026-11-16); absent before
                    "formal": _formal(pid, p.get("formal")),
                    "visible": None if visible is None else
                    [{"item": v["item"], "tag": v["tag"], "quotes": _quotes(v["quotes"])}
                     for v in visible],
                    "visible_at_least": p.get("visible_at_least", False) is True,
                    "forms": [{"item": f["item"], "quotes": _quotes(f["quotes"])}
                              for f in p.get("forms") or []],
                    # GL-11 (amended 2026-11-17): what the petal lacks for Met, what its step
                    # comes from, the facts its reading rests on, the Why line's inputs and the
                    # facts the page words it from; absent from an older board
                    "to_met": _to_met(p),
                    "came_from": p.get("sources"),
                    "read_facts": [dict(f) for f in p.get("read_facts") or []],
                    "why": p.get("why"),
                    "facts": next((p[k] for k in ("bound", "hiding", "fidelity", "trust")
                                   if k in p), None)})  # fmt: skip
    return out


def _to_met(p: dict[str, Any]) -> list[dict[str, Any]]:
    """GL-11: the petal's items for Met; on a board from before 2026-11-17, its next step's
    needs as one group in their own words."""
    if "to_met" in p:
        return list(p["to_met"])
    nx = p.get("next")
    if not nx:
        return []
    kind = "up" if nx["to"] is not None else ("decide" if p["step"] is None else "repair")
    items = [{"need": "text", "text": n["text"], "by": n["by"]} for n in nx["needs"]]
    return [{"to": nx["to"], "kind": kind, "items": items}]


def _checks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for cid in CHECKS:
        c = raw[cid]
        if c["state"] not in STATES:
            raise inputs.config(f"check {cid}: unknown state {c['state']!r}")
        out.append({"id": cid, "state": c["state"], "cause": c["cause"],
                    "note": c.get("note"), "evidence": list(c["evidence"]),
                    "trials": [dict(t) for t in c.get("trials", [])]})  # fmt: skip
    return out


ROW_FIGURES = ("multiple", "session_multiple", "steady_gpu_seconds_per_reply",
               # CO-7 (amended 2026-11-15): the session cost per reply in its timed calls
               "session_commit_gpu_seconds_per_reply", "session_proving_gpu_seconds_per_reply",
               "generation_gpu_seconds_per_reply_token",
               "steady_generation_gpu_seconds_per_reply", "steady_proving_gpu_seconds_per_reply",
               "generation_multiple", "proving_multiple",
               # CO-7 (amended 2026-11-13): the session cost per reply in two parts
               "session_generation_gpu_seconds_per_reply",
               "session_commit_and_proving_gpu_seconds_per_reply",
               "session_generation_multiple", "session_commit_and_proving_multiple",
               "session_gpu_seconds_per_reply", "steady_usd_per_reply", "session_usd_per_reply",
               "verify_seconds_per_reply", "proof_bytes_per_reply",
               # CO-8 (adopted 2026-11-16): printed once, under Cost
               "session_reply_tokens_per_gpu_second",
               # CO-9 (adopted 2026-11-26, Q55): the cost of a further reply, its two parts and
               # multiples, its proved rate, the one-time work and its mark, the prove step's
               # diagnostics; on a board built by the further-reply rule only
               "further_reply_gpu_seconds", "further_reply_generation_gpu_seconds",
               "further_reply_proving_gpu_seconds", "further_reply_multiple",
               "further_reply_proving_multiple", "further_reply_tokens_per_gpu_second",
               "further_reply_usd_per_reply", "one_time_gpu_seconds", "one_time_mark_replies",
               "one_time_usd", "prove_gpu_util_mean", "prove_gpu_memory_peak")  # fmt: skip


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
        # SE-3b: kept out of the release by RFC-0014, each reason code with its stable words
        "ineligible": [
            {**s, "words": [REASONS[c] for c in s["reasons"]]}
            for s in raw.get("ineligible_sessions", [])
        ],
        "fidelity": None if fid is None else {
            **{k: fid[k] for k in ("n", "mean_prefix", "p_above_bar", "p_below_bar", "kl_note")},
            "kl": figure(fid.get("kl"), f"{at}/fidelity/kl", board)},
        "security": raw.get("security"),
        "level_statement": raw.get("level_statement"),  # SI-4a
        # CO-9 (Q55): the replies one proof batch holds, where the generation part comes from
        # (with each session's adapter check) and the setups the sessions reused; None, [] on a
        # board built by the whole-session rule
        "proving_batch": raw.get("proving_batch"),
        "further_split": raw.get("further_reply_split"),
        "one_time_setups": [dict(s) for s in raw.get("one_time_setups") or []],
        # completeness, the one property tested here (MC-6, amended 2026-11-15): the replies of
        # the counted sessions, every one released with an accepted proof (Terms, Session)
        "honest_accepted": sum(sum(s.get("groups") or ()) for s in raw["sessions"]),
        # where the row's plain numbers (session values, mean prefix) are read from
        "record": f"{board}#{at}" if board else at,
    }  # fmt: skip


def _serving(f: dict[str, Any] | None) -> dict[str, Any] | None:
    """A serving baseline's figure as the site labels it. The board stores it under the timing
    scope `prove.steady` (RFC-0004 has no scope of serving); it is a rate at full load (CO-4),
    with no release groups, so the site words its scope as serving's."""
    return None if f is None else {**f, "scope": "serving"}


def _served(q: Any, pointer: str, board: str | None) -> dict[str, Any] | None:
    """The baseline's served rate as the site labels it (`_serving`), with the board's note on
    what it counts (one run, the timed replies, the GPUs): its n, printed in its title."""
    f = _serving(figure(q, pointer, board))
    return None if f is None else {**f, "note": q.get("note")}


def _baseline(raw: dict[str, Any] | None, at: str, board: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    return {
        "serving": raw["serving"],
        "run_id": raw["run_id"],
        "gpus": raw["gpus"],
        "concurrency": raw["concurrency"],
        "cause": raw["cause"],
        "gpu_seconds_per_reply": _serving(figure(raw["gpu_seconds_per_reply"],
                                                 f"{at}/gpu_seconds_per_reply", board)),
        "usd_per_reply": _serving(figure(raw["usd_per_reply"], f"{at}/usd_per_reply", board)),
        # CO-8 (amended 2026-11-16): the reply tokens per GPU-second it serves, with what it counts
        "reply_tokens_per_gpu_second": _served(raw.get("reply_tokens_per_gpu_second"),
                                               f"{at}/reply_tokens_per_gpu_second", board),
        "gpu_model": raw.get("gpu_model"),
        # CO-4: the rate at each concurrency of the ladder, the full-load rung among them
        "ladder": [{"concurrency": c["concurrency"],
                    "rate": _serving(figure(c["replies_per_gpu_second"],
                                            f"{at}/ladder/{i}/replies_per_gpu_second", board))}
                   for i, c in enumerate(raw.get("ladder") or [])],
    }  # fmt: skip


def _fidelity(raw: dict[str, Any] | None, at: str, board: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    return {
        "path": raw["path"],
        "record": f"{board}#{at}" if board else at,
        "bar": raw["bar"],
        "cause": raw["cause"],
        # FI-9, FM-5: each part of the fidelity run, its engine and slots, and the count FM-5 reads
        "runs": raw.get("runs") or [],
        "slots": raw.get("slots"),
        "slots_cause": raw.get("slots_cause"),
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
        "teacher_forced": None,
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
    # SI-9: the teacher-forced figures, printed beside fidelity; they set no state. `record`:
    # where the board holds them (a printed percentage names its value there)
    tf = raw.get("teacher_forced")
    here = f"{at}/teacher_forced"
    rung["teacher_forced"] = None if tf is None else {
        **tf, "record": f"{board}#{here}" if board else here}  # fmt: skip
    rung["rows"] = [_row(r, f"{at}/rows/{i}", board, rung) for i, r in enumerate(raw["rows"])]
    return rung


def _correct_size(rung: dict[str, Any], fix: dict[str, Any] | None) -> None:
    """An erratum to a frozen level's parameter count (`web/_data/errata.json`): the count less
    the tensors it names that are not weights (GPT-2's checkpoint stores 12 causal-mask buffers,
    which the Hub's safetensors total counts). The stored count must be the one it corrects."""
    if fix is None:
        return
    if rung["parameters_total"] != fix["level_value"]:
        raise inputs.config(f"{inputs.ERRATA}: {rung['id']} has {rung['parameters_total']:,} "
                            f"parameters, the erratum corrects {fix['level_value']:,}")  # fmt: skip
    drop = fix["not_parameters"]
    count = rung["parameters_total"] - int(drop["count"]) * math.prod(drop["shape"])
    for key in ("parameters_total", "parameters_active"):
        if rung.get(key) == fix["level_value"]:
            rung[key] = count
    rung["parameters_erratum"] = {"level_value": fix["level_value"], "why": fix["why"],
                                  "card": fix["card"]}  # fmt: skip


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
    """SI-4: every system of the facts file with a reason and no row on the board, A to Z, each
    with the source of its reason (SI-4b)."""
    out = []
    for sid, row in facts.rows.items():
        if row.reason is None or sid in ran:
            continue
        if row.reason not in inputs.REASONS:
            raise inputs.config(f"{inputs.FACTS} {sid}: unknown reason {row.reason!r}")
        src = row.reason_source
        if src is None and row.reason != "not yet run":  # SI-4b: the one reason with no source
            raise inputs.config(f"{inputs.FACTS} {sid}: a reason with no reason_source (SI-4b)")
        source = None if src is None else {"words": src.words, "url": src.url}
        out.append({"id": sid, "name": row.name, "reason": row.reason, "source": source})
    return sorted(out, key=lambda r: str(r["name"]).lower())


def credit(facts: Any) -> dict[str, Any]:
    """Who builds the site and its members, in the facts file's order (a member is listed once
    its entry is there)."""
    c = facts.credit
    return {
        "builder": {"name": c.builder.name, "url": c.builder.url},
        "lead": {"name": c.lead.name, "url": c.lead.url},
        "members": [{"name": m.name, "url": m.url, "mark": m.mark} for m in c.members],
    }


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
    corrections = inputs.errata(root).get("parameters") or {}
    for lr in level["rungs"]:
        i, found = raw.get(lr["id"], (None, None))
        rungs.append(_rung(lr, found, f"/rungs/{i}", shown))
        rungs[-1]["original"] = inputs.original(root, lr)  # FI-1: where the reference came from
        _correct_size(rungs[-1], corrections.get(lr["id"]))
    _pages(rungs)
    ran = {row["system"] for r in rungs for row in r["rows"]}
    systems = {sid: _system(sid, facts, root) for sid in sorted(ran)}
    frontier = None
    if doc is not None and doc["frontier"] is not None:
        f = doc["frontier"]
        rung = next(r for r in rungs if r["id"] == f["rung"])
        frontier = {"rung": rung["id"], "model": rung["model"], "systems_run": f["systems_run"],
                    "rows": [next(row for row in rung["rows"] if row["system"] == s)
                             for s in f["rows"]]}  # fmt: skip
    request = (doc or {}).get("request") or level["request"]
    # SI-3 (amended 2026-11-15): what each row's page prints from the records beside the board
    models = {k: {"precision_words": dict(v.precision_words or {})}
              for k, v in facts.models.items()}  # fmt: skip
    release_id = None if doc is None else str(doc["release"])
    for rung in rungs:
        if rung["baseline"] is not None:
            rung["baseline"]["release"] = system.serving_release(root, rung["baseline"]["serving"])
            # the GPU the serving run's manifest records, by the facts file's short name
            model = rung["baseline"]["gpu_model"]
            rung["baseline"]["gpu"] = None if model is None else dict(facts.gpus).get(model, model)
        for row in rung["rows"]:
            row["statement"] = system.statement(root, release_id, row, request)
            row["machine"] = system.machine(root, release_id, row, dict(facts.gpus))
            row["precision"] = system.precision(root, row, models)
            row["trials_kept"] = system.kept_trials(root, release_id, row)
    engine = inputs.engine(root)
    return {
        "repository": REPOSITORY,
        "link_ref": LINK_REF,
        "licence": facts.site.licence,
        "credit": credit(facts),
        "level": {
            "id": level["id"],
            "name": level["name"],
            "frozen": level.get("frozen"),
            "path": inputs.LEVEL,
            "digest": level_digest,
        },
        # RFC-0018 Q55: the cost rule the board was built by (a board without the field was
        # built by the whole-session rule, v1.0's)
        "cost_rule": (doc or {}).get("cost_rule") or "whole-session",
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
            "timed_batches": level["baseline"]["timed_batches"],
            # FI-4: where a test's p reaches its floor (2^-n exact, 1 / (1 + resamples) drawn)
            "fidelity_exact_up_to": level["fidelity"]["exact_up_to"],
            "fidelity_resamples": level["fidelity"]["resamples"],
            # FI-1, FI-2: the llama.cpp pin that makes the quantized copies, in a copy's title
            "fidelity_engine": dict(level["fidelity"].get("engine") or {}),
        },
        # what the prompts are cut from (RFC-0003), for the Fidelity section's limits
        "corpus": inputs.corpus(root),
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
