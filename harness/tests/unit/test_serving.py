"""Production-serving records (RFC-0015 SRV-6; RFC-0014 SM-1 to SM-3), on fixtures only: no
network, no GPU. The two pinned records are checked as stored."""

import copy
import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import ServingModel, Workload, load
from iproofs.schema import SchemaRegistry
from iproofs.serving import (
    check_files,
    check_mirror,
    ensure_serving_model,
    git_blob_id,
    lfs_pointer_blob,
    listing_digest,
    load_records,
    mapping_problems,
    pin_files,
    pin_record,
    record_for,
    serving_manifest,
    shape_of,
    sm1_problems,
)
from iproofs.validate.precision import serve_entry_problems

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
MAVERICK = "llama-4-maverick-17b-128e-instruct-fp8"
LLAMA = "llama-3.1-8b-instruct-bf16"


def record(name: str) -> ServingModel:
    doc = load(ROOT / f"workloads/serving/{name}.yaml", REGISTRY)
    assert isinstance(doc, ServingModel)
    return doc


def workload(wid: str) -> Workload:
    doc = load(ROOT / f"workloads/{wid}.yaml", REGISTRY)
    assert isinstance(doc, Workload)
    return doc


def test_git_blob_id_matches_git() -> None:
    """`git hash-object` of "hello\\n" is ce01362503..."""
    assert git_blob_id(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_sm1_lfs_pointer_fixture() -> None:
    """SM-1 on a fixture pointer: the pointer text of a 3-byte file, hashed as git does."""
    sha = hashlib.sha256(b"abc").hexdigest()
    pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{sha}\nsize 3\n"
    assert lfs_pointer_blob(sha, 3) == git_blob_id(pointer.encode())


@pytest.mark.parametrize("name", [MAVERICK, LLAMA])
def test_pinned_records_hold_sm1(name: str) -> None:
    """Every LFS file's pointer blob is the publisher's, and the digest is the files'."""
    assert sm1_problems(record(name)) == []


def test_pinned_record_facts() -> None:
    """The pinned sets (Hub listings of 2026-11-09, external): 90 files of 416,785,753,788 B for
    Maverick FP8 and 9 files of 16,069,667,318 B for Llama 3.1 8B BF16, plus Meta's own
    tokenizer_config.json of 55,351 B (RFC-0015 Q7, added 2026-11-11), summed here from the
    records, not typed into them."""
    mav, l31 = record(MAVERICK), record(LLAMA)
    assert (len(mav.model.files), sum(f.bytes for f in mav.model.files)) == (90, 416785753788)
    assert (len(l31.model.files), sum(f.bytes for f in l31.model.files)) == (10, 16069722669)
    # the prompts are token ids of the workloads' own vocabulary and tokenizer
    tok = next(f for f in mav.model.files if f.path == "tokenizer.json")
    source = workload("fp-maverick-w1024-b24").model.tokenizer_source
    assert source is not None
    assert tok.sha256 == source.file.sha256
    sash = {f.sha256 for f in workload("sash-l31-8b-c1024").model.files if "safetensors" in f.path}
    assert sash <= {f.sha256 for f in l31.model.files}
    assert (mav.model.shape.kv_dtype, mav.model.shape.layers, mav.model.shape.kv_heads) == (
        "bfloat16", 48, 8)  # fmt: skip


def test_sm1_refuses_a_changed_sha() -> None:
    rec = record(LLAMA)
    f = next(f for f in rec.model.files if f.storage == "lfs")
    bad = dataclasses.replace(f, sha256="0" * 64)
    files = tuple(bad if g is f else g for g in rec.model.files)
    changed = dataclasses.replace(rec, model=dataclasses.replace(rec.model, files=files))
    problems = sm1_problems(changed)
    assert any(p.startswith(f"SM-1: {f.path}") for p in problems)
    assert any("model.digest" in p for p in problems)  # the digest no longer matches


def test_mapping() -> None:
    """SRV-6: the stored records map every serve-role workload once, and each refusal."""
    records = load_records(ROOT, REGISTRY)
    wls = {p.stem: workload(p.stem) for p in (ROOT / "workloads").glob("*.yaml")}
    assert mapping_problems(records, wls, ["ref-serve"]) == []
    assert record_for(ROOT, REGISTRY, "fp-maverick-w1024-b1") == records[MAVERICK]
    assert record_for(ROOT, REGISTRY, "fake-tiny-ci") is None
    twice = {**records, "copy": dataclasses.replace(records[LLAMA], id="copy")}
    assert any(
        "named by 2 serving records" in p for p in mapping_problems(twice, wls, ["ref-serve"])
    )
    unnamed = {MAVERICK: records[MAVERICK]}
    assert any(p.startswith("workload sash-l31-8b-c1024 names a serve-role system and no")
               for p in mapping_problems(unnamed, wls, ["ref-serve"]))  # fmt: skip
    vocab = dataclasses.replace(records[MAVERICK], model=dataclasses.replace(
        records[MAVERICK].model, vocab_size=1))  # fmt: skip
    assert any("vocab_size 1 differs" in p for p in mapping_problems({MAVERICK: vocab}, wls, []))
    gone = dataclasses.replace(records[LLAMA], workloads=("nope",))
    assert any("has no workloads/nope.yaml" in p for p in mapping_problems({LLAMA: gone}, wls, []))


def test_serving_manifest_keys() -> None:
    doc = serving_manifest(record(MAVERICK))
    assert doc["digest"] == record(MAVERICK).model.digest
    assert doc["publisher"] == {"repo": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
                                "revision": "94125d2bd83076b21eed33119525e29eaf3894f4"}  # fmt: skip


def tiny(tmp_path: Path) -> tuple[ServingModel, dict[str, bytes]]:
    """A two-file record over fixture bytes: one git file and one LFS file."""
    data = {"config.json": b'{"torch_dtype": "bfloat16"}\n', "w.safetensors": b"\x00" * 16}
    files = []
    for path, body in data.items():
        sha = hashlib.sha256(body).hexdigest()
        lfs = path.endswith(".safetensors")
        files.append({"path": path, "sha256": sha, "bytes": len(body),
                      "storage": "lfs" if lfs else "git",
                      "publisher_blob": lfs_pointer_blob(sha, len(body)) if lfs
                      else git_blob_id(body)})  # fmt: skip
    doc = yaml.safe_load((ROOT / f"workloads/serving/{LLAMA}.yaml").read_text())
    doc["model"]["files"] = files
    doc["model"]["digest"] = listing_digest((str(f["path"]), str(f["sha256"])) for f in files)
    out = tmp_path / "tiny.yaml"
    out.write_text(yaml.safe_dump(doc))
    rec = load(out, REGISTRY)
    assert isinstance(rec, ServingModel)
    return rec, data


def test_sm2_fetch_and_rehash(tmp_path: Path) -> None:
    """SM-2: the fetched files are checked, made read-only and rehashed when present; a git
    file with the right sha256 but another blob id cannot exist, so a changed byte is caught
    by the sha256 first."""
    rec, data = tiny(tmp_path)
    calls = []

    def download(repo: str, rev: str, files: list[str], into: Path, token: str | None) -> None:
        calls.append((repo, files, token))
        for f in files:
            (into / f).write_bytes(data[f])

    out = ensure_serving_model(rec, tmp_path / "cache", download=download, token="t")
    assert sorted(p.name for p in out.iterdir()) == sorted(data)
    assert calls == [(rec.model.source.repo, list(data), None)]  # no token for the mirror
    assert ensure_serving_model(rec, tmp_path / "cache", download=download) == out
    assert len(calls) == 1
    for p in out.iterdir():
        p.chmod(0o644)
    (out / "config.json").write_bytes(b"{}\n")
    with pytest.raises(IProofsError) as e:
        check_files(rec, out)
    assert e.value.kind is ErrorKind.CONFIG
    assert "config.json is not the record's (SM-2)" in e.value.message


def test_sm2_extra_and_publisher_files(tmp_path: Path) -> None:
    rec, data = tiny(tmp_path)
    pub = dataclasses.replace(rec.model.files[0], source="publisher")
    rec = dataclasses.replace(rec, model=dataclasses.replace(
        rec.model, files=(pub, rec.model.files[1])))  # fmt: skip
    calls = []

    def download(repo: str, rev: str, files: list[str], into: Path, token: str | None) -> None:
        calls.append((repo, files, token))
        for f in files:
            (into / f).write_bytes(data[f])
        (into / "extra.txt").write_text("x")

    with pytest.raises(IProofsError, match=r"unexpected \['extra.txt'\]"):
        ensure_serving_model(rec, tmp_path / "cache", download=download, token="t")
    assert calls[1] == (rec.publisher.release.repo, ["config.json"], "t")  # the token, here only
    assert not list((tmp_path / "cache" / "models").iterdir())  # nothing half-written is kept


def hub(entries: dict[str, list[dict[str, object]]], files: dict[str, bytes]):  # type: ignore[no-untyped-def]
    def get(url: str) -> bytes:
        for repo, listing in entries.items():
            if f"/api/models/{repo}/tree/" in url:
                return json.dumps(listing).encode()
        for name, body in files.items():
            if url.endswith("/" + name):
                return body
        raise AssertionError(url)

    return get


def test_sm3_and_pin(tmp_path: Path) -> None:
    """SM-3 and `serving pin` over fixture tree listings: equal blob ids pass and pin; a mirror
    file whose blob id differs from the publisher's is refused by both."""
    rec, data = tiny(tmp_path)
    listing: list[dict[str, object]] = [{"type": "file", "path": f.path, "oid": f.publisher_blob,
                **({"lfs": {"oid": f.sha256, "size": f.bytes}} if f.storage == "lfs" else {})}
               for f in rec.model.files]  # fmt: skip
    entries = {rec.model.source.repo: listing, rec.publisher.release.repo: listing}
    get = hub(entries, data)
    assert check_mirror(rec, get) == []
    pinned = pin_files(rec.model.source.repo, rec.model.revision, rec.publisher.release.repo,
                       rec.publisher.release.revision, ["*"], get)  # fmt: skip
    assert pinned == [{"path": f.path, "sha256": f.sha256, "bytes": f.bytes,
                       "storage": f.storage, "publisher_blob": f.publisher_blob}
                      for f in rec.model.files]  # fmt: skip
    other = [{**e, "oid": "f" * 40} if e["path"] == "config.json" else e for e in listing]
    bad = hub({rec.model.source.repo: listing, rec.publisher.release.repo: other}, data)
    assert check_mirror(rec, bad)[0].startswith("SM-3: config.json")
    with pytest.raises(IProofsError, match=r"config\.json: the mirror's bytes are not"):
        pin_files(rec.model.source.repo, rec.model.revision, rec.publisher.release.repo,
                  rec.publisher.release.revision, ["*"], bad)  # fmt: skip
    with pytest.raises(IProofsError, match="no mirror file matches"):
        pin_files(rec.model.source.repo, rec.model.revision, rec.publisher.release.repo,
                  rec.publisher.release.revision, ["*.gguf"], get)  # fmt: skip


def test_pin_record_rewrites_the_model_block(tmp_path: Path) -> None:
    rec, data = tiny(tmp_path)
    listing: list[dict[str, object]] = [{"type": "file", "path": f.path, "oid": f.publisher_blob,
                **({"lfs": {"oid": f.sha256, "size": f.bytes}} if f.storage == "lfs" else {})}
               for f in rec.model.files]  # fmt: skip
    config = {"num_hidden_layers": 2, "num_attention_heads": 4, "num_key_value_heads": 2,
              "hidden_size": 64, "vocab_size": 128256, "torch_dtype": "bfloat16"}  # fmt: skip
    files = {**data, "config.json": json.dumps(config).encode()}
    listing[0]["oid"] = git_blob_id(files["config.json"])
    get = hub({rec.model.source.repo: listing, rec.publisher.release.repo: listing}, files)
    text = (ROOT / f"workloads/serving/{LLAMA}.yaml").read_text()
    out = pin_record(text, yaml.safe_load(text), ["*"], get)
    assert out.startswith(text[: text.index("\nmodel:\n")])
    path = tmp_path / f"{LLAMA}.yaml"
    path.write_text(out)
    pinned = load(path, REGISTRY)
    assert isinstance(pinned, ServingModel)
    assert sm1_problems(pinned) == []
    assert pinned.model.shape.head_dim == 16  # hidden 64 over 4 heads
    assert pinned.model.vocab_size == 128256


def test_shape_kv_dtype_follows_the_cache_scheme() -> None:
    config = {"text_config": {"num_hidden_layers": 48, "num_attention_heads": 40,
                              "num_key_value_heads": 8, "head_dim": 128, "vocab_size": 9,
                              "torch_dtype": "bfloat16"},
              "quantization_config": {"kv_cache_scheme": None}}  # fmt: skip
    assert shape_of(config)["kv_dtype"] == "bfloat16"
    config["quantization_config"] = {"kv_cache_scheme": {"num_bits": 8, "type": "float"}}
    assert shape_of(config)["kv_dtype"] == "fp8"


def test_serve_entry_rules() -> None:
    """SRV-3: the allowlist as pairs, TP = GPUs, max model length = prompt + output, and the
    batch at matched load only."""
    system = load(ROOT / "systems/ref-serve/system.yaml", REGISTRY)
    entries = [w for w in system.workloads if not isinstance(w, str)]  # type: ignore[attr-defined]
    for entry in entries:
        assert serve_entry_problems(entry, workload(entry.id)) == []
    matched = next(
        e for e in entries if e.id == "fp-maverick-w1024-b24" and e.load_point == "matched"
    )
    wl = workload(matched.id)
    wrong_tp = dataclasses.replace(matched, gpus=8)
    assert "differ from" in serve_entry_problems(wrong_tp, wl)[0]
    odd = dataclasses.replace(matched, engine_args=("--tensor-parallel-size",))
    assert "not flag and value pairs" in serve_entry_problems(odd, wl)[0]
    high = next(e for e in entries if e.id == matched.id and e.load_point == "high")
    assert "names its batch_size" in serve_entry_problems(
        dataclasses.replace(high, batch_size=None), wl)[0]  # fmt: skip
    with_seqs = dataclasses.replace(high, engine_args=(*high.engine_args, "--max-num-seqs", "24"))
    assert "differ from" in serve_entry_problems(with_seqs, wl)[0]


def test_records_validate_in_the_tree(tmp_path: Path) -> None:
    """G2 runs SM-1 and the mapping; a record whose file blob is edited fails SM-1."""
    from iproofs.validate import precision  # noqa: PLC0415

    tree = tmp_path / "tree"
    for part in ("schema", "workloads", "systems"):
        shutil.copytree(ROOT / part, tree / part)
    assert precision.check(tree, ["workloads/x.yaml"], REGISTRY) == []
    path = tree / f"workloads/serving/{LLAMA}.yaml"
    text = path.read_text()
    blob = record(LLAMA).model.files[2].publisher_blob
    path.write_text(text.replace(blob, "0" * 40))
    found = precision.check(tree, ["workloads/x.yaml"], REGISTRY)
    assert [f.rule for f in found] == ["SM-1"]


def test_serve_entry_load_point_fields() -> None:
    system = load(ROOT / "systems/ref-serve/system.yaml", REGISTRY)
    entries = [w for w in system.workloads if not isinstance(w, str)]  # type: ignore[attr-defined]
    matched = next(e for e in entries if e.load_point == "matched")
    high = next(e for e in entries if e.load_point == "high")
    wl = workload(matched.id)
    assert "runs the workload's batch size" in serve_entry_problems(
        dataclasses.replace(matched, batch_size=1024), wl)[0]  # fmt: skip
    assert "max(batches_per_session, 2)" in serve_entry_problems(
        dataclasses.replace(high, batches_per_session_run=9), wl)[0]  # fmt: skip


def copied_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    for part in ("schema", "workloads", "systems"):
        shutil.copytree(ROOT / part, tree / part)
    return tree


def test_serving_tree_refusals(tmp_path: Path) -> None:
    """G2 over the serving records and the serve-role system: a duplicate entry, a precision
    other than the record's, unloadable workload and system files (left to G2 SCHEMA), and an
    unloadable record."""
    from iproofs.validate import precision  # noqa: PLC0415

    tree = copied_tree(tmp_path)
    path = tree / "systems/ref-serve/system.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["workloads"].append(copy.deepcopy(doc["workloads"][0]))  # no YAML anchor
    doc["workloads"][1]["precision_used"] = "FP8"
    doc["workloads"].append({**copy.deepcopy(doc["workloads"][0]), "id": "gone-workload"})
    path.write_text(yaml.safe_dump(doc))
    record = tree / f"workloads/serving/{LLAMA}.yaml"
    record.write_text(record.read_text().replace(', "l31-8b-c1024"', ""))
    (tree / "workloads/broken.yaml").write_text("schema: workload/1\n")
    (tree / "systems/broken").mkdir()
    (tree / "systems/broken/system.yaml").write_text("schema: system/1\n")
    found = {
        (f.rule, f.message.split(":")[0]) for f in precision.check(tree, ["systems/x"], REGISTRY)
    }
    assert ("SRV-6", "('sash-l31-8b-c4096', 'matched', 1) is listed twice") in found
    assert ("SRV-6", "sash-l31-8b-c4096") in found  # precision_used FP8, the record's BF16
    assert (
        "SRV-6",
        "workload l31-8b-c1024 names a serve-role system and no serving record",
    ) in found
    (tree / f"workloads/serving/{LLAMA}.yaml").write_text("schema: serving-model/1\n")
    [refused] = precision.check(tree, ["workloads/x.yaml"], REGISTRY)
    assert (refused.rule, refused.message.split(":")[0]) == ("SRV-6", "serving records do not load")


def test_stored_plain_serving_rows_pass_pm() -> None:
    """The PM rules skip a serve-role system (SRV-6), and a stored plain-serving run whose
    system.yaml no longer declares a substitution is not checked for the flags (SRV-10)."""
    from iproofs.validate import precision  # noqa: PLC0415

    run = next((ROOT / "results/v0.1/ref-serve").glob("*sash-l31-8b-c1024*/run.json"))
    files = ["systems/ref-serve/system.yaml", run.relative_to(ROOT).as_posix()]
    assert precision.check(ROOT, files, REGISTRY) == []


def test_fetch_no_weights(tmp_path: Path) -> None:
    """`fetch-model --serving R --no-weights DIR`: every file but the .safetensors, each
    checked as SM-2 checks it; the publisher's files with the token only; another byte or a
    git file with another blob id is `config`."""
    from iproofs.serving import fetch_no_weights  # noqa: PLC0415

    rec, data = tiny(tmp_path)
    calls = []

    def download(repo: str, rev: str, files: list[str], into: Path, token: str | None) -> None:
        calls.append((repo, files, token))
        for f in files:
            (into / f).write_bytes(data[f])

    assert fetch_no_weights(rec, tmp_path / "d", download=download, token="t") == ["config.json"]
    assert calls == [(rec.model.source.repo, ["config.json"], None)]
    assert not (tmp_path / "d/w.safetensors").exists()
    pub = dataclasses.replace(rec.model.files[0], source="publisher")
    moved = dataclasses.replace(rec, model=dataclasses.replace(
        rec.model, files=(pub, rec.model.files[1])))  # fmt: skip
    fetch_no_weights(moved, tmp_path / "p", download=download, token="t")
    assert calls[-1] == (rec.publisher.release.repo, ["config.json"], "t")
    data["config.json"] = b"{}\n"
    with pytest.raises(IProofsError, match=r"config\.json is not the record's"):
        fetch_no_weights(rec, tmp_path / "e", download=download)
    blob = dataclasses.replace(rec.model.files[0], publisher_blob="0" * 40)
    other = dataclasses.replace(rec, model=dataclasses.replace(
        rec.model, files=(blob, rec.model.files[1])))  # fmt: skip
    data["config.json"] = b'{"torch_dtype": "bfloat16"}\n'
    with pytest.raises(IProofsError, match="is not the publisher's bytes"):
        fetch_no_weights(other, tmp_path / "f", download=download)
