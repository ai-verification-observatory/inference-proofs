import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

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
              ["prompts", "build", "w", "--seed", "0"],
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


def test_gpus_list() -> None:
    """`--gpus 0,1,2,3` (RFC-0006 R6): distinct non-negative indices; `--load` takes the two
    load points of RFC-0015 SRV-1."""

    from iproofs.cli import build_parser, gpu_list  # noqa: PLC0415

    assert gpu_list("0,1,2,3") == [0, 1, 2, 3]
    for bad in ("0,0", "a", "-1", ""):
        with pytest.raises(argparse.ArgumentTypeError):
            gpu_list(bad)
    argv = ["run", "--system", "ref-serve", "--workload", "w", "--profile", "p", "--gpus", "4,5",
            "--load", "high"]  # fmt: skip
    args = build_parser().parse_args(argv)
    assert (args.gpus, args.load) == ([4, 5], "high")
    assert args.sizing_batches is None
    assert build_parser().parse_args([*argv[:-2], "--sizing-batches", "50"]).sizing_batches == 50


def test_sizing_batches_serving_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--sizing-batches` (RFC-0015 SRV-1) on a system that is not production serving is
    `config` before any step."""
    monkeypatch.chdir(Path(__file__).resolve().parents[3])
    argv = ["run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile", "ci-cpu",
            "--in-process", "--sizing-batches", "4"]  # fmt: skip
    assert cli.main(argv) == 2
    assert "--sizing-batches is for production serving" in capsys.readouterr().err


def test_fetch_model_no_weights(
    monkeypatch: pytest.MonkeyPatch, tmp_path: "object", capsys: pytest.CaptureFixture[str]
) -> None:
    """`fetch-model --serving RECORD --no-weights DIR` fetches the record's files without the
    weights into DIR (the tokenizer check before the weights); without --serving it is
    `config`."""
    import iproofs.serving  # noqa: PLC0415

    seen: list[tuple[str, str]] = []

    def fake(doc: Any, d: object, **kw: object) -> list[str]:
        seen.append((doc.id, str(d)))
        return []

    monkeypatch.setattr(iproofs.serving, "fetch_no_weights", fake)
    out = f"{tmp_path}/small"
    rc = cli.main(["fetch-model", "--serving", "llama-3.1-8b-instruct-bf16", "--no-weights", out])
    assert rc == 0
    assert seen == [("llama-3.1-8b-instruct-bf16", out)]
    assert capsys.readouterr().out.strip() == out
    assert cli.main(["fetch-model", "sash-l31-8b-c1024", "--no-weights", out]) != 0
