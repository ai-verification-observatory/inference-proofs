"""The glyph of a row (RFC-0018 §The glyph, GL-1 to GL-9): five petals, each a step on its own
question, never a total (GL-8). It never moves a position (GL-4).

Four statement petals are computed from the facts a reviewer copies into
`systems/<name>/properties.yaml` (schema `properties/2`): no state is typed (GL-1). Tests only
lower them (GL-2). `faithful_model` is measured: it reads the step tests that `iproofs fidelity
score` stores in the rung's `fidelity.json`. Each decision function follows its table line by
line (UF-1 to UF-9, MC-1 to MC-6, WH-1 to WH-6, FM-1 to FM-7, NT-1 to NT-6): the first matching
line wins. Every function here is pure except `load_properties` and `load_proof_build`.
"""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.fidelity import sign_flip_p
from iproofs.serialize import load_yaml

GREEN, AMBER, RED, HOLLOW = "green", "amber", "red", "hollow"
AMBER_UPPER, AMBER_LOWER = "amber_upper", "amber_lower"
STATEMENT, TEST = "statement", "test"
PETALS = ("unforgeable", "weights_hidden", "faithful_model", "machine_checked", "no_trusted_party")
STATEMENT_PETALS = ("unforgeable", "weights_hidden", "machine_checked", "no_trusted_party")
STEPS = (GREEN, AMBER_UPPER, AMBER_LOWER, RED, None)
STEP_STATE: Mapping[str | None, str] = {GREEN: GREEN, AMBER_UPPER: AMBER, AMBER_LOWER: AMBER,
                                        RED: RED, None: HOLLOW}  # fmt: skip
RED_CAUSES = ("not_stated", "stated", "check_failed")
HOLLOW_CAUSES = ("not_read", "not_decided", "proof_build_not_run")
NOT_STATED, STATED, CHECK_FAILED = RED_CAUSES
NOT_READ, NOT_DECIDED, PROOF_BUILD_NOT_RUN = HOLLOW_CAUSES
PROPERTIES_SCHEMA = "properties/2"
NO_PROPERTIES = "no properties file"
EXACT_MATCH = "exact_match"
# GL-2: the checks whose failure lowers a petal (Machine-checked only where it was green)
LOWERED_BY: Mapping[str, tuple[str, ...]] = {
    "unforgeable": ("model", "prompt", "reply"),
    "weights_hidden": ("no_weight_file",),
    "faithful_model": ("fidelity",),
    "machine_checked": ("model", "prompt", "reply"),
    "no_trusted_party": (),
}
_CHECK_NAMES = {"model": "Model", "prompt": "Prompt", "reply": "Reply",
                "no_weight_file": "Verify without weights", "fidelity": "Fidelity"}  # fmt: skip
_REACH_WORDS = {"part": "a part", "protocol": "the protocol",
                "protocol_and_statement": "the protocol and the model's statement",
                "verifier_run": "the verifier program the row runs",
                "none": "nothing", "not_stated": "not stated"}  # fmt: skip
_REST_WORDS = {"single_party_setup": "a setup run by one party",
               "hardware_key": "a hardware maker's key",
               "trusted_key": "a trusted key"}  # fmt: skip
SCOPE_ROWS = ("soundness", "zero_knowledge", "completeness")
SCOPE_COLS = ("protocol", "verifier_run", "prover_run")
# the facts whose quotes a board petal carries, in the properties order (spec 1.5)
_QUOTED = {
    "unforgeable": ("bound", ("stated", "expression", "basis", "unit", "batch", "adversary",
                              "parameters", "conditions_shown", "program")),
    "weights_hidden": ("hiding", ("stated", "verifier_gets_weights", "proof", "programs",
                                  "visible_listed")),
    "machine_checked": ("formal", ("reach", "tool", "toolchain", "trusted_base",
                                   "input_code_unverified")),
    "no_trusted_party": ("trust", ("rests_on", "publicly_checkable")),
}  # fmt: skip

Quote = Mapping[str, str]
SCORE_UNIT = "leading tokens"  # FI-3: a score is the number of leading tokens matched


@dataclass(frozen=True, slots=True)
class Petal:
    """One petal. `state` is the step's ink (STEP_STATE), never set on its own."""

    id: str
    step: str | None
    cause: str | None
    basis: str
    reason: str
    quotes: tuple[Quote, ...] = ()
    lowered_by: tuple[str, ...] = ()
    formal: Mapping[str, object] | None = None
    visible: Sequence[Mapping[str, object]] | None = None
    reading: bool = False  # a fact the decision read carries a note: the reader's reading (N1)

    @property
    def state(self) -> str:
        return STEP_STATE[self.step]

    def tree(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "state": self.state,
            "step": self.step,
            "cause": self.cause,
            "basis": self.basis,
            "reason": self.reason,
            "quotes": [_quote(q) for q in self.quotes],
            "lowered_by": list(self.lowered_by),
        }
        if self.id == "machine_checked":
            out["formal"] = None if self.formal is None else dict(self.formal)
        if self.id == "weights_hidden":
            out["visible"] = None if self.visible is None else [
                {"item": str(i.get("item")), "tag": str(i.get("tag")),
                 "quotes": [_quote(q) for q in _quotes(i)]} for i in self.visible]  # fmt: skip
        if self.reading:
            out["reading"] = True
        return out


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the row proves, from stored records (spec §2): the system's `proofs.granularity`
    and the workload's `shape.batch_size`, None when not recorded."""

    granularity: str | None
    batch_size: int | None

    @property
    def one_reply(self) -> bool:
        """One proof covers one reply (U4); the batch size does not change replies per proof."""
        return self.granularity == "request"


# ---------------------------------------------------------------- reading the records


def load_properties(root: Path, system: str) -> dict[str, object] | None:
    path = root / "systems" / system / "properties.yaml"
    return load_yaml(path) if path.is_file() else None


def load_proof_build(root: Path, release: str, system: str) -> dict[str, object] | None:
    """The proof-build record of `system` (`proof-build/1`), None when none is stored."""
    path = root / "results" / release / "proof-build" / system / "proof-build.json"
    if not path.is_file():
        return None
    found = json.loads(path.read_text())
    return found if isinstance(found, dict) else None


def _m(x: object) -> Mapping[str, object]:
    return x if isinstance(x, Mapping) else {}


def _v(fact: object) -> object:
    return _m(fact).get("value")


def _quotes(fact: object) -> tuple[Quote, ...]:
    found = _m(fact).get("quotes")
    return tuple(q for q in found if isinstance(q, Mapping)) if isinstance(found, list) else ()


def _quote(q: Quote) -> dict[str, str]:
    return {"text": str(q["text"]), "url": str(q["url"])}


class _Facts:
    """The facts of one group as a decision reads them, in order. `noted` turns true once a fact
    read carries a `note`: the value is then the reader's reading, not the publisher's words
    (N1)."""

    def __init__(self, group: Mapping[str, object]) -> None:
        self.group = group
        self.noted = False

    def __call__(self, key: str) -> object:
        fact = _m(self.group.get(key))
        if fact.get("note"):
            self.noted = True
        return fact.get("value")


def _pin(props: Mapping[str, object]) -> str:
    return str(_m(props.get("upstream")).get("commit"))


def read(
    props: Mapping[str, object] | None, commit: str | None
) -> tuple[Mapping[str, object] | None, str | None]:
    """The file's petals, or None and why it is not read (GL-3: not read is not silent)."""
    if props is None:
        return None, NO_PROPERTIES
    schema = props.get("schema")
    if schema != PROPERTIES_SCHEMA:
        return None, f"properties file is {schema}, the glyph reads {PROPERTIES_SCHEMA}"
    pin = _pin(props)
    if commit is None:  # U7: the row's commit is not known, so the file is not shown to fit it
        return None, "the row's commit is not recorded"
    if pin != commit:
        return None, f"properties file read at {pin[:7]}, the row runs {commit[:7]}"
    return _m(props.get("petals")), None


def failed(checks: Mapping[str, str], ids: Sequence[str]) -> list[str]:
    """GL-2: the failed checks among `ids`; an undecided check lowers nothing."""
    return [c for c in ids if checks.get(c) == "failed"]


def _check_failed(
    pid: str,
    ids: Sequence[str],
    quotes: tuple[Quote, ...] = (),
    formal: Mapping[str, object] | None = None,
    visible: Sequence[Mapping[str, object]] | None = None,
) -> Petal:
    """R-CF: red, cause check_failed, basis test, naming the failed checks (GL-2)."""
    names = ", ".join(_CHECK_NAMES[c] for c in ids)
    return Petal(pid, RED, CHECK_FAILED, TEST, f"our {names} check failed", quotes, tuple(ids),
                 formal, visible)  # fmt: skip


def _not_read(pid: str, reason: str) -> Petal:
    return Petal(pid, None, NOT_READ, STATEMENT, reason)


def _silent(petal: Mapping[str, object], props: Mapping[str, object]) -> str:
    """R-SILENT: the documents read, at the pin."""
    docs = ", ".join(str(s) for s in petal.get("sources_read") or ())  # type: ignore[attr-defined]
    return f"not stated in {docs} at {_pin(props)[:7]}"


def petal_quotes(pid: str, petal: Mapping[str, object]) -> tuple[Quote, ...]:
    """The quotes of the facts that decide `pid`, in the properties order, each once."""
    key, facts = _QUOTED[pid]
    group = _m(petal.get(key))
    seen: set[tuple[str, str]] = set()
    out: list[Quote] = []
    for fact in facts:
        for q in _quotes(group.get(fact)):
            k = (str(q.get("text")), str(q.get("url")))
            if k not in seen:
                seen.add(k)
                out.append(q)
    return tuple(out)


# ---------------------------------------------------------------- Unforgeable (UF-1 to UF-9)


def _batch_short(v: _Facts, n: int | None) -> str | None:
    """U5, U6: whether the bound covers each member of the row's batch as the row checks it."""
    if n == 1:
        return None
    if n is None:
        return "batch size not recorded"
    batch = v("batch")
    if batch == "each_member":
        return None
    if batch == "together":
        return f"the bound is stated for a batch checked together, not for the row's {n} replies " \
            "checked alone"  # fmt: skip
    return f"no bound stated for batch members, and the row proves {n} replies a batch"


def _coverage_short(  # noqa: PLR0911 (one return per condition, in the order of U6)
    v: _Facts, coverage: Coverage
) -> str | None:
    """U5, U6: the first condition that keeps a proved bound from covering the run, None when
    it covers it. Each fact is read only when the conditions before it hold."""
    if v("adversary") != "any_prover":
        return "the bound does not say which provers it holds against"
    unit = v("unit")
    if unit in ("part", "round"):
        return f"the bound is stated per {unit}, not per reply"
    if unit not in ("reply", "proof"):
        return "the bound does not say what it is stated per"
    if unit == "proof" and not coverage.one_reply:
        if coverage.granularity is None:
            return "replies per proof are not recorded"
        return "the bound is per proof, and a proof here covers more than one reply"
    short = _batch_short(v, coverage.batch_size)
    if short is not None:
        return short
    parameters = v("parameters")
    if parameters == "other":
        return "the bound is stated for other parameters than the row's"
    if parameters != "row":
        return "the bound's parameters are not shown to be the row's"
    if v("conditions_shown") is not True:
        return "the bound is not shown to hold for the row's files"
    if v("program") not in ("proved", "stated"):
        return "the bound is not stated for the verifier program the row runs"
    return None


def unforgeable(  # noqa: PLR0911 (one return per line of the table)
    props: Mapping[str, object] | None,
    checks: Mapping[str, str],
    commit: str | None,
    coverage: Coverage,
) -> Petal:
    pid = "unforgeable"
    petals, nr = read(props, commit)
    petal = _m(petals.get(pid)) if petals is not None else {}
    quotes = petal_quotes(pid, petal) if petals is not None else ()
    f = failed(checks, LOWERED_BY[pid])
    if f:  # UF-1
        return _check_failed(pid, f, quotes)
    if petals is None or props is None:  # UF-2
        return _not_read(pid, nr or NO_PROPERTIES)
    b = _m(petal.get("bound"))
    v = _Facts(b)
    raw_terms = b.get("terms")
    terms = [int(t) for t in raw_terms] if isinstance(raw_terms, list) else []
    if v("stated") is not True or not terms:  # UF-3
        return Petal(pid, RED, NOT_STATED, STATEMENT, _silent(petal, props), quotes,
                     reading=v.noted)  # fmt: skip

    def decided(step: str, cause: str | None, reason: str) -> Petal:
        return Petal(pid, step, cause, STATEMENT, reason, quotes, reading=v.noted)

    least = min(terms)
    if v("adversary") == "weaker":  # UF-4
        return decided(RED, STATED, "the bound is stated against a weaker prover")
    if least < 80:  # UF-5
        return decided(RED, STATED, f"the stated bound has exponent {least}, under 80")
    basis = v("basis")
    said = "the bound is proved" if basis == "proved" else (
        "the stated bound is conjectured, not proved" if basis == "conjectured"
        else "the bound does not say whether it is proved")  # fmt: skip
    if basis != "proved" and least < 100:  # UF-6
        return decided(RED, STATED, f"{said}, and its exponent {least} is under 100")
    short = _coverage_short(v, coverage) if basis == "proved" else said
    covered = "a proved bound covers each reply as the row runs it"
    if short is None and least >= 128:  # UF-7
        return decided(GREEN, None, f"{covered}, every exponent 128 or more")
    if short is None and least >= 100:  # UF-8
        return decided(AMBER_UPPER, None, f"{covered}, with exponent {least}, under 128")
    return decided(AMBER_LOWER, None,
                   short or f"{said}, but its exponent {least} is under 100")  # UF-9  # fmt: skip


# ---------------------------------------------------------------- Machine-checked (MC-1 to MC-6)


def stated_reach_step(
    formal: Mapping[str, object], v: Callable[[str], object] | None = None
) -> str:
    """The step the publisher's words reach, before a proof build or a check lowers it. `v`
    reads a fact's value (by default straight from `formal`)."""
    v = v or (lambda key: _v(formal.get(key)))
    r = v("reach")
    if r in ("part", "protocol"):
        return AMBER_LOWER
    if r == "protocol_and_statement":
        return AMBER_UPPER
    if r == "verifier_run":
        if v("trusted_base") and v("input_code_unverified") is False:
            return GREEN
        return AMBER_UPPER
    return RED  # none, not_stated, or anything the table does not name: the lower step


def _formal_tree(formal: Mapping[str, object], stated: str) -> dict[str, object]:
    card = _m(formal.get("scope_card"))
    base = _v(formal.get("trusted_base"))
    theorem, url = formal.get("theorem"), formal.get("theorem_url")
    return {
        "stated_step": stated,
        "reach": str(_v(formal.get("reach"))),
        "tool": None if _v(formal.get("tool")) is None else str(_v(formal.get("tool"))),
        "theorem": None if theorem is None else str(theorem),
        "theorem_url": None if url is None else str(url),
        "trusted_base": [str(i) for i in base] if isinstance(base, list) else [],
        "input_code_unverified": _v(formal.get("input_code_unverified")),
        "scope_card": {
            row: {col: {"value": str(_v(_m(card.get(row)).get(col))),
                        "quotes": [_quote(q) for q in _quotes(_m(card.get(row)).get(col))]}
                  for col in SCOPE_COLS}
            for row in SCOPE_ROWS
        },
    }  # fmt: skip


def _axioms(found: object) -> set[str]:
    return {str(a) for a in found} if isinstance(found, list) else set()


def _toolchain(found: object) -> str:
    t = _m(found)
    return f"{t.get('name')} {t.get('version')}"


def machine_checked(  # noqa: PLR0911, PLR0912 (one return per line of the table)
    props: Mapping[str, object] | None,
    checks: Mapping[str, str],
    commit: str | None,
    build: Mapping[str, object] | None,
) -> Petal:
    pid = "machine_checked"
    petals, nr = read(props, commit)
    if petals is None or props is None:  # MC-1
        return _not_read(pid, nr or NO_PROPERTIES)
    petal = _m(petals.get(pid))
    fm = _m(petal.get("formal"))
    v = _Facts(fm)
    quotes = petal_quotes(pid, petal)
    stated = stated_reach_step(fm, v)
    formal = _formal_tree(fm, stated)
    r = _v(fm.get("reach"))
    if stated == RED:  # MC-2
        if r == "none":
            return Petal(pid, RED, STATED, STATEMENT, "stated that nothing is machine-checked",
                         quotes, formal=formal, reading=v.noted)  # fmt: skip
        return Petal(pid, RED, NOT_STATED, STATEMENT, _silent(petal, props), quotes,
                     formal=formal, reading=v.noted)  # fmt: skip
    f = failed(checks, LOWERED_BY[pid])
    if f and stated == GREEN:  # MC-3
        return _check_failed(pid, f, quotes, formal=formal)
    pin = _pin(props)
    pin7 = pin[:7]
    theorem = fm.get("theorem")
    recorded = _m(build)
    b_upstream = _m(recorded.get("upstream"))
    b_commit = str(b_upstream.get("commit"))
    b_name = _m(recorded.get("theorem")).get("name")
    at_pin = (build is not None and b_upstream.get("repo") == _m(props.get("upstream")).get("repo")
              and b_commit == pin and theorem is not None and b_name == theorem)  # fmt: skip
    pinned = _m(v("toolchain")) if at_pin else {}  # M2: the publisher's toolchain, verbatim
    used = _m(recorded.get("toolchain"))
    match = at_pin and bool(pinned) and all(
        used.get(k) == pinned.get(k) for k in ("name", "version"))  # fmt: skip
    if match:
        status, code = recorded.get("status"), recorded.get("exit_code")
        if status != "built" or code != 0:  # MC-4
            return Petal(pid, RED, CHECK_FAILED, TEST,
                         f"the recorded proof build has status {status}, exit code {code}", quotes,
                         ("proof_build",), formal)  # fmt: skip
        reported, declared = _axioms(recorded.get("axioms_reported")), _axioms(fm.get("axioms"))
        if reported != declared:  # MC-4
            return Petal(pid, RED, CHECK_FAILED, TEST,
                         f"the build reports axioms {', '.join(sorted(reported))}, the publisher "
                         f"declares {', '.join(sorted(declared))}", quotes, ("proof_build",),
                         formal)  # fmt: skip
    reach = _REACH_WORDS.get(str(r), str(r))
    if not match:  # MC-5
        if at_pin and not pinned:
            reason = "the publisher pins no toolchain, so no proof build can match"
        elif at_pin:
            reason = (f"the recorded build used {_toolchain(used)}, the publisher pins "
                      f"{_toolchain(pinned)}")  # fmt: skip
        elif build is not None:
            reason = (f"the recorded proof build is of {b_name} at {b_commit[:7]}, not the row's "
                      "theorem at its commit")  # fmt: skip
        elif theorem is None:
            reason = "no theorem is named, so no proof build is recorded"
        else:
            reason = "no proof build of the named theorem is recorded yet"
        return Petal(pid, None, PROOF_BUILD_NOT_RUN, STATEMENT, reason, quotes, formal=formal,
                     reading=v.noted)  # fmt: skip
    reason = f"a proof build recorded at {pin7} checks {reach}"  # MC-6
    if r == "verifier_run" and stated == AMBER_UPPER:
        unverified = v("input_code_unverified")
        but = ("no trusted base listed" if not v("trusted_base")
               else "input code outside the proof" if unverified is True
               else "input code not stated to be inside the proof")  # fmt: skip
        reason += f", but {but}"
    return Petal(pid, stated, None, STATEMENT, reason, quotes, formal=formal, reading=v.noted)


# ---------------------------------------------------------------- Weights hidden (WH-1 to WH-6)


def _visible(hiding: Mapping[str, object]) -> list[Mapping[str, object]]:
    found = hiding.get("visible")
    return [i for i in found if isinstance(i, Mapping)] if isinstance(found, list) else []


def weights_hidden(  # noqa: PLR0911, PLR0912 (one return per line of the table)
    props: Mapping[str, object] | None, checks: Mapping[str, str], commit: str | None
) -> Petal:
    pid = "weights_hidden"
    petals, nr = read(props, commit)
    petal = _m(petals.get(pid)) if petals is not None else {}
    h = _m(petal.get("hiding"))
    v = _Facts(h)
    visible = _visible(h) if petals is not None else None
    quotes = petal_quotes(pid, petal) if petals is not None else ()
    f = failed(checks, LOWERED_BY[pid])
    if f:  # WH-1
        return _check_failed(pid, f, quotes, visible=visible)
    if petals is None or props is None or visible is None:  # WH-2
        return Petal(pid, None, NOT_READ, STATEMENT, nr or NO_PROPERTIES)

    def decided(step: str, cause: str | None, reason: str) -> Petal:
        return Petal(pid, step, cause, STATEMENT, reason, quotes, visible=visible,
                     reading=v.noted)  # fmt: skip

    if v("verifier_gets_weights") is True:  # WH-3
        return decided(RED, STATED, "the verifier receives the weights")
    stated = v("stated")
    if stated is False:  # WH-3
        return decided(RED, STATED, "stated not to hide the weights")
    if stated is not True:  # WH-3: not_stated
        return decided(RED, NOT_STATED, _silent(petal, props))
    proof = v("proof")
    if proof not in ("protocol", "configuration_run"):  # WH-4 (none)
        return decided(AMBER_LOWER, None, "hiding is stated, with no zero-knowledge theorem")
    programs, listed = v("programs"), v("visible_listed") is True
    fitted = [str(i.get("item")) for i in visible if i.get("tag") == "fitted_to_weights"]
    if (proof == "configuration_run" and programs == "stated" and listed and visible
            and not fitted):  # WH-5 (W1: a listed set is copied, not empty)  # fmt: skip
        return decided(GREEN, None, "zero knowledge proved for the configuration the row runs, "
                       "with no listed visible value fitted to the weights")  # fmt: skip
    missing = []  # WH-6
    if proof == "protocol":
        missing.append("zero knowledge proved for the protocol only")
    if programs == "expected":
        missing.append("only expected of its programs")
    elif programs != "stated":
        missing.append("not stated for its programs")
    if not listed:
        missing.append("no list of visible values")
    elif not visible:
        missing.append("visible values listed but none copied")
    if fitted:  # the names are printed in the visible list below the reason
        missing.append(f"{len(fitted)} visible value{'s' * (len(fitted) != 1)} fitted to the "
                       "weights")  # fmt: skip
    if len(missing) > 1:
        missing[-1] = f"and {missing[-1]}"
    return decided(AMBER_UPPER, None, ", ".join(missing))


# ---------------------------------------------------------------- No third party trusted (NT)


def no_trusted_party(  # noqa: PLR0911 (one return per line of the table)
    props: Mapping[str, object] | None, commit: str | None
) -> Petal:
    """NT-1 to NT-6; no check lowers it."""
    pid = "no_trusted_party"
    petals, nr = read(props, commit)
    if petals is None or props is None:  # NT-1
        return _not_read(pid, nr or NO_PROPERTIES)
    petal = _m(petals.get(pid))
    t = _m(petal.get("trust"))
    v = _Facts(t)
    quotes = petal_quotes(pid, petal)

    def decided(step: str, cause: str | None, reason: str) -> Petal:
        return Petal(pid, step, cause, STATEMENT, reason, quotes, reading=v.noted)

    r = v("rests_on")
    rests_noted = v.noted  # N1: the value of rests_on is the reader's reading
    if r not in ("transparent", "open_ceremony", "fixed_parties", *_REST_WORDS):  # NT-2
        return decided(RED, NOT_STATED, _silent(petal, props))
    if r in _REST_WORDS:  # NT-3
        return decided(RED, STATED, f"soundness rests on {_REST_WORDS[str(r)]}")
    if r == "fixed_parties":  # NT-4
        return decided(AMBER_LOWER, None, "soundness rests on one honest party among a fixed set")
    if v("publicly_checkable") is False:  # NT-4
        return decided(AMBER_LOWER, None, "proofs are not publicly checkable")
    if r == "open_ceremony":  # NT-5 (N2)
        return decided(AMBER_UPPER, None, "soundness rests on an open setup ceremony whose "
                       "secret stays unknown if one participant was honest")  # fmt: skip
    if rests_noted:  # NT-6, N1: no quote says it in words
        return decided(GREEN, None, "read as resting on cryptographic assumptions alone, not "
                       "said in those words")  # fmt: skip
    return decided(GREEN, None, "stated to rest on cryptographic assumptions alone, with no "
                   "setup that produced a secret")  # NT-6  # fmt: skip


def statement_petals(
    props: Mapping[str, object] | None,
    checks: Mapping[str, str],
    commit: str | None,
    coverage: Coverage,
    build: Mapping[str, object] | None,
) -> dict[str, Petal]:
    """The four statement petals, each decided on its own (GL-7)."""
    return {
        "unforgeable": unforgeable(props, checks, commit, coverage),
        "weights_hidden": weights_hidden(props, checks, commit),
        "machine_checked": machine_checked(props, checks, commit, build),
        "no_trusted_party": no_trusted_party(props, commit),
    }


# ---------------------------------------------------------------- Faithful model (FM-1 to FM-7)


def _scores(found: object) -> list[int] | None:
    scores = _m(found).get("scores")
    if not isinstance(scores, list) or not scores or not all(isinstance(s, int) for s in scores):
        return None
    return [int(s) for s in scores]


_THRESHOLD_NAMES = (("green", "T_green"), ("upper", "T_upper"))
_LINE_WORDS = {"green": "rerun and Q8_0", "upper": "Q8_0 and Q4_K_M"}  # whose midpoint each is


def recheck(doc: Mapping[str, object]) -> dict[str, int]:
    """Spec 1.4, rule 3: each stored threshold is recomputed from its controls' scores with the
    same expression; any difference stops the board. Returns each threshold's score sum
    S_a + S_b, by step key."""
    steps = doc.get("steps")
    if not isinstance(steps, Mapping):
        return {}
    controls = {str(_m(c).get("id")): _m(c) for c in doc.get("controls") or ()}  # type: ignore[attr-defined]
    totals: dict[str, int] = {}
    for key, name in _THRESHOLD_NAMES:
        threshold = _m(steps.get(key))
        stored = threshold.get("value")
        if stored is None:
            continue
        ids = threshold.get("controls")
        found = [_scores(controls.get(str(i))) for i in ids] if isinstance(ids, list) else []
        if len(found) != 2 or found[0] is None or found[1] is None or (
                len(found[0]) != len(found[1])):  # fmt: skip
            raise IProofsError(ErrorKind.CONFIG, f"fidelity.json {name} {stored}, its controls "
                               "give no value")  # fmt: skip
        a, b = found[0], found[1]
        computed = (sum(a) + sum(b)) / (2 * len(a))
        if computed != stored:
            raise IProofsError(
                ErrorKind.CONFIG, f"fidelity.json {name} {stored}, its controls give {computed}"
            )
        totals[key] = sum(a) + sum(b)
    return totals


def _tie_step_tests(
    steps: Mapping[str, object],
    tests: Mapping[str, object],
    scores: Sequence[int],
    totals: Mapping[str, int],
    system: str,
) -> None:
    """F5: each stored step test is the test of the row's scores over its stored threshold: its
    threshold name, value and n match, and an exact test's p is counted again. A mismatch
    stops the board (rule 3)."""
    n = len(scores)
    for key, name in _THRESHOLD_NAMES:
        found = tests.get(key)
        if found is None:
            continue
        stored = _m(found)
        value = _m(steps.get(key)).get("value")
        where = f"fidelity.json {system} step test {key}"
        if stored.get("threshold") != name or stored.get("value") != value or (
                stored.get("n") != n):  # fmt: skip
            raise IProofsError(ErrorKind.CONFIG, f"{where} is for {stored.get('threshold')} = "
                               f"{stored.get('value')} over n = {stored.get('n')}, the stored "
                               f"step is {name} = {value} over n = {n}")  # fmt: skip
        if stored.get("method") == "exact" and key in totals:
            diffs = [2 * n * s - totals[key] for s in scores]
            p = sign_flip_p(diffs, exact_up_to=n, resamples=1, seed=0)
            if p != stored.get("p"):
                raise IProofsError(ErrorKind.CONFIG, f"{where} has p = {stored.get('p')}, the "
                                   f"scores give {p}")  # fmt: skip


def _alpha(doc: Mapping[str, object], level_alpha: float | None) -> float:
    """F5: the stored test's alpha, which equals the level's `fidelity.alpha` when it is given;
    never a default."""
    found = _m(doc.get("test")).get("alpha")
    if not isinstance(found, int | float) or isinstance(found, bool):
        raise IProofsError(ErrorKind.CONFIG, "fidelity.json stores step tests but no test alpha")
    if level_alpha is not None and float(found) != float(level_alpha):
        raise IProofsError(ErrorKind.CONFIG, f"fidelity.json alpha {found}, the level's "
                           f"fidelity.alpha is {level_alpha}")  # fmt: skip
    return float(found)


def faithful_model(  # noqa: PLR0911, PLR0912 (one return per line of the table)
    fidelity_state: str,
    fidelity_cause: str | None,
    doc: Mapping[str, object] | None,
    system: str,
    policy: str | None,
    level_alpha: float | None = None,
) -> Petal:
    """FM-1 to FM-7 (basis test throughout). The step tests are read from `doc`, never run; an
    exact one is counted again to tie it to the stored threshold (F5)."""
    pid = "faithful_model"

    def petal(step: str | None, reason: str, cause: str | None = None) -> Petal:
        return Petal(pid, step, cause, TEST, reason)

    if fidelity_state == "failed":  # FM-1
        return Petal(pid, RED, CHECK_FAILED, TEST,
                     "the rung's bar scores above the row's replies",
                     lowered_by=("fidelity",))  # fmt: skip
    if doc is None:  # FM-2
        return petal(None, "no fidelity record stored for the rung", NOT_DECIDED)
    if fidelity_state != "held":
        return petal(None, f"the Fidelity check is undecided: {fidelity_cause or 'no cause'}",
                     NOT_DECIDED)  # fmt: skip
    row = _m(_m(doc.get("rows")).get(system))
    scores = _scores(row)
    if scores is None:
        return petal(None, "no fidelity scores stored for the row", NOT_DECIDED)
    totals = recheck(doc)
    if policy != EXACT_MATCH:  # FM-3
        return petal(
            AMBER_LOWER,
            f"the claim's policy is {policy}, not exact match"
            if policy is not None
            else "no claim card found, so exact match is not shown",
        )
    steps, tests = doc.get("steps"), row.get("step_tests")
    if not isinstance(steps, Mapping) or not isinstance(tests, Mapping):  # FM-4
        return petal(AMBER_LOWER, "no step tests stored for the rung")
    _tie_step_tests(steps, tests, scores, totals, system)
    for key, _ in _THRESHOLD_NAMES:  # FM-4 (F1): a control missing or failed
        threshold = _m(steps.get(key))
        if threshold.get("value") is None:
            cause = threshold.get("cause") or "no value stored"
            return petal(AMBER_LOWER, f"the {_LINE_WORDS[key]} midpoint has no value ({cause}), "
                         "and the steps above need it")  # fmt: skip
    g, u = _m(tests.get("green")), _m(tests.get("upper"))
    if not g or not u:  # FM-4
        return petal(AMBER_LOWER, "no step tests stored for the rung")
    alpha = _alpha(doc, level_alpha)
    pg, vg = float(g["p"]), float(g["value"])  # type: ignore[arg-type]
    pu, vu = float(u["p"]), float(u["value"])  # type: ignore[arg-type]
    # FI-3's unit, each threshold named in words (the p values, alpha and n stay in fidelity.json)
    t_green = f"the {_LINE_WORDS['green']} midpoint, {vg:.2f} {SCORE_UNIT}"
    t_upper = f"the {_LINE_WORDS['upper']} midpoint, {vu:.2f} {SCORE_UNIT}"
    green_shown, upper_shown = pg < alpha, pu < alpha
    slots = doc.get("slots")
    if green_shown and slots == 1:  # FM-5 (F2)
        return petal(GREEN, f"shown above {t_green}")
    had = "no slot count is stored" if slots is None else f"the run had {slots} slots"
    if upper_shown:  # FM-6 (F3)
        if green_shown:
            return petal(AMBER_UPPER, f"shown above {t_green}, but {had} and green needs 1")
        return petal(AMBER_UPPER, f"shown above {t_upper}, but not the {_LINE_WORDS['green']} "
                     f"one, {vg:.2f}")  # fmt: skip
    if green_shown:  # FM-7 (F4)
        return petal(AMBER_LOWER, f"shown above {t_green}, not the {_LINE_WORDS['upper']} one, "
                     f"{vu:.2f}, and {had}")  # fmt: skip
    return petal(AMBER_LOWER, f"not shown above {t_upper}")  # FM-7


def glyph(petals: Mapping[str, Petal]) -> list[dict[str, object]]:
    """The five petals in drawing order (no field sums them, GL-8)."""
    return [petals[p].tree() for p in PETALS]


# ---------------------------------------------------------------- offline checks (GL-1, GL-9)


def _all_quotes(tree: object) -> list[Quote]:
    """Every quote of a properties file, wherever it sits."""
    out: list[Quote] = []
    if isinstance(tree, Mapping):
        for k, v in tree.items():
            if k == "quotes" and isinstance(v, list):
                out += [q for q in v if isinstance(q, Mapping)]
            else:
                out += _all_quotes(v)
    elif isinstance(tree, list):
        for v in tree:
            out += _all_quotes(v)
    return out


# U1: the exponent t of each 2^-t, 2^(-t) and /2^t in a stated bound
_EXPONENT = re.compile(
    r"2\s*(?:\^|\*\*)\s*[{(]?\s*[-\u2212]\s*(\d+)"
    r"|/\s*2\s*(?:\^|\*\*)\s*[{(]?\s*(\d+)"
    r"|2\s*<sup>\s*[-\u2212]\s*(\d+)\s*</sup>"
)


def properties_problems(  # noqa: PLR0912 (one branch per offline rule of spec 1.2)
    doc: Mapping[str, object], system_dir: Path, system_pin: str | None
) -> list[str]:
    """What the properties/2 schema cannot check (spec 1.2): the pin, the directory, the quote
    urls, and that the expression, terms, trusted base and axioms are copied from the quotes."""
    problems: list[str] = []
    upstream = _m(doc.get("upstream"))
    repo, pin = str(upstream.get("repo")), str(upstream.get("commit"))
    if system_pin is not None and pin != system_pin:
        problems.append(f"read at {pin}, system.yaml pins {system_pin}")
    if doc.get("system") != system_dir.name:
        problems.append(f"system {doc.get('system')!r} is not the directory {system_dir.name!r}")
    prefix = f"https://github.com/{repo}/blob/{pin}/"
    for q in _all_quotes(doc.get("petals")):
        if not str(q.get("url")).startswith(prefix):
            problems.append(f"quote url {q.get('url')} is not under {prefix}")
    petals = _m(doc.get("petals"))
    bound = _m(_m(petals.get("unforgeable")).get("bound"))
    expr = _v(bound.get("expression"))
    if isinstance(expr, str):
        texts = [str(q.get("text")) for q in _quotes(bound.get("expression"))]
        if not any(expr in t for t in texts):
            problems.append(f"expression {expr!r} is in none of its quotes")
        raw = bound.get("terms")
        terms = [int(t) for t in raw] if isinstance(raw, list) else []
        exps = [int(next(g for g in m if g)) for m in _EXPONENT.findall(expr)]
        if exps and sorted(set(exps)) != sorted(set(terms)):  # U1: both ways
            problems.append(f"expression exponents {exps} differ from terms {terms}")
        whole = sorted({int(x) for x in re.findall(r"\d+", expr)})
        if not exps and terms and whole != sorted(set(terms)):  # no 2^-t form: both ways too
            problems.append(f"numbers {whole} in the expression differ from terms {terms}")
    formal = _m(_m(petals.get("machine_checked")).get("formal"))
    url = formal.get("theorem_url")
    if url is not None and not str(url).startswith(prefix):
        problems.append(f"theorem_url {url} is not under {prefix}")
    base = _v(formal.get("trusted_base"))
    base_items = [str(i) for i in base] if isinstance(base, list) else []
    texts = [str(q.get("text")) for q in _quotes(formal.get("trusted_base"))]
    for item in base_items:
        if not any(item in t for t in texts):
            problems.append(f"trusted_base item {item!r} is in none of its quotes")
    axioms = formal.get("axioms")
    for a in axioms if isinstance(axioms, list) else []:
        if str(a) not in base_items:
            problems.append(f"axiom {a!r} is not in trusted_base")
    return problems


def not_read_rows(board: Mapping[str, object]) -> list[str]:
    """GL-9: every petal of the board that is hollow because its properties file is not read."""
    out = []
    for rung in board.get("rungs") or ():  # type: ignore[attr-defined]
        for row in _m(rung).get("rows") or ():  # type: ignore[attr-defined]
            for p in _m(row).get("glyph") or ():  # type: ignore[attr-defined]
                if _m(p).get("state") == HOLLOW and _m(p).get("cause") == NOT_READ:
                    out.append(f"{_m(rung).get('id')}/{_m(row).get('system')}: "
                               f"{_m(p).get('id')} not read")  # fmt: skip
    return out
