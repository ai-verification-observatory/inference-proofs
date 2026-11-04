"""RFC-0006 §Cost basis C3, rule COST-1: the price is the recomputed median of the readings."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs.validate import cost

ROOT = Path(__file__).resolve().parents[3]
REL = "reference/v0.1.yaml"


def findings(tmp_path: Path, edit: Any) -> list[str]:
    doc = yaml.safe_load((ROOT / REL).read_text())
    edit(doc["cost"])
    (tmp_path / "reference").mkdir()
    (tmp_path / REL).write_text(yaml.safe_dump(doc))
    return [f.message for f in cost.check(tmp_path, [REL, "README.md"])]


def test_v01_price_is_the_median() -> None:
    assert cost.check(ROOT, [REL]) == []


def test_median_per_gpu_hand_computed() -> None:
    """4.29, 3.99 and 49.24 / 8 = 6.155 per GPU-hour: the median is 4.29."""
    readings = [{"list_price_usd_per_hour": p, "gpus": g} for p, g in ((4.29, 1), (3.99, 1),
                                                                      (49.24, 8))]  # fmt: skip
    assert cost.median_price(readings) == 4.29


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda c: c["price_per_gpu_hour_usd"].update(value=4.3), "is not the readings' median"),
        (lambda c: c.update(readings=c["readings"][:2], providers=c["providers"][:2]),
         "2 providers read; C3 needs at least 3"),
        (lambda c: c.update(providers=list(reversed(c["providers"]))), "in order"),
    ],
)  # fmt: skip
def test_cost_1(tmp_path: Path, edit: Any, message: str) -> None:
    [found] = findings(tmp_path, edit)
    assert message in found


def test_unpriced_file_left_to_freeze(tmp_path: Path) -> None:
    def unpriced(c: dict[str, Any]) -> None:
        c["price_per_gpu_hour_usd"]["value"] = 0.0
        c.pop("readings")

    assert findings(tmp_path, unpriced) == []
