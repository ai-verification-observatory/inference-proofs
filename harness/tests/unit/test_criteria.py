"""RFC-0016 §Validation rules: CRIT-1 to CRIT-14 on hand-made criteria files and release trees.

Each case starts from a copy of the committed `web/_data/criteria.json` and changes one thing;
the release trees are written here with the fields the rules read (no measurement).
"""

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures.repo import commit, git
from iproofs.controls import CONTROL_PROPERTY
from iproofs.errors import ErrorKind
from iproofs.serialize import load_yaml
from iproofs.validate import Finding
from iproofs.validate import criteria as crit
from iproofs.validate.tree import G2_GLOBS, documents

ROOT = Path(__file__).resolve().parents[3]
RFC = (ROOT / "rfcs/0016-glyph-properties-and-states.md").read_text()
COMMITTED = json.loads((ROOT / crit.PATH).read_text())
SASH = ("sash", "sound-defaults")


def doc() -> dict[str, Any]:
    return copy.deepcopy(COMMITTED)


def row(d: dict[str, Any], rid: str) -> dict[str, Any]:
    found: dict[str, Any] = next(r for r in d["rows"] if r["id"] == rid)
    return found


def cell(d: dict[str, Any], rid: str, prop: str) -> dict[str, Any]:
    found: dict[str, Any] = row(d, rid)["cells"][prop]
    return found


def found(d: dict[str, Any], rule: str, root: Path = ROOT) -> list[Finding]:
    return [f for f in crit.rules(root, d) if f.rule == rule]


def tree(tmp: Path, *parts: str) -> Path:
    """A copy of the parts of the repository the rules read, without git."""
    for part in (
        "systems/flashprove/claim.yaml",
        "systems/sash/claim.yaml",
        "systems/ref-serve/system.yaml",
        "systems/ref-recompute/system.yaml",
        crit.RFC_0015,
        *parts,
    ):
        (tmp / part).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / part, tmp / part)
    return tmp


# ---------------------------------------------------------------- the committed file


def test_committed_file_passes() -> None:
    """Every rule passes on the committed file. CRIT-8 needs the git objects of the commits the
    reference quotes cite: in a shallow clone it reports them as environment errors, so the
    test is skipped there with the reason printed (RFC-0016 §Testing Strategy)."""
    shallow = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    ours = COMMITTED["pins"]["ai-verification-observatory/inference-proofs"]
    if shallow == "true" or crit.git_show(ROOT, ours, crit.RFC_0015) is None:
        pytest.skip(f"commit {ours[:12]} is not in this clone (fetch-depth: 0 runs this test)")
    assert [f.line() for f in crit.rules(ROOT, doc())] == []


def test_criteria_file_is_a_g2_input() -> None:
    """RFC-0013 §G2 inputs: the criteria file is validated against `criteria/1`."""
    assert crit.PATH in G2_GLOBS
    assert documents(ROOT, [crit.PATH, "web/_data/other.json"]) == [crit.PATH]
    assert COMMITTED["schema"] == "criteria/1"


# ---------------------------------------------------------------- CRIT-1


def test_yes_cell_without_quote_fails() -> None:
    d = doc()
    cell(d, "sash", "model_bound")["quotes"] = []
    assert [f.message for f in found(d, "CRIT-1")] == ["a yes cell has no quote"]
    assert found(d, "CRIT-1")[0].kind is ErrorKind.CONFIG


def test_first_quote_must_decide() -> None:
    d = doc()
    quotes = cell(d, "flashprove", "whole_output")["quotes"]
    quotes[0]["decides"] = False
    assert [f.pointer for f in found(d, "CRIT-1")] == ["/rows/0/cells/whole_output/quotes/0"]
    quotes[0]["decides"], quotes[1]["decides"] = True, True
    assert "second deciding quote" in found(d, "CRIT-1")[0].message


def test_aside_quote_deciding_fails() -> None:
    d = doc()
    cell(d, "flashprove", "weights_hidden")["aside"]["quotes"][0]["decides"] = True
    (f,) = found(d, "CRIT-1")
    assert f.pointer.endswith("/aside/quotes/0")
    assert "sets nothing" in f.message


def test_conflict_cell_follows_table() -> None:
    """ST-8: two quotes meeting two states; yes with no gives no, never partly."""
    d = doc()
    c = cell(d, "sash", "model_bound")
    c["conflict"] = True
    c["quotes"] = c["quotes"][:1]
    assert "fewer than two" in found(d, "CRIT-1")[0].message
    yes = c["quotes"][0] | {"meets": "yes"}
    no = c["quotes"][0] | {"meets": "no", "decides": False}
    c["quotes"] = [no | {"decides": True}, yes | {"decides": False}]
    c["state"] = "partly"
    assert "a conflict of no and yes is no" in found(d, "CRIT-1")[0].message
    c["state"] = "no"
    assert found(d, "CRIT-1") == []
    del c["conflict"]
    assert "only for the quotes of a conflict cell" in found(d, "CRIT-1")[0].message


def test_every_quote_checked() -> None:
    d = doc()
    cell(d, "sash", "model_bound")["quotes"][1]["checked"] = False
    assert "not checked" in found(d, "CRIT-1")[0].message


# ---------------------------------------------------------------- CRIT-2


def test_repository_quote_short_commit_fails() -> None:
    d = doc()
    cell(d, "ezkl", "weights_hidden")["quotes"][0]["commit"] = "e196b111"
    messages = [f.message for f in found(d, "CRIT-2")]
    assert "commit 'e196b111' is not a full 40-hex commit" in messages
    assert found(d, "CRIT-2")[0].kind is ErrorKind.INTEGRITY


def test_quote_commit_differs_from_pin_fails() -> None:
    d = doc()
    other = "0" * 40
    q = cell(d, "ezkl", "weights_hidden")["quotes"][0]
    q["commit"], q["url"] = other, q["url"].replace(d["pins"]["zkonduit/ezkl"], other)
    (f,) = found(d, "CRIT-2")
    assert f.message.startswith("zkonduit/ezkl is quoted at 000000000000, pinned at e196b111c1ba")
    d = doc()
    d["pins"]["example/unused"] = other
    assert [f.pointer for f in found(d, "CRIT-2")] == ["/pins/example/unused"]


# ---------------------------------------------------------------- CRIT-3


def test_web_quote_without_archive_or_copy_fails() -> None:
    d = doc()
    del cell(d, "nanozk", "weights_hidden")["quotes"][0]["archive_url"]
    (f,) = found(d, "CRIT-3")
    assert "no archive_url and no copy" in f.message
    assert f.kind is ErrorKind.INTEGRITY
    d = doc()
    cell(d, "nanozk", "weights_hidden")["quotes"][0]["retrieved"] = "2099-01-01"
    assert "after the file's date" in found(d, "CRIT-3")[0].message


def test_web_copy_hash_mismatch_fails(tmp_path: Path) -> None:
    root = tree(tmp_path)
    (root / "web/_data/copies").mkdir(parents=True)
    (root / "web/_data/copies/page.txt").write_text("the text read\n")
    good = hashlib.sha256(b"the text read\n").hexdigest()
    d = doc()
    q = cell(d, "nanozk", "weights_hidden")["quotes"][0]
    del q["archive_url"]
    q["copy"] = {"path": "web/_data/copies/page.txt", "sha256": good}
    assert found(d, "CRIT-3", root) == []
    q["copy"]["sha256"] = "0" * 64
    assert "does not match its sha256" in found(d, "CRIT-3", root)[0].message
    q["copy"]["path"] = "web/_data/copies/gone.txt"
    assert "does not exist" in found(d, "CRIT-3", root)[0].message


def test_deciding_web_quote_not_own_source_fails() -> None:
    """SRC-8: a public row decides only from its own sources; a third-party page may support."""
    d = doc()
    q = cell(d, "nanozk", "weights_hidden")["quotes"][0]
    q["url"] = "https://press.example.org/nanozk-review"
    (f,) = found(d, "CRIT-3")
    assert f.message.startswith("the deciding quote is not from one of the row's own sources")
    c = cell(d, "nanozk", "weights_hidden")
    c["quotes"] = [
        c["quotes"][0] | {"url": "https://arxiv.org/abs/2603.18046"},
        q | {"decides": False},
    ]
    assert found(d, "CRIT-3") == []
    row(d, "nanozk")["own_sources"] = [{"domain": "arxiv.org", "how": "fixture"}]
    assert found(d, "CRIT-3") == []
    row(d, "nanozk")["own_sources"] = [{"repo": "example/nanozk", "how": "fixture"}]
    assert len(found(d, "CRIT-3")) == 1


# ---------------------------------------------------------------- CRIT-4


def test_not_stated_without_sources_or_marker_fails() -> None:
    d = doc()
    del cell(d, "ezkl", "model_bound")["not_copied"]
    (f,) = found(d, "CRIT-4")
    assert "exactly one of sources_read or not_copied" in f.message
    c = cell(d, "ezkl", "model_bound")
    c["not_copied"], c["sources_read"] = (
        True,
        [{"url": "https://example.org", "retrieved": "2026-11-07"}],
    )
    assert len(found(d, "CRIT-4")) == 1
    d = doc()
    cell(d, "ezkl", "formally_verified")["quotes"] = [
        cell(d, "ezkl", "weights_hidden")["quotes"][0]
    ]
    assert "has a deciding quote" in found(d, "CRIT-4")[0].message


def test_not_copied_on_card_row_fails() -> None:
    d = doc()
    c = cell(d, "sash", "weights_hidden")
    del c["sources_read"]
    c["not_copied"] = True
    messages = [f.message for f in found(d, "CRIT-4")]
    assert "not_copied on a row that is not a public-source row" in messages


# ---------------------------------------------------------------- CRIT-5


def test_card_quote_outside_card_repository_fails() -> None:
    """SRC-2: SASH decides only from zk-inference-prover at its pin; the results repository
    may appear in sources read and outside_pin."""
    d = doc()
    c = cell(d, "sash", "whole_output")
    c["quotes"][0] = c["outside_pin"]["quotes"][0] | {"decides": True}
    (f,) = found(d, "CRIT-5")
    assert f.message.startswith("quote from sg-ai-safety-hub/zk-inference-results")
    assert f.kind is ErrorKind.INTEGRITY


def test_card_quote_at_other_commit_fails() -> None:
    d = doc()
    q = cell(d, "flashprove", "model_bound")["quotes"][1]
    q["commit"] = "1" * 40
    assert [f.pointer for f in found(d, "CRIT-5")] == ["/rows/0/cells/model_bound/quotes/1"]
    d = doc()
    cell(d, "flashprove", "security_level")["sources_read"][0]["commit"] = "1" * 40
    assert "sources_read does not include anthropics/FlashProve" in found(d, "CRIT-5")[0].message


def test_card_version_mismatch_fails() -> None:
    d = doc()
    row(d, "flashprove")["card"]["card_version"] = "2"
    (f,) = found(d, "CRIT-5")
    assert f.message == "the card is version 1, the row names 2"


def test_card_configuration_mismatch_fails(tmp_path: Path) -> None:
    """RFC-0002 §File and identity: claim.yaml or claims/<configuration>.yaml, whose own
    configuration is the row's."""
    root = tree(tmp_path)
    d = doc()
    row(d, "flashprove")["card"]["configuration"] = "lean-verify"
    assert found(d, "CRIT-5", root)[0].message == "no claim card flashprove/lean-verify"
    claims = root / "systems/flashprove/claims"
    claims.mkdir()
    text = (root / "systems/flashprove/claim.yaml").read_text()
    (claims / "lean-verify.yaml").write_text(text.replace('"exact-match-cp-verify"', '"other"'))
    assert found(d, "CRIT-5", root)[0].message == "no claim card flashprove/lean-verify"
    (claims / "lean-verify.yaml").write_text(
        text.replace('"exact-match-cp-verify"', '"lean-verify"')
    )
    assert crit.card_file(root, row(d, "flashprove")["card"]) == claims / "lean-verify.yaml"
    assert found(d, "CRIT-5", root) == []


# ---------------------------------------------------------------- CRIT-6


def card(**edits: Any) -> dict[str, Any]:
    doc_: dict[str, Any] = dict(load_yaml(ROOT / "systems/flashprove/claim.yaml"))
    for path, value in edits.items():
        node: Any = doc_
        *head, last = path.split("__")
        for part in head:
            node = node[part]
        node[last] = value
    return doc_


@pytest.mark.parametrize(
    ("edits", "prop", "allowed"),
    [
        ({"zero_knowledge__claimed": "not stated"}, "weights_hidden", {"not_stated"}),
        ({"zero_knowledge__claimed": False}, "weights_hidden", {"partly", "no"}),
        ({"zero_knowledge__claimed": True}, "weights_hidden", set(crit.STATES)),
    ],
)
def test_card_bound_zero_knowledge(edits: dict[str, Any], prop: str, allowed: set[str]) -> None:
    assert crit.card_allows(card(**edits), prop) == allowed


def test_card_bound_zero_knowledge_end_to_end(tmp_path: Path) -> None:
    """With `claimed: false`, yes and not_stated fail and partly and no pass."""
    root = tree(tmp_path)
    path = root / "systems/flashprove/claim.yaml"
    path.write_text(path.read_text().replace("  claimed: true\n", "  claimed: false\n"))
    d = doc()
    for state, fails in (("yes", True), ("not_stated", True), ("partly", False), ("no", False)):
        cell(d, "flashprove", "weights_hidden")["state"] = state
        assert bool(found(d, "CRIT-6", root)) is fails, state


def test_card_bound_tolerance_policy() -> None:
    allowed = crit.card_allows(card(coverage__policy__kind="tolerance"), "model_bound")
    assert allowed == {"partly", "no"}
    assert crit.card_allows(
        card(coverage__policy__kind="not_stated", binding="not stated"), "model_bound"
    ) == {"not_stated"}


def test_card_bound_relation_formal() -> None:
    """The FlashProve card reads `relation_formal: "not stated"`: Formally verified yes fails."""
    assert crit.card_allows(card(), "formally_verified") == {"partly", "no", "not_stated"}
    d = doc()
    cell(d, "flashprove", "formally_verified")["state"] = "yes"
    (f,) = found(d, "CRIT-6")
    assert (
        f.message
        == "the card allows no, not_stated, partly on formally_verified, the cell states yes"
    )


def test_card_bound_level_not_stated() -> None:
    assert crit.card_allows(card(security__level="not stated"), "security_level") == {"not_stated"}


def test_card_bound_trusted_setup() -> None:
    assert crit.card_allows(card(security__setup="trusted"), "no_trusted_party") == {"partly", "no"}
    assert crit.card_allows(card(assumptions_not_stated=True), "no_trusted_party") == {"not_stated"}


# ---------------------------------------------------------------- CRIT-7


def test_reference_state_differs_from_table_fails() -> None:
    d = doc()
    cell(d, "ref-recompute", "no_trusted_party")["state"] = "partly"
    (f,) = found(d, "CRIT-7")
    assert f.message == "the reference table sets yes, the cell is partly"


def test_reference_substitution_sets_partly() -> None:
    """SRC-6: on SASH's workloads ref-recompute declares an FP8 substitution, so Model bound is
    Partly; a row whose workloads disagree on a substitution fails."""
    d = doc()
    row(d, "ref-recompute")["workloads"] = ["sash-l31-8b-c4096"]
    assert [f.message for f in found(d, "CRIT-7")] == [
        "the reference table sets partly, the cell is yes"
    ]
    cell(d, "ref-recompute", "model_bound")["state"] = "partly"
    assert found(d, "CRIT-7") == []
    row(d, "ref-recompute")["workloads"] = ["sash-l31-8b-c4096", "fp-maverick-w1024-b1"]
    assert any(
        "disagree on whether a precision substitution" in f.message for f in found(d, "CRIT-7")
    )
    row(d, "ref-recompute")["workloads"] = ["no-such-workload"]
    assert any("workload no-such-workload is not in" in f.message for f in found(d, "CRIT-7"))


def test_reference_quote_absent_from_current_rfc_fails(tmp_path: Path) -> None:
    root = tree(tmp_path)
    rfc = root / crit.RFC_0015
    rfc.write_text(rfc.read_text().replace("(they prove nothing)", "(they prove no statement)"))
    assert {f.message for f in found(doc(), "CRIT-7", root)} == {
        f"quote no longer in {crit.RFC_0015}"
    }


def rfc_reference_table(text: str = RFC) -> dict[str, dict[str, str]]:
    """The RFC-0016 reference table: role -> property -> state, from the markdown."""
    ids = dict(re.findall(r"^#### (.+?) \(`(\w+)`\)$", text, re.M))
    section = text.split("#### Reference rows", 1)[1].split("\n- SRC-7.", 1)[0]
    out: dict[str, dict[str, str]] = {"serve": {}, "recompute": {}}
    words = {"No": "no", "Yes": "yes", "Partly": "partly", "Not stated": "not_stated"}
    for name, serve, recompute in re.findall(
        r"^\| ([A-Z][^|]+?) \| ([^|]+) \| ([^|]+) \|", section, re.M
    ):
        if name.strip() in ids:
            for role, value in (("serve", serve), ("recompute", recompute)):
                out[role][ids[name.strip()]] = words[re.split(r"[ ;,(]", value.strip())[0]]
    return out


def test_reference_table_matches_rfc() -> None:
    assert rfc_reference_table() == {k: dict(v) for k, v in crit.REFERENCE_TABLE.items()}


# ---------------------------------------------------------------- CRIT-8


def this_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tree(tmp_path)
    git(root, "init", "-q")
    (root / "notes.md").write_text("first line\nthe quoted sentence\nthird line\n")
    return root, commit(root, "fixture")


def quoted(rev: str, lines: str) -> dict[str, Any]:
    d = doc()
    d["rows"] = [row(d, "ref-serve")]
    d["pins"] = {"ai-verification-observatory/inference-proofs": rev}
    c = cell(d, "ref-serve", "weights_hidden")
    c["quotes"] = [
        c["quotes"][0]
        | {
            "path": "notes.md",
            "lines": lines,
            "commit": rev,
            "text": "the quoted sentence",
            "url": f"https://x/{rev}",
        }
    ]
    for other in crit.PROPERTIES[1:]:
        cell(d, "ref-serve", other)["quotes"] = []
    return d


def test_this_repository_quote_not_at_lines_fails(tmp_path: Path) -> None:
    root, rev = this_repo(tmp_path)
    assert found(quoted(rev, "L2"), "CRIT-8", root) == []
    (f,) = found(quoted(rev, "L3"), "CRIT-8", root)
    assert f.message == f"text not at notes.md L3 in {rev[:12]}"
    assert f.kind is ErrorKind.INTEGRITY


def test_missing_commit_is_environment_error(tmp_path: Path) -> None:
    root, _ = this_repo(tmp_path)
    (f,) = found(quoted("f" * 40, "L2"), "CRIT-8", root)
    assert f.kind is ErrorKind.ENVIRONMENT
    assert "not in the local object store" in f.message


# ---------------------------------------------------------------- CRIT-9 to CRIT-12


def test_number_anywhere_fails() -> None:
    d = doc()
    d["properties"][0]["n"] = 1
    cell(d, "ezkl", "model_bound")["quotes"] = [0.5]
    i = d["rows"].index(row(d, "ezkl"))
    assert [f.pointer for f in found(d, "CRIT-10")] == [
        "/properties/0/n",
        f"/rows/{i}/cells/model_bound/quotes/0",
    ]


def test_aggregate_key_fails() -> None:
    d = doc()
    d["Total"] = "6"
    row(d, "sash")["score"] = "high"
    cell(d, "sash", "model_bound")["Weight"] = "a"
    assert sorted(f.pointer for f in found(d, "CRIT-10")) == [
        "/Total",
        "/rows/1/cells/model_bound/Weight",
        "/rows/1/score",
    ]


def test_order_differs_fails() -> None:
    d = doc()
    d["order"] = list(reversed(d["order"]))
    assert [f.pointer for f in found(d, "CRIT-9")] == ["/order"]
    d = doc()
    del row(d, "ezkl")["cells"]["security_level"]
    d["rows"].append(copy.deepcopy(row(d, "zkml")))
    assert {f.message for f in found(d, "CRIT-9")} == {
        "a row does not have exactly the six cells",
        "row id zkml repeats",
    }


def test_outside_pin_on_public_row_fails() -> None:
    d = doc()
    cell(d, "ezkl", "model_bound")["outside_pin"] = cell(d, "sash", "weights_hidden")["outside_pin"]
    assert [f.message for f in found(d, "CRIT-11")] == ["outside_pin on a public_sources row"]
    d = doc()
    row(d, "sash")["workloads"] = ["fp-maverick-w1024-b1"]
    row(d, "ref-serve")["own_sources"] = [{"repo": "a/b", "how": "fixture"}]
    assert len(found(d, "CRIT-11")) == 2


def test_override_on_public_row_fails() -> None:
    d = doc()
    c = cell(d, "nanozk", "weights_hidden")
    c |= {
        "state": "no",
        "stated": "yes",
        "contradicted_by": [{"control": "C1", "run_id": run_id(1)}],
    }
    row(d, "nanozk")["disclosures"] = [{"run_id": run_id(1), "state": "pending"}]
    messages = {f.message for f in found(d, "CRIT-11")}
    assert messages == {
        "stated on a public_sources row",
        "contradicted_by on a public_sources row",
        "disclosures on a public_sources row",
    }


def test_public_row_in_benchmarked_tab_fails() -> None:
    d = doc()
    row(d, "ezkl")["tab"] = "benchmarked"
    row(d, "sash")["tab"] = "archived"
    assert [f.pointer for f in found(d, "CRIT-12")] == ["/rows/1/tab", "/rows/6/tab"]


# ---------------------------------------------------------------- OVR-2 control map


def rfc_control_map(text: str = RFC) -> dict[str, str | None]:
    ids = dict(re.findall(r"^#### (.+?) \(`(\w+)`\)$", text, re.M))
    section = text.split("### Negative control override", 1)[1].split("\n- OVR-3.", 1)[0]
    rows = re.findall(r"^\| ([CP]\d) \| [^|]+ \| ([^|]+) \|", section, re.M)
    return {c: None if p.strip() == "none" else ids[p.strip()] for c, p in rows}


def test_control_map_matches_rfc() -> None:
    """OVR-2: the map CRIT-13 and CRIT-14 use is the RFC's table."""
    assert crit.control_map() is CONTROL_PROPERTY
    assert dict(crit.control_map()) == rfc_control_map()


# ---------------------------------------------------------------- CRIT-13 on hand-made releases

DATES = {"v0.1": ("2026-11-20", "2027-01-10"), "v0.2": ("2026-12-20", "2027-03-10")}


def run_id(n: int, rel: str = "v0.1") -> str:
    return f"{DATES[rel][0]}-sash-sash-l31-8b-c4096-prover-h100-{n}"


def control(
    cid: str, outcome: str, expected: tuple[str, ...] = ("rejected",), trials: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "id": cid,
        "outcome": outcome,
        "expected": list(expected),
        "trials": [{"outcome": t} for t in trials],
    }


class Release:
    """A release tree with the fields OVR-5 and CRIT-13 read."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def run(
        self,
        n: int,
        rel: str = "v0.1",
        *,
        controls: list[dict[str, Any]] | None = None,
        pending: bool = True,
        configuration: str = SASH[1],
        replaces: str | None = None,
        card_version: int = 1,
    ) -> str:
        rid = run_id(n, rel)
        rel_dir = f"results/{rel}/sash/{rid}"
        path = self.root / rel_dir
        path.mkdir(parents=True)
        claim = {"system": "sash", "configuration": configuration, "card_version": card_version}
        reps = None if replaces is None else {"run_id": replaces, "reason": "fixture"}
        (path / "run.json").write_text(
            json.dumps({"run_id": rid, "claim": claim, "replaces": reps})
        )
        if controls is not None:
            body = {"run_id": rid, "disclosure_pending": pending, "controls": controls}
            (path / "controls.json").write_text(json.dumps(body))
        return rel_dir

    def freeze(
        self,
        rel: str,
        runs: list[str],
        *,
        superseded: tuple[str, ...] = (),
        cards: tuple[tuple[str, str], ...] = (SASH,),
    ) -> None:
        doc_ = {
            "schema": "release/1",
            "release": rel,
            "freeze_date": DATES[rel][1],
            "runs": runs,
            "superseded_runs": [{"run_id": s, "reason": "fixture"} for s in superseded],
            "claim_cards": [{"system": s, "configuration": c, "card_version": 1} for s, c in cards],
        }
        path = self.root / "releases" / rel / "release.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(doc_, sort_keys=False))


@pytest.fixture
def rel(tmp_path: Path) -> Release:
    return Release(tree(tmp_path))


def sash_doc(release: str | None = "v0.1", published: tuple[str, ...] = ()) -> dict[str, Any]:
    """The committed file with only the SASH card row, built for `release`, the disclosures of
    `published` runs published."""
    d = doc()
    d["rows"] = [r for r in d["rows"] if r["source_class"] != crit.CARD or r["id"] == "sash"]
    if release is not None:
        d["release"] = release
    if published:
        row(d, "sash")["disclosures"] = [
            {
                "run_id": r,
                "state": "published",
                "date": "2027-02-01",
                "url": "https://example.org/d",
            }
            for r in sorted(published)
        ]
    return d


def override(d: dict[str, Any], prop: str, *pairs: tuple[str, str]) -> dict[str, Any]:
    c = cell(d, "sash", prop)
    c["stated"], c["state"] = c["state"], "no"
    c["contradicted_by"] = [{"control": k, "run_id": r} for k, r in sorted(pairs)]
    return d


def crit13(r: Release, d: dict[str, Any]) -> list[str]:
    return [f.message for f in found(d, "CRIT-13", r.root)]


def test_accepted_c1_overrides_whole_output(rel: Release) -> None:
    """SASH's Whole output checked is yes; C1 accepted in a read run, its disclosure published:
    the cell passes only as no, stated yes, contradicted by C1 in that run."""
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "accepted")])])
    left = sash_doc(published=(run_id(1),))
    assert crit13(rel, left) == [
        f"C1 in {run_id(1)} contradicts whole_output: the cell must be "
        "no, stated yes, contradicted_by those"
    ]
    assert crit13(rel, override(left, "whole_output", ("C1", run_id(1)))) == []


@pytest.mark.parametrize("cid", ["C3", "P1"])
def test_accepted_c3_overrides_model_bound(rel: Release, cid: str) -> None:
    """On a partly Model bound cell (the SASH cell set partly here)."""
    rel.freeze("v0.1", [rel.run(1, controls=[control(cid, "accepted")])])
    d = sash_doc(published=(run_id(1),))
    cell(d, "sash", "model_bound")["state"] = "partly"
    assert len(crit13(rel, d)) == 1
    d = override(d, "model_bound", (cid, run_id(1)))
    assert cell(d, "sash", "model_bound")["stated"] == "partly"
    assert crit13(rel, d) == []


def test_accepted_p1_overrides_model_bound(rel: Release) -> None:
    test_accepted_c3_overrides_model_bound(rel, "P1")


@pytest.mark.parametrize("cid", ["C1", "C2", "C3", "C4", "C7", "P1", "P2"])
def test_each_mapped_control_overrides_its_property(rel: Release, cid: str) -> None:
    rel.freeze("v0.1", [rel.run(1, controls=[control(cid, "accepted")])])
    prop = CONTROL_PROPERTY[cid]
    assert prop is not None
    d = override(sash_doc(published=(run_id(1),)), prop, (cid, run_id(1)))
    assert crit13(rel, d) == []
    for other in crit.PROPERTIES:
        if other == prop:
            continue
        wrong = copy.deepcopy(d)
        cell(wrong, "sash", other)["contradicted_by"] = [{"control": cid, "run_id": run_id(1)}]
        cell(wrong, "sash", other)["stated"] = "yes"
        assert found(wrong, "CRIT-13", rel.root) or found(wrong, "CRIT-14", rel.root), other


def test_c6_one_trial_accepted_sets_nothing(rel: Release) -> None:
    """C5, C6 and C8 change only proof bytes: no property (OVR-2)."""
    controls = [
        control("C6", "rejected", trials=("rejected", "accepted", "rejected")),
        control("C5", "accepted"),
        control("C8", "accepted"),
    ]
    rel.freeze("v0.1", [rel.run(1, controls=controls)])
    d = sash_doc(published=(run_id(1),))
    assert crit13(rel, d) == []
    bad = override(copy.deepcopy(d), "whole_output", ("C6", run_id(1)))
    assert crit13(rel, bad)
    assert found(bad, "CRIT-14", rel.root)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("rejected", ("rejected",)),
        ("prover_failed", ("rejected", "prover_failed")),
        ("invalid_call", ("rejected", "invalid_call")),
        ("invalid_call", ("rejected",)),
        ("no_verdict", ("rejected",)),
        ("void", ("rejected",)),
        ("not_applicable", ("rejected",)),
        ("error", ("rejected",)),
        ("absent", ("rejected",)),
        ("no_file", ("rejected",)),
    ],
)
def test_non_accepting_outcomes_set_nothing(
    rel: Release, outcome: str, expected: tuple[str, ...]
) -> None:
    controls = (
        None
        if outcome == "no_file"
        else []
        if outcome == "absent"
        else [control("C1", outcome, expected)]
    )
    rel.freeze("v0.1", [rel.run(1, controls=controls, pending=False)])
    d = sash_doc()
    assert crit13(rel, d) == []
    assert crit13(rel, override(d, "whole_output", ("C1", run_id(1)))) == [
        "an override where no read run contradicts it"
    ]


def test_pass_does_not_raise_not_stated(rel: Release) -> None:
    rel.freeze("v0.1", [rel.run(1, controls=[control("C3", "rejected")], pending=False)])
    d = sash_doc()
    cell(d, "sash", "model_bound").update(
        state="not_stated",
        quotes=[],
        sources_read=cell(d, "sash", "weights_hidden")["sources_read"],
    )
    assert crit13(rel, d) == []
    assert found(d, "CRIT-1", rel.root) == []
    cell(d, "sash", "model_bound")["state"] = "yes"
    assert found(d, "CRIT-1", rel.root)[0].message == "a yes cell has no quote"


def test_not_stated_and_no_cells_not_overridden(rel: Release) -> None:
    """Q5: a contradicting outcome changes neither a not_stated nor a stated no cell."""
    rel.freeze("v0.1", [rel.run(1, controls=[control("C3", "accepted")])])
    for state in ("not_stated", "no"):
        d = sash_doc(published=(run_id(1),))
        cell(d, "sash", "model_bound")["state"] = state
        assert crit13(rel, d) == [], state
        c = cell(d, "sash", "model_bound")
        c["stated"], c["contradicted_by"] = state, [{"control": "C3", "run_id": run_id(1)}]
        assert crit13(rel, d) == [f"an override where its stated state is {state}"], state


def test_expected_accepted_sets_nothing(rel: Release) -> None:
    """A `weakened_prover` control expects accepted: an accepted outcome contradicts nothing,
    and a system-specific control maps to no property (Q7)."""
    controls = [
        control("sash-unsound-skip-residual-stream", "accepted", ("accepted",)),
        control("C1", "accepted", ("accepted",)),
    ]
    rel.freeze("v0.1", [rel.run(1, controls=controls, pending=False)])
    assert crit13(rel, sash_doc()) == []


def test_other_configuration_run_ignored(rel: Release) -> None:
    other = rel.run(1, controls=[control("C1", "accepted")], configuration="other")
    rel.freeze("v0.1", [other, rel.run(2, controls=[], pending=False)])
    assert crit13(rel, sash_doc()) == []  # and its pending disclosure needs no entry
    newer = rel.run(3, controls=[control("C1", "accepted")], card_version=2)
    (rel.root / "releases/v0.1/release.yaml").unlink()
    rel.freeze("v0.1", [other, newer])
    d = override(sash_doc(published=(run_id(3),)), "whole_output", ("C1", run_id(3)))
    assert crit13(rel, d) == []


def test_superseded_and_replaced_runs_ignored(rel: Release) -> None:
    bad = rel.run(1, controls=[control("C1", "accepted")])
    fixed = rel.run(2, controls=[control("C1", "rejected")], pending=False, replaces=run_id(1))
    rel.freeze("v0.1", [bad, fixed])
    assert crit13(rel, sash_doc()) == []
    shutil.rmtree(rel.root / "releases")
    rel.freeze("v0.1", [bad, rel.run(3, controls=[], pending=False)], superseded=(run_id(1),))
    assert crit13(rel, sash_doc()) == []


def test_override_carries_to_later_release(rel: Release) -> None:
    """A later rejection does not clear an accepted C1 (INV-CTRL-3)."""
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "accepted")])])
    rel.freeze("v0.2", [rel.run(1, "v0.2", controls=[control("C1", "rejected")], pending=False)])
    d = sash_doc("v0.2", published=(run_id(1),))
    assert len(crit13(rel, d)) == 1
    assert crit13(rel, override(d, "whole_output", ("C1", run_id(1)))) == []


def test_later_release_not_read(rel: Release) -> None:
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "rejected")], pending=False)])
    rel.freeze("v0.2", [rel.run(1, "v0.2", controls=[control("C1", "accepted")])])
    assert crit13(rel, sash_doc("v0.1")) == []


def test_no_release_no_override() -> None:
    d = override(sash_doc(None), "whole_output", ("C1", run_id(1)))
    assert crit13(Release(ROOT), d) == ["an override without a release"]
    d = sash_doc(None, published=(run_id(1),))
    assert crit13(Release(ROOT), d) == ["disclosures without a release"]


def test_disclosure_pending_withholds_override(rel: Release) -> None:
    rel.freeze(
        "v0.1",
        [rel.run(1, controls=[control("C1", "accepted")]), rel.run(2, controls=[], pending=False)],
    )
    d = sash_doc()
    assert any("missing ['" + run_id(1) + "'], extra []" in m for m in crit13(rel, d))
    row(d, "sash")["disclosures"] = [{"run_id": run_id(2), "state": "pending"}]
    assert any("extra ['" + run_id(2) + "']" in m for m in crit13(rel, d))
    row(d, "sash")["disclosures"] = [{"run_id": run_id(1), "state": "pending"}]
    assert crit13(rel, d) == []  # the stated states pass, drawn as none (OVR-8)
    assert crit13(rel, override(copy.deepcopy(d), "whole_output", ("C1", run_id(1)))) == [
        "an override while a disclosure is pending"
    ]
    d = sash_doc(published=(run_id(1),))
    assert len(crit13(rel, d)) == 1
    assert crit13(rel, override(d, "whole_output", ("C1", run_id(1)))) == []


def test_new_pending_disclosure_after_published_withholds(rel: Release) -> None:
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "accepted")])])
    rel.freeze("v0.2", [rel.run(1, "v0.2", controls=[control("C2", "accepted")])])
    d = override(sash_doc("v0.2", published=(run_id(1),)), "whole_output", ("C1", run_id(1)))
    assert any("missing ['" + run_id(1, "v0.2") + "']" in m for m in crit13(rel, d))
    row(d, "sash")["disclosures"].append({"run_id": run_id(1, "v0.2"), "state": "pending"})
    assert crit13(rel, d) == ["an override while a disclosure is pending"]


def test_card_row_without_run_fails(rel: Release) -> None:
    rel.freeze("v0.1", [rel.run(1, controls=[], pending=False)], cards=())
    assert crit13(rel, sash_doc()) == [
        "sash/sound-defaults is not benchmarked in v0.1: no claim_cards entry"
    ]
    shutil.rmtree(rel.root / "releases")
    rel.freeze("v0.1", [])
    assert crit13(rel, sash_doc()) == [
        "sash/sound-defaults is not benchmarked in v0.1: no run is read"
    ]
    assert crit13(rel, sash_doc("v0.2")) == ["no releases/v0.2/release.yaml"]


def test_reply_does_not_change_cell(rel: Release) -> None:
    """OVR-6: a reply is printed, never read by CRIT-13."""
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "accepted")])])
    d = sash_doc(published=(run_id(1),))
    before = crit13(rel, d)
    (rel.root / "systems/sash/replies").mkdir()
    (rel.root / "systems/sash/replies/v0.1.md").write_text("We disagree with C1.\n")
    assert crit13(rel, d) == before
    assert len(before) == 1


def test_missing_controls_file_is_environment_error(rel: Release) -> None:
    listed = rel.run(1, controls=[], pending=False)
    rel.freeze("v0.1", [listed])
    shutil.rmtree(rel.root / listed)
    (f,) = found(sash_doc(), "CRIT-13", rel.root)
    assert f.kind is ErrorKind.ENVIRONMENT
    assert "cannot read" in f.message
    rel.run(1, controls=[], pending=False)
    (rel.root / listed / "controls.json").write_text("{not json")
    (f,) = found(sash_doc(), "CRIT-13", rel.root)
    assert f.kind is ErrorKind.ENVIRONMENT


# ---------------------------------------------------------------- CRIT-14


def test_contradicted_by_on_documentation_only_property_fails() -> None:
    for prop in ("weights_hidden", "formally_verified", "security_level", "no_trusted_party"):
        d = sash_doc(None)
        c = cell(d, "sash", prop)
        c |= {
            "state": "no",
            "stated": "yes",
            "contradicted_by": [{"control": "C1", "run_id": run_id(1)}],
        }
        assert [f.message for f in found(d, "CRIT-14")] == [f"control C1 cannot contradict {prop}"]
    d = override(sash_doc(None), "model_bound", ("C5", run_id(1)))
    assert [f.message for f in found(d, "CRIT-14")] == ["control C5 cannot contradict model_bound"]


def test_stated_without_contradicted_by_fails() -> None:
    d = sash_doc(None)
    cell(d, "sash", "model_bound").update(stated="yes", state="no")
    assert [f.message for f in found(d, "CRIT-14")] == ["stated and contradicted_by come together"]
    d = override(sash_doc(None), "model_bound", ("C3", run_id(2)), ("C3", run_id(1)))
    cell(d, "sash", "model_bound")["contradicted_by"].reverse()
    assert [f.message for f in found(d, "CRIT-14")] == ["contradicted_by is not sorted and unique"]
    d = sash_doc(None)
    row(d, "sash")["disclosures"] = [
        {"run_id": run_id(2), "state": "pending"},
        {"run_id": run_id(1), "state": "published"},
    ]
    assert {f.message for f in found(d, "CRIT-14")} == {
        "disclosures are not sorted by run_id and unique",
        "a published disclosure needs its date and url",
    }


def test_overridden_cell_quotes_decide_stated(rel: Release) -> None:
    """CRIT-1 and CRIT-6 read `stated`, not `state`: an overridden yes keeps its deciding quote,
    and a card that allows only not_stated still fails an overridden stated yes."""
    rel.freeze("v0.1", [rel.run(1, controls=[control("C1", "accepted")])])
    d = override(sash_doc(published=(run_id(1),)), "whole_output", ("C1", run_id(1)))
    assert found(d, "CRIT-1", rel.root) == []
    assert found(d, "CRIT-6", rel.root) == []
    cell(d, "sash", "whole_output")["quotes"] = []
    assert found(d, "CRIT-1", rel.root)[0].message == "a yes cell has no quote"
    path = rel.root / "systems/sash/claim.yaml"
    path.write_text(
        path.read_text().replace(
            'policy:\n    kind: "exact_match"', 'policy:\n    kind: "tolerance"'
        )
    )
    d = override(sash_doc(published=(run_id(1),)), "model_bound", ("C3", run_id(1)))
    assert "the cell states yes" in found(d, "CRIT-6", rel.root)[0].message
