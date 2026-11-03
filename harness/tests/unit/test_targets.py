"""RFC-0009 §Targets: evaluation on the least favourable completed repetition."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures.release_tree import build, commit
from iproofs import cli
from iproofs.release import evaluate_target

ROOT = Path(__file__).resolve().parents[3]
TARGET = yaml.safe_load((ROOT / "schema/target/examples/valid/verify-under-60s.yaml").read_text())


def seconds(*values: float, scope: str = "verify") -> list[tuple[str, dict[str, object]]]:
    """Fixture repetitions, not results."""
    return [(f"run-{i}#/metrics/verify_seconds", {"value": v, "unit": "s", "scope": scope})
            for i, v in enumerate(values)]  # fmt: skip


def test_least_favourable_repetition_used() -> None:
    result, reason, worst = evaluate_target(TARGET, seconds(58, 59, 63))
    assert (result, reason) == ("does_not_meet", None)  # the mean, 60, alone would meet it
    assert worst is not None
    assert worst["value"] == 63
    assert evaluate_target(TARGET, seconds(58, 59, 60))[0] == "meets"
    assert (
        evaluate_target({**TARGET, "comparator": ">="}, seconds(61, 70, 59))[2]
        == (seconds(59)[0][1])
    )
    assert evaluate_target({**TARGET, "comparator": "=="}, seconds(60, 60))[0] == "meets"
    assert evaluate_target({**TARGET, "comparator": "=="}, seconds(60, 61))[0] == "does_not_meet"


def test_scope_mismatch_not_evaluable() -> None:
    result, reason, worst = evaluate_target(TARGET, seconds(10, scope="verify.single_thread"))
    assert (result, worst) == ("not_evaluable", None)
    assert reason == "scope verify.single_thread differs from the threshold's verify"
    assert evaluate_target(TARGET, [])[:2] == ("not_evaluable", "metric missing")
    null = [("run-0#/metrics/verify_seconds", {"value": None, "unit": "s", "scope": "verify"})]
    assert evaluate_target(TARGET, null)[1] == "metric null in run-0#/metrics/verify_seconds"
    unit = [("r#/m", {"value": 1.0, "unit": "ms", "scope": "verify"})]
    assert evaluate_target(TARGET, unit)[1] == "unit ms differs from the threshold's s"


CARD = 'claim_class: "next-token/exact-match/committed-weights"\ncoverage: {phase: "prefill"}\n'


def target(root: Path, name: str, **change: object) -> None:
    doc = TARGET | {"id": name, "metric": "prove_session_seconds", "profile": "ci-cpu",
                    "claim_class": "*/exact-match/*",
                    "threshold": {**TARGET["threshold"], "value": 2, "scope": "prove.session",
                                  "source": {"kind": "reference_file",
                                             "ref": f"targets/example-lab/{name}.yaml#/threshold"}},
                    **change}  # fmt: skip
    path = root / "targets/example-lab" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_applies_to_filter_hides_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path, card_text=CARD)
    target(tmp_path, "session-under-2s")
    target(tmp_path, "decode-only", applies_to={"coverage.phase": "decode"})
    target(tmp_path, "other-profile", profile="prover-h100")
    target(tmp_path, "other-class", claim_class="*/tolerance/*")
    commit(tmp_path, "targets")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 0, capsys.readouterr().err
    found: list[dict[str, Any]] = json.loads(
        (tmp_path / "releases/v0.1/index.json").read_text())["targets"]  # fmt: skip
    assert [t["target"] for t in found] == ["targets/example-lab/session-under-2s.yaml"]
    assert (found[0]["result"], found[0]["reason"]) == ("meets", None)
    assert found[0]["least_favourable"]["value"] == 1.5
    assert found[0]["mean"]["stats"]["n"] == 3
