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
              "faithful_model": "Faithful model", "machine_checked": "Machine-checked",
              "no_trusted_party": "No third party trusted"}  # fmt: skip
# a petal's stored step in words (None: hollow, not decided), §The glyph, step table and GL-8
STEP_WORD = {"green": "green · in full", "amber_upper": "amber · in part",
             "amber_lower": "amber · in lesser part", "red": "red · no",
             None: "not decided"}  # fmt: skip
# why a petal is red or hollow (GL-1, GL-3); the checks page defines each at #cause-<id>
CAUSE_WORD = {"not_stated": "not stated", "stated": "stated, short of amber",
              "check_failed": "our check failed", "not_read": "not read yet",
              "not_decided": "not decided yet",
              "proof_build_not_run": "no proof build yet"}  # fmt: skip
# each cause in a line, on the checks page (#cause-<id>)
PETAL_CAUSE_RULE = {
    "not_stated": "Red: the publisher's documents at the pinned commit do not state the property. "
    "Drawn as an outline in the red ink, its name not struck.",
    "stated": "Red: the publisher states that the property does not hold, or the facts it "
    "states fall short of amber.",
    "check_failed": "Red: one of our checks failed, or a recorded build of the publisher's "
    "machine-checked proof failed or reported other axioms. The petal names which.",
    "not_read": "Hollow: the publisher's documents are not read yet for the commit the row runs.",
    "not_decided": "Hollow: the petal is measured, and its check is undecided or has no record "
    "yet.",
    "proof_build_not_run": "Hollow: the publisher states a reach above red for Machine-checked, "
    "and no build of the named proof at the pinned commit, with the toolchain the publisher pins, "
    "is recorded yet.",
}
BASIS_WORD = {"statement": "the publisher's documents", "test": "our checks"}
# the From cell of a petal decided on the publisher's documents when a fact it read carries a note
# (the board petal's `reading`), and what that means, on the checks page (#reading)
BASIS_READING = ("the publisher's documents", "our reading")
READING_RULE = ("Our reading: a fact the petal's step rests on is our reading of the publisher's "
                "quoted words, not a sentence that states it. The quotes are printed with the "
                "petal.")  # fmt: skip
# Machine-checked's scope card: what is machine-checked, for which program (printed, sets no state)
SCOPE_ROW_WORD = {"soundness": "Soundness", "zero_knowledge": "Zero knowledge",
                  "completeness": "Completeness"}  # fmt: skip
SCOPE_COL_WORD = {"protocol": "protocol", "verifier_run": "verifier run",
                  "prover_run": "prover run"}  # fmt: skip
SCOPE_VALUE_WORD = {"machine_checked": "machine-checked", "paper": "on paper", "tested": "tested",
                    "not_stated": "not stated"}  # fmt: skip
# Weights hidden: what kind of value a proof leaves visible (only fitted_to_weights sets a step)
VISIBLE_TAG_WORD = {"statement_io": "the statement's input or output", "shape": "shape",
                    "side_channel": "side channel",
                    "fitted_to_weights": "fitted to the weights"}  # fmt: skip
# what each step means for each petal, RFC-0018's tables in short: (green, amber in part, amber
# in lesser part, red)
PETAL_RULE = {
    "unforgeable": (
        "A bound on a false reply being accepted, proved, against any prover, that covers the "
        "run: one reply a proof, each member of a batch checked alone, the row's parameters, its "
        "conditions shown to hold for the row's files, and the verifier program the row runs "
        "proved or stated to implement what the bound is about. Every exponent in the stated "
        "bound 128 or more; a term 2^-t or q/2^t has exponent t.",
        "The same, with every exponent 100 or more.",
        "A bound that is conjectured or whose basis is not said, with every exponent 100 or "
        "more. Or a proved bound that does not cover the run: the adversary not said; stated per "
        "part, per round, or with no unit said; more than one reply a proof, or replies a proof "
        "not recorded; stated only for batch members handed in together, or not said for batch "
        "members, or the batch size not recorded; the parameters not the row's or not said; the "
        "conditions not shown for the row's files; the verifier program the row runs not proved "
        "or stated to implement what the bound is about. Or a proved bound with an exponent "
        "under 100.",
        "No bound stated, a bound against a weaker prover, an exponent under 80, a conjectured "
        "bound or one whose basis is not said with an exponent under 100, or our Model, Prompt "
        "or Reply check failed.",
    ),
    "weights_hidden": (
        "Zero knowledge proved for the configuration the row runs, the programs stated to "
        "implement it, and a published list of what stays visible with nothing fitted to the "
        "weights.",
        "Zero knowledge proved for the protocol only, the programs only expected, or not stated, "
        "to implement it, no list of what stays visible, or a visible value fitted to the "
        "weights.",
        "Hiding stated, with no zero-knowledge theorem.",
        "The verifier receives the weights, hiding is stated not to hold or not stated, or our "
        "No weight file check failed.",
    ),
    "faithful_model": (
        "The proved replies are shown above the midpoint between a second run of the "
        "publisher's model and its Q8_0 copy, in a fidelity run of one request at a time.",
        "Shown above the midpoint between the Q8_0 and Q4_K_M copies. Replies also shown above "
        "the green midpoint, in a fidelity run of more than one request at a time, stay here.",
        "Fidelity held but the replies are not shown above the Q8_0 and Q4_K_M midpoint; the "
        "claim accepts tokens other than the model's top token; or the second run, the Q8_0 "
        "copy or the Q4_K_M copy is missing or failed, or no step tests are stored.",
        "Our Fidelity check failed.",
    ),
    "machine_checked": (
        "A machine-checked soundness theorem covers the verifier program the row runs, from the "
        "bytes it reads to its verdict, with its trusted base listed and no input code outside "
        "it, and a build of it at the pinned commit, with the toolchain the publisher pins, is "
        "recorded.",
        "Machine-checked for the whole protocol and for the statement that encodes the model, "
        "but not for the verifier program the row runs, or for that program without a listed "
        "trusted base, or with input code outside the proof or not stated to be inside it.",
        "Machine-checked for a part, or for the protocol or the model's statement alone.",
        "Nothing machine-checked or not stated, a recorded build that failed or reports axioms "
        "other than those the publisher declares, or our Model, Prompt or Reply check failed "
        "where it was green.",
    ),
    "no_trusted_party": (
        "The publisher's documents show soundness resting on cryptographic assumptions alone: no "
        "setup ever produced a secret. Public files fixed before the hash, or derived from public "
        "inputs, do not count.",
        "A setup produced a secret in an open ceremony with a public transcript; the secret "
        "stays unknown if one participant was honest.",
        "One honest party among a fixed set, a challenger in a challenge window, or proofs only a "
        "designated party can check or checked interactively.",
        "A setup run by one party, a hardware maker's key, a trusted key, or not stated.",
    ),
}
# the checks page: why a petal is hollow, and that silence is not
HOLLOW_RULE = ("A petal is hollow while it is not decided: its properties file is not read yet, "
               "its fidelity run is not measured or not decided yet, or, for Machine-checked, no "
               "build of the named proof with the toolchain the publisher pins is recorded yet. "
               "Silence is not hollow: a property the publisher does not state is red, drawn as an "
               "outline in the red ink, its name not struck.")  # fmt: skip
# the checks whose failure a petal's red names (PETAL_RULE), so a petal and its checks light
# together on a system page
PETAL_CHECKS = {"unforgeable": ("model", "prompt", "reply"), "weights_hidden": ("no_weight_file",),
                "faithful_model": ("fidelity",), "machine_checked": ("model", "prompt", "reply"),
                "no_trusted_party": ()}  # fmt: skip
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
# why a check is undecided (its cause as the board stores it)
CHECK_CAUSE_WORD = {
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


# a stored unit -> how its value reads: (number, unit words). One unit per quantity, whatever the
# value's size: every row of a column, and every page, reads a quantity in the same unit (money in
# USD, times in seconds, sizes in MB), so two rows are compared by their numbers alone. Per request
# reads per reply: the request is the level's one request, and its reply is what each proof covers
# (RFC-0018)
def number(v, unit):  # noqa: PLR0911 (one return per stored unit)
    if unit == "ratio":
        return sig(v), "×"
    if unit == "gpu_s/request":
        return sig(v), "GPU-s/reply"
    if unit == "s/request":
        return sig(v), "s/reply"
    if unit == "USD/request":
        return sig(v), "USD/reply"
    if unit == "B/request":
        return sig(v / 1e6), "MB/reply"
    if unit == "USD/gpu_hour":
        return sig(v), "USD/GPU-hour"
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
    """The one line under a figure: its scope in a word and its sample size. The dot keeps to the
    scope word (no break before it), so a wrapped line never starts with it."""
    count = f["n"] if f["n"] is not None else n
    parts = [SCOPE_SHORT[f["scope"]], f"n\u00a0=\u00a0{count}" if count is not None else ""]
    return SEP.join(p for p in parts if p)


# the dot between a scope and its sample size
SEP = "\u00a0· "
