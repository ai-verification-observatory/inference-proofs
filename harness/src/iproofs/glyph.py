"""The glyph of a row (RFC-0018 §The glyph, GL-1 to GL-5): five petals showing how close the
row is to a perfect prover. It never moves a position (GL-4).

Statement petals come from `systems/<name>/properties.yaml` (schema `properties/1`); tests only
lower them (GL-2). `faithful_model` comes from the rung's `fidelity.json`, `any_model` from the
board's rows on every rung. Every function here is pure except `load_properties`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from iproofs.serialize import load_yaml

GREEN, AMBER, RED, HOLLOW = "green", "amber", "red", "hollow"
STATEMENT, TEST, RUN = "statement", "test", "run"
PETALS = ("unforgeable", "weights_hidden", "faithful_model", "any_model", "no_trusted_party")
NO_PROPERTIES = "no properties file"
REFERENCE_RERUN = "reference-2"  # FI-2: the reference run a second time
# GL-2: the checks whose failure sets a statement petal red, with what the failure shows
LOWERED_BY = {
    "unforgeable": ("model", "prompt", "reply"),
    "weights_hidden": ("no_weight_file",),
    "no_trusted_party": (),
}
_CHECK_NAMES = {"model": "Model", "prompt": "Prompt", "reply": "Reply",
                "no_weight_file": "No weight file"}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Petal:
    id: str
    state: str
    basis: str
    reason: str
    quotes: tuple[Mapping[str, str], ...] = ()

    def tree(self) -> dict[str, object]:
        return {"id": self.id, "state": self.state, "basis": self.basis, "reason": self.reason,
                "quotes": [{"text": str(q["text"]), "url": str(q["url"])}
                           for q in self.quotes]}  # fmt: skip


# ---------------------------------------------------------------- statement petals (GL-1, GL-2)


def load_properties(root: Path, system: str) -> dict[str, object] | None:
    path = root / "systems" / system / "properties.yaml"
    return load_yaml(path) if path.is_file() else None


def statement_petal(
    petal: str, properties: Mapping[str, object] | None, commit: str | None = None
) -> Petal:
    """GL-1: the reviewer's state at the pin; silence and a missing file are red. A file read
    at another commit than the row's (`commit`) decides nothing, so it is red too."""
    if properties is None:
        return Petal(petal, RED, STATEMENT, NO_PROPERTIES)
    upstream = properties.get("upstream")
    pin = str(upstream.get("commit")) if isinstance(upstream, Mapping) else ""
    if commit is not None and pin != commit:
        return Petal(petal, RED, STATEMENT, f"properties file read at {pin}, the row runs {commit}")
    petals = properties.get("petals")
    found = petals.get(petal) if isinstance(petals, Mapping) else None
    if not isinstance(found, Mapping):
        return Petal(petal, RED, STATEMENT, f"{petal} not in the properties file")
    quotes = tuple(q for q in found.get("quotes") or () if isinstance(q, Mapping))
    if found.get("state") == "not_stated":
        read = ", ".join(str(s) for s in found.get("sources_read") or ())
        return Petal(petal, RED, STATEMENT, f"not stated in {read} at {pin}", quotes)
    return Petal(petal, str(found.get("state")), STATEMENT, str(found.get("reason")), quotes)


def lowered(petal: Petal, checks: Mapping[str, str]) -> Petal:
    """GL-2: a failed check named in LOWERED_BY sets the petal red; a held one raises nothing.
    `checks` maps check ids to their states."""
    failed = [c for c in LOWERED_BY.get(petal.id, ()) if checks.get(c) == "failed"]
    if not failed:
        return petal
    names = ", ".join(_CHECK_NAMES[c] for c in failed)
    return Petal(petal.id, RED, TEST, f"our {names} check failed", petal.quotes)


def statement_petals(
    properties: Mapping[str, object] | None, checks: Mapping[str, str], commit: str | None = None
) -> dict[str, Petal]:
    """unforgeable, weights_hidden and no_trusted_party, lowered by failed checks."""
    return {p: lowered(statement_petal(p, properties, commit), checks) for p in LOWERED_BY}


# ---------------------------------------------------------------- faithful model (FI-4)


def _scores(found: object) -> list[int] | None:
    scores = found.get("scores") if isinstance(found, Mapping) else None
    if not isinstance(scores, list) or not all(isinstance(s, int) for s in scores):
        return None
    return [int(s) for s in scores]


def _rerun(controls: object) -> Mapping[str, object] | None:
    for c in controls if isinstance(controls, list) else []:
        if isinstance(c, Mapping) and c.get("id") == REFERENCE_RERUN and c.get("status") == "ok":
            return c
    return None


def faithful_model(  # noqa: PLR0911 (one return per state of the rule)
    fidelity_state: str,
    fidelity_cause: str | None,
    doc: Mapping[str, object] | None,
    system: str,
    randomness_hex: str | None,
) -> Petal:
    """Red when FIDELITY failed; hollow when it is undecided or no fidelity.json is stored
    (GL-3); when it held, the FI-4 test "the reference rerun beats the row" on the per-prompt
    scores: green when p >= alpha (the row is not shown below the rerun), amber otherwise."""
    pid = "faithful_model"
    if fidelity_state == "failed":
        return Petal(
            pid, RED, TEST, "the rung's bar scores above the row's replies (FIDELITY failed)"
        )
    if doc is None:
        return Petal(pid, HOLLOW, TEST, "no fidelity run stored")
    if fidelity_state != "held":
        return Petal(pid, HOLLOW, TEST, f"FIDELITY undecided: {fidelity_cause or 'no cause'}")
    rows = doc.get("rows")
    row = _scores(rows.get(system) if isinstance(rows, Mapping) else None)
    again = _scores(_rerun(doc.get("controls")))
    if row is None or again is None or len(row) != len(again):
        return Petal(pid, HOLLOW, TEST, "no reference rerun scores paired with the row's")
    test = doc.get("test")
    test = test if isinstance(test, Mapping) else {}
    alpha = float(test.get("alpha", 0.05))
    exact_up_to = int(test.get("exact_up_to", 20))
    resamples = int(test.get("resamples", 200_000))
    from iproofs.fidelity import SignFlipRule, beats  # noqa: PLC0415

    if len(row) > exact_up_to and not randomness_hex:
        return Petal(pid, HOLLOW, TEST, "no beacon randomness to seed the test")
    rule = SignFlipRule(alpha, exact_up_to, resamples, randomness_hex or "0" * 64)
    p = beats(REFERENCE_RERUN, again, system, row, rule).p
    if p >= alpha:
        return Petal(pid, GREEN, TEST, f"the reference rerun is not shown above the row "
                     f"(p = {p:.4g}, alpha {alpha:g}, n = {len(row)})")  # fmt: skip
    return Petal(pid, AMBER, TEST, f"above the bar; the reference rerun scores above the row "
                 f"(p = {p:.4g}, alpha {alpha:g}, n = {len(row)})")  # fmt: skip


# ---------------------------------------------------------------- any model


def any_model(passed_rungs: int, rungs: int, undecided: bool) -> Petal:
    """Green when the system passed on every rung, amber on more than one, red on one or none;
    hollow while it has passed nowhere and a row of it still has an undecided check (GL-3)."""
    pid = "any_model"
    said = f"passed on {passed_rungs} of {rungs} rungs"
    if passed_rungs == 0 and undecided:
        return Petal(pid, HOLLOW, RUN, f"{said}; a check is still undecided")
    if rungs > 0 and passed_rungs == rungs:
        return Petal(pid, GREEN, RUN, said)
    if passed_rungs > 1:
        return Petal(pid, AMBER, RUN, said)
    return Petal(pid, RED, RUN, said)


def glyph(petals: Mapping[str, Petal]) -> list[dict[str, object]]:
    """The five petals in drawing order."""
    return [petals[p].tree() for p in PETALS]
