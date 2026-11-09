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
STATE_CLS = {"yes": "yes", "partly": "partly", "no": "no", "not_stated": "unstated"}
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
    "prove.session": "proving session, start-up included",
    "whole_wall": "the whole run, wall clock",
    "verify": "checking ({cpus} CPU threads)",
    "verify.single_thread": "checking (one CPU thread)",
    "primitive": "one primitive",
}
# RFC-0004 INV-DERIVE-11: the warm overhead names both scopes wherever it appears
WARM = "overhead_vs_production_warm"
WARM_LINE = ("proving session (start-up included; it proves one request at a time) vs warm "
             "serving (steady)")  # fmt: skip
STEADY_LINE = "steady state on both sides, start-up excluded"
# the scope line of an overhead, by its stored statistic
SCOPE_LINES = {"overhead_vs_production_prove.steady": STEADY_LINE, WARM: WARM_LINE}
# the overview's scopes in short, the one line under a figure (the full words ride in its title)
SCOPE_SHORT = {"prove.steady": "steady", "prove.session": "with start-up",
               "verify": "{cpus} threads", "overhead_vs_production_prove.steady": "steady",
               WARM: "with start-up vs warm"}  # fmt: skip
# RFC-0004 D-SPAB-S, D-BPAB, D-VSPAB: the one basis of the overview's three cost columns; a
# value per bit prints per Gbit (x 1e9), in seconds or bytes with their own prefix
PER_GBIT = "per token, per Gbit of active weights"
PER_GBIT_BASE = {"s/bit_token": "s", "B/bit_token": "B"}
# RFC-0004 INV-DERIVE-7: printed beside a figure per active weight bit wherever it is shown
PER_BIT_LIMIT = ("Attention cost grows with prompt length and is not in this normaliser, so two "
                 "workloads of one model with different prompt lengths differ for that reason too "
                 "({prompts}). Weight bits are as the workload records them, with their basis and "
                 "source.")  # fmt: skip
BITS_BASIS = {"stated": "stated by the system", "file_size": "from the file size",
              "computed": "computed from the files"}  # fmt: skip
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
# serving ran on this GPU model, but not this workload
NO_SERVING_WORKLOAD = ("No production-serving run of this workload ({batch}) is in the release, so "
                       "there is no baseline to divide by (RFC-0015 SRV-6).")  # fmt: skip
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
    ("rejected", "rejected {n}"),
    ("invalid_call", "refused as malformed {n}"),
    ("accepted", "accepted {n}"),
    ("no_verdict", "no verdict {n}"),
    ("prover_failed", "the prover would not build it {n}"),
    ("error", "error {n}"),
    ("void", "void {n}"),
    ("not_applicable", "did not apply {n}"),
)
# RFC-0008: each control's tamper in a few words, beside its id
CONTROL_WORDS = {
    "C1": "changed output token", "C2": "changed prompt token", "C3": "perturbed weights",
    "C4": "proof replayed for another request", "C5": "truncated part", "C6": "flipped bit",
    "C7": "proofs of two requests swapped", "C8": "dropped part",
    "P1": "proved with other weights", "P2": "proved at another precision",
}  # fmt: skip
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
# an accepted trial that tampered with a part the system declares its verify step does not read
# (RFC-0008, amendment of 2026-11-09: a gap in the control design, not a finding)
NOT_READ = "tests nothing"
NOT_READ_HEAD = "accepted only on {parts}, which <code>verify</code> does not read; tests nothing"
COUNT_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
              8: "eight", 9: "nine", 10: "ten"}  # fmt: skip


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
PREFIXED = {"B": ("B", SI, 1.0), "J": ("J", SI, 1e-9)}
MIB = 1024.0**2  # a MiB in bytes: memory prints in the SI family, as proof sizes do
# the glossary's term (docs/spec/10-glossary.md, Tokens covered)
UNIT_WORDS = {"token": "tokens", "token/s": "tokens/s"}
PCT = "\u202f%"  # a percent sign never leaves its number


def per_unit(v, unit):
    """A rate below 1 a second per minute, below 1 a minute per hour; a cost per 1M tokens, in
    USD, below 1 USD in cents."""
    if unit == "token/s":
        factor, per = next(((k, p) for k, p in ((1, "s"), (60, "min"), (3600, "h"))
                            if abs(v * k) >= 1), (3600, "h"))  # fmt: skip
        return sig4(v * factor), f"tokens/{per}"
    usd = v * 1000
    if abs(usd) >= 1 or usd == 0:
        return sig4(usd), "USD per 1M tokens"
    return sig4(usd * 100), "\u00a2 per 1M tokens"


def amount(v, unit):
    """(number, unit words) for a stored value in its stored unit, in the unit that reads it with
    no leading zeros (S4)."""
    if unit in PER_GBIT_BASE:  # per bit, printed per Gbit; the basis is in the column's head
        return amount(v * 1e9, PER_GBIT_BASE[unit])
    if unit in ("token/s", "USD/1k_token"):
        return per_unit(v, unit)
    if unit == "s":
        return seconds(v)
    if unit == "MiB":
        v, unit = v * MIB, "B"
    if unit in PREFIXED:
        base, steps, lo = PREFIXED[unit]
        return prefixed(v, base, steps, lo)
    base, slash, per = unit.partition("/")
    if slash and base in ("s", "B", "gpu_s"):  # s/token, B/token: the numerator takes the prefix
        n, u = amount(v, "s" if base == "gpu_s" else base)  # GPU-seconds: seconds summed over GPUs
        return n, f"{u}/{per}"
    return sig4(v), UNIT_WORDS.get(unit, unit)


def shown(v, unit):
    n, u = amount(v, unit)
    return f"{n}×" if unit == "ratio" else f"{n} {u}"


def range_words(lo, hi, unit, n):
    """A range with its unit once: "67.61 to 68.91 µs"; two units only where the prefix
    changes inside it ("999.9 µs to 1.001 ms"); a ratio keeps its sign on both ends; ends alike
    at four digits read as the one value "in all <n> runs"."""
    if unit == "ratio":
        return f"{shown(lo, unit)} to {shown(hi, unit)}"
    (a, u), (b, w) = amount(lo, unit), amount(hi, unit)
    if (a, u) == (b, w):  # the ends differ below four digits
        return f"{a} {u} in all {n} runs"
    return f"{a} to {b} {u}" if u == w else f"{a} {u} to {b} {w}"


def title_spread(f):
    """The spread in an overview cell's title: the sample size and the range (S3)."""
    st = f.get("stats")
    if not st:
        return ""
    return (f"{st['n']} completed, {st['n_failed']} failed, "
            f"{range_words(st['min'], st['max'], f['unit'], st['n'])}")  # fmt: skip


def sd_words(f):
    """The standard deviation as a share of the mean ("sd 0.877 %"), unit-free, so plates side
    by side read alike, the range beside it carrying the unit; "sd < 0.1 %" below that, its
    sign held to both sides; in the mean's unit only where the mean is 0; "" when none is
    stored. The record keeps the stored value."""
    st, unit = f["stats"], f["unit"]
    sd, mean = st.get("stdev"), st["mean"]
    if sd is None:
        return ""
    if sd == 0:
        return "sd 0"
    if not mean:
        return f"sd {shown(sd, unit)}"
    share = abs(sd / mean) * 100
    if share < 0.1:
        return f"sd\u00a0<\u00a00.1{PCT}"
    return f"sd {f'{share:#.3g}'.rstrip('.')}{PCT}"  # three digits, a trailing zero kept


def spread_line(f, count=False):
    """The spread as a system page prints it (S3): the range with its unit once and the mean
    ("28.83 to 29.88 tokens/s, mean 29.42"), then the sd; a constant, or ends alike at four
    digits, as "1,024 tokens in all 4 runs". count: the sample size first, where no runs line
    above names it."""
    st, unit = f["stats"], f["unit"]
    parts = [f"{st['n']} completed, {st['n_failed']} failed"] if count else []
    if st["min"] == st["max"]:
        return " · ".join([*parts, f"{shown(st['min'], unit)} in all {st['n']} runs"])
    rng = range_words(st["min"], st["max"], unit, st["n"])
    if rng.endswith(" runs"):  # the ends alike at four digits: the value once, then the sd
        parts.append(f"{shown(st['mean'], unit)} in all {st['n']} runs")
    else:
        hi_unit = amount(st["max"], unit)[1]
        m, mu = amount(st["mean"], unit)
        mean = (f"mean {m}" if mu == hi_unit and unit != "ratio"
                else f"mean {shown(st['mean'], unit)}")  # fmt: skip
        parts.append(f"{rng}, {mean}")
    if sd := sd_words(f):
        parts.append(sd)
    return " · ".join(parts)


def gpu_words(cfg):
    g = cfg["gpu"]
    return f"{count_word(g['count'])} {g['short'] or g['model']}"


# RFC-0004 INV-SCOPE-5: the stored label of runs that keep the older steady boundary, as a phrase
BOUNDARY = re.compile(r"^first-proof boundary \(before (\S+)\)$")


def boundary_words(cfg):
    """The steady boundary a configuration's earlier runs keep, worded from its stored label
    (RFC-0009 S2): "first-proof boundary (before 2026-11-09)" reads "steady window from the
    first proof (runs before 2026-11-09)"; another label as stored; "" without one."""
    label = cfg.get("steady_boundary") or ""
    m = BOUNDARY.match(label)
    return f"steady window from the first proof (runs before {m[1]})" if m else label


def scope_words(f, cfg):
    """A figure's scope in words; a steady figure of a configuration whose runs cut their steady
    window at another boundary names it (RFC-0004 INV-SCOPE-5)."""
    words = SCOPE_WORD[f["scope"]].format(cpus=cfg["verifier"]["logical_cpus"])
    if f["scope"] == "prove.steady" and cfg.get("steady_boundary"):
        words += f", {boundary_words(cfg)}"
    return words


def why_words(f, cfg):
    """Why a figure has no value, from its stored null reason (or its absence from the runs)."""
    if not f["recorded"]:
        return NOT_RECORDED
    if f["null_reason"] == "not_measurable_on_profile" and f["metric"].startswith("overhead_"):
        return NM1_OVERHEAD
    if f["null_reason"] in ("not_applicable", "missing_input") and f["metric"].startswith(
        "overhead_"
    ):
        if cfg.get("serving_on_gpu"):  # serving ran on this GPU model, not on this workload
            b = cfg["workload"]["shape"]["batch_size"]
            return NO_SERVING_WORKLOAD.format(
                batch=f"{b:,}\u00a0request{'s' if b != 1 else ''} per batch"
            )
        return NO_SERVING_OVERHEAD
    return NULL_WORD[f["null_reason"]].format(gpu=gpu_words(cfg))


def labels(f, cfg):
    # an overhead names both sides' scope (INV-DERIVE-11), in the words its cell uses
    scope = SCOPE_LINES.get(f.get("metric")) or scope_words(f, cfg)
    return [("scope", scope), ("grade", GRADE_WORD[f["grade"]]),
            ("evidence", TIER_WORD[f["tier"]])]  # fmt: skip
