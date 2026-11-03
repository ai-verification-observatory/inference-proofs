import ast
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, Failure
from iproofs.log import patterns
from iproofs.log.redact import Redactor
from secret_samples import RULES, sample

ROOT = Path(__file__).resolve().parents[3]


def redactor(**kw: object) -> Redactor:
    defaults: dict[str, object] = {
        "env": {},
        "hostname": "gpu-box-07.lab.example",
        "home": "/home/alice",
    }
    return Redactor.from_host(**{**defaults, **kw})  # type: ignore[arg-type]


# One sample per RFC-0013 G9 rule; every one must disappear from captured output.
SAMPLES = {rule: sample(rule) for rule in RULES}


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
    home = sample("SEC-10")  # a home directory with its trailing slash
    assert (
        redactor(home=home.rstrip("/"))(home + ".cache/iproofs/model") == "~/.cache/iproofs/model"
    )
    users = "/Users"  # split so this source holds no home path
    assert redactor(home=f"{users}/al")(f"{users}/al/x and {users}/zed/y") == "~/x and ~/y"


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
    ip, gpu = sample("SEC-5"), sample("SEC-8")
    stderr = [f"connecting to {ip}", f"device {gpu} busy"]
    f = Failure.build(ErrorKind.ADAPTER, "prove", f"host {ip} failed", last_lines=stderr)
    clean = redactor().failure(f)
    text = clean.message + "\n".join(clean.last_lines)
    assert ip not in text
    assert gpu not in text
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
