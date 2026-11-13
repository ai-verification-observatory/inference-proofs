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
              "no_weight_file": "Verify without weights", "fidelity": "Fidelity"}  # fmt: skip
# {slots}, {attempts} and {reply_tokens} are the level file's constants (`overview.filled`)
CHECK_HELD = {
    "run": "Across all {slots} sessions (each starting cold on its own prompt set), the system "
    "returned an accepted proof for every request, running the published code at its pinned "
    "commit without patches or proof-weakening flags.",
    "model": "When we modified a single model weight and generated a proof, the verifier "
    "rejected it; when we took an honest proof and swapped the weight commitment in the "
    "verifier's statement, the verifier rejected that too (3 of 3 trials each).",
    "prompt": "When we changed a single prompt token in the statement given to the verifier, the "
    "verifier rejected the proof in all 3 of 3 trials.",
    "reply": "Every accepted proof covers all {reply_tokens} reply tokens, and when we altered "
    "the first token, the last token, or a randomly chosen interior token in the verifier's "
    "statement, the verifier rejected the proof in all 3 of 3 trials each.",
    "no_weight_file": "Every counted verification ran on a CPU machine with no GPU attached and "
    "no model weight file on disk, and our trace of every file the verifier opened confirmed it "
    "never read a weight file.",
    "fidelity": "On our fidelity prompt suite, the system's proved replies matched the "
    "publisher's unquantized reference weights for more leading tokens than our calibration bar "
    "did. That bar is the highest-scoring intentionally damaged copy of the model (chosen from "
    "damaged copies that every honest quantization still outperforms). Passing this check is a "
    "minimum floor against broken weights; the Faithful model petal grades how close the replies "
    "actually are.",
}
# after the colon, what an accepted trial is: the verifier accepted a false statement (RFC-0018
# §The glyph)
CHECK_FAILED = {
    "run": "At least one prompt set failed to finish within {attempts} attempts, the system's "
    "own code rejected the request, or a counted session ran with a flag that weakens the proof.",
    "model": "The verifier accepted a tampered trial: it accepted a proof for weights other than "
    "the committed model.",
    "prompt": "The verifier accepted a tampered trial: it accepted a proof for a prompt other "
    "than the one that was proved.",
    "reply": "A proof covered fewer reply tokens than requested, or the verifier accepted a "
    "tampered trial with an altered reply token.",
    "no_weight_file": "The file-access trace showed the verifier opening a model weight file, or "
    "a verify call required one on disk.",
    "fidelity": "The calibration bar scored above the system's replies: the proved replies "
    "matched the publisher's original weights for fewer leading tokens than an intentionally "
    "damaged copy of the model.",
}
STATE_WORD = {"held": "held", "failed": "failed", "undecided": "undecided"}

# ------------------------------------------------------------------ the five petals (RFC-0018 §The glyph)
PETAL_NAME = {"unforgeable": "Unforgeable", "weights_hidden": "Weights hidden",
              "faithful_model": "Faithful model", "machine_checked": "Machine-checked",
              "no_trusted_party": "No third party trusted"}  # fmt: skip
# a petal's stored step in words (None: hollow, undecided), §The glyph, step table and GL-8
STEP_WORD = {"green": "green · in full", "amber_upper": "amber · in part",
             "amber_lower": "amber · in lesser part", "red": "red · no",
             None: "undecided"}  # fmt: skip
# why a petal is red or hollow (GL-1, GL-3); the checks page defines each at #cause-<id>
CAUSE_WORD = {"not_stated": "not stated", "stated": "stated, short of amber",
              "check_failed": "our check failed", "not_read": "not read yet",
              "not_decided": "our check undecided",
              "proof_build_not_run": "no proof build yet"}  # fmt: skip
# each cause in a line, on the checks page (#cause-<id>)
PETAL_CAUSE_RULE = {
    "not_stated": "Red (open outline): the publisher's documentation at the pinned commit does "
    "not address this property. We draw the petal as an open red outline without striking "
    "through its name.",
    "stated": "Red (filled): the publisher's documentation states that this property does not "
    "hold, or states parameters that fall below the minimum threshold for amber.",
    "check_failed": "Red (filled): one of our own verification checks failed, or our clean "
    "build of the publisher's formal proof failed or reported axioms different from those "
    "declared. The petal's row names which check failed.",
    "not_read": "Hollow: we have not yet finished reading and recording the publisher's "
    "documentation for the commit this row runs.",
    "not_decided": "Hollow: this petal depends on a benchmark measurement whose check is still "
    "undecided or has not been recorded yet.",
    "proof_build_not_run": "Hollow: the publisher documents a formal proof that would qualify "
    "for amber or green on Machine-checked, but we have not yet recorded a clean build of that "
    "theorem at the pinned commit and toolchain.",
}
BASIS_WORD = {"statement": "the publisher's documents", "test": "our tests"}
# the From cell of a petal decided on the publisher's documents when a fact it read carries a note
# (the board petal's `reading`), and what that means, on the checks page (#reading)
BASIS_READING = ("the publisher's documents", "our reading")
READING_RULE = (
    "Our reading: the step rests on our interpretation of a passage in the publisher's "
    "documentation rather than an explicit sentence stating the fact directly. We print the "
    "verbatim quotes right alongside our interpretation so you can judge for yourself."
)
# Machine-checked's scope card: what is machine-checked, for which program (printed, sets no state)
SCOPE_ROW_WORD = {"soundness": "Soundness", "zero_knowledge": "Zero knowledge",
                  "completeness": "Completeness"}  # fmt: skip
SCOPE_COL_WORD = {"protocol": "Protocol", "verifier_run": "Verifier run",
                  "prover_run": "Prover run"}  # fmt: skip
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
        "The publisher states a proved soundness bound against any prover (arbitrary or "
        "computationally bounded) showing that a false reply is accepted with probability at "
        "most 2^-128 per term (where a term 2^-t or q/2^t has exponent t at least 128). The "
        "bound must cover the actual benchmark run: one proof per reply (or a batch bound that "
        "holds for each member checked on its own), using the row's parameters, with its "
        "preconditions satisfied by the row's files, and with the verifier binary we run proved "
        "or stated to implement the verifier the bound analyzes.",
        "Every condition for green holds, except the smallest exponent in the proved bound sits "
        "between 100 and 127 bits instead of reaching 128.",
        "The publisher states a bound whose exponents are at least 100 bits on a conjectured "
        "(or unstated) basis, or states a proved bound of at least 80 bits that either has an "
        "exponent below 100 or does not fully cover the run. For example, a proved bound lands "
        "here if the adversary model is left unstated, if the bound is given per layer or per "
        "round rather than per reply, if a proof covers multiple replies or only holds when a "
        "whole batch is checked together, if the parameters or preconditions are not shown for "
        "the row's files, or if the verifier binary is not stated to implement the protocol "
        "analyzed.",
        "The publisher states no soundness bound, assumes a restricted prover, states a proved "
        "bound with an exponent below 80 bits, states a conjectured (or unspecified) bound with "
        "an exponent below 100 bits, or our Model, Prompt, or Reply check failed.",
    ),
    "weights_hidden": (
        "Our Verify without weights check held, the publisher states a proved zero-knowledge "
        "theorem for the configuration the row runs, the prover and verifier binaries are proved "
        "or stated to implement that protocol, and the publisher lists everything the proof and "
        "statement leave visible, with none of those visible values fitted to the model weights.",
        "Our Verify without weights check held and the publisher states a proved zero-knowledge "
        "theorem, but the theorem covers only the abstract protocol, the binaries are only "
        "expected (or not stated) to implement it, the publisher does not list what remains "
        "visible, or the visible parameters include values fitted to the weights (such as "
        "quantization scales).",
        "Our Verify without weights check held and the publisher states that the model weights "
        "remain hidden, but cites no proved zero-knowledge theorem.",
        "The verifier requires the model weights, the publisher states that weights are not "
        "hidden (or says nothing about weight secrecy), or our Verify without weights check "
        "failed.",
    ),
    "faithful_model": (
        "In a single-request-at-a-time fidelity run, the system's proved replies score "
        "significantly above the midpoint between a second run of the publisher's unquantized "
        "model and its 8-bit quantized copy (Q8_0).",
        "The proved replies score significantly above the midpoint between the 8-bit (Q8_0) and "
        "4-bit (Q4_K_M) quantized copies, or they clear the upper (green) midpoint in a batched "
        "fidelity run of more than one request at a time.",
        "Our Fidelity check held against the damaged calibration bar, but the replies did not "
        "clear the midpoint between Q8_0 and Q4_K_M, the system's claim card allows tokens other "
        "than the model's top token, or one of the reference or quantized controls is missing "
        "or failed.",
        "Our Fidelity check failed.",
    ),
    "machine_checked": (
        "A machine-checked soundness theorem covers the actual verifier program the row runs, "
        "from the raw bytes it reads to the verdict it returns, with its trusted base explicitly "
        "listed and no unverified input-translation code outside the theorem, and we have "
        "recorded a clean build of that proof at the pinned commit using the publisher's pinned "
        "toolchain.",
        "Our recorded build of the formal proof succeeded, and the theorem covers the full "
        "protocol and the statement encoding the model, but it does not cover the executable "
        "verifier program itself, leaves out the list of axioms and trusted base, or relies on "
        "unverified code to translate the model into the theorem's input.",
        "Our recorded build of the formal proof succeeded, but the theorem covers only a "
        "component of the system (such as a primitive or gadget), or covers only the abstract "
        "protocol or model statement in isolation.",
        "The publisher states no machine-checked proof, our recorded build failed or reported "
        "axioms different from those declared, or a theorem that would have been green was "
        "lowered because our Model, Prompt, or Reply check failed.",
    ),
    "no_trusted_party": (
        "The publisher's documentation shows that soundness rests on standard cryptographic "
        "assumptions alone, with no setup step that ever generated a secret. Public parameters "
        "fixed before hashing or derived deterministically from public seeds qualify here.",
        "Setup generated a secret through an open multi-party ceremony with a publicly "
        "verifiable transcript, where the secret remains unknown as long as at least one "
        "participant was honest.",
        "Verification relies on a ceremony among a fixed set of parties, an optimistic challenge "
        "window requiring an active challenger, or interactive or designated-verifier proofs "
        "that cannot be checked by arbitrary third parties.",
        "Verification relies on a setup run by a single party, a hardware vendor's attestation "
        "key, another trusted key, or the publisher's documentation does not state what setup "
        "trust is required.",
    ),
}
# the checks page: why a petal is hollow, and that silence is not
HOLLOW_RULE = (
    "A petal is drawn as a hollow dashed outline while it is still undecided: either we have "
    "not yet recorded the system's properties file at the pinned commit, its fidelity run has "
    "not finished, or (for Machine-checked) we have not yet run a clean build of the cited "
    "formal proof. Silence in the publisher's documentation never makes a petal hollow: if the "
    "documents at the pinned commit do not state a property, the petal is red with an open "
    "outline."
)
# the checks whose failure a petal's red names (PETAL_RULE), so a petal and its checks light
# together on a system page
PETAL_CHECKS = {"unforgeable": ("model", "prompt", "reply"), "weights_hidden": ("no_weight_file",),
                "faithful_model": ("fidelity",), "machine_checked": ("model", "prompt", "reply"),
                "no_trusted_party": ()}  # fmt: skip
# ------------------------------------------------------------------ the figures (RFC-0018 §Cost, FI-7)
# The overview's four figure columns: the anchor on the checks page, the column head, and the
# definition as (label, words) lines. {slots}, {gap} (the release-group gap), {full} (the share
# of the highest rate that is full load) and {top} (the ladder's top concurrency) are the level
# file's constants; {reference} is each model's reference precision.
FIGURE_NAME = {"multiple": "Cost vs serving", "cost": "Cost per reply",
               "check-time": "Verify time per reply", "kl": "KL to the original weights"}  # fmt: skip
# a figure's head where its unit stands beside it: the unit says "per reply", so the head does
# not; and the surface names fidelity, not the metric (KL and the matched tokens' bar are under
# Fidelity on a system's page)
FIGURE_HEAD = {"multiple": "Cost vs serving", "cost": "Cost", "check-time": "Verify time",
               "proof-size": "Proof size", "fidelity": "Fidelity", "serving": "Serving"}  # fmt: skip
FIDELITY_TITLE = "leading tokens matching the original, mean"  # in a fidelity word's title


def beside_unit(name):
    """A figure's name where its unit follows it: "per reply" is the unit's to say."""
    return name.replace(" per reply", "")


FIGURE_RULE = {
    "multiple": (
        ("m", "Steady-state GPU-seconds per proved reply after the first release group. Within a "
         "session, proofs released within {gap} of the previous proof form a release group. We "
         "measure the GPU time from the end of the first group to the final proof of the session "
         "and divide by the number of replies in those later groups (including token generation). "
         "Reported as the mean across {slots} cold-start sessions."),
        ("serving", "Baseline GPU-seconds per reply (b) for plain unproved serving: we run the "
         "publisher's original model weights under the pinned inference engine on the fewest H200 "
         "GPUs that fit the model, at full load. Full load is the lowest concurrency that reaches "
         "{full} of peak throughput on a concurrency ladder up to {top} requests."),
        ("multiple", "The ratio m / b on the same model. Because both numbers are measured in "
         "GPU-seconds on the same GPU type at the same hourly rate, this ratio is identical in "
         "dollars."),
        ("whole session", "If a system's sessions release too few groups (or groups that are too "
         "uneven) to establish a steady state, it has no m. Instead, we divide its total session "
         "GPU time per reply by b and label the figure as whole sessions."),
        ("parts", "When a system runs token generation in a separate phase from proving, we split "
         "the multiple into two parts (each divided by b): generation and the remaining work. For "
         "steady-state rows that remainder is proving; for whole-session rows it combines model "
         "commitment and proving."),
    ),
    "cost": (
        ("steady", "Steady-state GPU time per reply (m) converted to US dollars at the release's "
         "benchmark price for one H200 GPU-hour."),
        ("session", "For systems without a steady-state multiple: total GPU time from the start "
         "of model commitment to the release of the last proof, divided by the session's replies, "
         "in US dollars."),
    ),
    "check-time": (
        ("verify", "Total CPU wall-clock time the system's verifier takes to check all proofs in "
         "a session, divided by the number of replies in that session."),
    ),
    "kl": (
        ("kl", "Mean Kullback-Leibler divergence per scored token (in nats) between the model "
         "file the system commits to and the publisher's original {reference} reference weights."),
        ("computed by", "Measured directly on the committed weight file using llama.cpp rather "
         "than inside the prover. We print this figure for context; it does not decide any check."),
        ("none", "Omitted when llama.cpp cannot load the format of the committed weight file."),
    ),
}  # fmt: skip
# a rung's fidelity reference, by its stored precision (FI-1)
REFERENCE_WORD = {"bf16": "16-bit", "f16": "16-bit", "f32": "32-bit"}


def kl_head(dtype):
    """The KL column's head: one name on every page; the precision of each model's reference is
    in the figure's definition."""
    return FIGURE_NAME["kl"]


# the order rule (RFC-0018 OR-1 to OR-4, GL-4), as (label, words). {margin} is the level's.
# "Session m" is one counted session's m.
ORDER_RULE = (
    ("ranked", "Only systems that pass all six checks on a model are eligible to be ranked, and "
     "they are ranked only within that model's table."),
    ("above", "One system is placed strictly above another when its cost multiple is at least "
     "{margin} lower and its slowest session (highest session m) is still faster than the other's "
     "fastest session (lowest session m). Systems with a steady-state multiple are placed above "
     "systems measured only on whole sessions; two whole-session systems are compared the same "
     "way using session cost per reply."),
    ("position", "A system's position is 1 plus the number of systems placed strictly above it, "
     "shown alongside the total number of systems run on that model."),
    ("unranked", "A system that passes all six checks is given a numbered position only when its "
     "publisher states a cryptographic security level at the pinned commit; otherwise it is "
     "listed as passed, unranked."),
    ("glyph", "The five-petal glyph never affects a system's position in the table."),
    ("models", "Nothing is ranked across models."),
)  # fmt: skip
# ------------------------------------------------------------------ the scale page (RFC-0018 SI-7)
SCALE_LOG = "log scale"  # beside an axis's unit
SCALE_SERVING = "Serving"  # a lane's foot: serving's line and its stored figure
SCALE_NOT_RUN = "Not run yet."
# ------------------------------------------------------------------ the mandate page
# The headline, what the site is for, then what we do, what we do not do, who runs it and how to
# check us: each line (a plain label, the rule that binds it, the file that rule is in, the
# words). A line with no file is the owner's commitment. The members (facts.json `credit`) are
# listed in the section MANDATE_MEMBERS_IN names, once any has agreed.
RFC_18 = "rfcs/0018-level-1-ladder.md"
MANDATE_BELIEF = (
    "We believe a claim about which AI model answered should come with evidence anyone can "
    "afford to check."
)
MANDATE_WHAT = (
    "When an AI service tells you that a reply came from a specific model, you normally have to "
    "take the operator's word for it. A proof of inference is a cryptographic receipt that lets "
    "anyone verify that claim without re-running the model. This benchmark tests the systems "
    "that build those proofs. On a ladder of open-weights models, we measure how much more it "
    "costs to generate a proved reply than to serve the same reply normally, and we test whether "
    "each system's verifier actually rejects the proof when we tamper with the model, the "
    "prompt, or the reply. Every system receives the exact same workload on the same class of "
    "hardware, running the publisher's unmodified code."
)
MANDATE = (
    ("What we do", (
        ("As published", "rule 1", "AGENTS.md", "We run each system at a pinned public commit, "
         "with no patches to its source code and no flags or settings that are not documented by "
         "its publisher."),
        ("Same request", "Request, PR-2", RFC_18, "We give every system on a model the exact "
         "same request. The prompts are drawn from a public randomness beacon after the benchmark "
         "rules are frozen, so neither we nor any system author can cherry-pick prompts or tune "
         "rules around them."),
        ("Every run", "rule 5", "AGENTS.md", "We publish every run we execute for a release, "
         "including crashes and failed checks, complete with exit codes and log tails. We report "
         "full session ranges and sample sizes, never a single cherry-picked run."),
        ("Computed", "CH-6", RFC_18, "We compute every check outcome, ratio, and summary "
         "automatically from the stored run records; no reviewer sets a check state or types a "
         "number by hand."),
        ("Confirmed", "CH-8", RFC_18, "Before we publish that a system's verifier accepted a "
         "tampered model, prompt, or reply, we reproduce that failure using the system's own "
         "command-line interface outside our harness. Until we confirm it, the check is marked "
         "undecided and we notify the publisher."),
    )),
    ("What we do not do", (
        ("Payment", "", None, "We do not accept payment for listing a system, ranking it, or "
         "running a benchmark session."),
        ("Building", "What this project is", "AGENTS.md", "We do not build or sell a prover of "
         "our own, and we do not certify the systems we test."),
        ("Security", "Non-Goals", RFC_18, "We do not attempt to cryptographically forge proofs "
         "or extract hidden weights. Our six checks test what an external harness can observe; "
         "for mathematical soundness and zero-knowledge claims, we quote what the publisher's "
         "own documentation states."),
        ("Across models", "OR-1", RFC_18, "We never rank systems across different models. Each "
         "model on the ladder has its own separate table of systems that passed all six checks."),
    )),
    ("Who runs it", (
        ("Operator", "", None, "This benchmark is operated by Lucid Computing."),
        ("Conflicts", "Conflicts of Interest", RFC_18, "FlashProve is published by Anthropic. "
         "Parts of this project's harness code and documentation were drafted with the help of "
         "Claude, Anthropic's model."),
    )),
    ("How to check us", (
        ("Sources", "rule 2", "AGENTS.md", "Every number on this site carries its unit, timing "
         "scope, sample size and the stored record it was computed from. A system's page prints "
         "them."),
        ("Open code", "Licence", "README.md", "All of our benchmark rules, system adapters, "
         "measurement scripts, and raw run records are open source in our public repository."),
    )),
)  # fmt: skip
MANDATE_MEMBERS_IN = "Who runs it"
# the mandate's line on the level (its label is the level and its state, linked to the level file)
MANDATE_LEVEL_IN = "How to check us"
MANDATE_LEVEL = (
    "The models, the request, the constants of the checks and the order rule are "
    "one file. It does not change once frozen: a change of rule is a new level."
)
# why a check is undecided (its cause as the board stores it)
CHECK_CAUSE_WORD = {
    "system limit": "the system does not support what this test requires (the publisher's own "
    "statement is quoted on the system page)",
    "not run": "this check has not been run yet",
    "not resolved": "the test ran but did not reach a conclusive verdict",
    "not reproduced": "the verifier accepted a tampered input under our adapter, and we are "
    "confirming the result with the system's standalone command before marking it failed",
}

# ------------------------------------------------------------------ labels of a stored figure
SCOPE_SHORT = {None: "", "prove.steady": "steady", "prove.session": "session",
               "whole_wall": "session", "verify": "verify", "commit": "commit",
               "setup": "setup", "verify.single_thread": "verify, one thread"}  # fmt: skip
SCOPE_WORD = {
    None: "not a timed number",
    "setup": "setting up",
    "commit": "committing to the model",
    "prove.steady": "steady state, after the first release group",
    "prove.session": "the whole session, start-up included",
    "whole_wall": "the whole session, from commit to the last proof",
    "verify": "verifying",
    "verify.single_thread": "verifying on one CPU thread",
    "primitive": "one primitive",
    "serving": "serving at full load, steady state",  # the serving baseline's, in its title (CO-4)
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
# in place of a null reason: a steady figure on a row with no steady state (CO-3, CO-5)
NO_STEADY_WORD = "not every session had a steady state"
# the line under the serving baseline's figure: it is timed at full load, not steady (CO-4)
FULL_LOAD_WORD = "full load"
# CO-7: the two parts a multiple or a GPU time splits into where the system generates in a phase
# of its own. A session's second part holds commit as well (most of it), so it is never "proving"
PART_WORD = {"proving": "proving", "generation": "generation",
             "commit_and_proving": "commit and proving"}  # fmt: skip
OF_WHICH = "of which"  # before a part's name where it stands under its whole (the Cost section)
# the GPU time per reply after the first release group, m (CO-1); its column in the sessions table
M_NAME, M_COL = "GPU time per reply after the first group (m)", "After the first group"
# the line under a whole session's figure, N the level's replies per session (CO-5)
WHOLE_SESSIONS = "whole sessions of {n:,} replies"
# the fidelity table (FI-5, FI-6): the replies' figure, a control's id as printed, the p line
PREFIX = "Leading tokens matching the original, mean"
CONTROL_NAME = {"reference-2": "original, run again"}
# a check's record as its link reads, by the file's name (the path stands in the link's title)
RECORD_WORD = {"run.json": "run record", "controls.json": "controls", "verify-trace": "verify traces",
               "reverify.json": "re-verify record", "fidelity.json": "fidelity record"}  # fmt: skip
P_ABOVE = "above the bar: p\u00a0=\u00a0{p}"


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


def labels(f, n=None, note=None):
    """A figure's labels in words, for its title: scope, grade, evidence, sample size, record.
    `n` stands where the figure stores no sample size (the row's counted sessions); `note` opens
    the title (CO-5's "whole sessions of N replies")."""
    parts = [note] if note else []
    parts += [f"scope: {SCOPE_WORD[f['scope']]}", f"grade: {GRADE_WORD[f['grade']]}",
              f"evidence: {TIER_WORD[f['tier']]}"]  # fmt: skip
    count = f["n"] if f["n"] is not None else n
    if count is not None:
        parts.append(f"n = {count}")
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
