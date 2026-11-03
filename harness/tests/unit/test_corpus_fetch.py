"""RFC-0014 §Corpus fetch against a local HTTP fixture."""

import hashlib
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Corpus, CorpusText, Normalisation
from iproofs.provenance import corpus_digest
from iproofs.runner import retry_fetch
from iproofs.workloads import ensure_corpus, http_get, listed_digest, normalised

TEXTS = {"a.txt": "﻿Café au lait.\r\nSecond line.\r\n", "b.txt": "Plain text.\n"}


class Handler(http.server.BaseHTTPRequestHandler):
    failures = 0  # requests to fail with 503 before serving

    def do_GET(self) -> None:
        if Handler.failures:
            Handler.failures -= 1
            self.send_error(503)
            return
        body = TEXTS[self.path.lstrip("/")].encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # keep test output clean
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def corpus(base: str, **wrong: str) -> Corpus:
    texts = tuple(
        CorpusText(
            id=name.removesuffix(".txt"),
            source_url=f"{base}/{name}",
            licence="public domain in the United States",
            sha256=wrong.get(name, hashlib.sha256(body.encode()).hexdigest()),
            bytes=len(body.encode()),
        )
        for name, body in TEXTS.items()
    )
    normalisation = Normalisation(unicode="NFC", newlines="LF", strip_bom=True)
    return Corpus(schema="corpus/1", normalisation=normalisation, texts=texts)


def test_corpus_fetch_and_cache(tmp_path: Path, server: str) -> None:
    files = ensure_corpus(corpus(server), tmp_path)
    assert sorted(files) == ["a", "b"]
    assert files["a"] == tmp_path / "corpus" / hashlib.sha256(TEXTS["a.txt"].encode()).hexdigest()
    assert normalised(files["a"].read_bytes()) == "Café au lait.\nSecond line.\n"  # NFC, LF, no BOM
    assert ensure_corpus(corpus(server), tmp_path, get=lambda url: b"unused") == files  # cached


def test_corpus_digest_mismatch_is_integrity(tmp_path: Path, server: str) -> None:
    with pytest.raises(IProofsError) as e:
        ensure_corpus(corpus(server, **{"b.txt": "0" * 64}), tmp_path)
    assert e.value.kind is ErrorKind.INTEGRITY
    assert not any((tmp_path / "corpus").glob("0*"))  # nothing unverified is kept


def test_cached_file_changed_is_integrity(tmp_path: Path, server: str) -> None:
    files = ensure_corpus(corpus(server), tmp_path)
    files["b"].write_text("tampered\n")
    with pytest.raises(IProofsError) as e:
        ensure_corpus(corpus(server), tmp_path)
    assert e.value.kind is ErrorKind.INTEGRITY


def test_corpus_digest_matches_rfc0012_definition(tmp_path: Path, server: str) -> None:
    c = corpus(server)
    files = ensure_corpus(c, tmp_path)
    lines = sorted(f"{t.id}\t{t.sha256}\n" for t in c.texts)
    expected = "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest()
    assert corpus_digest(files) == listed_digest(c) == expected


def test_corpus_fetch_retries(tmp_path: Path, server: str) -> None:
    Handler.failures = 2
    retry = lambda op: retry_fetch(op, "corpus", sleep=lambda s: None)  # noqa: E731
    assert sorted(ensure_corpus(corpus(server), tmp_path, retry=retry)) == ["a", "b"]
    Handler.failures = 3
    with pytest.raises(IProofsError) as e:
        ensure_corpus(corpus(server), tmp_path / "again", retry=retry)
    assert e.value.kind is ErrorKind.FETCH
    Handler.failures = 0
    with pytest.raises(IProofsError, match="failed"):
        http_get(f"{server}/missing.txt")
