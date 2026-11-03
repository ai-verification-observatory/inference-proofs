import shutil
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind
from iproofs.model import ClaimRef
from iproofs.schema import SchemaRegistry
from iproofs.validate import check_claim, check_run_claim

ROOT = Path(__file__).resolve().parents[3]
COMMIT = "0123456789abcdef0123456789abcdef01234567"
DOC = f"https://github.com/ai-verification-observatory/inference-proofs/blob/{COMMIT}/README.md"
CARD = f'''schema: "claim/1"
system: "fake"
configuration: "default"
card_version: 2
upstream: {{repo: "ai-verification-observatory/inference-proofs", commit: "{COMMIT}"}}
claim_class: "next-token/exact-match/committed-weights"
relation: "The tag binds the request, the output and the committed toy weights."
security:
  notion: {{kind: "not_stated", verifier: "not stated"}}
  level: "not stated"
  model: {{assumption: "not stated", adversary: "not_stated"}}
  setup: "not_stated"
zero_knowledge:
  claimed: false
  hidden: "not stated"
  not_hidden: "not stated"
  status: "neither"
assumptions: []
assumptions_not_stated: true
coverage:
  phase: "prefill"
  unit: "request"
  tokens_covered: "the window's positions"
  operations: "not stated"
  policy: {{kind: "exact_match", detail: "keyed hash equality"}}
binding: "not stated"
residual: ["not stated"]
availability: "available"
sources:
  relation: "{DOC}"
  zero_knowledge: "{DOC}"
  coverage: "{DOC}"
  availability: "{DOC}"
reviewed_by: []
'''


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_tree(ROOT / "schema")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    system = tmp_path / "systems/fake"
    system.mkdir(parents=True)
    shutil.copy(ROOT / "schema/system/examples/valid/fake.yaml", system / "system.yaml")
    (system / "claim.yaml").write_text(CARD)
    return tmp_path


def findings(tree: Path, registry: SchemaRegistry, old: str = "", new: str = "") -> list[str]:
    card = tree / "systems/fake/claim.yaml"
    if old:
        text = card.read_text()
        assert old in text
        card.write_text(text.replace(old, new))
    return [f.line() for f in check_claim(card, tree, registry)]


def test_valid_card_passes(tree: Path, registry: SchemaRegistry) -> None:
    assert findings(tree, registry) == []


def test_sources_complete(tree: Path, registry: SchemaRegistry) -> None:
    lines = findings(tree, registry, f'  coverage: "{DOC}"\n', "")
    assert lines == [
        "G2 systems/fake/claim.yaml#/coverage INV-CLAIM-3: coverage has no entry in sources "
        "(fix: link the upstream documentation at the pinned commit)"
    ]


def test_not_stated_fields_need_no_source(tree: Path, registry: SchemaRegistry) -> None:
    # security, binding, residual and assumptions are all "not stated" in CARD
    assert findings(tree, registry) == []


def test_source_commit_mismatch(tree: Path, registry: SchemaRegistry) -> None:
    other = DOC.replace(COMMIT, "f" * 40)
    lines = findings(tree, registry, f'  relation: "{DOC}"', f'  relation: "{other}"')
    assert lines == [f"G2 systems/fake/claim.yaml#/sources/relation INV-CLAIM-3: source "
                     f"'{other}' is not at {COMMIT}"]  # fmt: skip


def test_upstream_pin_must_match_system(tree: Path, registry: SchemaRegistry) -> None:
    lines = findings(tree, registry, f'commit: "{COMMIT}"}}', f'commit: "{"e" * 40}"}}')
    assert any("CLAIM-PIN" in line for line in lines)


def test_forbidden_flags_subset(tree: Path, registry: SchemaRegistry) -> None:
    lines = findings(tree, registry, "reviewed_by: []\n",
                     'reviewed_by: []\nforbidden_flags: ["--weaken"]\n')  # fmt: skip
    assert any("INV-CLAIM-4" in line and "--weaken" in line for line in lines)


def test_card_without_system_file_is_config(tree: Path, registry: SchemaRegistry) -> None:
    (tree / "systems/fake/system.yaml").unlink()
    found = check_claim(tree / "systems/fake/claim.yaml", tree, registry)
    assert [f.kind for f in found] == [ErrorKind.CONFIG]
    assert found[0].rule == "CLAIM-SYSTEM"


def test_schema_error_reported_as_finding(tree: Path, registry: SchemaRegistry) -> None:
    lines = findings(tree, registry, 'availability: "available"', 'availability: "maybe"')
    assert lines[0].startswith("G2 systems/fake/claim.yaml SCHEMA:")


def test_run_card_resolution(tree: Path, registry: SchemaRegistry) -> None:
    ok = ClaimRef(system="fake", configuration="default", card_version=1)  # older version is fine
    assert check_run_claim(ok, tree, registry, "results/x/manifest.json") == []
    newer = ClaimRef(system="fake", configuration="default", card_version=3)
    assert "newer than the card's 2" in check_run_claim(newer, tree, registry, "m")[0].message
    other = ClaimRef(system="fake", configuration="other", card_version=1)  # the single claim.yaml
    assert check_run_claim(other, tree, registry, "m")[0].message == (
        "card configuration is 'default'"
    )
    missing = ClaimRef(system="other", configuration="default", card_version=1)
    assert check_run_claim(missing, tree, registry, "m")[0].rule == "CLAIM-REF"


def test_not_a_claim_card(tree: Path, registry: SchemaRegistry) -> None:
    found = check_claim(tree / "systems/fake/system.yaml", tree, registry)
    assert [(f.rule, f.message) for f in found] == [("SCHEMA", "not a claim card")]


def test_binding_edges_and_formal_relation_pinned(tree: Path, registry: SchemaRegistry) -> None:
    other = DOC.replace(COMMIT, "f" * 40)
    edge = f'{{edge: "weights to commitment", state: "bound", switch: null, source: "{other}"}}'
    findings(tree, registry, 'binding: "not stated"\n',
             f'binding: {{edges: [{edge}]}}\nrelation_formal: "{other}"\n')  # fmt: skip
    lines = findings(tree, registry, "sources:\n",
                     f'sources:\n  binding: "{DOC}"\n  relation_formal: "{DOC}"\n')  # fmt: skip
    assert [line.split()[1] for line in lines] == [
        "systems/fake/claim.yaml#/binding/edges/0/source",
        "systems/fake/claim.yaml#/relation_formal",
    ]
