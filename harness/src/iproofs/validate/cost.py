"""RFC-0006 §Cost basis C3, rule COST-1 (gate G2): a set price is the median per-GPU list price
of at least three named providers' readings, recomputed here so it is never typed by hand. It
holds for `cost` and for every basis of `costs` (C7); rule COST-2: a prover profile's `cost`
names a basis of `costs`."""

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


def bases(doc: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(JSON pointer, basis) for `cost` and every basis of `costs` (RFC-0006 C7)."""
    found = [("/cost", doc.get("cost") or {})]
    found += [(f"/costs/{k}", v or {}) for k, v in sorted((doc.get("costs") or {}).items())]
    return found


def _problem(cost: dict[str, Any]) -> str | None:
    value = (cost.get("price_per_gpu_hour_usd") or {}).get("value")
    readings = cost.get("readings") or []
    if not value:
        return None  # unpriced: release freeze refuses it (C6)
    providers = [r["provider"] for r in readings]
    if len(set(providers)) < MIN_PROVIDERS:
        return f"{len(set(providers))} providers read; C3 needs at least {MIN_PROVIDERS}"
    if cost.get("providers") != providers:
        return "`providers` must name the readings' providers, in order"
    if not math.isclose(value, median_price(readings), rel_tol=0, abs_tol=1e-9):
        return f"price {value} is not the readings' median {median_price(readings)}"
    return None


def check(root: Path, files: Iterable[str]) -> list[Finding]:
    found = []
    for rel in files:
        if not re.fullmatch(r"reference/[^/]+\.yaml", rel):
            continue
        doc = yaml.safe_load((root / rel).read_text()) or {}
        for where, cost in bases(doc):
            if (problem := _problem(cost)) is not None:
                found.append(Finding("G2", rel, "COST-1", problem, ErrorKind.CONFIG, where,
                                     hint="RFC-0006 §Cost basis"))  # fmt: skip
        named = set(doc.get("costs") or {})
        for pid, profile in sorted((doc.get("profiles") or {}).items()):
            basis = profile.get("cost") if isinstance(profile, dict) else None
            if basis is not None and basis not in named:
                found.append(Finding("G2", rel, "COST-2", f"profile {pid} names cost basis "
                                     f"{basis!r}, which `costs` does not define", ErrorKind.CONFIG,
                                     f"/profiles/{pid}/cost", hint="RFC-0006 C7"))  # fmt: skip
    return found
