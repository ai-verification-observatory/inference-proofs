"""The fixed words the pages print for stored values, and the numbers as they are shown.

Scope, grade, tier, null reasons, failure kinds, outcomes, states and families are worded through
the tables here, keyed by the stored ids (RFC-0009 S2), so an id with no words stops the build.
`sig4`, `amount` and `shown` print a stored value at four significant digits in a reading unit
(S4); they never change the stored value. Nothing here reads the view.
"""

import html
import math
import re


def e(s):
    return html.escape(str(s), quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ------------------------------------------------------------------ words
# The fixed words a stored value prints as (RFC-0009 S2: the generator may word a stored value;
# it never changes it). Keyed by the stored ids, so an id with no words stops the build.
STATE_WORD = {"yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "Not stated"}
# None: a row under a pending disclosure, drawn with no state (RFC-0016 OVR-8; words.css .sl.none)
STATE_CLS = {"yes": "yes", "partly": "partly", "no": "no", "not_stated": "unstated", None: "none"}
STATE_ORDER = ("yes", "partly", "no", "not_stated")  # the legend's order, display only
FAMILY_WORD = {"proved": "Proved", "attested": "Attested", "re_executed": "Re-executed",
               "fingerprinted": "Fingerprinted", "unchecked": "Unchecked"}  # fmt: skip
STATUS_WORD = {"active": "active", "unmaintained": "unmaintained", "archived": "archived",
               "no_repository": "no repository"}  # fmt: skip
SCOPE_WORD = {
    None: "none (not a timed number)",
    "setup": "setting up",
    "commit": "preparing the model",
    "prove.steady": "proving, steady state",
    "prove.session": "proving session",
    "whole_wall": "the whole run, wall clock",
    "verify": "checking ({cpus} CPU threads)",
    "verify.single_thread": "checking (one CPU thread)",
    "primitive": "one primitive",
}
SESSION_LINE = "proving session, start-up included on both sides"
# RFC-0004 INV-DERIVE-11: the warm overhead names both scopes wherever it appears
WARM = "overhead_vs_production_warm"
WARM_LINE = ("proving session (start-up included; it proves one request at a time) vs warm "
             "serving (steady)")  # fmt: skip
STEADY_LINE = "steady state on both sides, start-up excluded"
# the scope line of an overhead, by its stored statistic
SCOPE_LINES = {"overhead_vs_production_prove.steady": STEADY_LINE,
               "overhead_vs_production_prove.session": SESSION_LINE, WARM: WARM_LINE}  # fmt: skip
# the overview's scopes in short, the one line under a figure (the full words ride in its title)
SCOPE_SHORT = {"prove.steady": "steady", "prove.session": "session", "verify": "{cpus} threads",
               "overhead_vs_production_prove.steady": "steady",
               "overhead_vs_production_prove.session": "session", WARM: "session vs warm"}  # fmt: skip
# RFC-0004 D-SPAB-S, D-BPAB, D-VSPAB: the one basis of the overview's three cost columns; a
# value per bit prints per Gbit (x 1e9), in seconds or bytes with their own prefix
PER_GBIT = "per token, per Gbit of active weights"
PER_GBIT_BASE = {"s/bit_token": "s", "B/bit_token": "B"}
# RFC-0004 INV-DERIVE-7: printed beside a figure per active weight bit wherever it is shown
PER_BIT_LIMIT = ("Attention cost grows with prompt length and is not in this normaliser, so two "
                 "workloads of one model with different prompt lengths differ for that reason too "
                 "(the SASH workloads have 1,024 and 4,096 prompt tokens). Weight bits are as the "
                 "workload records them, with their basis and source.")  # fmt: skip
BITS_BASIS = {"stated": "as the system states it", "file_size": "from the file size",
              "computed": "computed from the files"}  # fmt: skip
GRADE_WORD = {
    "measured": "recorded by our harness",
    "derived": "calculated from recorded numbers",
    "projected": "projected, not measured",
    "external": "as the system publishes it",
    "asserted": "set in the reference file",
}
TIER_WORD = {
    "reported": "one runner, not yet checked",
    "peer-reviewed": "reviewed, not yet rerun",
    "reproduced": "rerun by an unaffiliated runner",
}
NULL_WORD = {
    "not_externally_observable": "The harness cannot observe this number from outside the system.",
    "fewer_than_two_proofs": "Fewer than two proofs in a run, so there is no per-proof figure.",
    "not_applicable": "Does not apply to this setup.",
    "step_failed": "The step that records this number failed in these runs.",
    "not_measurable_on_profile": "Not measurable on {gpu} (RFC-0015 NM-1).",
    "missing_input": "A number this one is calculated from is missing.",
}
# A missing overhead names its baseline: overhead divides by production serving's GPU-seconds (D-OVERHEAD-S).
NM1_OVERHEAD = "Production serving could not run this model on the serving GPUs, so there is no baseline to divide by (RFC-0015 NM-1)."
NO_SERVING_OVERHEAD = "No production-serving run on this profile's GPU model is in the release, so there is no baseline to divide by (RFC-0015 SRV-6)."
NOT_RECORDED = "Not recorded in these runs."
FAIL_KIND = {
    "config": "a configuration error",
    "environment": "a fault on the runner's machine",
    "integrity": "an integrity check failed",
    "fetch": "a download failed",
    "adapter": "the adapter failed",
    "timeout": "the run ran out of time",
    "resource": "the machine ran out of resources",
    "policy": "a policy check stopped it",
    "internal": "an error in our harness",
}
FAIL_STEP = {
    "setup": "while setting up",
    "commit": "while preparing the model",
    "prove": "while proving",
    "verify": "while checking",
    "upload": "while uploading its proofs",
    "fetch": "while fetching",
}
# RFC-0008 outcomes, each count as stored; zero counts are left out, and no total is printed
OUTCOME_WORDS = (
    ("rejected", "the checker rejected {n}"),
    ("invalid_call", "it refused {n} as malformed input"),
    ("accepted", "it accepted {n}"),
    ("no_verdict", "{n} ended with no verdict"),
    ("prover_failed", "in {n} the prover would not build the tampered proof"),
    ("error", "{n} ended in an error"),
    ("void", "{n} were void"),
    ("not_applicable", "{n} do not apply to this setup"),
)
OUTCOME_VERB = {"accepted": "accepted", "rejected": "rejected", "invalid_call": "refused",
                "no_verdict": "gave no verdict on", "error": "failed on"}  # fmt: skip
# one control's outcome in a run, as a property's list on the system page prints it (RFC-0016 OVR-7)
OUTCOME_SHORT = {
    "rejected": "rejected", "accepted": "accepted", "invalid_call": "refused as malformed",
    "no_verdict": "no verdict", "prover_failed": "the prover would not build it",
    "error": "error", "void": "void", "not_applicable": "does not apply", "not_run": "not run",
}  # fmt: skip
# a listed run's status on the release page
RUN_STATUS = {"completed": "completed", "failed": "failed"}
# an accepted control record, by whether its own expected set holds the outcome (`passed`)
ACCEPTED_WHY = {
    ("system", True): "{id}, the control test below, which expects acceptance",
    ("shared", True): "{id}, whose expected outcomes include acceptance",
    ("system", False): "{id}, outside its expected outcomes",
    ("shared", False): "{id}, outside its expected outcomes",
}
# RFC-0016 OVR-8 and RFC-0008 §Disclosure: what a page prints while a disclosure is pending
PENDING = (
    "A disclosure is pending (RFC-0008): a control outcome of this system is under embargo. "
    "Until the finding is published, the outcomes of its controls are not printed and its "
    "states are not drawn; the states below are the ones its documentation states at the pin."
)
PENDING_TAMPER = (
    "A disclosure is pending (RFC-0008): the outcomes of this setup's controls are not printed "
    "until the finding is published."
)
COUNT_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
              8: "eight", 9: "nine", 10: "ten"}  # fmt: skip
REF_LEAD = "The same model and task without a proof: production serving checks nothing, a rerun needs the weights; they are baselines, not systems."


def count_word(n):
    return COUNT_WORD.get(n, f"{n:,}")


# ------------------------------------------------------------------ numbers (display only)
# A stored value prints at four significant digits in a unit chosen for reading (S4); the sort key
# and the record keep the stored value in its base unit.
def sig4(v):
    if v == 0:
        return "0"
    places = 3 - math.floor(math.log10(abs(v)))
    if places >= 0:
        return f"{v:,.{places}f}"
    return f"{round(v, places):,.0f}"  # 122880 prints 122,900: four digits, then zeros


# the SI prefixes a reading unit may take, largest first
SI = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"),
      (1e-9, "n"))  # fmt: skip
IEC = ((1024.0**2, "Ti"), (1024.0, "Gi"), (1.0, "Mi"), (1 / 1024, "Ki"))  # from MiB


def prefixed(v, base, steps=SI, lo=1e-9, hi=1e12):
    """(number, unit) with the prefix that puts the number between 1 and 1000 where one can:
    68.21 µs, not 0.06821 ms. The value is rounded to four digits first, so 999.96 µs prints
    1.000 ms, not 1,000 µs."""
    r = float(f"{v:.4g}")
    if r == 0:
        return "0", base
    steps = [(f, p) for f, p in steps if lo <= f <= hi]
    f, p = next(((f, p) for f, p in steps if abs(r) >= f), steps[-1])
    return sig4(r / f), p + base


def seconds(v):
    """A time: ns to s with their prefix, then minutes and hours."""
    r = float(f"{v:.4g}")
    if abs(r) < 1e3:
        return prefixed(v, "s", hi=1.0)
    return (sig4(v / 60), "min") if abs(r) < 6e4 else (sig4(v / 3600), "h")


# the stored units that take a prefix: (base unit, prefixes, smallest factor)
PREFIXED = {"B": ("B", SI, 1.0), "MiB": ("B", IEC, 1 / 1024), "J": ("J", SI, 1e-9)}
UNIT_WORDS = {"token": "positions", "token/s": "positions/s", "USD/1k_token": "USD / 1k positions"}


def amount(v, unit):
    """(number, unit words) for a stored value in its stored unit, in the unit that reads it with
    no leading zeros (S4)."""
    if unit in PER_GBIT_BASE:  # per bit, printed per Gbit; the basis is in the column's head
        return amount(v * 1e9, PER_GBIT_BASE[unit])
    if unit == "s":
        return seconds(v)
    if unit in PREFIXED:
        base, steps, lo = PREFIXED[unit]
        return prefixed(v, base, steps, lo)
    base, slash, per = unit.partition("/")
    if slash and base in ("s", "B"):  # s/token, B/token: the numerator takes the prefix
        n, u = amount(v, base)
        return n, f"{u}/{per}"
    return sig4(v), UNIT_WORDS.get(unit, unit)


def shown(v, unit):
    n, u = amount(v, unit)
    return f"{n}×" if unit == "ratio" else f"{n} {u}"


def spread_parts(f):
    """The sample size and the range, the two parts the overview shows (S3)."""
    st = f.get("stats")
    if not st:
        return []
    lo, hi = (shown(st[k], f["unit"]) for k in ("min", "max"))
    if f["unit"] == "token":  # the figure above names the unit
        lo, hi = (x.rsplit(" ", 1)[0] for x in (lo, hi))
    return [f"{st['n']} completed, {st['n_failed']} failed", f"{lo} to {hi}"]


def spread_line(f):
    """The whole spread as a plate prints it: sample size, range, mean and sd (S3)."""
    st = f["stats"]
    parts = [*spread_parts(f), f"mean {shown(st['mean'], f['unit'])}"]
    if st.get("stdev") is not None:
        parts.append("sd 0" if st["stdev"] == 0 else f"sd {shown(st['stdev'], f['unit'])}")
    return " · ".join(parts)


def gpu_words(cfg):
    g = cfg["gpu"]
    return f"{count_word(g['count'])} {g['short'] or g['model']}"


def scope_words(f, cfg):
    return SCOPE_WORD[f["scope"]].format(cpus=cfg["verifier"]["logical_cpus"])


def why_words(f, cfg):
    """Why a figure has no value, from its stored null reason (or its absence from the runs)."""
    if not f["recorded"]:
        return NOT_RECORDED
    if f["null_reason"] == "not_measurable_on_profile" and f["metric"].startswith("overhead_"):
        return NM1_OVERHEAD
    if f["null_reason"] in ("not_applicable", "missing_input") and f["metric"].startswith(
        "overhead_"
    ):
        return NO_SERVING_OVERHEAD
    return NULL_WORD[f["null_reason"]].format(gpu=gpu_words(cfg))


def labels(f, cfg):
    scope = WARM_LINE if f.get("metric") == WARM else scope_words(f, cfg)  # INV-DERIVE-11
    return [("scope", scope), ("grade", GRADE_WORD[f["grade"]]),
            ("checked", TIER_WORD[f["tier"]])]  # fmt: skip
