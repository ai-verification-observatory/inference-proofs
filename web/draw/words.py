"""The fixed words the pages print for stored ids, and the numbers as they are shown.

Check ids, states, causes, scopes, grades, tiers, null reasons and units are worded through the
tables here, keyed by the stored ids, so an id with no words stops the build. `number` prints a
stored value at four significant digits in a reading unit; it never changes the stored value.
The check definitions are RFC-0018's table in short. Nothing here reads the view.
"""

import html
import math
import re


def e(s):
    return html.escape(str(s), quote=True)


def curly(text):
    """Straight double quotes curly: opening at the start or after a space or bracket, closing
    elsewhere."""
    return re.sub(r'(?:^|(?<=[\s(\[{]))"', "“", text).replace('"', "”")


def quoted(text):
    """A publisher's words as the card stores them: escaped, quotes curly, `code` set as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", e(curly(str(text))).replace("&quot;", '"'))


# ------------------------------------------------------------------ the six checks (RFC-0018)
CHECK_NAME = {"run": "Run", "model": "Model", "prompt": "Prompt", "reply": "Reply",
              "no_weight_file": "No weight file", "fidelity": "Fidelity"}  # fmt: skip
CHECK_HELD = {
    "run": "Three session slots each hold a complete session, built from the public pin, "
    "unpatched, with no weakening flag.",
    "model": "A proof made after one weight was changed is not accepted, and an honest proof "
    "checked against the changed weights' commitment is refused, in 3 of 3 trials each.",
    "prompt": "A proof checked with one prompt token changed is refused, in 3 of 3 trials.",
    "reply": "Every accepted proof covers all 512 reply tokens, and a changed reply token is "
    "refused at the first, the last and one seeded interior position, in 3 of 3 trials each.",
    "no_weight_file": "Every counted verdict came from a check run with no GPU visible, on a "
    "filesystem holding no model file, under a file-open trace that names no model file.",
    "fidelity": "The system's replies score above the model's bar: the damaged copy of the model "
    "that every honest copy scores above, scored by the leading tokens each reply shares with the "
    "publisher's 16-bit model.",
}
CHECK_FAILED = {
    "run": "A slot has five incomplete runs, or a counted session used a weakening flag.",
    "model": "Any trial is accepted.",
    "prompt": "Any trial is accepted.",
    "reply": "A proof covers fewer reply tokens, or any trial is accepted.",
    "no_weight_file": "The trace names a model file, or a check needed one.",
    "fidelity": "The bar scores above the system's replies.",
}
CHECK_EVIDENCE = {
    "run": "every session's run record",
    "model": "the controls record",
    "prompt": "the controls record",
    "reply": "the run records and the controls record",
    "no_weight_file": "the file-open trace of every check",
    "fidelity": "the model's fidelity record",
}
STATE_WORD = {"held": "held", "failed": "failed", "undecided": "undecided"}

# ------------------------------------------------------------------ the five petals (RFC-0018 §The glyph)
PETAL_NAME = {"unforgeable": "Unforgeable", "weights_hidden": "Weights hidden",
              "faithful_model": "Faithful model", "any_model": "Any model",
              "no_trusted_party": "Only the verifier trusted"}  # fmt: skip
PETAL_WORD = {"green": "green", "amber": "amber", "red": "red", "hollow": "not decided"}
BASIS_WORD = {"statement": "the publisher's documents", "test": "our checks",
              "run": "our runs"}  # fmt: skip
# what each colour means for each petal, RFC-0018's table in short: (green, amber, red)
PETAL_RULE = {
    "unforgeable": (
        "A soundness level of 128 bits or more, proven for the verifier code the system runs.",
        "A level that is conjectured, below 128 bits, stated per part only, or proven for the "
        "protocol but not for the code run.",
        "No level stated, or our Model, Prompt or Reply check failed.",
    ),
    "weights_hidden": (
        "Zero knowledge proven for the program run, with no leak beyond public sizes.",
        "Hidden with leaks the publisher lists, or proven for the protocol but not for the "
        "program run.",
        "The checker receives the weights, hiding is off or not stated, or our No weight file "
        "check failed.",
    ),
    "faithful_model": (
        "The replies are not shown below a second run of the publisher's 16-bit model.",
        "The replies score above the model's bar, and the second run of the 16-bit model scores above them.",
        "Our Fidelity check failed.",
    ),
    "any_model": (
        "The system passed on every model of the level.",
        "It passed on more than one model, not all.",
        "It passed on one model or none.",
    ),
    "no_trusted_party": (
        "Soundness rests on cryptographic assumptions alone (for example a random oracle): no "
        "setup ceremony, hardware maker's key or third party. Public files fixed before the hash "
        "do not count: every non-interactive proof has them.",
        "One honest party among several, or a setup the publisher says anyone can reproduce.",
        "A trusted setup, hardware attestation or a trusted key, or not stated.",
    ),
}
CAUSE_WORD = {
    "system limit": "the system cannot do what the test needs; the publisher's sentence is quoted",
    "not run": "the test has not been run",
    "not resolved": "the test ran and decided nothing",
    "not reproduced": "failed in our adapter, not yet reproduced outside it",
}

# ------------------------------------------------------------------ labels of a stored figure
SCOPE_SHORT = {None: "", "prove.steady": "steady", "prove.session": "session",
               "whole_wall": "session", "verify": "check", "commit": "commit",
               "setup": "setup", "verify.single_thread": "check, one thread"}  # fmt: skip
SCOPE_WORD = {
    None: "not a timed number",
    "setup": "setting up",
    "commit": "committing to the model",
    "prove.steady": "steady state, after the first release group",
    "prove.session": "the whole session, start-up included",
    "whole_wall": "the whole session, from commit to the last proof",
    "verify": "checking",
    "verify.single_thread": "checking on one CPU thread",
    "primitive": "one primitive",
}
GRADE_WORD = {
    "measured": "recorded by our harness",
    "derived": "calculated from recorded numbers",
    "projected": "projected, not measured",
    "external": "as the system publishes it",
    "asserted": "set in the reference file",
}
TIER_WORD = {
    "reported": "one runner, not reproduced",
    "peer-reviewed": "reviewed, not rerun",
    "reproduced": "rerun by an unaffiliated runner",
}
NULL_WORD = {
    "not_externally_observable": "not observable from outside the system",
    "fewer_than_two_proofs": "fewer than two proofs",
    "not_applicable": "does not apply",
    "step_failed": "the step that records it failed",
    "not_measurable_on_profile": "not measurable on this GPU",
    "missing_input": "a number it is calculated from is missing",
}


# ------------------------------------------------------------------ numbers (display only)
def sig(v, d=4):
    """v at d significant digits, thousands separated."""
    if v == 0:
        return "0"
    places = d - 1 - math.floor(math.log10(abs(v)))
    if places >= 0:
        return f"{v:,.{places}f}"
    return f"{round(v, places):,.0f}"


SI = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"),
      (1e-9, "n"))  # fmt: skip


def prefixed(v, base, lo=1e-9, hi=1e12, d=4):
    """(number, unit) with the prefix that puts the number between 1 and 1000 where one can. The
    value is rounded to its d digits first, so 999.96 ms prints 1.000 s."""
    r = float(f"{v:.{d}g}")
    if r == 0:
        return "0", base
    steps = [(f, p) for f, p in SI if lo <= f <= hi]
    f, p = next(((f, p) for f, p in steps if abs(r) >= f), steps[-1])
    return sig(r / f, d), p + base


def seconds(v, d=4):
    """A time: ns to s with their prefix, then minutes and hours."""
    r = float(f"{v:.{d}g}")
    if abs(r) < 1e3:
        return prefixed(v, "s", hi=1.0, d=d)
    return (sig(v / 60, d), "min") if abs(r) < 6e4 else (sig(v / 3600, d), "h")


def usd(v, d=4):
    """An amount in USD, below 1 USD in cents."""
    if abs(v) >= 1 or v == 0:
        return sig(v, d), "USD"
    return sig(v * 100, d), "¢"


# a stored unit -> how its value reads: (number, unit words). Per request reads per reply: the
# request is the level's one request, and its reply is what each proof covers (RFC-0018)
def number(v, unit):  # noqa: PLR0911 (one return per stored unit)
    if unit == "ratio":
        return sig(v), "×"
    if unit == "gpu_s/request":
        n, u = seconds(v)
        return n, f"GPU-{u}/reply"
    if unit == "s/request":
        n, u = seconds(v)
        return n, f"{u}/reply"
    if unit == "USD/request":
        n, u = usd(v)
        return n, f"{u}/reply"
    if unit == "B/request":
        n, u = prefixed(v, "B", lo=1.0)
        return n, f"{u}/reply"
    if unit == "USD/gpu_hour":
        return sig(v), "USD per GPU-hour"
    if unit == "nat/token":
        return sig(v), "nats/token"
    raise KeyError(f"no words for the unit {unit!r}")


def shown(v, unit):
    n, u = number(v, unit)
    return f"{n}{u}" if unit == "ratio" else f"{n}\u00a0{u}"


def params(n):
    """A parameter count in billions, or millions below one billion ("400B", "8.03B", "137M")."""
    text = sig(n / 1e9, 3) if n >= 1e9 else sig(n / 1e6, 3)
    text = text.rstrip("0").rstrip(".") if "." in text else text  # "17.0" reads "17"
    return f"{text}B" if n >= 1e9 else f"{text}M"


def architecture(total, active):
    """ "MoE, 400B total, 17B active" or "Dense, 8.03B": a mixture of experts reads fewer
    parameters per token than it holds."""
    if active and active < total:
        return f"MoE, {params(total)} total, {params(active)} active"
    return f"Dense, {params(total)}"


def labels(f):
    """A figure's labels in words, for its title: scope, grade, evidence, sample size, record."""
    parts = [f"scope: {SCOPE_WORD[f['scope']]}", f"grade: {GRADE_WORD[f['grade']]}",
             f"evidence: {TIER_WORD[f['tier']]}"]  # fmt: skip
    if f["n"] is not None:
        parts.append(f"n = {f['n']}")
    parts.append(f"record: {f['source']}")
    return "; ".join(parts)


def sub_words(f, n=None):
    """The one line under a figure: its scope in a word and its sample size."""
    count = f["n"] if f["n"] is not None else n
    parts = [SCOPE_SHORT[f["scope"]], f"n\u00a0=\u00a0{count}" if count is not None else ""]
    return " · ".join(p for p in parts if p)
