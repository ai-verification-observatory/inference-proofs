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
# Each check in one plain sentence, printed first under its name on the checks page, before the
# precise rule, and the title of a check's name on a system page and the ladder: what passes it (SPEC section 8; RFC-0018 SI-3, amended 2026-11-16). {slots} and
# {reply_tokens} are the level file's constants, 0.05 its fidelity.alpha
CHECK_PLAIN = {
    "run": "The publisher's prover ran as published at the pinned commit for {slots} cold-start "
    "sessions, producing an accepted proof for every reply.",
    "model": "When we alter one weight, no proof built with the changed weights is accepted "
    "against the original commitment.",
    "prompt": "When we alter one prompt token, the verifier rejects the proof.",
    "reply": "Every proof covers all {reply_tokens} reply tokens, and altering the first, last, "
    "or an interior reply token causes the verifier to reject the proof.",
    "no_weight_file": "The verifier reached every verdict with no model weights on disk and no "
    "GPU visible.",
    "fidelity": "Proved replies match more leading tokens of the original model than the pass "
    "bar (a deliberately damaged copy) does, tested at p\u00a0<\u00a00.05.",
}
# Each check's rule, RFC-0018's table ("Held when", "Failed when") in short, as a condition in the
# present tense. {slots}, {attempts}, {reply_tokens} and {reference} are the level file's
# constants (`ladder.filled`); 3 of 3 and 0.05 (fidelity.alpha) are typed as the level's.
CHECK_HELD = {
    # Terms (Slot, Session: complete), SE-1
    "run": "The model's prompts are divided into {slots} slots, and each slot has a complete "
    "cold-start session whose prove call exits 0 with an accepted proof for every request. The "
    "container is built from the pinned public commit as published, with no weakening flags.",
    # P1 against the commitment of W, CH-1a (p1_refusals: an outcome the publisher documents at
    # the pin as meaning the weights are not the committed ones; a layout guard is not one), C3
    "model": "Proving with one modified weight against the original commitment produces no "
    "accepted proof in 3\u00a0of\u00a03 trials of the same change (a prover stop counts only when "
    "the publisher documents at the pinned commit that it signals mismatched weights). Checking "
    "an honest proof against the modified weights' commitment is rejected in 3\u00a0of\u00a03 "
    "trials.",
    "prompt": "Changing one prompt token at a seeded position (fresh in each trial) causes the "
    "verifier to reject the proof in 3\u00a0of\u00a03 trials.",
    "reply": "Every accepted proof covers all {reply_tokens} reply tokens. Changing the first "
    "token, the last token, or a seeded interior token (fresh per trial) causes the verifier to "
    "reject the proof in 3\u00a0of\u00a03 trials at each position.",
    # the table's (a) to (c), CH-4a (the re-verify counts in the run's image, when it accepts)
    "no_weight_file": "Every counted verdict comes from a verify call with no GPU visible, no "
    "model files on disk, and a file-open trace confirming none were opened. A verdict from a "
    "GPU host still counts once the same proof is re-verified and accepted inside the same "
    "image on a host with no GPU.",
    "fidelity": "The replies proved in counted sessions score above the pass bar in a paired "
    "one-sided sign-flip test at p\u00a0<\u00a00.05.",
}
# CH-8: an accepted trial is failed only once the system's own command accepts the same input
CHECK_FAILED = {
    "run": "A slot accumulates {attempts} incomplete runs, the system's own code records a "
    "refusal caused by its inputs, or a counted session passes a weakening flag.",
    "model": "A tampered trial was accepted, and running the system's own command outside our "
    "adapter accepted the same modified input.",
    "prompt": "A tampered trial was accepted, and running the system's own command outside our "
    "adapter accepted the same modified input.",
    "reply": "A proof covered fewer than {reply_tokens} reply tokens, or a tampered trial was "
    "accepted and reproduced with the system's own command outside our adapter.",
    "no_weight_file": "The file-open trace records a model file, or a verify call required one.",
    "fidelity": "The pass bar scores above the system's replies under the same paired test. If "
    "neither side is shown higher, the check remains not decided.",
}
# a check's lines after held and failed: Run's cap (SE-4: 40 and 120 USD are the level file's
# sessions.cap_usd and the Maverick rung's cap_usd, typed as the level's; the view carries
# neither) and which session counts (SE-3, SE-3a); Fidelity's score and bar (FI-1 to FI-6)
CHECK_MORE = {
    "run": (
        ("cap", "Any session that hits the spending cap (120\u00a0USD on Llama 4 Maverick, "
         "40\u00a0USD on other models) is stopped and recorded as incomplete."),
        ("counted", "Each slot counts its earliest complete session by start time, never cherry-picked "
         "for speed. If a session missed Verify without weights only because a GPU was visible and "
         "was never re-verified, the slot passes to the next complete session from the same image "
         "and adapter commit that meets the check."),
    ),
    "fidelity": (
        ("score", "Each reply is scored by how many consecutive leading tokens match the original "
         "model's reply to the same prompt (0 to {reply_tokens}). The original is a Hub copy of "
         "the publisher's release at its release precision, pinned on each system page: "
         "{reference}."),
        ("bar", "The bar is the highest-scoring damaged control that every honest control still "
         "outperforms. Honest controls are the original rerun plus 8-bit and 4-bit quantizations "
         "(Q8_0 and Q4_K_M); damaged controls are listed on each system page. If no damaged "
         "control qualifies, the model has no bar and Fidelity stays not decided for every row."),
    ),
}  # fmt: skip
# a check in one line, for its search entry: the held rule with every condition kept, about 95
# characters at most (two lines of the search list); {slots} and {reply_tokens} as above
CHECK_LINE = {
    "run": "{slots} complete cold-start sessions from the pinned commit as published, with no "
    "weakening flags.",
    "model": "Changing a weight gives no accepted proof; checking an honest proof against a "
    "changed commitment is rejected (3\u00a0of\u00a03).",
    "prompt": "Changing one prompt token at a seeded position is rejected in 3\u00a0of\u00a03 "
    "trials.",
    "reply": "All {reply_tokens} reply tokens covered; changing the first, last, or a seeded "
    "interior token is rejected (3\u00a0of\u00a03).",
    "no_weight_file": "All verdicts (or accepted re-verifications) run with no GPU visible and "
    "no model file present or opened.",
    "fidelity": "Proved replies from counted sessions score above the pass bar (paired sign-flip "
    "test, p\u00a0<\u00a00.05).",
}
# a check's stored state in words (RFC-0018 Terms, amended 2026-11-16); the ids stay
STATE_WORD = {"held": "passed", "failed": "failed", "undecided": "not decided"}
# what a control's counted trials sent, from the board's `trials` (RFC-0018 CH-1c), by control
# and C1's position; printed with a check's records
TRIAL_WHAT = {("P1", None): "proving with one modified weight",
              ("C3", None): "checking an honest proof against the modified weights' commitment",
              ("C2", None): "changing one prompt token",
              ("C1", "first"): "changing the first reply token",
              ("C1", "last"): "changing the last reply token",
              ("C1", "interior"): "changing one interior reply token"}  # fmt: skip
TRIALS_HEAD = "What ran"
# how a counted trial was refused (CH-1c): the prover made no proof (`no_proof`, a stop its
# publisher documents, CH-1a), so no verifier saw one; or a verifier refused the proof
TRIAL_NO_PROOF = "the prover stopped without producing a proof, as documented by the publisher"
TRIAL_REFUSED = "rejected by the verifier"
# a stored verifier trial (RFC-0008 §Verifier trials), printed beside the check whose change it
# makes, or under Machine-checked for another of the publisher's verifiers; it sets no state
KEPT_HEAD = "Outside the counted suite"
KEPT_CHANGE = {"reply_token": "changing one reply token at every reply position in turn",
               "other_session_commitment": "checking against a commitment from another session "
               "using the same weights",
               "commitment_id": "checking against a commitment ID never recorded by any session"}  # fmt: skip
# what a trial whose every changed call was refused shows, by its change
KEPT_MEANS = {"other_session_commitment": "Rejecting a modified weights' commitment does not on "
              "its own prove that the verifier distinguishes weights, because it also rejects a "
              "separate commitment generated from the same weights."}  # fmt: skip
KEPT_TIME = "the trial script's wall clock"
STATEMENT_WORD = {
    "stated": "the publisher explicitly states that an accepted proof means the reply is the "
    "committed model's greedy output for the prompt",
    "read": "combining several passages from the publisher (no single sentence says it alone), "
    "we read an accepted proof as meaning the reply is the committed model's greedy output",
    "not": "not stated: the documents we read at the pinned commit do not state that an accepted "
    "proof means the reply is the committed model's greedy output, so the row is unranked",
}
READ_AS = "our reading"  # before ACCEPT_STATE["read"], linked to the checks page's #reading

# ------------------------------------------------------------------ the five petals (RFC-0018 §The glyph)
# the display names (RFC-0018 §The glyph, amended 2026-11-16, Q37); the ids stay
PETAL_NAME = {"unforgeable": "Integrity", "weights_hidden": "Confidentiality",
              "faithful_model": "Fidelity", "machine_checked": "Formally verified",
              "no_trusted_party": "Trust assumptions"}  # fmt: skip
# each petal's field term, in the title of its name's link on a system page and under its name on
# the checks page (depths 2 to 4): the plain name for the policy reader, the term for the expert
PETAL_TERM = {"unforgeable": "soundness",
              "weights_hidden": "zero knowledge of the weights",
              "faithful_model": "quantization error, in matched leading tokens",
              "machine_checked": "machine-checked soundness proof",
              "no_trusted_party": "trusted setup or party"}  # fmt: skip
# the title of a criterion's name on a system page, which the probe shows beside it: its field term
FIELD_TERMS_TITLE = "in the field's terms: {term}"
# each petal in plain words: a question, what it grades, whom it protects, what Met means. The
# name's title at depths 1 and 2; printed on the checks page
PETAL_PLAIN = {
    "unforgeable": "Could a provider get a reply accepted that the committed model did not "
    "actually compute? Integrity grades the soundness bound stated by the publisher and whether "
    "it covers the exact setup we run. It protects the customer. Met requires a proved error "
    "bound of at most 2^-128 (128 bits) covering what we run.",
    "weights_hidden": "Does checking a proof leak the model's weights? Confidentiality grades "
    "what the publisher states and proves about weight hiding. It protects the provider. Met "
    "requires zero knowledge proved for the exact setup we run.",
    "faithful_model": "Does the proved model behave like the publisher's original release? "
    "Because provers usually run a quantized copy with fewer bits per number, Fidelity compares "
    "the proved replies against the original using standard 8-bit and 4-bit copies as "
    "yardsticks. It protects the customer. Met requires scoring closer to a rerun of the "
    "original than to the 8-bit copy.",
    "machine_checked": "Has a proof assistant checked the mathematical proof that false replies "
    "are rejected, and does that proof reach the actual verifier binary we run? It protects the "
    "customer. Met requires a machine-checked proof covering the verifier we run.",
    "no_trusted_party": "Does checking a proof rely on trusting anyone beyond mathematics, such "
    "as whoever ran a one-time setup or controls a hardware signing key? It protects the "
    "customer. Met requires the publisher to state that verification rests on cryptography alone.",
}
# whom each petal protects (the "Protects" line on the checks page and in an opened criterion)
PETAL_PROTECTS = {"unforgeable": "the customer", "weights_hidden": "the provider",
                  "faithful_model": "the customer", "machine_checked": "the customer",
                  "no_trusted_party": "the customer"}  # fmt: skip
# a petal's stored (step, cause) in words (RFC-0018 §The glyph, step table, amended 2026-11-16):
# one word set for all five petals, keyed by the step, and by the cause where red splits; the
# inks are drawn, never printed (SI-6)
STEP_WORD = {"green": "Met", "amber_upper": "Mostly met", "amber_lower": "Partly met",
             ("red", "stated"): "Not met", ("red", "check_failed"): "Failed",
             ("red", "not_stated"): "Not stated", None: "Not decided"}  # fmt: skip


def step_key(step, cause):
    """The STEP_WORD key of a stored (step, cause): red splits by its cause."""
    return (step, cause) if step == "red" else step


def petal_step(p):
    """A petal's step in words (STEP_WORD)."""
    return STEP_WORD[step_key(p["step"], p["cause"])]


# why a petal is red or hollow (GL-1, GL-3); the checks page defines each at #cause-<id>
CAUSE_WORD = {"not_stated": "not stated",
              "stated": "below Partly met, as the publisher states it",
              "check_failed": "a check failed, or the proof build failed",
              "not_read": "not read yet",
              "not_decided": "Fidelity check not decided or not recorded",
              "proof_build_not_run": "waits on our finished build of the publisher's machine-checked proof"}  # fmt: skip
# each cause in a line, on the checks page (#cause-<id>), opened by its word and how it is drawn:
# the checks page draws that opening as the chip a system page prints for the petal
# (PETAL_CAUSE_DRAW), the words kept for a screen reader
PETAL_CAUSE_RULE = {
    "not_stated": "Not stated (drawn as an outline): the publisher's documentation at the pinned "
    "commit says nothing about this property. Because users cannot rely on an unstated "
    "guarantee, we grade silence at the bottom rather than leaving it undecided.",
    "stated": "Not met or Failed (drawn filled, name struck): the publisher explicitly states "
    "that the property does not hold, or what it states falls below Partly met.",
    "check_failed": "Not met or Failed (drawn filled, name struck): one of our entry checks "
    "failed, or our rebuild of the publisher's machine-checked proof failed or reported "
    "undeclared axioms.",
    "not_read": "Not decided (drawn hollow): our properties record is missing, uses an older "
    "schema, or was read at a different commit than the one we ran (or the row has no recorded "
    "commit). We never mark unread documentation as silent.",
    "not_decided": "Not decided (drawn hollow), Fidelity only: the Fidelity check is not "
    "decided, or the row has no recorded fidelity scores.",
    "proof_build_not_run": "Not decided (drawn hollow), Formally verified only: the publisher "
    "claims a machine-checked proof, but we have no completed rebuild of the named theorem at "
    "the pinned commit using the publisher's pinned toolchain (or the recorded build timed out "
    "or was killed before finishing). If the publisher pins no toolchain, no build can match.",
}
# how a cause's opening words are drawn: (state, form) of the chip, its word the cause's step's
# (STEP_WORD)
PETAL_CAUSE_DRAW = {"Not stated (drawn as an outline)": ("red", "open"),
                    "Not met or Failed (drawn filled, name struck)": ("red", ""),
                    "Not decided (drawn hollow)": ("hollow", "")}  # fmt: skip
# what a petal decided on the publisher's documents comes from when a fact it read carries a note
# (the board petal's `reading`), and what that means, on the checks page (#reading, a block of its
# own after the causes, headed by BASIS_READING[1]; GL-1, GL-5)
BASIS_READING = ("the publisher's documents", "our reading")
READING_RULE = (
    "At least one fact behind this grade comes from our interpretation of multiple passages "
    "rather than a single explicit sentence from the publisher. The petal flags that it relies "
    "on our reading, links the supporting quotes, and caps the grade at Mostly met for every "
    "system equally. We never infer claims simply from the name of a cryptographic construction."
)
# Machine-checked's scope card: what is machine-checked, for which program (printed, sets no state)
SCOPE_ROW_WORD = {"soundness": "Soundness", "zero_knowledge": "Zero knowledge",
                  "completeness": "Completeness"}  # fmt: skip
SCOPE_COL_WORD = {"protocol": "Protocol", "verifier_run": "The verifier we run",
                  "prover_run": "The prover we run"}  # fmt: skip
# "tested" is the publisher's word for its own tests ("tested, not proved"), never ours: our runs are
# the Completeness line above the card
SCOPE_VALUE_WORD = {"machine_checked": "machine-checked", "paper": "on paper",
                    "tested": "tested by the publisher, not proved",
                    "not_stated": "not stated", "does_not_apply": "does not apply"}  # fmt: skip
# the scope card's bound column head, and the three lines over the card (MC-6, amended
# 2026-11-15): what the publisher states and what we test, for the row
SCOPE_BOUND_HEAD = "Bound, as stated"
# beside the claim card's link, while web/_data/errata.json corrects the card ({fields}, {says})
CARD_ERRATUM = "Erratum: the card's {fields} describe {says}. At Level 1:"
SCOPE_CARD_HEAD = (
    "What is verified, and for which code, as the publisher states it. It sets no state."
)
# the one line under the five criteria (RFC-0018, the paragraph after MC-7, amended 2026-11-17, owner
# decision): the three properties a proof system is read for, in priority order, each its
# glossary entry, then where it is graded or tested; what each means and whom it protects is the
# glossary's. (glossary id, name, the petal that grades it or None)
SCOPE_TERMS = (("soundness", "Soundness", "unforgeable"),
               ("zero-knowledge", "Zero knowledge", "weights_hidden"),
               ("completeness", "Completeness", None))  # fmt: skip
SCOPE_TESTED = "{n} of {n} replies accepted, our {run}"
SCOPE_CARD_WORD = "scope card"  # with the stated security, behind one disclosure under the line
STATED_SECURITY = "Stated security"
NOTION_HEAD = "Its notion, as the publisher names it"
# Weights hidden: what kind of value a proof leaves visible (only fitted_to_weights sets a step)
VISIBLE_TAG_WORD = {"statement_io": "the statement's input or output", "shape": "shape",
                    "side_channel": "side channel",
                    "fitted_to_weights": "depends on the weights"}  # fmt: skip
# the head of the visible values not tagged fitted, after those that are: "8 others" (an untagged
# item's quote does not say it is fitted; that does not show it is not, AGENTS.md rule 9)
VISIBLE_OTHERS = "others"
# the kinds, in plain words (RFC-0018 WH facts: `side_channel`, `shape`, `statement_io`)
VISIBLE_KINDS = ("side channel: seen around a proof, such as time, lengths, failures or volume \u00b7 "
                 "shape: the architecture and sizes \u00b7 the statement's input or output: the prompt, the reply, "
                 "served or refused")  # fmt: skip
# each petal's question in the field's terms, RFC-0018's petal table ("rung" said "model"): on the
# checks page under the plain sentence, and its search line
PETAL_QUESTION = {
    "unforgeable": "The soundness bound stated by the publisher on a false reply being accepted, "
    "whether it is proved, and whether it covers the exact setup we run.",
    "weights_hidden": "What the publisher states and proves about proofs keeping the model's "
    "weight values secret.",
    "faithful_model": "How closely the proved replies match the publisher's original release, "
    "measured against standard 8-bit and 4-bit quantized copies.",
    "machine_checked": "How far a machine-checked soundness proof reaches: part of the protocol, "
    "an abstraction of it, the protocol with the model, or the actual verifier binary we run.",
    "no_trusted_party": "What verification depends on beyond cryptography: a setup secret, a "
    "fixed group of parties, or a hardware vendor's or other trusted key.",
}
# each petal's steps, RFC-0018's tables in plain sentences, top step first: (STEP_WORD key, rule);
# a rule that is a tuple prints as a list. The first line that matches decides (§Reading the
# tables); 128, 100 and 80 are RFC-0018's cut points, 0.05 the level's fidelity.alpha. A petal
# lists only the steps it can take: Fidelity has no Not met or Not stated (it is a test), Trust
# assumptions no Failed (no check lowers it)
NOT_READ_RULE = "We have not yet read the publisher's documentation at the commit we run."
PETAL_RULE = {
    "unforgeable": (
        ("green", "A proved soundness bound covering what we run, with every exponent at least "
         "128."),
        ("amber_upper", "A proved bound covering what we run with every exponent at least 100, "
         "or a Met-level bound that depends on our reading."),
        ("amber_lower", "Any other stated bound above Not met: conjectured, not shown to cover "
         "what we run, or a proved bound with an exponent between 80 and 99."),
        (("red", "stated"), "The bound holds only against a weaker adversary, has an exponent "
         "below 80, or is unproved with an exponent below 100."),
        (("red", "not_stated"), "The documentation read at the pinned commit gives no soundness "
         "bound with exponents."),
        (("red", "check_failed"), "Our Model, Prompt, or Reply check failed."),
        (None, NOT_READ_RULE),
    ),
    "weights_hidden": (
        ("green", "A zero-knowledge theorem proved for the exact configuration and batch size we "
         "run, stated for the actual programs we run, paired with a published list of visible "
         "values containing nothing that depends on the weights."),
        ("amber_upper", "A zero-knowledge theorem is proved, but at least one requirement for "
         "Met is missing."),
        ("amber_lower", "The publisher states that proofs hide the weights, without a "
         "zero-knowledge theorem."),
        (("red", "stated"), "The verifier receives the weights, or the publisher states that "
         "proofs do not hide them."),
        (("red", "not_stated"), "The documentation read says nothing about hiding the weights."),
        (("red", "check_failed"), "Our Verify without weights check failed."),
        (None, NOT_READ_RULE),
    ),
    # FM-5, FM-6, FM-7 in the RFC's order, then FM-1 and FM-2
    "faithful_model": (
        ("green", "Replies score significantly above the midpoint between a rerun of the "
         "original and the 8-bit copy, in a fidelity run sending one request at a time."),
        ("amber_upper", "Replies score significantly above the midpoint between the 8-bit and "
         "4-bit copies."),
        ("amber_lower", (
            "The Fidelity check passed, but replies are not shown above the midpoint between "
            "the 8-bit and 4-bit copies.",
            "Or no claim card exists, or its decoding policy accepts tokens other than the "
            "model's top token.",
            "Or a reference copy needed for a midpoint did not run, failed, or was scored on a "
            "different number of replies.",
        )),
        (("red", "check_failed"), "The Fidelity check failed: the pass bar (a damaged copy) "
         "scores above the system's replies."),
        (None, "The Fidelity check is not decided, or no fidelity record is stored."),
    ),
    # §3 (amended 2026-11-16): the step grades what is verified (REACH_LABEL)
    "machine_checked": (
        ("green", "Rebuilt by us: the proof covers the actual verifier binary we run from raw "
         "input bytes to verdict, lists its trusted base, and leaves no input-reading code "
         "outside the proof."),
        ("amber_upper", "Rebuilt by us: the proof covers the protocol including the model's "
         "computation, or covers the verifier binary with a gap in its trusted base or "
         "input-reading code."),
        ("amber_lower", "Rebuilt by us: the proof covers an abstraction of the protocol (the "
         "protocol without the model, or the model without the protocol) or only part of the "
         "protocol. Theorems whose conclusion is not about the model, or builds relying on "
         "non-standard axioms, also stop here."),
        (("red", "stated"), "The publisher states that nothing is machine-checked."),
        (("red", "not_stated"), "The documentation read names no machine-checked proof."),
        (("red", "check_failed"), "Our rebuild of the named theorem failed or reported undeclared "
         "axioms, or our Model, Prompt, or Reply check failed on a system claiming Met."),
        (None, "A machine-checked proof is claimed, but our rebuild is not recorded yet or "
         "stopped before reaching a verdict, or we have not yet read the documentation at the "
         "pinned commit."),
    ),
    # NT-4 comes before NT-5 and NT-6; Q12's line is printed under the steps (PETAL_MORE)
    "no_trusted_party": (
        ("green", "The publisher explicitly states that soundness rests on cryptography alone "
         "and no setup produced a secret. Proofs must also be publicly verifiable unless the "
         "publisher is silent on who can check them."),
        ("amber_upper", "An open setup ceremony with a public transcript that holds if at least "
         "one participant was honest, or Met-level facts established only via our reading."),
        ("amber_lower", "Relies on one honest party within a fixed group, a live challenger "
         "within a time window, or proofs only a designated verifier can check."),
        (("red", "stated"), "Relies on a single-party trusted setup, a hardware vendor's key, "
         "or another trusted key."),
        (("red", "not_stated"), "The documentation read says nothing about what soundness "
         "depends on."),
        (None, NOT_READ_RULE),
    ),
}  # fmt: skip
# a petal's terms, defined under its steps, as (label, words)
PETAL_MORE = {
    "unforgeable": (
        ("covers what we run", "The bound applies to our benchmark settings against any cheating "
         "prover, covers a full reply (or one proof per reply), and holds when each reply is "
         "verified individually. Records show its preconditions hold for our files, and the "
         "verifier program we run is proved or stated to match the bound. An unrecorded batch "
         "size is treated as uncovered."),
        ("exponent", "In 2^-t or q/2^t, the exponent is t, where a larger exponent means a "
         "smaller forgery probability. When a bound sums multiple terms, every term must clear "
         "the threshold. We read exponents verbatim as stated by the publisher without inventing "
         "our own bit counts or fixing a query budget q. A bound stated per segment or layer is "
         "read per part as stated; not covering a full reply counts as a coverage gap without "
         "lowering the grade further."),
    ),
    "faithful_model": (
        ("halfway", "The arithmetic midpoint of two reference copies' unrounded mean scores."),
        ("one request at a time", "Every part of the model's fidelity run executes one request "
         "at a time in llama.cpp (slots = 1). When pinned llama.cpp cannot run the original "
         "model, the original and its rerun execute in vLLM in a single batched call, which does "
         "not count as one-at-a-time (the rerun sends prompts in reverse order so its batches "
         "differ from the first pass)."),
        ("shown above", "Our paired sign-flip test gives p\u00a0<\u00a00.05 comparing the "
         "system's scores against the midpoint."),
        ("measure", "This petal is graded on matched leading tokens, the same metric used by "
         "the Fidelity check. The headline Fidelity figure reports top-token agreement and sets "
         "no grade."),
    ),
    "machine_checked": (
        ("build", "Every grade above Not met requires a recorded rebuild of the named theorem "
         "at the pinned commit using the publisher's pinned toolchain. We run the publisher's "
         "own verification command unpatched and log its output. We do not audit the theorem's "
         "formal semantics; we grade its reach from the publisher's quotes shown with the "
         "petal."),
        ("above Partly met", "Grades above Partly met require a theorem whose conclusion refers "
         "to a formal definition of the model, rebuilt using only the proof assistant's standard "
         "axioms (in Lean: propext, Classical.choice, and Quot.sound, with no sorry). Each "
         "system page notes that no outside expert has reviewed the theorem statement."),
        ("the code", "Only the verifier binary we actually execute counts as the code. A "
         "verified reference verifier that we do not run counts at the protocol level."),
        ("protocol or code", "A proof about a formal model of the algorithm verifies the "
         "protocol rather than the implementation. Level 1 distinguishes the full protocol "
         "(including the model's computation) from an abstraction (omitting either the model or "
         "the protocol). Only a proof covering the actual verifier binary verifies the code."),
        ("scope card", "Printed under a system's petals for context without affecting any grade, "
         "since this petal covers soundness alone. Because soundness belongs to the verifier and "
         "zero knowledge to the prover, opposite-party cells read 'does not apply'."),
    ),
    # Q12: printed under the steps, as the question is printed over them
    "no_trusted_party": (
        ("", "This petal does not grade which real model a commitment represents, nor whether "
         "soundness is proved or conjectured (Integrity covers that). Preconditions requiring "
         "public files to be fixed before hashing are also tracked under Integrity."),
    ),
}  # fmt: skip
# what each petal leaves to another place, under its steps on the checks page
PETAL_NOT_GRADED = {
    "unforgeable": "Integrity grades soundness only, not completeness (which the Run check "
    "tests). Failing our Model, Prompt, or Reply checks flips this petal to Failed, though "
    "passing them never measures the soundness bound.",
    "weights_hidden": "Confidentiality does not grade hiding the model architecture, because "
    "every Level 1 model has open weights (a closed-weights level would grade it). Failing "
    "Verify without weights flips this petal to Failed, though passing it cannot measure what a "
    "proof reveals.",
    "machine_checked": "Formally verified does not grade prover code, which affects completeness "
    "and zero knowledge (shown separately on the scope card without setting a grade). Publisher "
    "caveats outside the five graded criteria (reach, conclusion, input-reading code, axioms, "
    "and our rebuild) are displayed without lowering the grade. Two rule questions remain open: "
    "whether grades above Partly met should require showing the verifier accepts honest proofs "
    "on our files, and whether trials of alternate verifiers should affect grades (currently "
    "they do not).",
}
# once for the checks page's glyph section, after the steps
PETAL_STEPS_FOOT = "Each system page shows what every petal still needs for Met and who must act, computed directly from these rules."
# Formally verified: what is verified, by `formal.reach` (§3, amended 2026-11-16); glyph.py's
# _REACH_WORDS holds the same words for the reasons
REACH_LABEL = {"verifier_run": "the verifier we run",
               "protocol_and_statement": "the protocol, model included",
               "protocol": "an abstraction of the protocol (the protocol without the model, or "
               "the model without the protocol)",
               "part": "part of the protocol",
               "none": "nothing, as the publisher states", "not_stated": "not stated"}  # fmt: skip
# a petal's next step (GL-11), at depth 3 under its reason
NEXT_HEAD = {"up": "Next step, {to}", "decide": "To decide", "repair": "Next step"}
NEXT_BY = {("publisher",): "By the publisher.", ("us",): "By us.",
           ("publisher", "us"): "By the publisher and us."}  # fmt: skip
# ------------------------------------------------------------------ a criterion on a system page (RFC-0018 SI-3, GL-11,
# amended 2026-11-17 and 2026-11-22, owner decisions): what full marks need, what the system has, what it misses
# and who acts, and where to check. Every line is worded here from the board's keys; nothing is typed per system.
# the grade scale, one click down at the Criteria section's title (amended 2026-11-22, owner
# decision): each grade in its ink, best first, linked to its definition in the glossary
GRADE_SCALE = (("green", "Met", "met-mostly-met-partly-met"),
               ("amber", "Mostly met", "met-mostly-met-partly-met"),
               ("amber cut", "Partly met", "met-mostly-met-partly-met"),
               ("red", "Not met", "not-met"), ("red open", "Not stated", "not-stated"),
               ("red", "Failed", "failed"), ("hollow", "Not decided", "not-decided"))  # fmt: skip
GRADE_SCALE_HEAD = "Grades"
# between two grades on the scale line: an angle quote (U+203A) where the left one is higher, a
# slash between the three reds, which are not ranked among themselves, a middle dot before Not
# decided, which is on no rank
GRADE_SCALE_SEP = ("\u203a", "\u203a", "\u203a", "/", "/", "\u00b7")
# each petal's plain question, under its name in its row
PETAL_ASK = {
    "unforgeable": "Could a fake reply pass verification?",
    "weights_hidden": "Does a proof keep the model weights secret?",
    "faithful_model": "Does the proved model answer like the original?",
    "machine_checked": "Has a proof assistant checked that fake replies are rejected?",
    "no_trusted_party": "Does checking rely on a trusted setup or party?",
}
# what a grade comes from (the board's `sources`), beside the grade
CAME_FROM = {
    "test": "our test",
    "statement": "the publisher's words",
    "statement_reading": "the publisher's words and our reading",
    "build": "the publisher's words and our rebuild",
    "build_reading": "the publisher's words, our rebuild, and our reading",
}
FROM_WORD = "from"
# an opened row's three lines under its question, in this order
PROTECTS_HEAD, NEEDS_HEAD, HAS_HEAD = "Protects", "Met needs", "Has"
# beside the grade, where a reading of ours sets it (GL-10), linked to the checks page's #reading
READING_MARK = "our reading"
# the row's one control: how many items Met lacks; with none, the evidence alone
MISSING_TAG = "{n} missing"
EVIDENCE_TAG = "Evidence"
# who acts on an opened row's items: under each item where both act, else once under them all
WHO_HEAD = "Who acts"
WHO_TAG = {"publisher": "publisher", "us": "us"}
# the track in words, for a screen reader (the drawing is hidden from it): each grade the row
# holds, and for each it does not how many items it lacks, or that the board lists none for it
# yet (a grade past the last one listed, drawn dashed); a decision or a repair before any grade
TRACK_SAID = {"held": "{grade}: held", "open": "{grade}: {n} missing",
              "unlisted": "{grade}: items not listed", "lead": "{grade}: {n} missing"}  # fmt: skip
# Fidelity's opened row: its mean, what each grade needs and the runs those thresholds are
# halfway between (and the bar's copy), as bars from zero to the reply's length; the axis says
# the measure and n
CHART_CAPTION = "matched leading tokens, mean, n\u00a0=\u00a0{n} prompts"
CHART_NEEDS = "{grade} needs"  # a grade's threshold, as the "Met needs" line names it
CHART_NOT_SHOWN = ", not shown"  # a threshold the mean is above, not shown above by the test
CHART_BAR = "the bar"  # after the pass bar's copy, linked to its glossary entry
# the one more click down in an opened row: this system's own facts in full
IN_FULL = "Why this grade"
# what full marks need, per petal, in a few words for the opened row ({green}: Fidelity's Met
# threshold)
NEEDS_TINY = {
    "unforgeable": "a proved bound of 2^-128 for {run}",
    "weights_hidden": "a zero-knowledge theorem for the exact setup we run",
    "faithful_model": "an average shown above {green} tokens, one request at a time",
    "machine_checked": "a rebuilt formal proof covering {run}",
    "no_trusted_party": "an explicit publisher statement: cryptography only, no setup secret",
}
# the row's one sentence: the first item missing for Met, in plain words (amended 2026-11-17),
# by the item's `need`; GAP_ANY words an item with no sentence of its own
GAP = {
    "none": "Nothing missing.",
    "decide": "To decide: {need}.",
    "repair": "To repair: {need}.",
    "program_proved": "The bound is proved for {stated}, not for {run}.",
    "program_stated": "The bound is stated for {stated}, not for {run}.",
    "program_none": "The stated bound does not name a verifier.",
    "zk_batch": "The theorem covers one request per proof, not our {n}-reply batches.",
    "zk_run": "The theorem does not cover the exact setup we run.",
    "above": "Our test has not shown an average above {value} matched tokens, as {to} requires.",
    "one_at_a_time": "Our fidelity run did not execute one request at a time.",
    "reach_stated": "The formal proof stops at {stated} and does not cover {run}.",
    "reach_none": "No formal proof covers {run}, the verifier we run.",
    "rests_sentence": "No single publisher sentence says checking rests on cryptography alone.",
    "no_setup_secret": "The setup produced a secret in an open ceremony.",
    "hide_statement": "We read {docs} and found no claim about hiding the weights.",
    "zk_theorem": "The publisher does not prove a zero-knowledge theorem.",
    "named_theorem": "We found no machine-checked theorem named in the {docs} we read.",
    "basis_conjectured": "The bound rests on an unproven conjecture rather than a theorem.",
    "basis": "The documentation we read does not say whether the bound is proved.",
    "exponent": "At least one term in the bound is weaker than 2^-{floor}.",
    "reading": "Met requires explicit publisher wording {topics}, whereas today we rely on our reading.",
}
GAP_ANY = "Missing: {need}."
# what full marks need, per petal, in one line, one click down under "Why this grade" ({green}:
# Fidelity's Met threshold)
NEEDS_SHORT = {
    "unforgeable": "a proved bound of at most 2^-128 on a fake reply passing the verifier we run",
    "weights_hidden": "a theorem proving that proofs of the exact setup we run reveal nothing "
    "about the weights",
    "faithful_model": "an average shown above {green} matched leading tokens in a one-at-a-time "
    "fidelity run",
    "machine_checked": "a machine-checked theorem, rebuilt by us, proving that the verifier we "
    "run rejects fake replies",
    "no_trusted_party": "an explicit statement from the publisher that verification needs no "
    "setup secret and no trusted party",
}
# the blocks one click down in an opened row (IN_FULL), in order: this system's own facts
PETAL_BLOCK = {"needs": "Met needs, in full", "has": "What this system has",
               "missing": "Where each item stands today",
               "records": "Our records", "terms": "In the field's terms",
               "limits": "Limits stated by the publisher (not graded)"}  # fmt: skip
# who acts on an item, one click down where both act ("for the publisher")
WHO = {"publisher": "for the publisher", "us": "for us"}
# the word over a track's first cell, where a row lacks items before any grade: a Not decided
# row's decision, a Failed row's repair
MISSING_STEP = {"decide": "To decide", "repair": "To repair"}
# the topics our reading covers, per fact: (subject, predicate), so two that share a subject
# read "that the limit holds ... and is ..."
READING_TOPIC = {
    "adversary": ("the bound", "holds against any cheating prover"),
    "parameters": ("the bound", "applies to the settings we run"),
    "unit": ("the bound", "covers a whole reply"),
    "batch": ("the bound", "covers each reply checked individually"),
    "conditions_shown": ("its preconditions", "hold for our files"),
    "program": ("the bound", "covers the verifier we run"),
    "basis": ("the bound", "is mathematically proved"),
    "stated": ("a proof", "hides the weights"),
    "proof": ("the theorem", "covers the setup we run"),
    "programs": ("its compiled programs", "keep the weights secret"),
    "visible_listed": ("its list of visible values", "is complete"),
    "verifier_gets_weights": ("the verifier", "never receives the weights"),
    "reach": ("the theorem", "covers the model's computation"),
    "conclusion": ("its conclusion", "is about the model"),
    "rests_on": ("soundness", "rests solely on cryptographic assumptions"),
}  # fmt: skip
# the opened row's evidence lines, then the heads one click down
EVIDENCE = {
    "quotes": "Publisher's quotes at {pin} ({n})",
    "notes": "Our reading notes ({n})",
    "docs": "Documents checked ({n})",
    "forms": "Zero knowledge, as stated ({n})",
    "visible": "What stays visible ({n})",
    "head": "Evidence",
    "from": "From {src}",
    "points": " ({n} points)",
    "checks_short": "Our {names} check{s}: {state} ↓",
    "rebuild_short": "Our rebuild: exit code {code}",
    "fidelity_short": "Our fidelity run, {n} ↓",
    "none_short": "no harness test bears on this property",
    "rebuild": "Our rebuild:",
    "outside": "Outside the grade:",
    "used": "This grade uses our reading {this}.",
    "not_used": "This grade does not rely on our reading {this}, though Met still requires explicit publisher wording there.",
}  # fmt: skip
# what each petal's tests do, under Evidence
RECORDS = {
    "unforgeable": "in our Model, Prompt, and Reply checks, we hand the verifier proofs with an "
    "altered weight, prompt token, or reply token. {state}",
    "weights_hidden": "in our Verify without weights check, we confirm every verdict ran with no "
    "model files on disk and no GPU visible. {state}",
    "machine_checked": "our Model, Prompt, and Reply checks {state}.",
    "no_trusted_party": "no harness test bears on this property.",
}
RECORD_LINK = "Record ↗"
SCOPE_LINK = "the scope table further down this page ↓"
# ------------------------------------------------------------------ the figures (RFC-0018 §Cost, FI-7)
# The figures the checks page defines: the anchor on the checks page, the figure's name, and the
# definition as (label, words) lines, a line with no label its figure's own. {slots}, {gap} (the
# release-group gap), {full} (the share of the highest rate that is full load) and {top} (the
# ladder's top concurrency) are the level file's constants; 3 and 5 % (steady.min_later_groups,
# steady.tolerance), 1 (baseline.ladder's first rung), 64 and 512 (kl.texts, kl.tokens) are typed
# as the level's. "fidelity-figure" is the figure the ladder prints as Fidelity (SI-9); "fidelity"
# is the check's anchor.
FIGURE_NAME = {"multiple": "Cost vs serving", "proving": "Proving vs serving",
               "one-time": "One-time work", "cost": "Cost per reply", "rate": "Tokens per second",
               "check-time": "Verify time per reply", "proof-size": "Proof size per reply",
               "fidelity-figure": "Fidelity figure", "kl": "KL to the original weights"}  # fmt: skip
# a figure's head where its unit stands beside it: the unit says "per reply", so the head does
# not; and the surface names fidelity, not the metric (KL and the matched tokens' bar are under
# Fidelity on a system's page)
FIGURE_HEAD = {"multiple": "Cost vs serving", "proving": "Proving vs serving",
               "one-time": "One-time work", "cost": "Cost", "check-time": "Verify time",
               "proof-size": "Proof size", "fidelity": "Fidelity", "serving": "Serving",
               "rate": "Tokens per second"}  # fmt: skip
# where a head links on the checks page, where its anchor is not its key: the Fidelity figure has
# a rule of its own there, apart from the check it does not set (SI-9)
FIGURE_ANCHOR = {"fidelity": "fidelity-figure"}
# the plain question a ladder column answers, in its head's title (amended 2026-11-23, owner
# decision, RFC-0018 Q54): the head stays the site's term, linked to its definition
FIGURE_ASK = {"multiple": "What does proving cost?", "proof-size": "How big is the proof?",
              "check-time": "How long to check a proof?",
              "fidelity": "Same as the original model?"}  # fmt: skip
# the same for a board built by the further-reply rule (RFC-0018 CO-9, Q55): the two multiples
FIGURE_ASK_FURTHER = {"multiple": "What does a proved reply cost, writing it included?",
                      "proving": "What does the proof cost once the reply is written?"}  # fmt: skip
# the ladder's columns before the figures, named for a screen reader only: the eye reads them from
# the square, the glyph and the name (Q54)
LADDER_COLS = ("Position", "Criteria", "System")
# how the headline is computed, in one plain sentence (B5): at the Cost section's head and first
# in the headline figure's title, by the figure printed (`chrome.lead_figure`); {on} the GPUs
HOW_MULTIPLE = {
    "session_multiple": "Cost vs serving divides the GPU-seconds a proved reply took over whole "
    "sessions (from the start of the commit call to the last proof: commit, generation and "
    "proving, not the loading before the commit) by the GPU-seconds serving the same reply took "
    "with no proof, at full load, {on}, at the same GPU price on both sides.",
    "multiple": "Cost vs serving divides the GPU-seconds each further proved reply took in steady "
    "state (generation included) by the GPU-seconds serving the same reply took with no proof, "
    "at full load, {on}, at the same GPU price on both sides.",
    # CO-9 (adopted 2026-11-26, Q55): every release after v1.0
    "further_reply_multiple": "Cost vs serving divides the GPU-seconds a further proved reply "
    "takes (from the start of the prove call to the last reply, generation included, the "
    "one-time work before it left out) by the GPU-seconds serving the same reply took with no "
    "proof, at full load, {on}, at the same GPU price on both sides.",
    "further_reply_proving_multiple": "Proving vs serving divides what a further reply costs "
    "once its tokens exist (the further reply less its generation) by the GPU-seconds serving "
    "the same reply took with no proof, at full load, {on}, at the same GPU price on both sides.",
}
HOW_ON = {True: "both on {gpu} GPUs", False: "proved on {gpu}, served on {serving}"}
SERVING_GPU = "H200"  # CO-4: the serving baseline runs on the fewest H200 that hold the model
# CO-8 (adopted 2026-11-16): reply tokens per GPU-second under Cost (depth 3); amended 2026-11-16,
# 2026-11-23: on the ladder the proved rate prints under the multiple (`ladder.rate_html`) and the
# served rate once on its model's divider (`ladder.served_html`)
REPLY_TOKENS_HEAD = "Tokens per second"
# that line (Q41): the proved rate's word after its number ("2.027 proved"; on the ladder heard,
# not printed, its rate standing under its model's served rate, Q54), then its unit and GPU
# ("tokens/s per H200"); a model's divider prints its served rate in the same unit
RATE_PROVED = "proved"
RATE_PER = "tokens/s per {gpu}"
# its title, first: how the two rates are read against the multiple above them
RATE_HOW = ("how: the request's {tokens} reply tokens over the GPU-seconds one reply took, on "
            "one GPU")  # fmt: skip
RATE_IS = "ratio: served ÷ proved = {multiple}, Cost vs serving"
FIDELITY_TITLE = "leading tokens matching the original, mean"  # in a fidelity word's title
# Fidelity as a figure (RFC-0018 SI-9, amended 2026-11-14): FI-10's mean as a percentage of the
# reply's positions, beside the model's Q8_0 and Q4_K_M copies; it sets no state
FIDELITY_AGAINST = ("q8_0", "q4_k_m")  # the controls printed once on a model's divider
FIDELITY_FIG_TITLE = ("Fidelity figure: the share of reply positions where the system's top token is "
                      "the original's reply token, fed the prompt and then that reply token by "
                      "token")  # fmt: skip
# the copies printed with a row's Fidelity at depths 1 and 2 (RFC-0018 SI-9, amended 2026-11-16;
# on the ladder once, on the model's divider, amended 2026-11-23): plain words; their ids (Q8_0,
# Q4_K_M) stand in titles and at depth 3
COPY_WORD = {"q8_0": "8-bit copy", "q4_k_m": "4-bit copy"}
# a copy's Fidelity figure on the ladder: what it is, first in its title ({copy}: CONTROL_NAME's)
COPY_FIG_TITLE = ("Fidelity of the {copy}, run unproved on the same prompts: the share of reply "
                  "positions where its top token is the original's reply token")  # fmt: skip
# what the row proves, on its system page (the Fidelity block's Proved line and the Fidelity
# criterion): the weight bits (the workload record) and the number format (the properties file,
# the publisher's words), one word per recorded value
FORMAT_WORD = {"integer": "integer", "fixed_point": "fixed-point",
               "floating_point": "floating-point"}  # fmt: skip
PROVED_HEAD = "proved"
FORMAT_HEAD = "number format"  # the depth-3 Proved line's words where none is stated
# the Cost section's Serving line points to the Proved line at the head of Fidelity
PROVED_LINK = ("the copy this row proves", " is under Fidelity")
# how a workload record found its weight bits, in words
BASIS_BITS = {"computed": "computed from its files", "stated": "as the publisher states it",
              "file_size": "from its file size"}  # fmt: skip
# why the surface figure is top-token agreement, in one line ({tokens}: the request's reply tokens)
WHY_HEAD = "Why top-token agreement: "
WHY_TOP_TOKEN = (
    "Why top-token agreement: greedy decoding chooses the top token at each step, so this "
    "measures how often the proved model makes the same choice as the original across all "
    "{tokens:,} positions, not just up to the first mismatch."
)
FIDELITY_CHECK_TITLE = "Fidelity check: {state}"
# FI-16: the row's pass against its proofs, in the Fidelity figure's title
FIDELITY_PROVED_TITLE = (
    "against the proofs: the proved token at {agreeing:,} of {positions:,} positions a proof covers"
)


def beside_unit(name):
    """A figure's name where its unit follows it: "per reply" is the unit's to say."""
    return name.replace(" per reply", "")


FIGURE_RULE = {
    "multiple": (
        ("multiple", "Steady proving cost m divided by serving baseline b on the same model. GPU "
         "time counts only the H200 GPUs allocated to the job."),
        ("m", "Mean GPU-seconds per proved reply (including generation) across {slots} sessions. "
         "Proofs released within {gap} of the previous one form a release group. m measures the "
         "time from the end of the first group to the end of the last group divided by the "
         "replies released after the first group. If a system generates replies in a separate "
         "phase, m adds that phase's GPU-seconds divided by all session replies."),
        # CO-4; FP8 on Maverick is the level file's serving record (the original is 16-bit, FI-1)
        ("b", "GPU-seconds per reply when serving the same request without a proof. The model "
         "publisher's release (FP8 on Llama 4 Maverick) runs on the pinned engine at full load "
         "using the fewest NVIDIA H200 GPUs that fit it. Full load is the lowest concurrency "
         "(doubling from 1 to {top}) that reaches {full} of peak throughput; if that happens only "
         "at {top}, the model is not saturated and has no b."),
        ("whole sessions", "A row has a steady m when every one of its {slots} sessions has at "
         "least 3 release groups after the first and each group's per-reply time stays within "
         "5\u202f% of their median. Otherwise it has no steady multiple and reports whole-session "
         "GPU-seconds per reply divided by b, labelled \u201cwhole sessions of N replies\u201d."),
        ("parts", "When a system runs reply generation in its own phase, the figure splits into "
         "two parts, each divided by b: generation, and the remainder (proving for m, or commit "
         "and proving for whole sessions). Because not every system times them separately, the "
         "split appears only under Cost on the system page and never affects ranking."),
    ),
    # CO-8 (amended 2026-11-16): the two rates under the multiple; {reply_tokens} the level's
    "rate": (
        ("", "The request's {reply_tokens} reply tokens divided by the GPU-seconds required for "
         "one reply on a single GPU, reported in tokens/s per GPU with the GPU model named. The "
         "proved rate covers whole sessions (matching Cost vs serving), and the served rate "
         "covers unproved serving at full load on the same GPU type. Dividing the served rate by "
         "the proved rate equals Cost vs serving."),
        ("", "Because both rates depend on GPU hardware, neither is used for ranking (OR-3 ranks "
         "by the steady multiple m)."),
        ("", "Prefill (prompt processing) and decode (reply generation) are not timed separately "
         "in the stored records."),
    ),
    "cost": (
        ("steady", "Steady GPU time m converted to USD at the release's hourly H200 price."),
        ("session", "Mean GPU-seconds per reply across {slots} sessions (from the start of "
         "commit to the final proof, including generation), converted to USD at the same hourly "
         "price."),
    ),
    "check-time": (
        ("", "Total wall time of all verify calls in a session divided by the session's replies, "
         "averaged across {slots} sessions. Re-verification runs never replace the session's own "
         "verify timing."),
    ),
    "proof-size": (
        ("", "Total stored bytes of all proof files in a session divided by the session's "
         "replies (a proof covering multiple replies is counted once), averaged across {slots} "
         "sessions in MB (1\u00a0MB = 1,000,000 bytes)."),
    ),
    "fidelity-figure": (
        ("", "The percentage of reply positions where the system's top token matches the "
         "original model's reply token when fed the prompt followed by that reply token by "
         "token. Averaged across prompts (counting declined prompts as 0), with the model's "
         "standard 8-bit and 4-bit copies (Q8_0 and Q4_K_M) shown alongside."),
        ("", "100\u00a0% means picking the original's exact token at every position. This metric "
         "compares top choices rather than full distributions (KL divergence compares "
         "distributions)."),
        ("", "Computed by the system's own scoring code on the reference reply rather than by "
         "the proved computation. It sets no check or petal grade."),
        ("", WHY_TOP_TOKEN.replace("{tokens:,}", "{reply_tokens}")),
        # FI-16 (adopted 2026-11-14): the figure tied to the proofs
        ("", "Whenever a proved reply starts identically to the original's, both models saw the "
         "same prefix, so the proof fixes which token the proved model chose up to and including "
         "the first difference. The system's scoring code must pick that exact token at every "
         "such position (the count appears on the system page); otherwise we display the "
         "Fidelity check state instead of the percentage."),
    ),
    "kl": (
        # FI-7 over the KL texts (PR-3; 64 and 512 are the level file's kl.texts and kl.tokens)
        ("", "Mean KL divergence per scored token (in nats) between the committed weights file "
         "and the original model over 64 texts of 512 tokens, computed by llama.cpp on the "
         "committed file rather than the proved computation. Displayed for context; gates "
         "nothing."),
        ("not measured", "Shown with the reason whenever llama.cpp cannot run the original "
         "model (such as Llama 4 Maverick's 16-bit weights) or cannot load the committed file "
         "and the adapter provides no distributions of its own."),
    ),
}  # fmt: skip
# a figure in one line, for its search entry: what the figure is, about 95 characters at most
FIGURE_LINE = {
    "multiple": "GPU-seconds per proved reply (including generation) divided by unproved "
    "serving at full load.",
    "rate": "Reply tokens per GPU-second (proved and served on the same GPU type). Their ratio "
    "is Cost vs serving.",
    "check-time": "Total verify wall time per session divided by replies, averaged across "
    "{slots} sessions.",
    "proof-size": "Stored proof bytes per session divided by replies (in MB); shared proofs "
    "count once.",
    "fidelity-figure": "Percentage of reply positions where the system's top token matches the "
    "original's reply.",
    "kl": "KL divergence per token between the committed file and original model via llama.cpp "
    "(non-gating).",
}
# a rung's fidelity reference, by its stored precision (FI-1)
# (a no-break hyphen: the precision never splits from its number at a line's end)
REFERENCE_WORD = {"bf16": "16\u2011bit", "f16": "16\u2011bit", "f32": "32\u2011bit"}


def kl_head(dtype):
    """The KL column's head: one name on every page; the precision of each model's reference is
    in the figure's definition."""
    return FIGURE_NAME["kl"]


# the order rule (RFC-0018 OR-1 to OR-6, GL-4), as (label, words). {margin} is the level's.
# "Session m" is one counted session's m.
ORDER_RULE = (
    ("ranked", "Only systems that pass all six checks on a model are ranked."),
    # OR-2; no floor: Non-Goals (printed as stated), Alternatives (a security floor, rejected)
    ("unranked", "A passing system is ranked only if its publisher states at the pinned commit "
     "(or we read its quotes as stating, marked with links) that an accepted proof means the "
     "reply is the committed model's greedy output for the prompt, and the level file records a "
     "numeric security level stated there for at least one verifier it ships. Otherwise the row "
     "is listed as Passed, not ranked with the reason. Level 1 sets no minimum bit floor."),
    ("above", "One system ranks ahead of another when both have a steady multiple, its mean is "
     "at least {margin} lower, and its highest session m falls strictly below the other's "
     "lowest. Any system with a steady multiple ranks ahead of one without; two systems without "
     "one compare the same way using whole-session cost per reply."),
    ("position", "A system's position is 1 plus the number of systems ranked strictly ahead of "
     "it, so tied systems share a position. It counts among the systems run on its own model "
     "only."),
    ("below", "Ranked systems appear first, followed by passed unranked systems, then systems "
     "that have not passed, sorted alphabetically within each group. Systems that have not "
     "passed still show their checks and figures without a position."),
    ("largest model with a passed row", "The largest model by total parameters that has at "
     "least one passing system whose publisher states that an accepted proof represents the "
     "model's own reply."),
    ("glyph", "The glyph never changes a system's ranking."),
    ("models", "Systems are never ranked across models."),
)  # fmt: skip
# the checks page's table of what we test and what we read (RFC-0018 CH-6, GL-1, OR-2, SI-4a):
# what a line is about, where a row shows it (checks, petals, figures and the order rule, by their
# addresses on the checks page; "figures" stands for every figure) and how it is known
KNOW_HEAD = "What we test and what we read"
KNOW_COLS = ("What", "Where", "How we know it")
KNOW_WORD = {"test": "tested directly by our harness", "read": "read from the publisher's documentation",
             "neither": "not tested by any check; the petal reports what the publisher states"}  # fmt: skip
KNOW_LINES = (
    ("completeness: the publisher's honest prover produces accepted proofs", ("run",),
     "test"),
    ("binding: a modified weight, commitment, prompt token, or reply token is rejected",
     ("model", "prompt", "reply"), "test"),
    ("verdicts reached without model files or a GPU", ("no_weight_file",), "test"),
    ("how closely proved replies match the original model", ("fidelity", "faithful_model"),
     "test"),
    ("all timing, cost, size, and fidelity figures", ("figures",), "test"),
    ("soundness as a stated mathematical bound", ("unforgeable",), "read"),
    ("zero knowledge of the weights", ("weights_hidden",), "read"),
    ("machine-checked formal proofs", ("machine_checked",), "read"),
    ("setup and trust assumptions", ("no_trusted_party",), "read"),
    ("stated numeric security level", ("unranked",), "read"),
    ("whether an accepted proof means the committed model's greedy reply", ("unranked",), "read"),
    ("soundness against an arbitrary cheating prover", ("unforgeable",), "neither"),
    ("zero knowledge of the compiled programs we run", ("weights_hidden",), "neither"),
)  # fmt: skip
KNOW_WHERE = {"figures": "Figures", "unranked": "Order"}  # the two that are no check or petal
# the checks page in one sentence: its description and its search entry
CHECKS_DESC = (
    "The rules behind every row on the ladder: the six entry checks, cost and fidelity figures, "
    "ranking order, and the five glyph petals."
)
# the words of a rule that link to where Learn gives the rule's reason (/method), by the rule's
# constant and its line's label: (phrase, address). The phrase is linked where the line holds it,
# or the label itself where it is the phrase
REASON_LINK = {
    ("NOT_TESTED", ""): ("not tested", "/method#the-checks"),
    ("summary", ""): ("a passed check raises none", "/method#order-and-the-glyph"),
    ("FIGURE_RULE", "parts"): ("generation", "/method#the-figure"),
    ("CHECK_MORE", "bar"): ("bar", "/method#the-checks"),
    ("ORDER_RULE", "models"): ("across models", "/method"),
}
# ------------------------------------------------------------------ the overview page (RFC-0018 SI-7)
SCALE_LOG = "log scale"  # beside an axis's unit
SCALE_LINEAR = "linear scale"  # beside a linear axis's unit (Fidelity's on the overview)
SCALE_SERVING = "Serving"  # a lane's foot: serving's line and its stored figure
# a model no system has run on (the ladder, the overview page); its serving line keeps "not run yet"
SCALE_NOT_RUN = "no system run yet"
# the start of the overview page's description and search line, before its figures' names
OVERVIEW_LEAD = "Every system run, on one plot"
# over the rows a plot of the overview page could not place: one of their two figures is missing
OVERVIEW_OFF = "Not on the plot, a figure missing"
# the overview plot's axes: the name of the one figure FIGURE_HEAD does not hold, the pickers'
# names, and which way each figure is better, in words (the plot sets that end up and right)
OVERVIEW_MODEL = "Model size"
OVERVIEW_UP, OVERVIEW_ACROSS = "Up", "Across"
OVERVIEW_BETTER = {"multiple": "cheaper to prove", "proving": "cheaper to prove",
                   "check-time": "faster to verify",
                   "proof-size": "smaller proof", "fidelity": "closer to the model",
                   "model": "larger model"}  # fmt: skip
# beside a row the plot leaves out on the axes picked (a figure missing there)
OVERVIEW_OFF_SHORT = "not on the plot"
# the counts under the page's title
OVERVIEW_COUNTS = (("run", "systems run"), ("passed", "passed"), ("models", "models"),
                   ("not_run", "systems not run"))  # fmt: skip
# ------------------------------------------------------------------ the autoresearch page
# announced, not open yet: the tab's word, the page's title, and what the page says
AUTORESEARCH_TITLE = "Autoresearch"
AUTORESEARCH_SOON = "Coming soon"
# the parts the track is for, set huge behind the title as a texture (read by no one: aria-hidden)
AUTORESEARCH_PARTS = ("Lookup", "Range check", "Softmax", "SiLU", "RMSNorm", "GPU kernel")
# ------------------------------------------------------------------ the mandate page
# The headline, then who runs it, its ties, what we do, what we do not do, how to check us and how
# a row is changed, with the dated corrections: each line
# (a plain label, the rule that binds it, the file that holds the rule with its section's anchor,
# the words; two rules of one file in two sections: a pair of each; a source outside the
# repository: its link's words and its address). A line with no file is the owner's commitment. {lead} and {builder} are the names
# facts.json `credit` gives, linked as the footer links them. The members (`credit`) are listed in
# the section MANDATE_MEMBERS_IN names, once any has agreed.
RFC_18 = "rfcs/0018-level-1-ladder.md"
MANDATE_BELIEF = (
    "We believe any claim about which AI model produced a reply should come with evidence "
    "anyone can afford to check."
)
# the page's description, share text and search line
MANDATE_DESC = "Who runs Inference proofs, what rules we follow, and how to verify our results."
MANDATE = (
    ("Who runs it", (
        ("Run by", "", None, "{lead}."),
        ("Built by", "", None, "The {builder}, convened by {lead}."),
    )),
    ("Ties", (
        ("Its business", "lucidcomputing.ai", "https://lucidcomputing.ai/", "{lead} operates "
         "this project and builds this site. Its commercial product runs inference inside "
         "hardware enclaves: \u201cAll inference runs inside hardware-encrypted Trusted Execution "
         "Environments.\u201d It does not build any of the proof systems on the ladder, though "
         "two systems listed under another kind of check (Private ML SDK and Tinfoil) also use "
         "hardware enclaves."),
        ("Rules", "Conflicts of Interest", f"{RFC_18}#conflicts-of-interest", "We drafted Level "
         "1's rules with help from an AI model built by FlashProve's publisher. RFC-0018 "
         "documents every rule this touches and every interpretation that favours FlashProve."),
        ("SASH's change", "pull request #36",
         "https://github.com/sg-ai-safety-hub/zk-inference-prover/pull/36", "SASH runs commit "
         "4f41667 from pull request #36, which was authored by this project's owner and remains "
         "unmerged upstream (a SASH maintainer has since pushed additional commits to the PR). "
         "At upstream's own commit eb95bfa, SASH refused one of Level 1's prompts."),
        # {se3a} and {se3b}: the board's replaced and ineligible sessions, in words (pages.py)
        ("After the freeze", ("CH-1a", "SE-3a", "SE-3b", "SI-4a"),
         (f"{RFC_18}#the-six-checks", f"{RFC_18}#sessions-and-what-is-recorded",
          f"{RFC_18}#sessions-and-what-is-recorded", f"{RFC_18}#site"), "Four rules added to "
         "RFC-0018 after the level freeze affected published rows. Under CH-1a, FlashProve "
         "passed the Model check when its prover answered \u201cfailed\u201d. Under SE-3a, "
         "{se3a}. Under SE-3b, {se3b}. Under SI-4a, ranking a passing row requires a recorded "
         "publisher statement (or our reading of one) that an accepted proof represents the "
         "committed model's greedy reply. Going forward, rule changes of this kind belong in a "
         "new level (LV-1)."),
    )),
    ("What we do", (
        ("Pinned commit", "rule 1", "AGENTS.md#hard-rules", "We build each system at a full "
         "public commit hash and pass only settings documented by the system. FlashProve runs "
         "its upstream commit untouched; SASH runs a commit from an unmerged pull request "
         "authored by this project's owner (see Ties)."),
        ("Same request", "Prompts, PR-2", f"{RFC_18}#prompts", "Every system receives the exact "
         "same request. Prompts are sampled using drand's first public randomness round after "
         "the freeze commit's timestamp (set by our own clock; GitHub recorded each freeze 2 s "
         "later). We froze Level 1 three times on 2026-11-11, drawing fresh prompts each time; "
         "every counted run uses the third draw."),
        ("Sample size", "rule 5", "AGENTS.md#hard-rules", "Every cost figure is published with "
         "its sample size and all counted session values, never a single cherry-picked run."),
        ("Computed", ("CO-6", "CH-6"), (f"{RFC_18}#cost", f"{RFC_18}#the-six-checks"),
         "All check states and metrics are computed automatically from stored run records; no "
         "human types a figure or flips a check state."),
        ("Reproduced first", "CH-8", f"{RFC_18}#the-six-checks", "If a verifier accepts a "
         "tampered model, prompt, or reply inside our adapter, we mark the check not decided "
         "(not reproduced) and notify the publisher. The check turns failed only after we "
         "reproduce the same acceptance using the system's own command outside our adapter."),
    )),
    ("What we do not do", (
        ("Payment", "", None, "We accept no payment for listings, rankings, or benchmark runs."),
        ("Provers", "What this project is", "AGENTS.md#what-this-project-is", "We benchmark "
         "provers; we do not build or certify them."),
        ("Not tested", "Non-Goals", f"{RFC_18}#non-goals", "None of our checks attempt to forge "
         "proofs or extract weights. Each system page quotes the publisher directly on soundness "
         "and weight hiding."),
        ("Ranking", "OR-1", f"{RFC_18}#order", "We rank only systems that pass all six checks, "
         "and never across different models."),
    )),
    ("How to check us", (
        ("Labels", "rule 2", "AGENTS.md#hard-rules", "Every number links to its underlying "
         "record and carries its unit and timing scope. Nobody outside our team has rerun these "
         "benchmarks yet."),
        ("Repository", "Licence", "README.md#licence", "All rules, adapters, measurement code, "
         "and run records live in one public repository. Bulk artifacts (proofs and model "
         "weights) stay outside git and are pinned by SHA-256 digest; proof bytes are not yet "
         "public."),
        ("Rebuild", "Tier 1", "docs/REPRODUCE.md", "Anyone can rebuild the board from stored "
         "records, recompute every derived figure, and run all repository checks on a laptop "
         "with no GPU. Re-verifying proofs requires the proof files themselves."),
    )),
    ("Changes and corrections", (
        ("Contest a row", "issues", "https://github.com/ai-verification-observatory/"
         "inference-proofs/issues", "Open an issue naming the row, the fact you dispute, and "
         "your supporting source. We respond publicly in the issue and log every resulting change "
         "below."),
        ("A petal", "GL-1", f"{RFC_18}#the-glyph", "Statement petals change only when backed by "
         "a linked quote from the pinned commit or a failed entry check. Grades relying on our "
         "reading are flagged and capped at Mostly met. Fidelity changes only on a fidelity run."),
        ("A check", "CH-6", f"{RFC_18}#the-six-checks", "Check states change only from stored "
         "run records. A tampered input accepted inside our adapter fails a check only once "
         "reproduced with the system's own command."),
    )),
)  # fmt: skip
# the corrections the mandate lists in the section MANDATE_CORRECTIONS_IN names, newest first:
# (date, words). A correction is added here when it is made; none is removed.
# the board's replaced (SE-3a) and ineligible (SE-3b) sessions in the mandate's words, one
# clause per row that has any; with none, the empty case
SE3A_ROW = "{n} {name} {slot} moved to a later session"
SE3A_NONE = "no slot moved to a later session"
SE3B_ROW = "{n} {name} {session} ran on a host that failed its self-test and no longer counts"
SE3B_NONE = "no session was dropped"
MANDATE_CORRECTIONS_IN = "Changes and corrections"
MANDATE_CORRECTIONS = (
    ("2026-11-16", "SASH's slot 2 now uses a fresh session run on a host that passed its "
     "self-test and re-verified on a CPU-only host, bringing SASH back to Passed."),
    ("2026-11-16", "Petals were renamed to Integrity, Confidentiality, Fidelity, Formally "
     "verified, and Trust assumptions, with plain grade labels. No grades, positions, or "
     "figures changed."),
    ("2026-11-15", "SASH's Trust assumptions petal was evaluated under the same reading test as "
     "FlashProve's, moving from Not stated to Mostly met (our reading). Both rely on our "
     "reading of the publisher's linked quotes."),
    ("2026-11-15", "Corrected the mandate's count of replaced SASH slots from two to one: the "
     "replacement for slot 2 ran on a host that failed its self-test and was dropped."),
    ("2026-11-15", "Dropped a SASH session whose host failed its self-test (RFC-0014), moving "
     "SASH temporarily to Not passed yet pending a replacement run."),
    ("2026-11-15", "Any statement grade relying on our reading rather than an explicit "
     "publisher sentence is now flagged and capped at Mostly met across all systems. "
     "FlashProve's Trust assumptions petal moved from Met to Mostly met."),
    ("2026-11-15", "Disclosed SASH's pinned commit as an owner-authored pull request after "
     "earlier wording implied our adapters never modified upstream code."),
    ("2026-11-15", "Clarified the randomness-beacon wording: we controlled the freeze "
     "timestamp and ran three freezes on 2026-11-11, each drawing new prompts."),
    ("2026-11-15", "Unified non-run reasons under one ordered rule: DeepProve, JOLT Atlas, "
     "and zkLLM are listed under no public verifier, and zkGPT under a different statement."),
)  # fmt: skip
MANDATE_MEMBERS_IN = "Who runs it"
# the mandate's line on the level (its label is the level and its state, linked to the level
# file): the one home of the level's history (three freezes on 2026-11-11, each followed by its
# beacon round, in the git history of levels/L1.yaml and levels/L1-beacon.json; the file unchanged
# since; LV-1; RFC-0018's changes since, and the rules added since that decided rows, which
# MANDATE_LEVEL_LINK leads to: CH-1a, SE-3a)
MANDATE_LEVEL_IN = "How to check us"
MANDATE_LEVEL = (
    "One file fixes all models, request dimensions, prompt corpus, beacon seed, and cost, "
    "fidelity, and ranking constants. We froze it three times on 2026-11-11 before any counted "
    "runs, drawing a fresh beacon round each time, and have not touched it since. Rule changes "
    "are meant to start a new level, though several RFC-0018 amendments added after the freeze "
    "decided rows."
)
# the words of the level line that link to where Learn names those rules: (phrase, address)
MANDATE_LEVEL_LINK = ("decided rows", "/method#judgement-and-changes")
# the line under it: the models the level fixes, largest first, each with its publisher and
# architecture (the ladder prints neither since 2026-11-23, Q54; a system's band names both for
# its model, and a model no system has run on has no page of its own)
MANDATE_MODELS = "Models"
# why a check is undecided (its cause as the board stores it): a system page's title for the cause,
# lower case and with no full stop; the checks page prints each as a sentence (#cause-<cause>)
CHECK_CAUSE_WORD = {
    # CH-5: "with the publisher's sentence. The row cannot pass."
    "system limit": "the system cannot run what this check requires (publisher's quote linked), "
    "so the row cannot pass",
    "not run": "not run yet",
    "not resolved": "the test ran, but its result does not yet count",
    "not reproduced": "a verifier accepted a tampered input in our adapter, and we have not yet "
    "reproduced it with the system's own command",
}
# what decides a check that is not decided, and who acts, by (check, cause); None for any check.
# {session}: the session the check's note names, by date and ordinal. Printed under its cause
CHECK_DECIDE = {
    ("no_weight_file", "not resolved"): ("re-verifying the proofs from session {session} inside "
                                         "the run's image on a CPU-only host", "us"),
    (None, "not reproduced"): ("running the same tampered input through the system's own command "
                               "outside our adapter", "us"),
}  # fmt: skip
# the figures' rules on a board built by the further-reply rule (RFC-0018 CO-9, Q55: every release
# after v1.0): Cost vs serving is a further reply's, Proving vs serving its proving part, and the
# one-time work stands apart; the other figures' rules are FIGURE_RULE's. 1 % (the adapter
# phases' tolerance), 5 % and 19 (the one-time work's mark) are CO-9's
# the two routes of use the pair of multiples reads for, said once at depth 3 (Cost) and in the
# rule (CO-9)
ROUTES = ("Letting the system write the reply costs about the total; serving with another "
          "engine and proving afterwards costs about the proving part, a route no run of this "
          "release measures.")  # fmt: skip
FIGURE_RULE_FURTHER = {
    "multiple": (
        ("multiple", "A further proved reply's GPU time c divided by serving baseline b on the same "
         "model. GPU time counts only the H200 GPUs allocated to the job, for as long as they are "
         "held, never weighted by how busy they were."),
        ("c", "GPU-seconds from the start of the prove call to the last reply's proof, summed "
         "over {slots} sessions and divided by their replies: everything a reply needs once the "
         "one-time work exists, generation included. Each session's own value gives the range."),
        FIGURE_RULE["multiple"][2],
        ("parts", "c splits into generation (the reply's tokens) and proving (the rest). "
         "Generation comes from the system's own generation phase, or, for a system that "
         "generates inside its prove call, from the phase its adapter reports as generation, "
         "used only when the phases the adapter reports add up to the timed prove call within "
         "1\u00a0%. Otherwise the row prints no proving figure and says why under Cost."),
        ("routes", ROUTES),
        ("order", "Rows with a steady state still rank by their steady GPU time per reply m; "
         "rows without one compare by c."),
    ),
    "proving": (
        ("", "The proving part of c (c less its generation) divided by b: what a reply costs "
         "once its tokens exist. It depends on how many replies one proof covers, which each "
         "row states."),
    ),
    "one-time": (
        ("", "Work that depends only on the system's version, the model and the request shape, "
         "never on a request, and that every later reply reuses: the commit call and the "
         "handover up to the prove call, plus a setup run a session reuses. Printed once, in "
         "GPU-hours, never divided by the replies."),
        ("mark", "The fewest replies after which the one-time work is at most 5\u00a0% of the "
         "total: 19 times the one-time work divided by c, rounded up."),
    ),
    "rate": (
        ("", "The request's {reply_tokens} reply tokens divided by the GPU-seconds of one further "
         "reply on a single GPU, reported in tokens/s per GPU with the GPU model named. The "
         "served rate covers unproved serving at full load on the same GPU type. Dividing the "
         "served rate by the proved rate equals Cost vs serving."),
        *FIGURE_RULE["rate"][1:],
    ),
    "cost": (
        ("further", "c converted to USD at the release's hourly H200 price; the one-time work "
         "likewise, once."),
    ),
    **{k: v for k, v in FIGURE_RULE.items() if k not in ("multiple", "rate", "cost")},
}  # fmt: skip


def figure_rules(rule):
    """The figures' rules the checks page prints, by the board's cost rule (Q55)."""
    return FIGURE_RULE_FURTHER if rule == "further-reply" else FIGURE_RULE


# the line that opens the not-decided causes (a check not decided is never worded as a failure;
# the standing words are chrome.not_passed's)
CHECK_CAUSE_LEAD = (
    "An undecided check is not a failure. When a row has no failed checks but at least one "
    "undecided check, its standing shows Not passed yet. System pages may also display verifier "
    "trials run outside the counted suite next to the relevant check, without affecting any "
    "check state."
)

# ------------------------------------------------------------------ labels of a stored figure
SCOPE_SHORT = {None: "", "prove.steady": "steady", "prove.session": "further reply",
               "whole_wall": "session", "verify": "verify", "commit": "commit",
               "setup": "setup", "verify.single_thread": "verify, one thread",
               "serving": "full load"}  # fmt: skip
WHOLE_WALL_SPAN = "from commit to the last proof"  # what a whole session's time runs over
SCOPE_WORD = {
    None: "not a timed number",
    "setup": "setting up",
    "commit": "committing to the model",
    "prove.steady": "steady state, after the first release group",
    # CO-9 (Q55) is the one rule the site prints this scope for: RFC-0004's prove call start to
    # the last proof, the one-time work before it left out
    "prove.session": "a further reply, from the start of the prove call to the last proof, the "
    "one-time work before it left out",
    "whole_wall": f"the whole session, {WHOLE_WALL_SPAN}",
    "verify": "verifying",
    "verify.single_thread": "verifying on one CPU thread",
    "primitive": "one primitive",
    "serving": "serving at full load",  # the serving baseline's, in its title (CO-4)
}
GRADE_WORD = {
    "measured": "recorded by our harness",
    "derived": "computed by our code from recorded numbers",
    "projected": "projected, not measured",
    "external": "as the system publishes it",
    "asserted": "set in the reference file",
}
TIER_WORD = {
    "reported": "our runs only, not rerun by anyone else",
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
# before a part's name where it stands beside its whole in a table's head (the sessions table);
# under its whole, a part's name stands alone
OF_WHICH = "of which"
# the Cost block's head over the multiple's two parts (CO-7, amended 2026-11-17: printed only there)
PARTS_HEAD = "Cost vs serving, in two parts"
# the GPU time per reply after the first release group, m (CO-3): its name beside the serving and
# session GPU times (Cost), its full name (that line's title, the sessions column's), its column
# (beside Session; a session with none prints why under its "none")
M_HEAD = "Steady GPU time per reply"
M_NAME, M_COL = "GPU time per reply after the first release group (m)", "Steady"
# CO-5's label for a figure of the whole sessions, N the level's replies per session
WHOLE_SESSIONS = "whole sessions of {n:,} replies"
# CO-9 (adopted 2026-11-26, Q55): what a figure of a further reply counted, its glossary entry
FURTHER = "further reply"
FURTHER_TERM = "Further reply"
# the replies one proof batch holds, under the proving multiple (CO-9: the proving part depends
# on it)
BATCH = {1: "1 reply per proof"}
BATCH_MANY = "{n:,} replies per proof"
# a proving multiple the board holds none for (no split, CO-9): its words at every depth; the
# board's cause stands one step down, under Cost
NOT_SPLIT = "not measured"
# the Cost block of a further-reply board: the further reply's two parts, the one-time work and
# its mark, the two routes the pair reads for (said once, at depth 3), the diagnostics
FURTHER_PARTS_HEAD = "Further reply, in two parts"
ONE_TIME_MARK = "at most 5\u00a0% of the total from"
ADAPTER_SPLIT = "generation as the adapter reports it, its phases within {tol} of the prove call"
NO_SPLIT = "not split"
UTIL_HEAD = "Prove GPU utilisation"
MEMORY_HEAD = "Prove peak GPU memory"
STEADY_STATE = "steady state"  # under a steady multiple, before its sessions (CO-3)


def session_count(k):
    """A count of sessions in words: "3 sessions", "1 session"."""
    return f"{k:,} session" if k == 1 else f"{k:,} sessions"


# the fidelity table (FI-5, FI-6): the replies' figure, a control's name as the table prints it
# (its id, with the llama.cpp pin that makes a quantized copy, in the title), the p line. FI-2's
# words: a quantized copy by its bits, which llama.cpp's type names (Q8_0 is 8-bit, Q4_K_M mostly
# 4-bit), the id kept in parentheses at this depth; a quarter of the blocks, both models; the
# smaller model is named in the level file
PREFIX = "Fidelity check: matched leading tokens, mean"
CONTROL_NAME = {"reference-2": "the original, run again",
                "q8_0": "8-bit copy (Q8_0)", "q4_k_m": "4-bit copy (Q4_K_M)",
                "q3_k_s": "3-bit copy (Q3_K_S)", "q2_k": "2-bit copy (Q2_K)",
                "drop-every-4th-block": "a quarter of blocks cut",
                "smaller-model": "a smaller model"}  # fmt: skip
# the table's first two heads: whose replies a row holds, and whether it is the system, an honest
# copy or a damaged one (FI-2)
FID_WHO = "Replies"
FID_KIND = "Kind"
KIND_TERM = "Honest and damaged copies"  # the glossary entry a control's kind links to
# a check's record as its link reads, by the file's name (the path stands in the link's title)
RECORD_WORD = {"run.json": "run record", "controls.json": "controls", "verify-trace": "verify traces",
               "reverify.json": "re-verify record", "fidelity.json": "fidelity record"}  # fmt: skip
P_ABOVE = "above the bar: {p}"  # {p} reads "p = 0.0058" or the floor's bound (`p_said`)
P_FLOOR = ", the test's floor"  # after a p at the lowest value its test can give (FI-4)
# the reference's precision in words, where a line names the original (FI-1)
DTYPE_BITS = {"bf16": "16-bit", "f16": "16-bit", "f32": "32-bit"}
# a column's head as the table prints it, on every width: the measure's name alone (its full
# name, with what it is a mean of and on which reply, is the head's title and the glossary's)
FID_HEAD = {"Fidelity figure: top-token agreement, mean": "Top-token agreement",
            "Fidelity check: matched leading tokens, mean": "Matched leading tokens",
            "KL to the original, on its reply": "KL divergence",
            "KL to the original weights": "KL on fixed texts"}  # fmt: skip
TF_INTERVAL = "95\u00a0% interval {low} to {high}\u202f%"  # SI-9, under and in a percentage's title
# the limits under the table (depth 3), each generated from the board, the level and its records
LIM_ORIGINAL = "Original: {repo} at {rev} ({bits})."
LIM_COPY = " This is a Hugging Face Hub mirror rather than {publisher}'s own repository."
LIM_CEILING = (" When fed its own reply, the original engine repeats its own token at "
               "{ceiling}\u202f% of positions, setting the reference ceiling.")  # fmt: skip
LIM_ENGINES = "Engines: {parts}."
LIM_PART = {None: "the original model and co-run controls", "controls": "the quantized controls"}
LIM_VLLM = "{part} ran in vLLM with all prompts in one batch"
LIM_LLAMA = "{part} ran in llama.cpp ({slots} at a time)"
LIM_PROMPTS = ("Prompts: {tokens}-token excerpts from {texts} texts hosted on {hosts} "
               "({licences}), with no chat template.")  # fmt: skip
TF_AGREE = "Fidelity figure: top-token agreement, mean"
TF_KL = "KL to the original, on its reply"
# the summary of FI-11's tests: they are on top-token agreement and set nothing (the matched
# leading tokens set the check and the petal)
TF_TESTS_ON = "on top-token agreement (diagnostic only; sets no state)"
# the two teacher-forced columns by name: the lead and FI-13's label say which columns they are about
TF_BOTH = "top-token agreement and KL divergence"  # the table's heads for the two (FID_HEAD)
# the KL head's title (FI-12: the tokens both lists hold, every other token one outcome)
TF_KL_TITLE = (
    "At each position, KL compares every token shared by both top-{k:,} probability lists, "
    "pooling all remaining tokens into one tail bucket."
)
TF_SUB = "median {median}"
TF_FAILED = "{k:,} of {n:,} prompts failed (counted as 0)"
TF_TEST = "{name} above it: {above} · below it: {below}"  # each p as `p_said` reads it
# FI-16 (adopted 2026-11-14): the row's pass against its proofs, a cell of the Fidelity block
PROOFS_HEAD = "Against the proofs"
TF_PROVED = "{agreeing:,} of {positions:,} positions"
TF_PROVED_SPLIT = "{agreeing:,} of {positions:,} where the two replies diverge"
TF_PROVED_MEAN = "wherever a proof fixes the model's token, {name}'s scoring code matched it"
TF_NOT_PROVED = "this row does not have a proved reply for every prompt"
TF_KL_SUB = "n\u00a0=\u00a0{n:,}"  # under a KL figure whose n is not the block's


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
def number(v, unit):  # noqa: PLR0911, PLR0912 (one return per stored unit)
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
    if unit == "gpu_s/token":  # CO-7 (amended 2026-11-15): generation per reply token
        return sig(v), "GPU-s/reply token"
    if unit == "request/gpu_s":  # CO-4: a rung of the serving ladder
        return sig(v), "replies/GPU-s"
    if unit == "gpu_s":  # CO-9: the one-time work, once, in hours a reader counts in
        return sig(v / 3600), "GPU-h"
    if unit == "USD":  # CO-9: the one-time work's price
        return sig(v), "USD"
    if unit == "count":  # CO-9: the one count the site prints, the one-time work's 5 % mark
        return f"{v:,.0f}", "replies"
    if unit == "%":  # CO-9: the prove step's GPU utilisation, a diagnostic
        return f"{v:.1f}", "%"
    if unit == "MiB":  # CO-9: the prove step's peak GPU memory, in GB as a GPU's size is said
        return sig(v * 1048576 / 1e9), "GB"
    if unit == "token/gpu_s":  # CO-8: 4 digits, every whole digit, so served over proved as
        # printed gives the printed multiple (amended 2026-11-16)
        return (f"{v:,.0f}" if abs(v) >= 1000 else sig(v, 4)), "tokens/s per GPU"
    raise KeyError(f"no words for the unit {unit!r}")


def release_tail(rel):
    """A release in words, "v1.0, runs to 2026-11-13": the board's date is its newest run date,
    not a date the release was made on, so it says what it is."""
    return rel["id"] + (f", runs to {rel['date']}" if rel["date"] else "")


def shown(v, unit):
    n, u = number(v, unit)
    return f"{n}{u}" if unit == "ratio" else f"{n}\u00a0{u}"


def params(n):
    """A parameter count in billions, or millions below one billion ("400B", "8.03B", "124M")."""
    text = sig(n / 1e9, 3) if n >= 1e9 else sig(n / 1e6, 3)
    text = text.rstrip("0").rstrip(".") if "." in text else text  # "17.0" reads "17"
    return f"{text}B" if n >= 1e9 else f"{text}M"


def architecture(total, active, sized=True):
    """ "Mixture of experts, 400B total, 17B active" or "Dense, 8.03B": a mixture of experts reads
    fewer parameters per token than it holds (the glossary's term, spelled out). Beside a size that
    says the total (a model's tab: `sized` False), the rest only: "Mixture of experts, 17B active"
    or "Dense"."""
    if active and active < total:
        return (f"Mixture of experts, {params(total)} total, {params(active)} active" if sized
                else f"Mixture of experts, {params(active)} active")  # fmt: skip
    return f"Dense, {params(total)}" if sized else "Dense"


def labels(f, n=None, note=None):
    """A figure's labels in words, for its title: scope, grade, evidence, sample size, record.
    `n` stands where the figure stores no sample size (the row's counted sessions); `note` opens
    the title (CO-5's "whole sessions of N replies")."""
    # CO-5's note says the session once, inside the scope: "scope: whole sessions of N replies,
    # from commit to the last proof"
    if note and f["scope"] == "whole_wall":
        parts = [f"scope: {note}, {WHOLE_WALL_SPAN}"]
    else:
        parts = [note] if note else []
        parts.append(f"scope: {SCOPE_WORD[f['scope']]}")
    parts += [f"grade: {GRADE_WORD[f['grade']]}", f"evidence: {TIER_WORD[f['tier']]}"]
    count = f["n"] if f["n"] is not None else n
    if count is not None:
        parts.append(f"n = {count}")
    if spread := range_words(f):  # AGENTS.md rule 5: a mean carries its range
        parts.append(f"range: {spread}")
    parts.append(f"record: {f['source']}")
    return "; ".join(parts)


def range_words(f):
    """A mean's range over its sessions, in the figure's unit ("17.66 to 18.07 s/reply"), where
    the board stores one over more than one value; None otherwise."""
    st = f.get("stats") or {}
    if (st.get("n") or 0) < 2 or st.get("min") is None or st.get("max") is None:
        return None
    lo, unit = number(st["min"], f["unit"])
    hi, _ = number(st["max"], f["unit"])
    return f"{lo} to {hi}\u00a0{unit}"


def sub_words(f, n=None):
    """The one line under a figure: its scope in a word and its sample size. The dot keeps to the
    scope word (no break before it), so a wrapped line never starts with it."""
    count = f["n"] if f["n"] is not None else n
    parts = [SCOPE_SHORT[f["scope"]], f"n\u00a0=\u00a0{count}" if count is not None else ""]
    return SEP.join(p for p in parts if p)


# the dot between a scope and its sample size
SEP = "\u00a0· "


# ------------------------------------------------------------------ systems not run (SI-4b)
# the checks page's last section: the one rule that gives a system not run its reason, each
# reason with its words, then the systems it holds, each with the fact that sets it and its link
NOT_RUN_LEAD = (
    "Systems without a row on the ladder are listed below with a single reason: the first "
    "criterion below that applies in their documentation, checked in order. Each entry cites "
    "and links the specific fact behind its classification."
)
NOT_RUN_RULE = {
    "another kind of check": "Does not produce a cryptographic proof of inference; instead uses "
    "hardware attestation, re-execution, a dispute game, or an activation fingerprint.",
    "a different statement": "Proves a different claim from Level 1's requirement that the reply "
    "is the committed model's greedy output for a prompt given to the verifier.",
    "no public verifier": "No public repository to pin, or no standalone public program that "
    "verifies a stored proof against an externally supplied commitment (including provers and "
    "verifiers that only run together, or verifiers that read the commitment from inside the "
    "proof file).",
    "licence": "No licence file at the repository root, or a licence granting no use rights. "
    "Licences permitting internal testing and evaluation cover our own runs, though they do not "
    "permit redistributing the software.",
    "no configuration at the request": "No documented configuration proves a reply to Level 1's "
    "request on any Level 1 model.",
    "not yet run": "None of the exclusions above apply, and we have not run a session yet.",
}
