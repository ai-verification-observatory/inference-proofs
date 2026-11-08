"""The placeholder frozen release the public site is built from until v0.1 exists (#320, #146).

`build_placeholder(root, repetitions=3, extras=False)` writes a git repository at `root` and
returns its `releases/v0.1/release.yaml`. The tree holds copies of the real `schema/`,
`reference/`, `rfcs/`, `MAINTAINERS.md`, `LICENSES/`, the tracked files of `web/` (less
`shots/`), the workload `fp-maverick-w1024-b24` and the system directories of `flashprove`, `sash`,
`ref-serve` and `ref-recompute`, so the deployed pages keep the real names, pins, claim cards
and criteria rows. Only the runs are synthetic: PLACEHOLDER records of no real run, built from
the `run/1` and `manifest/1` shapes, with every derived metric computed by
`iproofs.derive.derive_repetition` and tokens counted by `iproofs.derive.tokens_per_proof`, so
`iproofs release freeze` passes the real gates G2 to G7 on them.

One tree-local edit: SASH joins the copy of `fp-maverick-w1024-b24` (the workload's `systems`
and the copy of `systems/sash/system.yaml` `workloads`), so SASH has a placeholder row on
Llama 4 Maverick. SASH's real code runs Llama 3.1 8B only (RFC-0003); the real tree is never
changed.

Placeholder raw values (no measurement; chosen so the figures the site printed from its data
snapshot before #320, `web/_data/` at 39662bf, keep their digits where the stored metric is the
same one): three repetitions per prover configuration, the minimum, the middle and the maximum
of that file's statistics (the middle is 3 x mean - min - max). SASH's proving session is scaled
by its tokens on this shape over the 4,608 tokens of its earlier placeholder, so its rate and
cost per 1,000 tokens keep their digits. Both reference rows fail every repetition with kind
`resource` (RFC-0015 NM-1, as the site said: plain serving could not run this model on one
H100); their failure records carry no invented log line.

`extras=True` adds cases the site tests need and the deployed build must not carry (a reply
written by no system maintainer, a target, a criteria copy naming the release with a pending
disclosure and an override, an ineligible run, a withdrawn run, an unexpected control, a
second workload, SASH on the closed Llama 3.1 8B workload `l31-8b-c1024` with the model's name
in the tree's facts copy (RFC-0003 §Closed workloads; test data only, as no second system with
its class runs it yet), a review and a reproduction record). It holds no second claim card of one
system: the renderer draws one glyph per system page, so `iproofs site build` refuses a system
with two card configurations (RFC-0016 SRC-1).

Command (site.yml, until #146): `PYTHONPATH=harness/tests uv run python -m
fixtures.placeholder_release --site OUT` builds the tree in a temporary directory, freezes it
and runs `iproofs site build --out OUT` there. `--tree DIR` keeps the frozen tree instead.
"""

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fixtures.repo import commit, git
from iproofs import __version__
from iproofs.controls import controls_document
from iproofs.derive import (
    QuantityTree,
    derive_repetition,
    measured,
    scope_seconds,
    tokens_metrics,
    tokens_per_proof,
)
from iproofs.model import Shape
from iproofs.provenance import file_digest
from iproofs.quantity import Scope, Unit
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json
from iproofs.workloads import asserted_inputs, load_workload

ROOT = Path(__file__).resolve().parents[3]
RELEASE = "v0.1"
WORKLOAD = "fp-maverick-w1024-b24"
SECOND_WORKLOAD = "fp-maverick-w1024-b1"  # extras only
CLOSED_WORKLOAD = "l31-8b-c1024"  # extras only
CLOSED_MODEL = "Llama 3.1 8B"  # its display name in the tree's facts copy, extras only
PROFILE = "prover-h100"
VERIFIER = "verifier-cpu"
REFERENCE = "reference/v0.1.yaml"
RUN_DATE = "2026-11-25"
# A commit on this repository's main, so the RFC links of the pages resolve (RFC-0009 S1).
RFC_COMMIT = "39662bf6dd02b1ee8586c78f9a3b7f77b0d06ec1"
SYSTEMS = ("flashprove", "sash", "ref-serve", "ref-recompute")
SYSTEM_FILES = ("system.yaml", "claim.yaml", "controls.yaml", "external.yaml", "README.md")
COPY = ("schema", "reference", "rfcs", "MAINTAINERS.md", "LICENSES", f"workloads/{WORKLOAD}.yaml")
WEB_SKIP = ("shots", ".tools", "node_modules", "__pycache__", ".vercel", ".env*", ".DS_Store")
REVIEW_WINDOW = {"opens": "2026-12-01", "closes": "2026-12-15"}
FREEZE_DATE = "2026-12-16"
CONTROL_SEED = "0x0123456789abcdef"
PLACEHOLDER_LINE = "placeholder record: no run was made"


@dataclass(frozen=True)
class Rep:
    """One repetition's placeholder raw values, in seconds and bytes per proof."""

    setup: float
    commit: float
    session: float
    steady: float | None
    verify_per_proof: float
    single_thread: float
    proof_bytes: int


def _three(low: float, mean: float, high: float) -> tuple[float, float, float]:
    """Minimum, middle and maximum of three values with this mean, to two decimals."""
    return low, round(3 * mean - low - high, 2), high


def _reps(
    setup: tuple[float, float, float],
    commit_s: tuple[float, float, float],
    session: tuple[float, float, float],
    steady: tuple[float, float, float] | None,
    verify: tuple[float, float, float],
    single: tuple[float, float, float],
    proof_bytes: tuple[int, int, int],
) -> tuple[Rep, ...]:
    return tuple(
        Rep(setup[i], commit_s[i], session[i], None if steady is None else steady[i],
            verify[i], single[i], proof_bytes[i])
        for i in range(3)
    )  # fmt: skip


# FlashProve: the snapshot's configurations["flashprove--fp-maverick-w1024-b24--..."].
FLASHPROVE = _reps(
    _three(119.9, 120.66666666666667, 121.4),
    _three(2398.2, 2410.5333333333333, 2422.9),
    _three(1179.4, 1185.5666666666666, 1192.0),
    _three(881.6, 887.9, 894.9),
    _three(3.09, 3.12, 3.15),
    _three(21.11, 21.14, 21.17),
    # proof_bytes_total 2,252,900,000 / 2,253,600,000 / 2,254,100,000 B over 120 proofs
    (18774167, 18780000, 18784167),
)
# SASH: the snapshot's configurations["sash--sash-l31-8b-c4096--..."] (4,608 tokens).
SASH_EARLIER_TOKENS = 4608
SASH = _reps(
    _three(40.9, 41.4, 42.0),
    _three(63.8, 64.36666666666666, 65.1),
    _three(5361.7, 5414.866666666667, 5480.8),  # scaled in _sash_reps
    None,  # steady boundary not observable (system.yaml proofs.steady_boundary)
    _three(119.8, 121.26666666666667, 122.6),
    _three(799.1, 802.6333333333333, 806.3),
    (19800000000, 19800000000, 19800000000),
)
FLASHPROVE_CONTROLS = (  # (id, outcome, note), as the snapshot printed them
    ("C1", "rejected", None),
    ("C2", "rejected", None),
    ("C3", "not_applicable", "perturbed commitment not created within the release budget "
                             "(RFC-0008 Q2)"),
    ("C4", "rejected", None),
    ("C5", "rejected", None),
    ("C6", "invalid_call", None),
    ("C7", "rejected", None),
    ("C8", "rejected", None),
    ("P1", "not_applicable", "perturbed commitment not created"),
    ("P2", "not_applicable", "the workload declares one precision"),
)  # fmt: skip
SASH_CONTROLS = (
    ("C1", "rejected", None),
    ("C2", "rejected", None),
    ("C3", "rejected", None),
    ("C4", "not_applicable", "one request per job, no second distinct request"),
    ("C5", "rejected", None),
    ("C6", "invalid_call", None),
    ("C7", "not_applicable", "batch size 1"),
    ("C8", "rejected", None),
    ("P1", "prover_failed", None),
    ("P2", "not_applicable", "the workload declares one precision"),
)
EXPECTED = {
    "C1": ["rejected"], "C2": ["rejected"], "C3": ["rejected"], "C4": ["rejected"],
    "C5": ["rejected", "invalid_call"], "C6": ["rejected", "invalid_call"],
    "C7": ["rejected"], "C8": ["rejected", "invalid_call"],
    "P1": ["prover_failed", "rejected"], "P2": ["prover_failed", "rejected"],
}  # fmt: skip
VERDICT = {"rejected": "reject", "invalid_call": "invalid_call", "accepted": "accept"}
SASH_FAILURE: dict[str, object] = {
    "kind": "environment",
    "step": "upload",
    "message": "harness: run failed in phase upload, proofs kept on the runner",
    "exit_code": 1,
    "last_lines": ["harness: run failed in phase upload, proofs kept on the runner"],
}
SASH_CORRECTION = "the checker's container ran with 4 CPUs instead of 8"
REFERENCE_FAILURE: dict[str, object] = {
    "kind": "resource",
    "step": "prove",
    "message": f"{PLACEHOLDER_LINE}; RFC-0015 NM-1: the reference cannot run this model on "
    "the profile's one GPU",
    "exit_code": None,
    "last_lines": [],
}


# ---------------------------------------------------------------- tree


def _copy(root: Path, extras: bool) -> None:
    rels = [*COPY, *(f"systems/{s}/{f}" for s in SYSTEMS for f in SYSTEM_FILES)]
    if extras:
        rels += [f"workloads/{SECOND_WORKLOAD}.yaml", f"workloads/{CLOSED_WORKLOAD}.yaml"]
    for rel in rels:
        src, dst = ROOT / rel, root / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    _copy_web(root / "web")


def _copy_web(dst: Path) -> None:
    """The tracked files of web/ (`git ls-files`), as they are in the working tree, so an
    untracked or ignored file (a local `.vercel/`, an `.env` file, a stray picture) never enters
    the tree; outside a git checkout, every file less `WEB_SKIP`."""
    try:
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "web"],
                                capture_output=True, check=True).stdout  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        listed = b""
    tracked = [ROOT / p for p in listed.decode().split("\0") if p]
    if not tracked:
        shutil.copytree(ROOT / "web", dst, ignore=shutil.ignore_patterns(*WEB_SKIP))
        return
    for src in tracked:
        rel = src.relative_to(ROOT / "web")
        if rel.parts[0] in WEB_SKIP or not src.is_file():  # skipped, or deleted and not staged
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst / rel)


def _edit_yaml(path: Path, edit: Any) -> None:
    """Load, edit and rewrite one authored YAML file of the tree, keeping its header comment."""
    text = path.read_text()
    head = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    doc = yaml.safe_load(text)
    edit(doc)
    body = yaml.safe_dump(doc, sort_keys=False, width=10_000, allow_unicode=True)
    path.write_text(head + body)


def _put_sash_on_maverick(root: Path, workloads: Sequence[str]) -> None:
    """The one tree-local edit (module docstring): SASH joins the Maverick workloads."""
    for wl in workloads:
        _edit_yaml(root / f"workloads/{wl}.yaml",
                   lambda d: d["systems"].insert(1, "sash"))  # fmt: skip
    _edit_yaml(root / "systems/sash/system.yaml",
               lambda d: d.__setitem__("workloads", [*d["workloads"], *workloads]))  # fmt: skip


def _system(root: Path, name: str) -> dict[str, Any]:
    doc = yaml.safe_load((root / f"systems/{name}/system.yaml").read_text())
    assert isinstance(doc, dict)
    return doc


def _workload(root: Path, wid: str) -> dict[str, Any]:
    doc = yaml.safe_load((root / f"workloads/{wid}.yaml").read_text())
    assert isinstance(doc, dict)
    return doc


def _image(system: dict[str, Any]) -> str:
    return f"{system['image']['repository']}@{system['image']['digest']}"


def _card(root: Path, name: str) -> tuple[str, dict[str, Any]]:
    """(card path, card) of a prover: claims/<configuration>.yaml or claim.yaml."""
    multi = sorted((root / f"systems/{name}/claims").glob("*.yaml"))
    path = multi[0] if multi else root / f"systems/{name}/claim.yaml"
    doc = yaml.safe_load(path.read_text())
    return path.relative_to(root).as_posix(), doc


def _hex(*parts: object) -> str:
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()


# ---------------------------------------------------------------- runs


@dataclass
class Config:
    """One configuration of the placeholder release and where its runs go."""

    system: str
    workload: str
    configuration: str | None  # None for a reference row
    card_version: int | None
    card_digest: str | None


def run_id(system: str, workload: str, n: int) -> str:
    return f"{RUN_DATE}-{system}-{workload}-{PROFILE}-{n}"


def _shape(wl: dict[str, Any]) -> Shape:
    s = wl["shape"]
    return Shape(prompt_tokens=s["prompt_tokens"], output_tokens=s["output_tokens"],
                 batch_size=s["batch_size"], batches_per_session=s["batches_per_session"],
                 context_window=s["context_window"])  # fmt: skip


def _per_proof_statistic(
    value: float, k: int, unit: Unit, scope: Scope | None, ref: str
) -> QuantityTree:
    """A measured statistic over the k proofs of one repetition, every proof equal."""
    q = measured(value, unit, scope, ref, None)
    q["stats"] = {"n": k, "n_failed": 0, "mean": value, "stdev": 0.0 if k >= 2 else None,
                  "min": value, "max": value}  # fmt: skip
    return q


def _timeline(rep: Rep, k: int, session: float) -> tuple[dict[str, int], list[int]]:
    """Call events and k proof release times (ns) that give these seconds (RFC-0011 C-2)."""
    ns = 1_000_000_000
    t = 1_000 * ns
    events = {"setup.start": t, "setup.end": t + round(rep.setup * ns)}
    events["commit.start"] = events["setup.end"] + ns
    events["commit.end"] = events["commit.start"] + round(rep.commit * ns)
    start = events["prove.start"] = events["commit.end"] + 6 * ns
    last = start + round(session * ns)
    first = last - round(rep.steady * ns) if rep.steady is not None else start + (last - start) // k
    step = (last - first) // (k - 1) if k > 1 else 0
    releases = [first + i * step for i in range(k - 1)] + [last]
    events["prove.end"] = last + ns // 2
    return events, releases


def _inputs(root: Path, wid: str) -> dict[str, QuantityTree]:
    """run.json `inputs`: the workload's asserted inputs, as the runner copies them."""
    registry = SchemaRegistry.from_tree(root / "schema")
    return asserted_inputs(load_workload(wid, root=root, registry=registry))


def _metrics(
    root: Path, cfg: Config, rep: Rep, session: float, run_json: str, observable: bool
) -> tuple[
    dict[str, QuantityTree], list[dict[str, object]], dict[str, int], dict[str, QuantityTree]
]:
    wl = _workload(root, cfg.workload)
    shape = _shape(wl)
    k = shape.batch_size * shape.batches_per_session
    kind = _system(root, cfg.system)["proofs"]["tokens_covered"]
    per_proof = [tokens_per_proof(kind, shape, None, f"req-{i}") for i in range(k)]
    events, releases = _timeline(rep, k, session)
    m = scope_seconds(events, releases, observable=observable, run_json=run_json)
    m |= tokens_metrics(per_proof, run_json)
    pref, vref = f"{run_json}#/proofs", f"{run_json}#/verifier"
    m["requests_count"] = measured(k, Unit.COUNT, None, pref, None)
    m["proofs_count"] = measured(k, Unit.COUNT, None, pref, None)
    m["verdicts_accept_count"] = measured(k, Unit.COUNT, None, pref, None)
    m["proof_bytes"] = _per_proof_statistic(float(rep.proof_bytes), k, Unit.B, None, pref)
    m["proof_bytes_total"] = measured(float(rep.proof_bytes * k), Unit.B, None, pref, None)
    m["verify_seconds"] = _per_proof_statistic(rep.verify_per_proof, k, Unit.S, Scope.VERIFY, vref)
    walls = [rep.verify_per_proof] * k
    m["verify_seconds_total"] = measured(sum(walls), Unit.S, Scope.VERIFY, vref, None)
    m["verify_single_thread_seconds"] = _per_proof_statistic(
        rep.single_thread, 1, Unit.S, Scope.VERIFY_SINGLE_THREAD, vref
    )
    price = json.loads(json.dumps(yaml.safe_load((root / REFERENCE).read_text())["cost"]))
    inputs = _inputs(root, cfg.workload)
    harness = {"tier": "reported", "source": {"kind": "harness", "ref": ""}}
    m |= derive_repetition(
        m,
        run_json=run_json,
        harness_version=__version__,
        gpus=1,
        price=(f"{REFERENCE}#/cost/price_per_gpu_hour_usd", price["price_per_gpu_hour_usd"]),
        active_parameters=(
            f"{run_json}#/inputs/active_parameters_per_token",
            inputs["active_parameters_per_token"],
        ),
        weight_bits=(f"{run_json}#/inputs/weight_bits", inputs["weight_bits"]),
        first_proof_tokens=(
            f"{run_json}#/proofs/0/tokens_covered",
            {"value": sum(per_proof[0]), **harness},
        ),
    )
    proofs = [
        {"proof_id": f"req-{i}", "release_mono_ns": r, "tokens_covered": sum(per_proof[i]),
         "verdict": "accept"}
        for i, r in enumerate(releases)
    ]  # fmt: skip
    return m, proofs, events, inputs


def _run_doc(  # noqa: PLR0913 (one keyword per run.json field it sets)
    cfg: Config,
    rid: str,
    n: int,
    kind: str,
    *,
    metrics: dict[str, QuantityTree] | None = None,
    proofs: list[dict[str, object]] | None = None,
    events: dict[str, int] | None = None,
    failure: dict[str, object] | None = None,
    replaces: dict[str, str] | None = None,
    inputs: dict[str, QuantityTree] | None = None,
) -> dict[str, object]:
    claim = (
        None
        if cfg.configuration is None
        else {"card_version": cfg.card_version, "configuration": cfg.configuration,
              "system": cfg.system}
    )  # fmt: skip
    return {
        "schema": "run/1",
        "run_id": rid,
        "release": RELEASE,
        "system": cfg.system,
        "workload": {"id": cfg.workload, "version": 1},
        "profile": PROFILE,
        "repetition": n,
        "control": False,
        "system_kind": kind,
        "claim": claim,
        "status": "failed" if failure else "completed",
        "failure": None if failure is None else {"at": f"{RUN_DATE}T12:00:00Z", **failure},
        "replaces": replaces,
        "raw": {},
        "adapter_phases": {},
        "metrics": metrics or {},
        "events": [{"event": e, "mono_ns": t} for e, t in sorted((events or {}).items(),
                                                                key=lambda x: x[1])],
        "proofs": proofs or [],
        "warnings": [],
    } | ({"inputs": inputs} if inputs else {})  # fmt: skip


def _manifest(
    root: Path,
    cfg: Config,
    rid: str,
    adapter: str,
    proofs: Sequence[dict[str, object]],
    *,
    archive: bool,
    prompts_from: str | None = None,
    dirty: bool = False,
) -> dict[str, object]:
    template = ROOT / "schema/manifest/examples/valid/fake-success.json"
    m: dict[str, Any] = json.loads(template.read_text())
    system = _system(root, cfg.system)
    wl = _workload(root, cfg.workload)
    m["run_id"], m["release"] = rid, RELEASE
    m["claim"] = (
        None
        if cfg.configuration is None
        else {"card_version": cfg.card_version, "configuration": cfg.configuration,
              "system": cfg.system}
    )  # fmt: skip
    m["provider"] = "placeholder"
    m["runner"] = {"affiliated_systems": [], "handle": "placeholder", "organisation": "none"}
    m["harness"] |= {"version": __version__, "git_dirty": dirty, "git_commit": RFC_COMMIT}
    m["profile"] = {"prover": PROFILE, "reference_digest": file_digest(root / REFERENCE),
                    "reference_file": REFERENCE, "verifier": VERIFIER,
                    "verifier_host": "same_as_prover"}  # fmt: skip
    upstream = system.get("upstream")
    m["system"] = {
        "adapter_commit": adapter,
        "adapter_dirty": False,
        "claim_digest": cfg.card_digest,
        "image": {"digest_kind": "manifest", "ref": _image(system)},
        "image_inputs": [],
        "name": cfg.system,
        "system_manifest_digest": file_digest(root / f"systems/{cfg.system}/system.yaml"),
        "upstream": None if not upstream else {"commit": upstream["commit"],
                                               "repo": upstream["repo"]},
    }  # fmt: skip
    model = wl["model"]
    m["workload"] = {
        "corpus_digest": wl["prompts"]["corpus_digest"],
        "file_digest": file_digest(root / f"workloads/{cfg.workload}.yaml"),
        "id": cfg.workload,
        "model": {"digest": model["digest"], "revision": model["revision"],
                  "source": f"{model['source']['hub']}:{model['source']['repo']}"},
        "prompt_seed": "0x" + _hex("seed", rid)[:16],
        "prompt_set_digest": "sha256:" + _hex("prompts", rid),
        "version": 1,
    }  # fmt: skip
    m["proofs"] = [
        {"archive": f"https://archive.example.org/placeholder/{RELEASE}/{rid}.tar"
                    if archive and i == 0 else None,
         "digest": "sha256:" + _hex("proof", rid, p["proof_id"]),
         "parts": [{"bytes": 32, "digest": "sha256:" + _hex("part", rid, p["proof_id"]),
                    "name": "proof.bin"}],
         "proof_id": p["proof_id"]}
        for i, p in enumerate(proofs)
    ]  # fmt: skip
    if prompts_from is not None:
        m["prompts_from"] = prompts_from
    return m


def _control(cid: str, outcome: str, note: str | None, *, source: str = "shared",
             expected: list[str] | None = None) -> dict[str, object]:  # fmt: skip
    """One placeholder control record (RFC-0008 §Outcomes), as `control_record` shapes it."""
    want = expected or EXPECTED[cid]
    side = "prover" if cid.startswith("P") or source == "system" else "verifier"
    record: dict[str, object] = {
        "id": cid, "side": side, "source": source, "expected": want, "twin": None,
        "trials": [], "outcome": outcome, "passed": None, "note": note,
    }  # fmt: skip
    if outcome in ("not_applicable", "void", "error"):
        return record
    record["passed"] = outcome in want
    if outcome == "prover_failed":
        return record
    trials = 5 if cid == "C6" else 1
    record["twin"] = {"raw_exit_code": 0, "verdict": "accept"}
    record["trials"] = [
        {"seed_index": i, "mutation": {}, "verdict": VERDICT[outcome], "outcome": outcome,
         "raw_exit_code": 0 if outcome == "accepted" else 1, "raw_last_line": PLACEHOLDER_LINE,
         "seconds": None}
        for i in range(trials)
    ]  # fmt: skip
    return record


def _write_controls(
    run_dir: Path, rid: str, image: str, records: Sequence[dict[str, object]]
) -> None:
    doc = controls_document(rid, CONTROL_SEED, image, VERIFIER, None, list(records))
    write_json(run_dir / "controls.json", doc)


@dataclass
class Written:
    """The runs one configuration wrote: listed run directories and kept completed run ids."""

    dirs: list[str]
    completed: list[str]


def _write_run(  # noqa: PLR0913 (one keyword per case a placeholder run covers)
    root: Path,
    cfg: Config,
    n: int,
    adapter: str,
    *,
    rep: Rep | None,
    session: float = 0.0,
    observable: bool = True,
    failure: dict[str, object] | None = None,
    replaces: dict[str, str] | None = None,
    archive: bool = False,
    prompts_from: str | None = None,
    dirty: bool = False,
) -> tuple[str, Path]:
    rid = run_id(cfg.system, cfg.workload, n)
    rel = f"results/{RELEASE}/{cfg.system}/{rid}"
    run_json = f"{rel}/run.json"
    kind = str(_system(root, cfg.system)["kind"])
    if rep is None:
        doc = _run_doc(cfg, rid, n, kind, failure=failure, replaces=replaces)
        proofs: list[dict[str, object]] = []
    else:
        metrics, proofs, events, inputs = _metrics(root, cfg, rep, session, run_json, observable)
        doc = _run_doc(cfg, rid, n, kind, metrics=metrics, proofs=proofs, events=events,
                       failure=failure, replaces=replaces, inputs=inputs)  # fmt: skip
    run_dir = root / rel
    run_dir.mkdir(parents=True)
    write_json(run_dir / "run.json", doc)
    manifest = _manifest(root, cfg, rid, adapter, proofs, archive=archive,
                         prompts_from=prompts_from, dirty=dirty)  # fmt: skip
    write_json(run_dir / "manifest.json", manifest)
    return rid, run_dir


def _sash_session(root: Path, workload: str, rep: Rep) -> float:
    """SASH's earlier placeholder session, scaled by its tokens on this workload (docstring)."""
    shape = _shape(_workload(root, workload))
    k = shape.batch_size * shape.batches_per_session
    tokens = k * (shape.prompt_tokens + shape.output_tokens)
    return rep.session * tokens / SASH_EARLIER_TOKENS


def _prover_runs(
    root: Path,
    cfg: Config,
    adapter: str,
    repetitions: int,
    controls: Sequence[Any],
) -> Written:
    """A prover configuration's runs; SASH also gets a failed and a superseded run."""
    sash = cfg.system == "sash"
    reps = SASH if sash else FLASHPROVE
    out = Written([], [])
    n = 0

    def add(rep: Rep | None, **kw: Any) -> tuple[str, Path]:
        nonlocal n
        n += 1
        if rep is not None:
            session = _sash_session(root, cfg.workload, rep) if sash else rep.session
            kw |= {"session": session, "observable": not sash}
        rid, run_dir = _write_run(root, cfg, n, adapter, rep=rep, **kw)
        out.dirs.append(run_dir.relative_to(root).as_posix())
        return rid, run_dir

    superseded = None
    if sash:  # a run replaced by a correction run, and a failed run (RFC-0009 §Corrections)
        superseded, _ = add(reps[0])
        add(None, failure=SASH_FAILURE)
    for i in range(repetitions):
        last = i == repetitions - 1
        replaces = {"run_id": superseded, "reason": SASH_CORRECTION} if sash and last else None
        rid, run_dir = add(reps[i % 3], archive=i == 0, replaces=replaces)
        out.completed.append(rid)
        if i == 0:
            image = _image(_system(root, cfg.system))
            _write_controls(run_dir, rid, image, [_control(*c) for c in controls] +
                            ([_weakened(root)] if sash else []))  # fmt: skip
    return out


def _weakened(root: Path) -> dict[str, object]:
    """The first `weakened_prover` control SASH registers, accepted as it expects."""
    doc = yaml.safe_load((root / "systems/sash/controls.yaml").read_text())
    first = next(c for c in doc["controls"] if c["kind"] == "weakened_prover")
    return _control(first["id"], "accepted", None, source="system", expected=first["expected"])


def _reference_runs(root: Path, cfg: Config, adapter: str, prompts: Sequence[str]) -> Written:
    out = Written([], [])
    for n in range(1, 4):
        source = prompts[(n - 1) % len(prompts)] if prompts else None
        _, run_dir = _write_run(root, cfg, n, adapter, rep=None, failure=REFERENCE_FAILURE,
                                prompts_from=source)  # fmt: skip
        out.dirs.append(run_dir.relative_to(root).as_posix())
    return out


# ---------------------------------------------------------------- build


def build_placeholder(root: Path, *, repetitions: int = 3, extras: bool = False) -> Path:
    """Write the placeholder release tree at `root`; returns its release.yaml (docstring)."""
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    _copy(root, extras)
    _put_sash_on_maverick(root, [WORKLOAD])
    if extras:
        _extras_tree(root)
    git(root, "init", "-q", "-b", "main")
    adapter = commit(root, "placeholder tree: systems, workloads, schemas, site")
    cards = []
    configs: list[Config] = []
    for name in ("flashprove", "sash"):
        card_path, card = _card(root, name)
        digest = file_digest(root / card_path)
        cards.append(
            {
                "system": name,
                "configuration": card["configuration"],
                "card_version": card["card_version"],
                "path": card_path,
                "digest": digest,
            }
        )
        configs.append(Config(name, WORKLOAD, card["configuration"], card["card_version"],
                              digest))  # fmt: skip
    runs: list[str] = []
    prompts: list[str] = []
    for cfg, controls in zip(configs, (FLASHPROVE_CONTROLS, SASH_CONTROLS), strict=True):
        written = _prover_runs(root, cfg, adapter, repetitions, controls)
        runs += written.dirs
        prompts += written.completed[:2]
    for ref in ("ref-serve", "ref-recompute"):
        cfg = Config(ref, WORKLOAD, None, None, None)
        pairs = [prompts[0], prompts[2], prompts[1]] if ref == "ref-recompute" else []
        runs += _reference_runs(root, cfg, adapter, pairs).dirs
    release: dict[str, Any] = {
        "schema": "release/1",
        "release": RELEASE,
        "reference_file": REFERENCE,
        "rfc_commit": RFC_COMMIT,
        "harness_version": __version__,
        "runs": runs,
        "superseded_runs": [],
        "claim_cards": cards,
        "review_window": dict(REVIEW_WINDOW),
        "freeze_date": FREEZE_DATE,
        "replies": {},
        "sponsors": [],
    }
    if extras:
        _extras_runs(root, release, adapter, configs)
    path = root / "releases" / RELEASE / "release.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(_release_yaml(release))
    commit(root, "placeholder runs and release v0.1")
    return path


def _release_yaml(release: dict[str, Any]) -> str:
    """release.yaml with every date quoted (RFC-0012: no unquoted YAML date)."""
    head = "# PLACEHOLDER release built by harness/tests/fixtures/placeholder_release.py\n"
    return head + yaml.safe_dump(release, sort_keys=False, width=10_000, default_style=None)


# ---------------------------------------------------------------- extras (tests only)


REPLY = "systems/sash/replies/v0.1.md"
REPLY_TEXT = (
    "Fixture text for the site tests, written by no SASH maintainer and never deployed.\n\n"
    "<b>Markup in a reply</b> is printed as text, not run.\n"
)
TARGET = "targets/example-lab/verify-under-60s.yaml"
DISCLOSURE_URL = "https://example.org/placeholder/fixture-disclosure"


def _extras_tree(root: Path) -> None:
    """Extras committed with the systems: a reply, a target, and SASH on the closed workload
    (its system.yaml lists it; the facts copy names its model)."""
    _edit_yaml(
        root / "systems/sash/system.yaml",
        lambda d: d.__setitem__("workloads", [*d["workloads"], CLOSED_WORKLOAD]),
    )
    digest = _workload(root, CLOSED_WORKLOAD)["model"]["digest"]
    facts_path = root / "web/_data/facts.json"
    facts = json.loads(facts_path.read_text())
    facts["models"][digest] = {"name": CLOSED_MODEL}
    write_json(facts_path, facts)
    (root / REPLY).parent.mkdir(parents=True)
    (root / REPLY).write_text(REPLY_TEXT)
    target = (ROOT / "schema/target/examples/valid/verify-under-60s.yaml").read_text()
    (root / TARGET).parent.mkdir(parents=True)
    (root / TARGET).write_text(
        target.replace("targets/example-policy-lab/", "targets/example-lab/")
    )


def _extras_runs(root: Path, release: dict[str, Any], adapter: str, configs: list[Config]) -> None:
    """Extra runs and records of the tests-only build (module docstring)."""
    fp, sash = configs
    first = run_id(fp.system, fp.workload, 1)
    sash_first = run_id(sash.system, sash.workload, 3)  # the first completed SASH run
    rep, other = FLASHPROVE[0], FLASHPROVE[1]
    dirty, _ = _write_run(root, fp, 101, adapter, rep=rep, session=rep.session, dirty=True)
    withdrawn, _ = _write_run(root, fp, 102, adapter, rep=other, session=other.session)
    release["runs"] += [f"results/{RELEASE}/{fp.system}/{r}" for r in (dirty, withdrawn)]
    release["superseded_runs"].append(
        {"run_id": withdrawn, "reason": "fixture: withdrawn to test the runs left out"}
    )
    # one control outside its expected set per card row: C1 on FlashProve, C2 on SASH
    for system, rid, cid in ((fp.system, first, "C1"), (sash.system, sash_first, "C2")):
        path = root / f"results/{RELEASE}/{system}/{rid}/controls.json"
        doc = json.loads(path.read_text())
        records = [
            _control(cid, "accepted", None) if r["id"] == cid else r for r in doc["controls"]
        ]
        _write_controls(path.parent, rid, str(doc["image"]), records)
    second_wl = Config(fp.system, SECOND_WORKLOAD, fp.configuration, fp.card_version,
                       fp.card_digest)  # fmt: skip
    release["runs"] += _prover_runs(root, second_wl, adapter, 3, FLASHPROVE_CONTROLS).dirs
    closed = Config(sash.system, CLOSED_WORKLOAD, sash.configuration, sash.card_version,
                    sash.card_digest)  # fmt: skip
    release["runs"] += _prover_runs(root, closed, adapter, 3, SASH_CONTROLS).dirs
    release["replies"] = {sash.system: REPLY}
    _records(root, fp, first)
    _criteria(root, first, sash_first)


def _records(root: Path, fp: Config, first: str) -> None:
    """An approved review and a within-tolerance reproduction of FlashProve's first run."""
    run_dir = root / f"results/{RELEASE}/{fp.system}/{first}"
    review = json.loads((ROOT / "schema/review/examples/valid/approved.json").read_text())
    review |= {
        "run_id": first,
        "date": "2026-12-05",
        "reviewer": {"handle": "example-reviewer", "organisation": "Example Review Org"},
    }
    (run_dir / "reviews").mkdir()
    write_json(run_dir / "reviews/example-reviewer-2026-12-05.json", review)
    path = ROOT / "schema/reproduction/examples/valid/ineligible-same-machine.json"
    repro = json.loads(path.read_text())
    others = [run_id(fp.system, fp.workload, n) for n in (1, 2, 3)]
    again = [f"2026-12-06-{fp.system}-{fp.workload}-{PROFILE}-{n}" for n in (1, 2, 3)]
    stats = {"mean": 103.6, "n": 3, "stdev": 0.55}
    repro |= {
        "outcome": "within_tolerance",
        "original_run_ids": others,
        "reproduction_run_ids": again,
        "fresh_seed_runs": again[:1],
        "eligibility": {**repro["eligibility"], "different_machine": True},
        "comparisons": [{"bound": 0.1, "difference": 0.0, "metric": "rate_prove.session",
                         "original": stats, "reproduction": stats, "scope": "prove.session",
                         "unit": "token/s", "within": True}],
        "runner": {"affiliated_systems": [], "handle": "example-reproducer",
                   "organisation": "Example Reproduction Lab"},
    }  # fmt: skip
    (run_dir / "reproductions").mkdir()
    write_json(run_dir / f"reproductions/{again[0]}.json", repro)


def _criteria(root: Path, first: str, sash_first: str) -> None:
    """The tree's criteria copy names the release, overrides FlashProve's Whole output checked
    from the accepted C1 (OVR-4, its disclosure published) and holds SASH under a pending
    disclosure (OVR-8). Test data only: the real criteria file is not changed."""
    path = root / "web/_data/criteria.json"
    crit = json.loads(path.read_text())
    crit["release"] = RELEASE
    for row in crit["rows"]:
        if row["id"] == "flashprove":
            cell = row["cells"]["whole_output"]
            cell |= {"stated": "partly", "state": "no",
                     "contradicted_by": [{"control": "C1", "run_id": first}]}  # fmt: skip
            row["disclosures"] = [{"run_id": first, "state": "published", "date": "2026-12-10",
                                   "url": DISCLOSURE_URL}]  # fmt: skip
        if row["id"] == "sash":
            row["disclosures"] = [{"run_id": sash_first, "state": "pending"}]
    write_json(path, crit)


# ---------------------------------------------------------------- command


@contextlib.contextmanager
def _cwd(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def freeze_tree(root: Path) -> int:
    """`iproofs release freeze v0.1` inside the tree, through the CLI."""
    from iproofs import cli  # noqa: PLC0415

    with _cwd(root):
        return cli.main(["release", "freeze", RELEASE])


def build_site(root: Path, out: Path, *, extras: bool = False) -> Path:
    """Build the placeholder tree at `root`, freeze it and run `iproofs site build --out out`
    there, as the site.yml command does; returns `out`. For tests."""
    from iproofs import cli  # noqa: PLC0415

    build_placeholder(root, extras=extras)
    if code := freeze_tree(root):
        raise RuntimeError(f"iproofs release freeze exited {code}")
    with _cwd(root):
        if code := cli.main(["site", "build", "--out", str(out)]):
            raise RuntimeError(f"iproofs site build exited {code}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fixtures.placeholder_release")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--site", type=Path, help="write the site built from the release here")
    group.add_argument("--tree", type=Path, help="keep the frozen placeholder tree here")
    parser.add_argument("--extras", action="store_true", help="test cases; never deployed")
    args = parser.parse_args(argv)
    if any(ROOT.glob("releases/*/index.json")):
        print("a frozen release exists: build the site with `uv run iproofs site build`",
              file=sys.stderr)  # fmt: skip
        return 1
    if args.tree is not None:
        tree = args.tree.resolve()
        tree.mkdir(parents=True, exist_ok=False)
        build_placeholder(tree, extras=args.extras)
        return freeze_tree(tree)
    out = args.site.resolve()
    from iproofs import cli  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="iproofs-placeholder-") as tmp:
        tree = Path(tmp) / "repo"
        tree.mkdir()
        build_placeholder(tree, extras=args.extras)
        if code := freeze_tree(tree):
            return code
        with _cwd(tree):
            return cli.main(["site", "build", "--out", str(out)])


if __name__ == "__main__":
    sys.exit(main())
