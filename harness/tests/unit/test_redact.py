import ast
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, Failure
from iproofs.log import patterns
from iproofs.log.redact import Redactor

ROOT = Path(__file__).resolve().parents[3]


def redactor(**kw: object) -> Redactor:
    defaults: dict[str, object] = {
        "env": {},
        "hostname": "gpu-box-07.lab.example",
        "home": "/home/alice",
    }
    return Redactor.from_host(**{**defaults, **kw})  # type: ignore[arg-type]


# One sample per RFC-0013 G9 rule; every one must disappear from captured output.
SAMPLES = {
    "SEC-1": "hf_" + "a" * 34,
    "SEC-2": "ghp_" + "B" * 36,
    "SEC-3": "AKIA" + "ABCDEFGHIJKLMNOP",
    "SEC-4": "-----BEGIN RSA PRIVATE KEY-----",
    "SEC-5": "10.20.30.40",
    "SEC-6": "fe80::1ff:fe23:4567:890a",
    "SEC-7": "00:1a:2b:3c:4d:5e",
    "SEC-8": "GPU-12345678-90ab-cdef-1234-567890abcdef",
    "SEC-9": "HostName bastion.internal",
    "SEC-10": "/home/bob/",
    "SEC-11": "api_key = 0123456789abcdefXYZ",
}


@pytest.mark.parametrize("rule", sorted(SAMPLES))
def test_every_g9_pattern_removed(rule: str) -> None:
    sample = SAMPLES[rule]
    text = f"captured stderr\n{sample}\nend"  # SEC-9 is anchored at line starts
    out = redactor()(text)
    secret = sample.split()[-1].split("=")[-1].strip()
    assert secret not in out, (rule, out)


def test_env_token_replaced_everywhere() -> None:
    value = "s3cr3t-value-0123456"  # 20 characters
    r = redactor(env={"FOO_TOKEN": value, "PATH": "/usr/bin", "SHORT_KEY": "abc"})
    out = r(f"a {value} b {value}")
    assert out == "a <redacted:env_secret> b <redacted:env_secret>"
    assert r("/usr/bin abc") == "/usr/bin abc"  # not secret-named, or too short


def test_hf_token_env_replaced() -> None:
    assert redactor(env={"HF_TOKEN": "abcdefgh12"})("t=abcdefgh12") == "t=<redacted:env_secret>"


def test_hostname_and_first_label_replaced() -> None:
    out = redactor()("on gpu-box-07.lab.example and gpu-box-07 today")
    assert out == "on <redacted:hostname> and <redacted:hostname> today"


def test_home_path_becomes_tilde() -> None:
    assert redactor()("/home/alice/.cache/iproofs/model") == "~/.cache/iproofs/model"
    assert redactor(home="/Users/al")("/Users/al/x and /Users/zed/y") == "~/x and ~/y"


def test_timestamps_and_versions_untouched() -> None:
    line = '{"ts":"2026-11-03T10:15:02.118Z","driver":"560.35.03","digest":"sha256:ab01"}'
    assert redactor()(line) == line


@pytest.mark.parametrize("kept", ["127.0.0.1", "0.0.0.0", "::1"])
def test_loopback_untouched(kept: str) -> None:
    assert redactor()(f"bind {kept} ok") == f"bind {kept} ok"


def test_gpu_serial_from_nvml_replaced() -> None:
    assert redactor(gpu_serials=["1652022000123"])("serial 1652022000123") == (
        "serial <redacted:gpu_serial>"
    )


def test_failure_record_redacted() -> None:
    stderr = ["connecting to 10.0.0.12", "device GPU-12345678-90ab-cdef-1234-567890abcdef busy"]
    f = Failure.build(ErrorKind.ADAPTER, "prove", "host 10.0.0.12 failed", last_lines=stderr)
    clean = redactor().failure(f)
    text = clean.message + "\n".join(clean.last_lines)
    assert "10.0.0.12" not in text
    assert "GPU-12345678" not in text
    assert clean.kind is ErrorKind.ADAPTER


def test_redactor_and_scanner_share_patterns() -> None:
    """One compiled pattern set covers every G9 rule; the redactor uses that same object."""
    assert Redactor.patterns is patterns.PATTERNS
    assert {p.rule for p in patterns.PATTERNS} == {f"SEC-{i}" for i in range(1, 12)}


def test_patterns_module_imports_stdlib_only() -> None:
    """INV-ARCH-1: the shared pattern module sits in layer 0."""
    tree = ast.parse((ROOT / "harness/src/iproofs/log/patterns.py").read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (
            node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
        )
    }
    assert imported <= {"re", "dataclasses"}
