import json
import re
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import InProcessRunner, StepResult
from iproofs.errors import IProofsError
from iproofs.runner import JobSpec, Runner, recorded_seed
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}
IMAGE = "local/in-process@sha256:" + "0" * 64


def spec(results: Path) -> JobSpec:
    return JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(results), "v0.1")


def workload_record(run_dir: Path) -> dict[str, str]:
    record: dict[str, str] = json.loads((run_dir / "manifest.json").read_text())["workload"]
    return record


def runner(replay_seed: int | None = None) -> Runner:
    return Runner(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV),
        root=ROOT,
        registry=REGISTRY,
        image=IMAGE,
        replay_seed=replay_seed,
    )


def test_fresh_seed_recorded(tmp_path: Path) -> None:
    """Two jobs draw different seeds; replaying one reproduces its prompt set digest."""
    a = workload_record(runner().run(spec(tmp_path)))
    b = workload_record(runner().run(spec(tmp_path)))
    assert a["prompt_seed"] != b["prompt_seed"]
    first = next((tmp_path / "v0.1/fake").glob("*-1"))
    seed = recorded_seed(first, "fake-tiny-ci", 1)
    replayed = workload_record(runner(replay_seed=seed).run(spec(tmp_path)))
    assert replayed["prompt_seed"] == a["prompt_seed"]
    assert replayed["prompt_set_digest"] == a["prompt_set_digest"]


def test_seed_format_hex16(tmp_path: Path) -> None:
    record = workload_record(runner(replay_seed=255).run(spec(tmp_path)))
    assert record["prompt_seed"] == "0x00000000000000ff"
    assert re.fullmatch(r"0x[0-9a-f]{16}", record["prompt_seed"])


def test_seed_drawn_before_info(tmp_path: Path) -> None:
    """The prompts exist, built from the job's seed, when the first adapter call starts."""
    seen: list[bool] = []
    inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV)

    class Watching:
        def run(self, image: str, subcommand: str, io_dir: Path, **kw: object) -> StepResult:
            if subcommand == "info":
                seen.append((io_dir / "prompts.jsonl").is_file())
            return inner.run(image, subcommand, io_dir, **kw)  # type: ignore[arg-type]

    Runner(Watching(), root=ROOT, registry=REGISTRY, image=IMAGE).run(spec(tmp_path))
    assert seen == [True]


def test_replay_refuses_another_workload(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    with pytest.raises(IProofsError, match="ran fake-tiny-ci v1, not other v1"):
        recorded_seed(run_dir, "other", 1)


def test_prompts_from_through_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    source = runner().run(spec(tmp_path / "a"))
    args = [
        "run",
        "--system",
        "fake",
        "--workload",
        "fake-tiny-ci",
        "--profile",
        "ci-cpu",
        "--repetitions",
        "1",
        "--results",
        str(tmp_path / "b"),
        "--in-process",
        "--prompts-from",
        str(source),
    ]
    assert cli.main(args) == 0
    replay = next((tmp_path / "b/v0.1/fake").iterdir())
    assert (
        workload_record(replay)["prompt_set_digest"] == workload_record(source)["prompt_set_digest"]
    )
