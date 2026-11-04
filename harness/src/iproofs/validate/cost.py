"""RFC-0006 §Cost basis C3, rule COST-1 (gate G2): a set price is the median per-GPU list price
of at least three named providers' readings, recomputed here so it is never typed by hand."""

import math
import re
import statistics
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from iproofs.errors import ErrorKind
from iproofs.validate import Finding

MIN_PROVIDERS = 3


def median_price(readings: list[dict[str, Any]]) -> float:
    """Median of each reading's list price divided by its GPU count, in USD per GPU-hour."""
    return float(statistics.median(r["list_price_usd_per_hour"] / r["gpus"] for r in readings))


def check(root: Path, files: Iterable[str]) -> list[Finding]:
    found = []
    for rel in files:
        if not re.fullmatch(r"reference/[^/]+\.yaml", rel):
            continue
        cost = (yaml.safe_load((root / rel).read_text()) or {}).get("cost") or {}
        value = (cost.get("price_per_gpu_hour_usd") or {}).get("value")
        readings = cost.get("readings") or []
        if not value:
            continue  # unpriced: release freeze refuses it (C6)
        providers = [r["provider"] for r in readings]
        if len(set(providers)) < MIN_PROVIDERS:
            problem = f"{len(set(providers))} providers read; C3 needs at least {MIN_PROVIDERS}"
        elif cost.get("providers") != providers:
            problem = "`providers` must name the readings' providers, in order"
        elif not math.isclose(value, median_price(readings), rel_tol=0, abs_tol=1e-9):
            problem = f"price {value} is not the readings' median {median_price(readings)}"
        else:
            continue
        found.append(Finding("G2", rel, "COST-1", problem, ErrorKind.CONFIG, "/cost",
                             hint="RFC-0006 §Cost basis"))  # fmt: skip
    return found
