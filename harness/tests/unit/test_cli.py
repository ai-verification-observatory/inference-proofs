import argparse
import subprocess
import sys

import pytest

from iproofs import cli
from iproofs.errors import ErrorKind, IProofsError
from secret_samples import sample

COMMANDS = [
    "validate",
    "derive",
    "run",
    "controls",
    "machine-record",
    "fetch-model",
    "prompts",
    "reproduce",
    "release",
    "site",
]


def run_with(handler: cli.Handler, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    original = cli.build_parser

    def patched() -> argparse.ArgumentParser:
        parser = original()
        parser.set_defaults(handler=handler)
        for action in parser._subparsers._group_actions:  # type: ignore[union-attr]
            for sub in action.choices.values():  # type: ignore[union-attr]
                sub.set_defaults(handler=handler)
        return parser

    monkeypatch.setattr(cli, "build_parser", patched)
    return cli.main(argv)


def test_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--system"])  # bad argument
    assert e.value.code == 2

    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("bug")

    assert run_with(boom, ["machine-record"], monkeypatch) == 5

    def environment(args: argparse.Namespace) -> int:
        raise IProofsError(ErrorKind.ENVIRONMENT, "cgroup v1")

    assert run_with(environment, ["machine-record"], monkeypatch) == 3

    def config(args: argparse.Namespace) -> int:
        raise IProofsError(ErrorKind.CONFIG, "bad file")

    assert run_with(config, ["validate"], monkeypatch) == 1  # a check found it
    assert (
        run_with(config, ["run", "--system", "s", "--workload", "w", "--profile", "p"], monkeypatch)
        == 2
    )


def test_every_command_has_a_handler() -> None:
    parser = cli.build_parser()
    leaves = [["validate"], ["derive", "x"], ["controls"], ["machine-record"], ["fetch-model", "w"],
              ["prompts", "build", "w", "--seed", "0"], ["reproduce", "compare", "a", "b"],
              ["release", "freeze", "v"], ["release", "plan", "v"], ["site", "build"]]  # fmt: skip
    for argv in leaves:
        assert callable(parser.parse_args(argv).handler), argv


def test_help_lists_all_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for command in COMMANDS:
        assert command in out


def test_run_arguments_match_rfc() -> None:
    args = cli.build_parser().parse_args(
        [
            "run",
            "--system",
            "fake",
            "--workload",
            "fake-tiny-ci",
            "--profile",
            "ci-cpu",
            "--control-suite",
            "--provider",
            "hosted",
            "--allow-nonconforming",
        ]
    )
    assert (args.repetitions, str(args.results), args.control_suite) == (3, "results", True)


def test_optional_extras_not_imported_on_help() -> None:
    code = (
        "import sys\nfrom iproofs import cli\n"
        "try:\n    cli.main(['--help'])\nexcept SystemExit:\n    pass\n"
        "extras = ('pynvml', 'huggingface_hub', 'tokenizers')\n"
        "bad = [m for m in extras if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_error_message_is_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def leak(args: argparse.Namespace) -> int:
        raise IProofsError(ErrorKind.FETCH, "could not reach " + sample("SEC-5"))

    run_with(leak, ["fetch-model", "w"], monkeypatch)
    assert sample("SEC-5") not in capsys.readouterr().err
