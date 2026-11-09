import shutil
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry
from iproofs.workloads import (
    asserted_inputs,
    load_workload,
    reference_role,
    serving_system,
    weight_bits,
    workload_digest,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "schema/workload/examples/valid/fake-tiny-ci.yaml"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_tree(ROOT / "schema")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "workloads").mkdir()
    shutil.copy(EXAMPLE, tmp_path / "workloads/fake-tiny-ci.yaml")
    for system in ("fake", "fake-broken"):
        (tmp_path / "systems" / system).mkdir(parents=True)
        (tmp_path / "systems" / system / "system.yaml").write_text("schema: system/1\n")
    return tmp_path


def edit(tree: Path, old: str, new: str) -> None:
    p = tree / "workloads/fake-tiny-ci.yaml"
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new))


def config_error(tree: Path, registry: SchemaRegistry, **kw: int) -> str:
    with pytest.raises(IProofsError) as e:
        load_workload("fake-tiny-ci", root=tree, registry=registry, **kw)
    assert e.value.kind is ErrorKind.CONFIG
    return e.value.message


def test_valid_workload_loads(tree: Path, registry: SchemaRegistry) -> None:
    wl = load_workload("fake-tiny-ci", 1, root=tree, registry=registry)
    assert wl.shape.batch_size == 2
    assert workload_digest(tree, "fake-tiny-ci") == file_digest(
        tree / "workloads/fake-tiny-ci.yaml"
    )


def test_inv_wl4(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, "count: 6", "count: 5")
    assert "INV-WL-4: prompts.count 5 != shape.batch_size 2" in config_error(tree, registry)


def test_inv_wl4_length_rule(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, "length_rule: {prompt_tokens: 8}", "length_rule: {prompt_tokens: 9}")
    assert "prompts.length_rule.prompt_tokens 9 != shape.prompt_tokens 8" in config_error(
        tree, registry
    )


def test_context_window_check(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, "context_window: 8", "context_window: 7")
    assert "shape.context_window 7 < prompt_tokens + output_tokens - 1 = 8" in config_error(
        tree, registry
    )


def test_tokenizer_file_listed(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, 'tokenizer_file: "tokenizer.json"', 'tokenizer_file: "vocab.txt"')
    assert "model.tokenizer_file 'vocab.txt' is not in model.files" in config_error(tree, registry)


TOKENIZER_SOURCE = (
    '  tokenizer_source: {hub: "huggingface", repo: "org/tok", revision: "'
    + "0" * 40
    + '", file: {path: "tok.json", sha256: "'
    + "a" * 64
    + '", bytes: 3}}\n'
)


def test_tokenizer_from_second_source(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003: the tokenizer file may come from a second pinned repository; then
    tokenizer_file names that file and need not be among the weights' files."""
    edit(
        tree,
        'tokenizer_file: "tokenizer.json"\n',
        'tokenizer_file: "tok.json"\n' + TOKENIZER_SOURCE,
    )
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert wl.model.tokenizer_source is not None
    assert (wl.model.tokenizer_source.repo, wl.model.tokenizer_source.file.bytes) == ("org/tok", 3)


def test_tokenizer_file_names_second_source(tree: Path, registry: SchemaRegistry) -> None:
    edit(
        tree,
        'tokenizer_file: "tokenizer.json"\n',
        'tokenizer_file: "tokenizer.json"\n' + TOKENIZER_SOURCE,
    )
    message = config_error(tree, registry)
    assert "'tokenizer.json' is not model.tokenizer_source.file.path 'tok.json'" in message


def test_unknown_system_in_workload(tree: Path, registry: SchemaRegistry) -> None:
    shutil.rmtree(tree / "systems/fake-broken")
    assert "'fake-broken' has no systems/fake-broken/system.yaml" in config_error(tree, registry)


def reference(tree: Path, name: str, role: str) -> None:
    (tree / "systems" / name).mkdir(parents=True)
    (tree / "systems" / name / "system.yaml").write_text(
        f"schema: system/1\nkind: reference\nreference_role: {role}\n"
    )


def test_srv7_two_plain_serving_systems(tree: Path, registry: SchemaRegistry) -> None:
    """TC-SRV-7: a workload naming two systems with reference_role serve fails config at load;
    one serve and one recompute system load, and the one serve system is the one joined."""
    for name, role in (("ref-a", "serve"), ("ref-b", "serve"), ("ref-c", "recompute")):
        reference(tree, name, role)
    edit(tree, 'systems: ["fake", "fake-broken"]', 'systems: ["fake", "ref-a", "ref-b"]')
    message = config_error(tree, registry)
    assert "SRV-7: systems names 2 production-serving systems ['ref-a', 'ref-b']" in message
    edit(tree, 'systems: ["fake", "ref-a", "ref-b"]', 'systems: ["fake", "ref-c", "ref-b"]')
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert serving_system(tree, wl.systems) == "ref-b"
    assert reference_role(tree, "fake") is None  # not a reference system
    assert reference_role(tree, "gone") is None  # no system.yaml


def test_srv7_none_named(tree: Path, registry: SchemaRegistry) -> None:
    """A CI workload names no production-serving system and loads; nothing is joined."""
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert serving_system(tree, wl.systems) is None


def test_srv7_repository_workloads(registry: SchemaRegistry) -> None:
    """Each native workload names one production-serving system, ref-serve (RFC-0015 SRV-7)."""
    named = {}
    for path in sorted((ROOT / "workloads").glob("*.yaml")):
        wl = load_workload(path.stem, root=ROOT, registry=registry)
        named[wl.id] = serving_system(ROOT, wl.systems)
    assert named["fp-maverick-w1024-b1"] == named["fp-maverick-w1024-b24"] == "ref-serve"
    assert named["sash-l31-8b-c1024"] == named["sash-l31-8b-c4096"] == "ref-serve"
    assert named["fake-tiny-ci"] is None


def test_version_mismatch(tree: Path, registry: SchemaRegistry) -> None:
    assert "version 1 != requested version 2" in config_error(tree, registry, version=2)


def test_unknown_workload(tree: Path, registry: SchemaRegistry) -> None:
    with pytest.raises(IProofsError, match="unknown workload 'nope'"):
        load_workload("nope", root=tree, registry=registry)


def test_schema_violation_is_config_error(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, 'rule: "greedy"', 'rule: "sampled"')
    assert "/decoding/rule" in config_error(tree, registry)


STATED = (
    'precision: {served: "int8", proved: "int8", alternatives: ["int4"], weight_bits: {bits: 8,'
    ' basis: "stated", covers: "part", source: "https://example.org/fake-tiny"}}'
)
PRECISION = 'precision: {served: "int8", proved: "int8", alternatives: ["int4"]}'


def file_size(files: str = '["weights.bin"]', bits: str = "") -> str:
    return (
        'precision: {served: "int8", proved: "int8", alternatives: ["int4"], weight_bits: {'
        f'{bits}basis: "file_size", covers: "all", source: "https://example.org/fake-tiny",'
        f" files: {files}}}}}"
    )


def test_weight_bits_stated(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003 WB-1: a stated width loads as written, with its basis, coverage and source."""
    edit(tree, PRECISION, STATED)
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    wb = wl.precision.weight_bits
    assert wb is not None
    assert (wb.bits, wb.basis, wb.covers, wb.files) == (8, "stated", "part", None)
    assert weight_bits(wl) == 8


def test_weight_bits_absent(tree: Path, registry: SchemaRegistry) -> None:
    """No weight bits is valid: D-SPAB-S is then null with `missing_input` (RFC-0004)."""
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert wl.precision.weight_bits is None
    assert weight_bits(wl) is None
    assert asserted_inputs(wl)["weight_bits"]["null_reason"] == "missing_input"


def test_weight_bits_file_size(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003 WB-2, hand-computed: weights.bin is 64 B over 16 parameters, so the loader
    computes 64 x 8 / 16 = 32; the record does not type it."""
    edit(tree, PRECISION, file_size())
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert wl.precision.weight_bits is not None
    assert wl.precision.weight_bits.bits == 32
    assert weight_bits(wl) == 32


def test_weight_bits_file_size_typed(tree: Path, registry: SchemaRegistry) -> None:
    """WB-2 and AGENTS.md rule 3: a file_size width is computed, so typing it is an error."""
    edit(tree, PRECISION, file_size(bits="bits: 32, "))
    assert "/precision/weight_bits" in config_error(tree, registry)


def test_weight_bits_file_size_unknown_file(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, PRECISION, file_size('["weights.bin", "other.bin"]'))
    assert "precision.weight_bits.files ['other.bin'] are not in model.files" in config_error(
        tree, registry
    )


COMPUTED = (
    'precision: {served: "int8", proved: "int8", alternatives: ["int4"], weight_bits: {bits: 5.5,'
    ' basis: "computed", covers: "all", method: "gguf-active-mean/1",'
    ' source: "https://example.org/fake-tiny", files: FILES}}'
)


def test_weight_bits_computed(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003 WB-5: a computed width loads as typed; fetch-model, not the loader, reruns
    its method, because the files are not in the repository."""
    edit(tree, PRECISION, COMPUTED.replace("FILES", '["weights.bin"]'))
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    wb = wl.precision.weight_bits
    assert wb is not None
    assert (wb.bits, wb.basis, wb.covers, wb.method) == (
        5.5,
        "computed",
        "all",
        "gguf-active-mean/1",
    )
    assert weight_bits(wl) == 5.5
    assert asserted_inputs(wl)["weight_bits"]["value"] == 5.5


def test_weight_bits_computed_unknown_file(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, PRECISION, COMPUTED.replace("FILES", '["other.gguf"]'))
    assert "precision.weight_bits.files ['other.gguf'] are not in model.files" in config_error(
        tree, registry
    )


def test_asserted_inputs(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003 WB-4: the inputs the runner copies into run.json are labelled asserted
    quantities that point at the workload record they were copied from."""
    edit(tree, PRECISION, STATED)
    inputs = asserted_inputs(load_workload("fake-tiny-ci", root=tree, registry=registry))
    params, bits = inputs["active_parameters_per_token"], inputs["weight_bits"]
    assert (params["value"], params["unit"], params["grade"]) == (16, "count", "asserted")
    assert (bits["value"], bits["unit"], bits["null_reason"]) == (8, "bit/weight", None)
    assert bits["source"] == {
        "kind": "reference_file",
        "ref": "workloads/fake-tiny-ci.yaml#/precision/weight_bits",
    }
    for q in inputs.values():
        assert registry.errors("quantity/1", q, def_name="quantity") == []


def test_weight_bits_file_size_needs_files(tree: Path, registry: SchemaRegistry) -> None:
    edit(tree, PRECISION, file_size().replace(', files: ["weights.bin"]', ""))
    assert "/precision/weight_bits" in config_error(tree, registry)


def test_closed_workload_loads(registry: SchemaRegistry) -> None:
    """#334: the shared Llama 3.1 8B workload is closed, fixes one claim class, and pins the
    model of sash-l31-8b-c1024 (same repository, revision, files and digest) at its shape and
    precision (RFC-0003 §Closed workloads)."""
    closed = load_workload("l31-8b-c1024", 1, root=ROOT, registry=registry)
    native = load_workload("sash-l31-8b-c1024", 1, root=ROOT, registry=registry)
    assert (closed.division, native.division) == ("closed", "native")
    assert closed.claim_class == "greedy-continuation/exact-match/committed-weights"
    assert closed.model == native.model
    assert closed.model.digest == native.model.digest
    assert (closed.shape, closed.precision, closed.prompts) == (
        native.shape,
        native.precision,
        native.prompts,
    )
    assert (closed.decoding, closed.phase) == (native.decoding, native.phase)
    assert closed.systems == ("sash", "ref-serve", "ref-recompute")


def test_closed_workload_needs_class(tree: Path, registry: SchemaRegistry) -> None:
    """RFC-0003 §Workload file: `claim_class` is required exactly when the division is closed."""
    edit(tree, 'division: "open"', 'division: "closed"')
    assert "claim_class" in config_error(tree, registry)
    edit(tree, 'division: "closed"', 'division: "closed"\nclaim_class: "other/other/other"')
    wl = load_workload("fake-tiny-ci", root=tree, registry=registry)
    assert (wl.division, wl.claim_class) == ("closed", "other/other/other")
