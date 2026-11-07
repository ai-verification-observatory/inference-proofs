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
from iproofs.errors import ErrorKind, IProofsError
from iproofs.release import not_measurable_on_profile
from iproofs.schema import SchemaRegistry
from iproofs.site import build, inputs
from iproofs.site import view as site_view_module
from iproofs.site.view import FIGURES, MORE, check_rows, site_view
from iproofs.validate import resolve

ROOT = Path(__file__).resolve().parents[3]


def frozen(root: Path, *, extras: bool = False) -> Path:
    ph.build_placeholder(root, extras=extras)
    assert ph.freeze_tree(root) == 0
    return root


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return frozen(tmp_path_factory.mktemp("view"))


@pytest.fixture(scope="module")
def view(tree: Path) -> dict[str, Any]:
    return site_view(tree)


@pytest.fixture(scope="module")
def extras_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return frozen(tmp_path_factory.mktemp("view-extras"), extras=True)


@pytest.fixture(scope="module")
def extras(extras_tree: Path) -> dict[str, Any]:
    return site_view(extras_tree)


def configuration(view: dict[str, Any], system: str, configuration: str | None = None,
                  workload: str = ph.WORKLOAD) -> dict[str, Any]:  # fmt: skip
    found = [c for c in view["configurations"] if c["system"] == system
             and c["workload"]["id"] == workload
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
    """The covers figure is D-STAT over D-TPP (RFC-0004): 1,024 and 1,025 token (fixture)."""
    for system, want in (("flashprove", 1024.0), ("sash", 1025.0)):
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
    """S7: run ids, reasons, the replacing run, and a failure's exit code and last line."""
    runs = configuration(view, "sash")["runs"]
    rid = ph.run_id
    assert runs["left_out"] == [{"run_id": rid("sash", ph.WORKLOAD, 1), "reasons": [
        f"superseded by {rid('sash', ph.WORKLOAD, 5)}: {ph.SASH_CORRECTION}"],
        "replaced_by": rid("sash", ph.WORKLOAD, 5)}]  # fmt: skip
    assert [(f["run_id"], f["exit_code"], f["last_line"]) for f in runs["failed"]] == [
        (rid("sash", ph.WORKLOAD, 2), 1, ph.SASH_FAILURE["message"])]  # fmt: skip
    assert runs["completed"] == [rid("sash", ph.WORKLOAD, n) for n in (3, 4, 5)]


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


def test_pending_row_draws_no_state(extras: dict[str, Any], extras_tree: Path) -> None:
    """OVR-8: a row under a pending disclosure is not drawn and lists no outcome; its cells
    keep the states the criteria file sets (the stated states, since no cell of the row carries
    `stated`), which the system page prints beside the notice."""
    row = extras["criteria"]["rows"]["sash"]
    assert (row["pending"], row["drawn"]) == (True, False)
    raw = next(r for r in json.loads((extras_tree / inputs.CRITERIA).read_text())["rows"]
               if r["id"] == "sash")  # fmt: skip
    for prop, cell in row["cells"].items():
        assert cell["state"] == inputs.STATE_OF[raw["cells"][prop]["state"]], prop
        assert "stated" not in raw["cells"][prop]
    assert extras["criteria"]["rows"]["flashprove"]["drawn"] is True
    assert configuration(extras, "sash")["property_controls"] == {"withheld": True,
                                                                  "properties": {}}  # fmt: skip


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
    shutil.copytree(src, dst)
    path = dst / inputs.CRITERIA
    doc = json.loads(path.read_text())
    edit(doc)
    path.write_text(json.dumps(doc))
    return dst


def _drop_override(doc: dict[str, Any]) -> None:
    """The extras criteria copy without FlashProve's override: Whole output back to Partly."""
    slot = doc["order"].index("whole_output")
    row = next(r for r in doc["rows"] if r["id"] == "flashprove")
    cell = row["cells"]["whole_output"]
    del cell["stated"]
    cell["state"] = "amber"
    del cell["contradicted_by"]
    row["states"][slot] = doc["test_mapping"]["flashprove"][slot] = "amber"


@pytest.mark.parametrize(("edit", "message"), [
    (lambda d: d.update(release="v0.0"), "built for release 'v0.0'"),
    (_drop_override, "C1 was accepted outside its expected set"),
])  # fmt: skip
def test_criteria_must_agree_with_the_release(
    extras_tree: Path, tmp_path: Path, edit: Any, message: str
) -> None:
    """Until CRIT-13 (#318): a criteria file built for another release, or one that draws a
    state a stored outcome contradicts (OVR-3, OVR-4), stops the build."""
    root = _edited_tree(extras_tree, tmp_path / "tree", edit)
    with pytest.raises(IProofsError, match=message) as e:
        site_view(root)
    assert e.value.kind is ErrorKind.CONFIG


def test_one_card_configuration_per_system() -> None:
    """SRC-1: rows are keyed by system until #318 adds `card`, so a second card of a system
    would borrow the first card's row: refused."""
    crit = inputs.load_criteria(ROOT)
    empty: dict[str, list[Any]] = {"outside_expected": []}
    configs = [{"kind": "prover", "system": "flashprove", "configuration": name,
                "controls": empty} for name in ("exact-match-cp-verify", "second")]  # fmt: skip
    with pytest.raises(IProofsError, match="2 card configurations") as e:
        check_rows(crit, "v0.1", configs)
    assert e.value.kind is ErrorKind.CONFIG
    check_rows(crit, "v0.1", configs[:1])


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
    (lambda d: d["test_mapping"]["flashprove"].reverse(), "disagrees with its cells"),
])  # fmt: skip
def test_criteria_loader_refuses(tmp_path: Path, edit: Any, message: str) -> None:
    root = edited(tmp_path, inputs.CRITERIA, edit)
    with pytest.raises(IProofsError, match=message) as e:
        inputs.load_criteria(root)
    assert e.value.kind is ErrorKind.CONFIG


def test_criteria_states_mapped() -> None:
    crit = inputs.load_criteria(ROOT)
    assert crit.release is None
    cells = crit.rows["sash"]["cells"]
    assert cells["weights_hidden"]["state"] == "not_stated"
    assert cells["model_bound"]["state"] == "yes"
    assert cells["weights_hidden"]["sources_read"]
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
