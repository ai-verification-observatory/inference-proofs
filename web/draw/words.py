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
# {slots}, {attempts} and {reply_tokens} are the level file's constants (`overview.filled`)
CHECK_HELD = {
    "run": "Each of the {slots} session slots holds a complete session, built from the public "
    "pin, unpatched, with no weakening flag.",
    "model": "A proof made after one weight was changed is not accepted, and an honest proof "
    "checked against the changed weights' commitment is refused, in 3 of 3 trials each.",
    "prompt": "A proof checked with one prompt token changed is refused, in 3 of 3 trials.",
    "reply": "Every accepted proof covers all {reply_tokens} reply tokens, and a changed reply "
    "token is refused at the first, the last and one seeded interior position, in 3 of 3 trials "
    "each.",
    "no_weight_file": "Every counted verdict came from a check run with no GPU visible, on a "
    "filesystem holding no model file, under a file-open trace that names no model file.",
    "fidelity": "The system's replies score above the model's bar: the damaged copy of the model "
    "that every honest copy scores above, scored by the leading tokens each reply shares with the "
    "reply of the publisher's original weights.",
}
# after the colon, what an accepted trial is: the verifier accepted a false statement (RFC-0018
# §The glyph)
CHECK_FAILED = {
    "run": "A slot has {attempts} incomplete runs, the system's own code refuses the request, or "
    "a counted session used a weakening flag.",
    "model": "Any trial is accepted: the verifier accepts a proof for weights other than the "
    "committed ones.",
    "prompt": "Any trial is accepted: the verifier accepts a proof for a prompt other than the "
    "one proved.",
    "reply": "A proof covers fewer reply tokens, or any trial is accepted: the verifier accepts "
    "a reply with a token changed.",
    "no_weight_file": "The trace names a model file, or a check needed one.",
    "fidelity": "The bar scores above the system's replies: they match the replies of the "
    "publisher's original weights for fewer leading tokens than those of a copy damaged on "
    "purpose.",
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
        "The replies are not shown below a second run of the publisher's original weights.",
        "The replies score above the model's bar, and the second run of the original weights "
        "scores above them.",
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
# ------------------------------------------------------------------ the checks page's terms
# RFC-0018 §Terms and the glossary's Proved and Commitment, in short. {request} is the level's
# request in words.
TERMS = (
    ("proof", "The files a system writes for one reply. Its verifier is a program that accepts "
     "or refuses them. Each publisher states what an accepted proof shows, for example that "
     "each reply token is the committed model's top choice, and under which assumptions. A "
     "sound verifier accepts a reply that statement does not cover only with the probability "
     "its security level bounds."),
    ("commitment", "The value a system's commit step produces: it fixes the weights a later "
     "proof refers to. The verifier is given the value from our record of that step, never from "
     "files sent with a proof."),
    ("request", "{request}. The same request for every system on every model."),
    ("ladder", "The models, largest first, each an open-weights release named by its publisher. "
     "A system has a row on each model it was run on."),
)  # fmt: skip

# ------------------------------------------------------------------ the figures (RFC-0018 §Cost, FI-7)
# The overview's four figure columns: the anchor on the checks page, the column head, and the
# definition as (label, words) lines. {slots}, {gap} (the release-group gap), {full} (the share
# of the highest rate that is full load) and {top} (the ladder's top concurrency) are the level
# file's constants; {reference} is each model's reference precision.
FIGURE_NAME = {"multiple": "Multiple of serving", "cost": "Cost per reply",
               "check-time": "Check time per reply", "kl": "KL to the reference"}  # fmt: skip
FIGURE_RULE = {
    "multiple": (
        ("proving", "m, GPU-seconds per further proved reply. In one session, proofs released "
         "within {gap} of the previous release form a group. m is the GPU time from the first "
         "group's last release to the session's last release, over the replies of the later "
         "groups, generating the replies included. The mean of {slots} sessions, each from a "
         "cold start."),
        ("serving", "b, GPU-seconds per reply of plain serving: the publisher's own release, "
         "served by the pinned engine on the fewest H200 that hold it, at full load. Full load "
         "is the lowest concurrency that reaches {full} of the highest rate, on a ladder up to "
         "{top} concurrent requests."),
        ("multiple", "m over b, on one model. Both halves are GPU-seconds of the same GPU at one "
         "price, so the multiple is the same in dollars."),
        ("cold", "A system whose sessions release too few groups, or uneven ones, has no m. It "
         "prints its session cost per reply over b, labelled as cold sessions."),
    ),
    "cost": (
        ("steady", "m in USD, at the release's price of one H200 GPU-hour."),
        ("session", "Where a system has no multiple: the GPU time from the start of commit to "
         "the release of the last proof, over the session's replies, in USD."),
    ),
    "check-time": (
        ("check", "The time the system's verifier takes on a session's proofs, over the "
         "session's replies."),
    ),
    "kl": (
        ("kl", "The mean KL divergence per scored token, in nats, of the file the system "
         "commits from the reference: the publisher's original weights, {reference}."),
        ("computed by", "llama.cpp, on the committed file, not on the proved computation. It is "
         "printed and decides no check."),
        ("none", "Not measured where llama.cpp cannot load the committed file."),
    ),
}  # fmt: skip
# a rung's fidelity reference, by its stored precision (FI-1)
REFERENCE_WORD = {"bf16": "16-bit", "f16": "16-bit", "f32": "32-bit"}


def kl_head(dtype):
    return f"KL to the {REFERENCE_WORD[dtype]} model"


# the order rule (RFC-0018 OR-1 to OR-4, GL-4), as (label, words). {margin} is the level's.
# "Session m" is one counted session's m.
ORDER_RULE = (
    ("ranked", "Only a system that passed on a model, and only on that model."),
    ("above", "A system is placed above another when its multiple is at least {margin} lower "
     "and its highest session m is below the other's lowest. A system with a multiple is placed "
     "above one without. Two without compare the same way on session cost per reply."),
    ("position", "1 plus the number of systems placed above. The count of systems run on the "
     "model is printed beside it."),
    ("unranked", "A system that passed is ranked only when its publisher states a security "
     "level at the pinned commit. The level is printed as stated: our tests cannot tell 60 bits "
     "from 128."),
    ("glyph", "The glyph never moves a position."),
    ("models", "Nothing is compared across models: they differ in what serving costs and in how "
     "proving scales."),
)  # fmt: skip
# ------------------------------------------------------------------ the mandate page
# The headline, what the site is for, then what we do, what we do not do, who runs it and how to
# check us: each line (a plain label, the rule that binds it, the file that rule is in, the
# words). A line with no file is the owner's commitment.
RFC_18 = "rfcs/0018-level-1-ladder.md"
MANDATE_BELIEF = (
    "We believe a claim about which AI model answered should come with evidence anyone can "
    "afford to check."
)
MANDATE_WHAT = (
    "When a service says a reply came from a given AI model, you normally have to take its word. "
    "A proof of inference is a file that lets anyone check that claim without running the model. "
    "This site tests the systems that make such proofs. It measures how much more a proved "
    "reply costs than serving the same reply without a proof, and whether each system's checker "
    "refuses a proof once the model, the prompt or the reply is changed. Every system gets the "
    "same request on the same kind of GPU, and we run each one as published, with no change to "
    "its code."
)
MANDATE = (
    ("What we do", (
        ("As published", "rule 1", "AGENTS.md", "Run each system at a fixed public version, "
         "with no change to its code and no setting its documentation does not name."),
        ("Same request", "Request, PR-2", RFC_18, "Give every system the same request. The "
         "prompts come from a public random draw made after the rules are frozen, so nobody, us "
         "included, picks them or sets a rule knowing them."),
        ("Every run", "rule 5", "AGENTS.md", "Record every run of a release, failed ones with "
         "their error code and last lines of output. Report ranges and sample sizes, never a "
         "single best run."),
        ("Computed", "CH-6", RFC_18, "Compute every check result from stored records. No "
         "reviewer sets one by hand."),
        ("Confirmed", "CH-8", RFC_18, "Before we publish that a system's checker accepted a "
         "changed model, prompt or reply, reproduce it with the system's own command, outside "
         "our own code. Until then the check reads undecided and we tell the system's "
         "publisher."),
    )),
    ("What we do not do", (
        ("Payment", "", None, "Take payment for a listing, a place in the ranking or a rerun."),
        ("Building", "What this project is", "AGENTS.md", "Build these systems or certify "
         "them."),
        ("Security", "Non-Goals", RFC_18, "Test whether a proof can be forged or whether it "
         "keeps the model's weights hidden. No check attempts a forged proof."),
        ("Across models", "OR-1", RFC_18, "Rank systems across models. Each model has its own "
         "ranking, of the systems that passed the six checks."),
    )),
    ("Who runs it", (
        ("Operator", "", None, "Lucid Computing runs this project."),
        ("Conflicts", "Conflicts of Interest", RFC_18, "FlashProve is published by Anthropic. "
         "Parts of this project's code and text are drafted with Claude, Anthropic's model."),
    )),
    ("How to check us", (
        ("Sources", "rule 2", "AGENTS.md", "Every figure shows its unit, what was timed and "
         "its sample size, and names the source it came from."),
        ("Open code", "Licence", "README.md", "The rules, the code we use to run each system "
         "and the measuring code are public."),
    )),
)  # fmt: skip
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
