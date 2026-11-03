import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import iproofs
from iproofs import cli

ROOT = Path(__file__).resolve().parents[3]
MODULES = [p.stem for p in (ROOT / "harness/src/iproofs").glob("*.py") if p.stem != "__init__"]
OPTIONAL = ["pynvml", "huggingface_hub", "tokenizers"]


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert iproofs.__version__ == pyproject["project"]["version"]


def test_base_import_without_extras() -> None:
    # INV-ARCH-6: importing every module must not pull in an optional dependency.
    code = (
        "import sys, importlib\n"
        f"for m in {MODULES!r}: importlib.import_module('iproofs.' + m)\n"
        f"bad = [m for m in {OPTIONAL!r} if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_version_flag_prints_version_and_commit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(f"iproofs {iproofs.__version__} (")
    assert out.strip().endswith(")")
