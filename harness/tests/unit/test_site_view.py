"""`iproofs.site.inputs` and `iproofs.site.view` over the placeholder release (#320).

Every number here is a placeholder fixture value (fixtures/placeholder_release.py), not a
result; the view copies stored values and labels, and these tests check that it does.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from fixtures import placeholder_release as ph
from fixtures.builds import SiteBuild, writable_copy
from iproofs.errors import ErrorKind, IProofsError
from iproofs.release import not_measurable_on_profile
from iproofs.schema import SchemaRegistry
from iproofs.site import build, inputs
from iproofs.site import view as site_view_module
from iproofs.site.view import FIGURES, MORE, check_rows, site_view
from iproofs.validate import resolve

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def tree(placeholder_build: SiteBuild) -> Path:
    """The deployed tree, frozen (the shared build: its freeze must exit 0, fixtures/builds)."""
    return placeholder_build.repo


@pytest.fixture(scope="module")
def view(tree: Path) -> dict[str, Any]:
    return site_view(tree)


@pytest.fixture(scope="module")
def extras_tree(extras_build: SiteBuild) -> Path:
    """The tree with every test-only case, frozen (shared, as `tree`)."""
    return extras_build.repo


@pytest.fixture(scope="module")
def extras(extras_tree: Path) -> dict[str, Any]:
    return site_view(extras_tree)


def configuration(view: dict[str, Any], system: str, configuration: str | None = None,
                  workload: str | None = None) -> dict[str, Any]:  # fmt: skip
    """The system's configuration on `workload`, by default its placeholder workload."""
    wid = workload or ph.NATIVE.get(system, ph.WORKLOAD)
    found = [c for c in view["configurations"] if c["system"] == system
             and c["workload"]["id"] == wid
             and (configuration is None or c["configuration"] == configuration)]  # fmt: skip
    assert len(found) == 1
    out = found[0]
    assert isinstance(out, dict)
    return out


def test_view_is_plain_json(view: dict[str, Any]) -> None:
    assert json.loads(json.dumps(view)) == view


def test_sort_key_is_stored_value(view: dict[str, Any], tree: Path) -> None:
    """S4: each sort key is the stored value in its base unit, nothing rescaled."""
    seen = 0
    for c in view["configurations"]:
        for f in [*c["figures"].values(), c["agreement"]]:
            if not f["recorded"]:
                assert f["sort_key"] is None
                continue
            stored = resolve(tree, f["source"])
            assert isinstance(stored, dict)
            assert f["sort_key"] == stored["value"]
            seen += f["value"] is not None
    assert seen >= 2 * len(FIGURES)


def test_labels_pass_through(view: dict[str, Any], tree: Path) -> None:
    """S2, S3: unit, scope, grade, tier, null reason and statistics are the stored ones."""
    for c in view["configurations"]:
        for f in c["figures"].values():
            if f["recorded"]:
                stored = resolve(tree, f["source"])
                assert isinstance(stored, dict)
                for key in ("unit", "scope", "grade", "tier", "null_reason"):
                    assert f[key] == stored[key], (c["system"], f["metric"], key)
                assert f["stats"] == stored.get("stats")


def test_one_proof_covers_names_d_tpp(view: dict[str, Any]) -> None:
    """The covers figure is D-STAT over D-TPP (RFC-0004): 1,024 and 1,088 token (fixture)."""
    for system, want in (("flashprove", 1024.0), ("sash", 1088.0)):
        f = configuration(view, system)["figures"]["tokens_covered_per_proof"]
        assert (f["value"], f["unit"], f["formula"], f["repetition_formula"]) == (
            want, "token", "D-STAT", "D-TPP")  # fmt: skip


def test_absent_metric_not_recorded(view: dict[str, Any]) -> None:
    """More numbers: a metric the runs do not record prints "No value", never a typed number."""
    f = configuration(view, "flashprove")["figures"]["prove_gpu_memory_peak"]
    assert f == {"metric": "prove_gpu_memory_peak", "recorded": False, "value": None,
                 "sort_key": None}  # fmt: skip
    assert set(configuration(view, "flashprove")["figures"]) == {*FIGURES, *MORE}


def test_runs_left_out_listed(view: dict[str, Any]) -> None:
    """S7: run ids, reasons, the replacing run, each run's record, and a failure's exit code and
    last line."""
    runs = configuration(view, "sash")["runs"]
    rid = ph.run_id
    reason = f"superseded by {rid('sash', ph.SASH_WORKLOAD, 5)}: {ph.SASH_CORRECTION}"
    record = f"results/{ph.RELEASE}/sash/{{}}/run.json"
    assert runs["left_out"] == [{
        "run_id": rid("sash", ph.SASH_WORKLOAD, 1), "reasons": [reason], "reason_words": [reason],
        "replaced_by": rid("sash", ph.SASH_WORKLOAD, 5),
        "record": record.format(rid("sash", ph.SASH_WORKLOAD, 1)),
        "replaced_by_record": record.format(rid("sash", ph.SASH_WORKLOAD, 5))}]  # fmt: skip
    assert [(f["run_id"], f["exit_code"], f["last_line"]) for f in runs["failed"]] == [
        (rid("sash", ph.SASH_WORKLOAD, 2), 1, ph.SASH_FAILURE["message"])]  # fmt: skip
    assert runs["completed"] == [rid("sash", ph.SASH_WORKLOAD, n) for n in (3, 4, 5)]


def test_reference_all_failed_counts(view: dict[str, Any]) -> None:
    """S3, S7: 0 completed, 3 failed, below minimum repetitions, NM-1."""
    for system in ("ref-serve", "ref-recompute"):
        c = configuration(view, system)
        assert (len(c["runs"]["completed"]), len(c["runs"]["failed"])) == (0, 3)
        assert c["insufficient_repetitions"] is True
        assert c["runs"]["not_measurable"] is True
        assert {f["kind"] for f in c["runs"]["failed"]} == {"resource"}


def test_orders(view: dict[str, Any]) -> None:
    """S5: benchmarked and not benchmarked in name order; reference serve then recompute."""
    orders = view["orders"]
    assert orders["benchmarked"] == ["flashprove", "sash"]
    assert orders["reference"] == ["ref-serve", "ref-recompute"]
    names = [view["facts"]["rows"][r]["name"].lower() for r in orders["not_benchmarked"]]
    assert names == sorted(names)
    assert len(names) == 19


def test_card_identity(view: dict[str, Any]) -> None:
    """S1 item 2: the card the index names, its digest, link and the not-reviewed state."""
    card = configuration(view, "flashprove")["card"]
    assert card["path"] == "systems/flashprove/claim.yaml"
    assert card["digest"].startswith("sha256:")
    assert card["link"].endswith("/blob/main/systems/flashprove/claim.yaml")
    assert card["reviewed"] is False
    assert card["upstream"]["commit"] == "9e2bdd8ff5bf9c62f18263d7dac189b0400b260c"
    assert configuration(view, "ref-serve")["card"] is None


def test_property_controls_without_release(view: dict[str, Any]) -> None:
    """OVR-5, OVR-7: no criteria release reads no run, so each mapped control prints
    "no run read", never "not run"; an unmapped property has no control."""
    lists = configuration(view, "flashprove")["property_controls"]["properties"]
    for prop, mapped in (("whole_output", ["C1", "C2", "C4", "C7"]),
                         ("model_bound", ["C3", "P1", "P2"]), ("weights_hidden", [])):  # fmt: skip
        assert lists[prop]["mapped"] == mapped
        assert {o["outcome"] for o in lists[prop]["outcomes"]} <= {"no_run_read"}
        assert [o["control"] for o in lists[prop]["outcomes"]] == mapped
    assert "property_controls" not in configuration(view, "ref-serve")


def test_property_controls_with_release(extras: dict[str, Any]) -> None:
    """With the criteria release named, every run OVR-5 reads is listed: the recorded
    outcome, or "not run" for a run whose controls.json lacks the control."""
    c = configuration(extras, "flashprove", "exact-match-cp-verify")
    whole = c["property_controls"]["properties"]["whole_output"]["outcomes"]
    first = ph.run_id("flashprove", ph.WORKLOAD, 1)
    c1 = {o["run_id"]: o["outcome"] for o in whole if o["control"] == "C1"}
    assert c1[first] == "accepted"
    assert c1[ph.run_id("flashprove", ph.WORKLOAD, 2)] == "not_run"  # no controls.json
    # the card row is the configuration on every workload it runs (OVR-5): b1 is read too
    assert c1[ph.run_id("flashprove", ph.SECOND_WORKLOAD, 1)] == "rejected"
    assert ph.run_id("flashprove", ph.WORKLOAD, 102) not in c1  # withdrawn: not read
    # each run read names its run.json, and its controls.json only when it has one
    runs = {r["run_id"]: r for r in c["property_controls"]["runs"]}
    assert runs[first]["controls"] == f"results/{ph.RELEASE}/flashprove/{first}/controls.json"
    assert runs[ph.run_id("flashprove", ph.WORKLOAD, 2)]["controls"] is None
    assert all(r["record"].endswith(f"/{i}/run.json") for i, r in runs.items())
    # the contradicting control of the overridden cell, with its record
    assert c["property_controls"]["properties"]["whole_output"]["contradicted"] == [
        {"control": "C1", "run_id": first, "record": runs[first]["controls"]}]  # fmt: skip


def test_release_record_listed(extras: dict[str, Any]) -> None:
    """Release page: every listed run with its status and record, the withdrawn runs, the
    claim cards; the unexpected outcomes with their stored records; the targets by file."""
    release = extras["release"]
    assert len(release["runs"]) == len(set(r["run_id"] for r in release["runs"]))
    failed = {r["run_id"] for r in release["runs"] if r["status"] == "failed"}
    assert ph.run_id("sash", ph.SASH_WORKLOAD, 2) in failed
    assert [x["run_id"] for x in release["superseded_runs"]] == [
        ph.run_id("flashprove", ph.WORKLOAD, 102)]  # fmt: skip
    fp = configuration(extras, "flashprove", "exact-match-cp-verify")
    first = ph.run_id("flashprove", ph.WORKLOAD, 1)
    [u] = fp["unexpected"]
    assert (u["control"], u["run_id"], u["outcome"]) == ("C1", first, "accepted")
    assert u["stored"]["expected"] == ["rejected"]
    assert u["stored"]["trials"]
    [t] = extras["targets"]
    assert t["path"] == ph.TARGET
    assert t["author"]["name"]
    assert [r["position"] for r in t["results"]] == list(range(len(t["results"])))


def test_pending_row_draws_no_state(extras: dict[str, Any], extras_tree: Path) -> None:
    """OVR-8: a row under a pending disclosure is not drawn and lists no outcome; its cells
    keep the states the criteria file sets (the stated states, since no cell of the row carries
    `stated`), which the system page prints beside the notice."""
    row = extras["criteria"]["rows"]["sash"]
    assert (row["pending"], row["drawn"]) == (True, False)
    raw = next(r for r in json.loads((extras_tree / inputs.CRITERIA).read_text())["rows"]
               if r["id"] == "sash")  # fmt: skip
    for prop, cell in row["cells"].items():
        assert cell["state"] == raw["cells"][prop]["state"], prop
        assert "stated" not in raw["cells"][prop]
    assert extras["criteria"]["rows"]["flashprove"]["drawn"] is True
    assert configuration(extras, "sash")["property_controls"] == {"withheld": True,
                                                                  "properties": {},
                                                                  "runs": []}  # fmt: skip


def test_accepted_records_listed(view: dict[str, Any], extras: dict[str, Any]) -> None:
    """RFC-0008 §Reporting: each stored `accepted` outcome is listed with its control, source
    and expected set, as many as the index counts, so the tally can name it."""
    sash = configuration(view, "sash")
    assert [(a["control"], a["source"], a["passed"]) for a in sash["accepted"]] == [
        ("sash-unsound-skip-residual-stream", "system", True)]  # fmt: skip
    assert len(sash["accepted"]) == sash["controls"]["counts"]["accepted"]
    got = {(a["control"], a["passed"]) for a in configuration(extras, "sash")["accepted"]}
    assert got == {("C2", False), ("sash-unsound-skip-residual-stream", True)}
    assert configuration(view, "flashprove")["accepted"] == []


def test_controls_and_verifier_per_configuration(view: dict[str, Any], tree: Path) -> None:
    """Each configuration's controls entry is the one with its system, workload and profile,
    and its verifier profile is the one its runs' manifests name (RFC-0006 verifier-cpu)."""
    doc = json.loads((tree / "releases/v0.1/index.json").read_text())
    for c in view["configurations"]:
        stored = doc["configurations"][c["position"]]
        key = (stored["system"], stored["workload"], stored["profile"])
        found = [x for x in doc["controls"] if (x["system"], x["workload"], x["profile"]) == key]
        assert found == [c["controls"]]
        assert c["verifier"] == {"profile": ph.VERIFIER, "logical_cpus": 8}, c["system"]


def test_verifier_profiles_must_agree() -> None:
    config = {"system": "x", "workload": {"id": "w"}, "runs": ["a", "b"]}
    records = {r: {"manifest": {"profile": {"verifier": v}}}
               for r, v in (("a", "verifier-cpu"), ("b", "verifier-other"))}  # fmt: skip
    with pytest.raises(IProofsError, match="verifier profiles") as e:
        site_view_module._verifier({"profiles": {}}, config, records)
    assert e.value.kind is ErrorKind.CONFIG


def test_nm1_one_rule() -> None:
    """RFC-0015 NM-1, the freeze's rule the site calls too, on hand-made attempts."""
    assert not_measurable_on_profile([(False, "resource"), (False, "adapter")])
    assert not not_measurable_on_profile([])
    assert not not_measurable_on_profile([(False, "resource"), (True, None)])
    assert not not_measurable_on_profile([(False, "resource"), (False, "timeout")])


def _edited_tree(src: Path, dst: Path, edit: Any) -> Path:
    writable_copy(src, dst)  # the shared tree stays as built
    path = dst / inputs.CRITERIA
    doc = json.loads(path.read_text())
    edit(doc)
    path.write_text(json.dumps(doc))
    return dst


def _drop_override(doc: dict[str, Any]) -> None:
    """The extras criteria copy without FlashProve's override: Whole output back to Partly."""
    row = next(r for r in doc["rows"] if r["id"] == "flashprove")
    cell = row["cells"]["whole_output"]
    del cell["stated"]
    cell["state"] = "partly"
    del cell["contradicted_by"]


@pytest.mark.parametrize(("edit", "message"), [
    (lambda d: d.update(release="v0.0"), "built for release 'v0.0'"),
    (_drop_override, "C1 was accepted outside its expected set"),
])  # fmt: skip
def test_criteria_must_agree_with_the_release(
    extras_tree: Path, tmp_path: Path, edit: Any, message: str
) -> None:
    """A criteria file built for another release, or one that draws a state a stored outcome
    contradicts (OVR-3, OVR-4), stops the build as well as failing CRIT-13."""
    root = _edited_tree(extras_tree, tmp_path / "tree", edit)
    with pytest.raises(IProofsError, match=message) as e:
        site_view(root)
    assert e.value.kind is ErrorKind.CONFIG


def test_one_card_configuration_per_system() -> None:
    """SRC-1: one card row per card; the renderer draws one glyph per system page, so a second
    card configuration of a system, or a configuration no card row names, is refused."""
    crit = inputs.load_criteria(ROOT)
    empty: dict[str, list[Any]] = {"outside_expected": []}
    configs = [{"kind": "prover", "system": "flashprove", "configuration": name,
                "controls": empty} for name in ("exact-match-cp-verify", "second")]  # fmt: skip
    with pytest.raises(IProofsError, match="2 card configurations") as e:
        check_rows(crit, "v0.1", configs)
    assert e.value.kind is ErrorKind.CONFIG
    with pytest.raises(IProofsError, match="no card row for flashprove/second"):
        check_rows(crit, "v0.1", configs[1:])
    check_rows(crit, "v0.1", configs[:1])
    assert crit.cards[("flashprove", "exact-match-cp-verify")] == "flashprove"


def test_override_cell_keeps_stated(extras: dict[str, Any]) -> None:
    cell = extras["criteria"]["rows"]["flashprove"]["cells"]["whole_output"]
    assert (cell["stated"], cell["state"]) == ("partly", "no")
    assert cell["contradicted_by"][0]["control"] == "C1"


def test_reply_escaped(extras: dict[str, Any]) -> None:
    reply = extras["release"]["replies"]["sash"]
    assert "&lt;b&gt;Markup in a reply&lt;/b&gt;" in reply
    assert "<b>" not in reply


def test_footer_facts(view: dict[str, Any]) -> None:
    assert view["release"]["candidate"] is True
    assert view["release"]["licence"] == "CC BY 4.0"
    assert view["criteria"]["rfc"] == {"file": "0016-glyph-properties-and-states.md",
                                       "status": "Draft"}  # fmt: skip
    assert view["criteria"]["sha256"].startswith("sha256:")


# ---------------------------------------------------------------- loader failures


def edited(tmp_path: Path, rel: str, edit: Any) -> Path:
    for part in ("schema", "rfcs", "web/_data"):
        shutil.copytree(ROOT / part, tmp_path / part)
    doc = json.loads((tmp_path / rel).read_text())
    edit(doc)
    (tmp_path / rel).write_text(json.dumps(doc))
    return tmp_path


def test_every_family_is_known() -> None:
    """Every family in the criteria file is one the site has words for (INV-GLYPH-1)."""
    crit = json.loads((ROOT / inputs.CRITERIA).read_text())
    assert {r["family"] for r in crit["rows"]} <= set(inputs.FAMILIES)


@pytest.mark.parametrize(("edit", "message"), [
    (lambda d: d["rows"][0]["cells"]["model_bound"].update(state="blue"), "unknown state"),
    (lambda d: d["rows"][0].update(family="guessed"), "unknown family"),
    (lambda d: d["rows"][0]["cells"]["model_bound"].update(score="1"), "unknown keys"),
    (lambda d: d["rows"][0].update(source_class="hearsay"), "unknown source class"),
    (lambda d: d.update(schema="criteria/0"), "the site reads 'criteria/1'"),
    (lambda d: d["rows"][0]["cells"]["model_bound"].update(stated="green"), "unknown state"),
])  # fmt: skip
def test_criteria_loader_refuses(tmp_path: Path, edit: Any, message: str) -> None:
    root = edited(tmp_path, inputs.CRITERIA, edit)
    with pytest.raises(IProofsError, match=message) as e:
        inputs.load_criteria(root)
    assert e.value.kind is ErrorKind.CONFIG


def test_criteria_states_read() -> None:
    """One vocabulary (RFC-0016 §States): state ids in the cells, one word for each."""
    crit = inputs.load_criteria(ROOT)
    assert crit.release is None
    assert {k: v["word"] for k, v in crit.states.items()} == {
        "yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "Not stated"}  # fmt: skip
    cells = crit.rows["sash"]["cells"]
    assert cells["weights_hidden"]["state"] == "not_stated"
    assert cells["model_bound"]["state"] == "yes"
    assert (
        cells["weights_hidden"]["sources_read"][0]["repo"] == "sg-ai-safety-hub/zk-inference-prover"
    )
    assert {c["state"] for r in crit.rows.values() for c in r["cells"].values()} <= set(
        inputs.STATES)  # fmt: skip


def test_facts_checks(tmp_path: Path) -> None:
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    facts = inputs.load_facts(ROOT, registry)
    crit = inputs.load_criteria(ROOT)
    inputs.check_facts(facts, crit, ["flashprove", "ezkl"], sorted(facts.models))
    with pytest.raises(IProofsError, match="no row 'nope'"):
        inputs.check_facts(facts, crit, ["nope"], [])
    with pytest.raises(IProofsError, match="no model"):
        inputs.check_facts(facts, crit, [], ["sha256:" + "0" * 64])
    root = edited(tmp_path, inputs.FACTS, lambda d: d["rows"]["zkllm"]["status"].update(
        state="active"))  # fmt: skip
    with pytest.raises(IProofsError, match="disagrees with facts status"):
        inputs.check_facts(inputs.load_facts(root, registry), crit, [], [])


@pytest.mark.parametrize("stale", ["old.html", "og/old.html"])
def test_stale_output_is_config_error(tree: Path, tmp_path: Path, stale: str) -> None:
    """A page or card source the build no longer writes stops it as a config error (not an
    assert, which `python -O` drops), before any page is written."""
    out = tmp_path / "out"
    (out / stale).parent.mkdir(parents=True, exist_ok=True)
    (out / stale).write_text("stale")
    with pytest.raises(IProofsError, match="no longer writes") as e:
        build(tree, out)
    assert e.value.kind is ErrorKind.CONFIG
    assert not (out / "index.html").exists()


def test_no_release_is_config_error(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match="placeholder_release") as e:
        inputs.newest_release(tmp_path)
    assert e.value.kind is ErrorKind.CONFIG


def test_overhead_conditions_words() -> None:
    """RFC-0004 INV-DERIVE-9: the conditions line, the precision note and the high-load
    context, built from a conditions block and stored quantities (fixture values, not a
    result); nothing without a value."""
    from iproofs.site.view import overhead_words  # noqa: PLC0415

    conditions = {
        "engine": {"name": "vllm", "version": "0.32.0", "interface": "vllm serve",
                   "image_digest": None,
                   "settings": "engine defaults except --tensor-parallel-size 4, "
                               "--max-model-len 1025, --max-num-seqs 24",
                   "settings_high": "engine defaults except --tensor-parallel-size 4, "
                                    "--max-model-len 1025",
                   "max_num_batched_tokens": {"matched": 8192, "high": 8192}},
        "decoding": "greedy", "warm": True, "runtime": "hosted",
        "serving_model": {"id": "m", "version": 1, "digest": "sha256:" + "0" * 64,
                          "publisher": "Meta", "precision": "FP8", "release_statement": "q"},
        "proved_precision": "UD-Q4_K_XL", "weight_bits": "w",
        "gpus": {"system": 1, "serving": 4, "serving_high": 4},
        "gpu_model": "NVIDIA H200",
        "profiles": {"system": "a", "serving": "b", "serving_high": "b"},
        "batch": {"matched": 24, "high": 1024},
        "batches_per_session": {"system": 5, "serving_matched": 25, "serving_high": 5},
        "prompt_count_run": {"system": 120, "serving_matched": 600, "serving_high": 5120},
        "n": {"system": 3, "serving_matched": 3, "serving_high": 3},
    }  # fmt: skip
    pairs = {"n_system": 3, "n_serving": 3, "min": 72.0, "max": 146.0}
    stats = {
        "overhead_vs_production_prove.steady": {"value": 100.0, "pairs": pairs,
                                                "scope": "prove.steady"},
        "overhead_vs_production_high_prove.steady": {"value": 200.0, "pairs": pairs,
                                                     "scope": "prove.steady"},
    }  # fmt: skip
    wl = {"precision": {"weight_bits": {"bits": 4.84, "basis": "computed"}}}
    words = overhead_words(conditions, stats, wl)
    assert words is not None
    assert words["precision"] == (
        "Proving the UD-Q4_K_XL model (4.84 bits per active weight, computed) costs 100 times "
        "(range 72 to 146 over 3 \u00d7 3 pairs) serving Meta's FP8 release, in GPU-seconds per "
        "token, steady, at 24 requests a batch."
    )
    line = words["conditions"]
    gpus = "1 \u00d7 NVIDIA H200 for the prover, 4 for serving"
    for part in ("prove.steady scope", "vllm 0.32.0, vllm serve", "480 further windows", gpus,
                 "RFC-0006 C5", "greedy", "--max-num-seqs 24",
                 "5 batches for the prover and 25 for serving"):  # fmt: skip
        assert part in line, part
    assert words["high"].startswith("At 1024 requests a batch: 200\u00d7")
    assert "the prover's 120 prompts plus 5000 further windows" in words["high"]
    assert (
        "prove.steady scope; 5 batches for serving on 4 \u00d7 NVIDIA H200, engine defaults"
        " except --tensor-parallel-size 4, --max-model-len 1025"
    ) in words["high"]
    unrecorded = {**conditions, "batches_per_session": {"system": 5, "serving_matched": None,
                                                        "serving_high": 5}}  # fmt: skip
    again = overhead_words(unrecorded, stats, wl)
    assert again is not None
    assert "5 batches for the prover and not recorded for serving" in again["conditions"]
    stats["overhead_vs_production_prove.steady"] = {"value": None, "pairs": pairs}
    assert overhead_words(conditions, stats, wl) is None


def sash_conditions(warm: bool) -> dict[str, Any]:
    """A conditions block of a SASH-like row: one request a batch, one GPU on each side."""
    return {
        "engine": {"name": "vllm", "version": "0.32.0", "interface": "vllm serve",
                   "image_digest": None, "settings": "engine defaults except x",
                   "settings_high": None,
                   "max_num_batched_tokens": {"matched": 8192, "high": None}},
        "decoding": "greedy", "warm": warm, "runtime": "hosted",
        "serving_model": {"id": "m", "version": 1, "digest": "sha256:" + "0" * 64,
                          "publisher": "Meta", "precision": "BF16", "release_statement": "q"},
        "proved_precision": "BF16", "weight_bits": None,
        "gpus": {"system": 1, "serving": 1, "serving_high": None},
        "gpu_model": "NVIDIA H200",
        "profiles": {"system": "a", "serving": "b", "serving_high": None},
        "batch": {"matched": 1, "high": None},
        "batches_per_session": {"system": 1, "serving_matched": 1, "serving_high": None},
        "prompt_count_run": {"system": 1, "serving_matched": 1, "serving_high": None},
        "n": {"system": 1, "serving_matched": 1, "serving_high": 0},
    }  # fmt: skip


def test_overhead_session_words() -> None:
    """RFC-0004 INV-DERIVE-10: the session figure's words say that start-up is inside it on
    both sides, and its high-load context is the session one too (fixture values, not a
    result)."""
    from iproofs.site.view import overhead_words  # noqa: PLC0415

    conditions = sash_conditions(warm=False)
    pairs = {"n_system": 1, "n_serving": 1, "min": 200.0, "max": 200.0}
    session = "overhead_vs_production_prove.session"
    stats = {
        "overhead_vs_production_prove.steady": {"value": None, "pairs": pairs,
                                                "scope": "prove.steady"},
        session: {"value": 200.0, "pairs": pairs, "scope": "prove.session"},
        "overhead_vs_production_high_prove.steady": {"value": 9.0, "pairs": pairs,
                                                     "scope": "prove.steady"},
    }  # fmt: skip
    wl = {"precision": {"weight_bits": {"bits": 16, "basis": "computed"}}}
    words = overhead_words(conditions, stats, wl, session)
    assert words is not None
    assert words["conditions"].startswith(
        "prove.session scope (start-up included on both sides: the prover's from the start of "
        "its prove call, production serving's from the start of its engine, each to its last "
        "token)"
    )
    assert "greedy decoding, cold: engine and prover start-up inside the session" in (
        words["conditions"])  # fmt: skip
    assert words["precision"].endswith(
        "in GPU-seconds per token, per proving session with start-up, at 1 requests a batch."
    )
    assert "high" not in words  # the steady high-load figure is not this row's context
    assert overhead_words(conditions, stats, wl) is None  # the steady figure has no value


def test_overhead_warm_words() -> None:
    """RFC-0004 INV-DERIVE-11: a row whose headline is the warm figure (SASH) names both
    scopes, the prover's session with its start-up and serving's steady scope, and prints no
    high-load context (no high-load figure pairs those scopes); the index's
    `overhead_headline` names the statistic (fixture values, not a result)."""
    from iproofs.site.view import WARM, overhead_metric, overhead_words  # noqa: PLC0415

    pairs = {"n_system": 1, "n_serving": 3, "min": 900.0, "max": 1100.0}
    stats = {
        "overhead_vs_production_prove.steady": {"value": None, "pairs": pairs,
                                                "scope": "prove.steady"},
        WARM: {"value": 1000.0, "pairs": pairs, "scope": "prove.session"},
        "overhead_vs_production_high_prove.session": {"value": 9.0, "pairs": pairs,
                                                      "scope": "prove.session"},
    }  # fmt: skip
    wl = {"precision": {"weight_bits": {"bits": 16, "basis": "computed"}}}
    headline = {"overhead_headline": {"metric": WARM, "formula": "D-OVERHEAD-WARM",
                                      "scope": "prove.session", "serving_scope": "prove.steady",
                                      "start_up": "prover_only"}}  # fmt: skip
    assert overhead_metric(headline) == WARM
    assert overhead_metric({}) == "overhead_vs_production_prove.steady"
    words = overhead_words(sash_conditions(warm=True), stats, wl, WARM)
    assert words is not None
    assert words["conditions"].startswith(
        "prove.session scope for the prover, from the start of its prove call to its last "
        "proof (its start-up included: it releases no proof before the whole request is "
        "proved), prove.steady scope for production serving"
    )
    assert "greedy decoding, warm serving, the prover's start-up inside its session" in (
        words["conditions"])  # fmt: skip
    assert "range 900 to 1,100 over 1 \u00d7 3 pairs" in words["conditions"]
    assert words["precision"].endswith(
        "in GPU-seconds per token, per proving session with the prover's start-up, against "
        "warm serving (steady), at 1 requests a batch."
    )
    assert "high" not in words
