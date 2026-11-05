// MOCK release index for the first dashboard. Every repetition value below is invented for layout
// and carries `mock: true`; no benchmark run has produced it. Derived values and statistics are
// computed here from the raw repetitions (AGENTS.md rule 3), never typed.
// shortcut: hand-written raw values, replace with releases/<release>/index.json once a release exists.
import { stats, type Stats } from "./format.ts";
import { reference } from "./repo.ts";

export type Grade = "measured" | "derived" | "projected" | "external" | "asserted";
export type Tier = "reported" | "peer-reviewed" | "reproduced";
export type Quantity = {
  value: number | null;
  unit: string;
  scope: string | null;
  grade: Grade;
  tier: Tier;
  source: { kind: string; ref: string };
  null_reason: string | null;
  stats?: Stats;
  mock?: boolean;
  /** path and JSON Pointer of the value in the published release index */
  pointer?: string;
};

export const RELEASE = {
  id: "v0.1",
  status: "draft, mock",
  freeze_date: "2026-12-15",
  review_window_days: 14,
  reference_file: "reference/v0.1.yaml",
  scope: "SASH and FlashProve on their native workloads, with plain-serving and recompute reference rows, claim cards and negative controls (PRD §Roadmap, v0.1).",
};

// ------------------------------------------------------------------ systems and claim cards

export type ClaimCard = {
  configuration: string;
  card_version: number;
  note: string;
  claim_class: string;
  relation: string;
  security: { notion: string; verifier: string; level: string; assumption: string; adversary: string; setup: string };
  zero_knowledge: { claimed: string; hidden: string; not_hidden: string; status: string };
  assumptions: string[];
  coverage: { phase: string; unit: string; tokens_covered: string; operations: string; policy: string };
  binding: string;
  residual: string[];
  availability: string;
  forbidden_flags: string[];
  /** null when the card file is not in this checkout */
  reviewed_by: string[] | null;
};

export type System = {
  name: string;
  title: string;
  kind: "prover" | "reference" | "test";
  upstream: { repo: string; commit: string } | null;
  summary: string;
  cards: ClaimCard[];
  reply: string | null;
};

const NS = "not stated";

export const systems: System[] = [
  {
    name: "flashprove",
    title: "FlashProve",
    kind: "prover",
    upstream: { repo: "anthropics/FlashProve", commit: "9e2bdd8ff5bf9c62f18263d7dac189b0400b260c" },
    summary: "One proof covers one request: a pass over a 1,024-token window, stating the next token (PRD §1).",
    cards: [
      {
        configuration: "exact-match-lean",
        card_version: 1,
        note: "Shape only, not a reviewed card: the values are the RFC-0002 §Example, to be filled from upstream documentation.",
        claim_class: "next-token/exact-match/committed-weights",
        relation:
          "The output token is the top choice of the integer model whose weights were committed under the given commitment ID, on the given 1,024-token window.",
        security: {
          notion: "knowledge_soundness",
          verifier: "Lean verifier; C++ verifier tested against it",
          level: "q/2^124 + 2^-101 after q hash queries, exact-match policy",
          assumption: "random oracle",
          adversary: "classical",
          setup: NS,
        },
        zero_knowledge: { claimed: "true", hidden: "weights", not_hidden: "a declared list of weights", status: "proved_and_tested" },
        assumptions: ["configuration files fixed before the hash function is drawn", "the commitment ID is obtained from a trusted party"],
        coverage: { phase: "prefill", unit: "request", tokens_covered: "the window's 1,024 positions", operations: NS, policy: "exact_match: top token of the integer model" },
        binding: NS,
        residual: ["proves the integer model, which differs from the 16-bit model's top token at some positions"],
        availability: "research",
        forbidden_flags: [],
        reviewed_by: [],
      },
    ],
    reply: null,
  },
  {
    name: "ref-recompute",
    title: "ref-recompute",
    kind: "reference",
    upstream: null,
    summary: "Reference row: recomputes the workload's forward pass without proving and compares the output positions (RFC-0015).",
    cards: [],
    reply: null,
  },
  {
    name: "ref-serve",
    title: "ref-serve",
    kind: "reference",
    upstream: null,
    summary: "Reference row: plain serving with vLLM 0.32.0 at the workload's shape, no proof (RFC-0015).",
    cards: [],
    reply: null,
  },
  {
    name: "sash",
    title: "SASH zk-inference-prover",
    kind: "prover",
    upstream: { repo: "sg-ai-safety-hub/zk-inference-prover", commit: "eb95bfa887299d1637550228d42086c27cbb2b3b" },
    summary: "One proof in the benchmark's sense is a sequence's whole grid of segments, every prompt and continuation position (systems/sash/README.md).",
    cards: [
      {
        configuration: "default",
        card_version: 1,
        note: "Draft for layout: no SASH card is in the repository yet. Coverage and flags copy systems/sash/README.md; every other field says not stated until it is filled from upstream.",
        claim_class: NS,
        relation: NS,
        security: { notion: NS, verifier: NS, level: NS, assumption: NS, adversary: NS, setup: NS },
        zero_knowledge: { claimed: NS, hidden: NS, not_hidden: NS, status: NS },
        assumptions: [NS],
        coverage: { phase: "both", unit: "segment_grid", tokens_covered: "every prompt and continuation position in the grid", operations: NS, policy: NS },
        binding: "per-edge table stated upstream (docs/statement.md at the pin)",
        residual: [NS],
        availability: NS,
        forbidden_flags: ["--unsound-skip-", "--unsound-argmax-lax"],
        reviewed_by: [],
      },
    ],
    reply: null,
  },
];

// ------------------------------------------------------------------ workloads (RFC-0003 §v0.1 native workloads)

export type Workload = {
  id: string;
  version: number;
  system: string;
  division: string;
  model: string;
  precision: string;
  prompt_tokens: number;
  output_tokens: number;
  batch: number;
  batches: number;
  prompts: number;
  phase: string;
  active_parameters_per_token: string;
  notes: string;
  model_digest?: string;
  corpus_digest?: string;
};

export const workloads: Workload[] = [
  { id: "fp-maverick-w1024-b1", version: 1, system: "flashprove", division: "native", model: "Llama 4 Maverick, public 4-bit conversion", precision: "4-bit", prompt_tokens: 1024, output_tokens: 1, batch: 1, batches: 5, prompts: 5, phase: "prefill", active_parameters_per_token: "not pinned yet", notes: "" },
  { id: "fp-maverick-w1024-b24", version: 1, system: "flashprove", division: "native", model: "Llama 4 Maverick, public 4-bit conversion", precision: "4-bit", prompt_tokens: 1024, output_tokens: 1, batch: 24, batches: 5, prompts: 120, phase: "prefill", active_parameters_per_token: "not pinned yet", notes: "the system's published steady-state shape" },
  { id: "sash-l31-8b-c1024", version: 1, system: "sash", division: "native", model: "Llama-3.1-8B", precision: "W8A8", prompt_tokens: 1024, output_tokens: 64, batch: 1, batches: 1, prompts: 1, phase: "both", active_parameters_per_token: "not pinned yet", notes: "close to FlashProve's window length" },
  { id: "sash-l31-8b-c4096", version: 1, system: "sash", division: "native", model: "Llama-3.1-8B", precision: "W8A8", prompt_tokens: 4096, output_tokens: 512, batch: 1, batches: 1, prompts: 1, phase: "both", active_parameters_per_token: "not pinned yet", notes: "the system's published headline shape" },
];

// ------------------------------------------------------------------ configurations

type Raw = Partial<Record<RawId, number[]>>;
type RawId =
  | "setup_seconds" | "commit_seconds" | "prove_session_seconds" | "prove_steady_seconds" | "whole_wall_seconds"
  | "tokens_covered_total" | "tokens_covered_steady" | "requests_count" | "proofs_count" | "proof_bytes_total"
  | "verify_seconds" | "verify_seconds_total" | "verify_single_thread_seconds";

const RAW_META: Record<RawId, { unit: string; scope: string | null }> = {
  setup_seconds: { unit: "s", scope: "setup" },
  commit_seconds: { unit: "s", scope: "commit" },
  prove_session_seconds: { unit: "s", scope: "prove.session" },
  prove_steady_seconds: { unit: "s", scope: "prove.steady" },
  whole_wall_seconds: { unit: "s", scope: "whole_wall" },
  tokens_covered_total: { unit: "token", scope: null },
  tokens_covered_steady: { unit: "token", scope: null },
  requests_count: { unit: "count", scope: null },
  proofs_count: { unit: "count", scope: null },
  proof_bytes_total: { unit: "B", scope: null },
  verify_seconds: { unit: "s", scope: "verify" },
  verify_seconds_total: { unit: "s", scope: "verify" },
  verify_single_thread_seconds: { unit: "s", scope: "verify.single_thread" },
};

export type Run = { run_id: string; status: "completed" | "failed" | "superseded" | "ineligible" | "included"; reason?: string; exit_code?: number; last_lines?: string[] };

export type Configuration = {
  system: string;
  configuration: string | null;
  workload: string;
  profile: string;
  effective_tier: Tier;
  runs: Run[];
  insufficient_repetitions?: boolean;
  raw: Raw;
  null_reasons: Partial<Record<string, string>>;
  statistics: Record<string, Quantity>;
  /** per-repetition values behind each statistic, for the repetition strips */
  reps: Record<string, number[]>;
};

/** D-RATE-S: T(S) / sec(S), null when sec(S) is null or 0 (RFC-0004). */
export const rate = (tokens: number, seconds: number) => tokens / seconds;

const per = (a: number[] | undefined, b: number[] | undefined, f: (x: number, y: number) => number) =>
  a && b ? a.map((x, i) => f(x, b[i])) : undefined;

function build(c: Omit<Configuration, "statistics" | "reps">): Configuration {
  const price = reference().cost.price_per_gpu_hour_usd.value!;
  const gpus = c.profile === "prover-h100" ? 1 : 0;
  const r = c.raw;
  const failed = c.runs.filter((x) => x.status === "failed").length;
  const ptr = (m: string) => `mock://releases/${RELEASE.id}/index.json#/configurations/${c.system}/${c.workload}/statistics/${m}`;
  const q = (m: string, values: number[] | undefined, unit: string, scope: string | null, grade: Grade): Quantity => {
    const kind = grade === "derived" ? "derivation" : "harness";
    if (!values) return { value: null, unit, scope, grade, tier: c.effective_tier, source: { kind, ref: ptr(m) }, null_reason: c.null_reasons[m] ?? "not_reported", mock: true };
    reps[m] = values;
    const s = stats(values, failed);
    return { value: s.mean, unit, scope, grade, tier: c.effective_tier, source: { kind, ref: ptr(m) }, null_reason: null, stats: s, mock: true };
  };
  const out: Record<string, Quantity> = {};
  const reps: Record<string, number[]> = {};
  for (const [m, meta] of Object.entries(RAW_META) as [RawId, (typeof RAW_META)[RawId]][])
    if (r[m] || c.null_reasons[m]) out[m] = q(m, r[m], meta.unit, meta.scope, "measured");

  const derived: [string, number[] | undefined, string, string | null][] = [
    ["rate_whole_wall", per(r.tokens_covered_total, r.whole_wall_seconds, rate), "token/s", "whole_wall"],
    ["rate_prove.session", per(r.tokens_covered_total, r.prove_session_seconds, rate), "token/s", "prove.session"],
    ["rate_prove.steady", per(r.tokens_covered_steady, r.prove_steady_seconds, rate), "token/s", "prove.steady"],
    // D-COST-1K-S = seconds per token × 1000 × gpus × price / 3600
    ["cost_per_1k_tokens_whole_wall", gpus ? per(r.whole_wall_seconds, r.tokens_covered_total, (s, t) => ((s / t) * 1000 * gpus * price) / 3600) : undefined, "USD/1k_token", "whole_wall"],
    ["proof_bytes_per_token", per(r.proof_bytes_total, r.tokens_covered_total, (b, t) => b / t), "B/token", null],
    ["verify_seconds_per_token", per(r.verify_seconds_total, r.tokens_covered_total, (s, t) => s / t), "s/token", "verify"],
  ];
  for (const [m, values, unit, scope] of derived) if (values || c.null_reasons[m]) out[m] = q(m, values, unit, scope, "derived");
  return { ...c, statistics: out, reps };
}

const rep = (...v: number[]) => v;
const same = (v: number, n = 3) => Array<number>(n).fill(v);
const sum = (a: number[], b: number[]) => a.map((x, i) => x + b[i]);

const fpB24Session = rep(1185.3, 1192.0, 1179.4);
const fpB24Commit = rep(2410.5, 2398.2, 2422.9);
const fpB1Session = rep(301.2, 302.8, 300.5);
const fpB1Commit = rep(2405.1, 2412.6, 2399.8);
const sashC4096Session = rep(5402.1, 5361.7, 5480.8);
const sashC4096Commit = rep(64.2, 63.8, 65.1);
const sashC1024Session = rep(1318.4, 1304.0, 1331.7);
const sashC1024Commit = rep(63.9, 64.4, 63.5);

// Alphabetical by system, workload, profile (RFC-0009 S5): the order is checked by the test.
export const configurations: Configuration[] = [
  build({
    system: "flashprove", configuration: "exact-match-lean", workload: "fp-maverick-w1024-b1", profile: "prover-h100", effective_tier: "reported",
    runs: [{ run_id: "mock-fp-b1-r1", status: "completed" }, { run_id: "mock-fp-b1-r2", status: "completed" }, { run_id: "mock-fp-b1-r3", status: "completed" }],
    raw: {
      setup_seconds: rep(118.2, 117.6, 119.0), commit_seconds: fpB1Commit, prove_session_seconds: fpB1Session, prove_steady_seconds: rep(234.8, 236.1, 233.9),
      whole_wall_seconds: sum(fpB1Commit, fpB1Session), tokens_covered_total: same(5120), tokens_covered_steady: same(4096), requests_count: same(5), proofs_count: same(5),
      proof_bytes_total: rep(93_910_000, 93_880_000, 93_940_000), verify_seconds: rep(3.11, 3.14, 3.09), verify_seconds_total: rep(15.6, 15.7, 15.5), verify_single_thread_seconds: rep(21.12, 21.17, 21.1),
    },
    null_reasons: {},
  }),
  build({
    system: "flashprove", configuration: "exact-match-lean", workload: "fp-maverick-w1024-b24", profile: "prover-h100", effective_tier: "reproduced",
    runs: [{ run_id: "mock-fp-b24-r1", status: "completed" }, { run_id: "mock-fp-b24-r2", status: "completed" }, { run_id: "mock-fp-b24-r3", status: "completed" }],
    raw: {
      setup_seconds: rep(121.4, 119.9, 120.7), commit_seconds: fpB24Commit, prove_session_seconds: fpB24Session, prove_steady_seconds: rep(887.2, 894.9, 881.6),
      whole_wall_seconds: sum(fpB24Commit, fpB24Session), tokens_covered_total: same(122_880), tokens_covered_steady: same(98_304), requests_count: same(120), proofs_count: same(120),
      proof_bytes_total: rep(2_253_600_000, 2_254_100_000, 2_252_900_000), verify_seconds: rep(3.12, 3.09, 3.15), verify_seconds_total: rep(374.4, 370.8, 378.0), verify_single_thread_seconds: rep(21.14, 21.11, 21.17),
    },
    null_reasons: {},
  }),
  build({
    system: "ref-recompute", configuration: null, workload: "sash-l31-8b-c4096", profile: "prover-h100", effective_tier: "reported",
    runs: [{ run_id: "mock-rr-c4096-r1", status: "completed" }, { run_id: "mock-rr-c4096-r2", status: "completed" }, { run_id: "mock-rr-c4096-r3", status: "completed" }],
    raw: { whole_wall_seconds: rep(9.84, 9.71, 9.93), tokens_covered_total: same(4608) },
    null_reasons: {},
  }),
  build({
    system: "ref-serve", configuration: null, workload: "fp-maverick-w1024-b24", profile: "prover-h100", effective_tier: "reported",
    runs: [],
    raw: {},
    null_reasons: { whole_wall_seconds: "not_measurable_on_profile", rate_whole_wall: "not_measurable_on_profile" },
  }),
  build({
    system: "ref-serve", configuration: null, workload: "sash-l31-8b-c4096", profile: "prover-h100", effective_tier: "reported",
    runs: [{ run_id: "mock-rs-c4096-r1", status: "completed" }, { run_id: "mock-rs-c4096-r2", status: "completed" }, { run_id: "mock-rs-c4096-r3", status: "completed" }],
    raw: { whole_wall_seconds: rep(3.42, 3.39, 3.45), tokens_covered_total: same(4608) },
    null_reasons: {},
  }),
  build({
    system: "sash", configuration: "default", workload: "sash-l31-8b-c1024", profile: "prover-h100", effective_tier: "reported",
    runs: [{ run_id: "mock-sash-c1024-r1", status: "completed" }, { run_id: "mock-sash-c1024-r2", status: "completed" }, { run_id: "mock-sash-c1024-r3", status: "completed" }],
    raw: {
      setup_seconds: rep(40.8, 41.2, 40.5), commit_seconds: sashC1024Commit, prove_session_seconds: sashC1024Session, whole_wall_seconds: sum(sashC1024Commit, sashC1024Session),
      tokens_covered_total: same(1088), requests_count: same(1), proofs_count: same(1), proof_bytes_total: same(4_870_000_000), verify_seconds: rep(30.2, 29.8, 30.5), verify_seconds_total: rep(30.2, 29.8, 30.5),
      verify_single_thread_seconds: rep(198.4, 197.1, 199.6),
    },
    null_reasons: { prove_steady_seconds: "not_observable", "rate_prove.steady": "not_observable" },
  }),
  build({
    system: "sash", configuration: "default", workload: "sash-l31-8b-c4096", profile: "prover-h100", effective_tier: "peer-reviewed",
    runs: [
      { run_id: "mock-sash-c4096-r1", status: "superseded", reason: "replaced by mock-sash-c4096-r4: the verifier container ran with 4 CPUs instead of 8 (mock correction)." },
      { run_id: "mock-sash-c4096-r2", status: "completed" },
      { run_id: "mock-sash-c4096-r3", status: "completed" },
      { run_id: "mock-sash-c4096-r4", status: "completed" },
      { run_id: "mock-sash-c4096-r5", status: "failed", exit_code: 1, last_lines: ["upload: archive part 3 of 7: connection reset", "harness: run failed in phase upload, proofs kept on the runner"] },
    ],
    raw: {
      setup_seconds: rep(41.3, 40.9, 42.0), commit_seconds: sashC4096Commit, prove_session_seconds: sashC4096Session, whole_wall_seconds: sum(sashC4096Commit, sashC4096Session),
      tokens_covered_total: same(4608), requests_count: same(1), proofs_count: same(1), proof_bytes_total: same(19_800_000_000), verify_seconds: rep(121.4, 119.8, 122.6), verify_seconds_total: rep(121.4, 119.8, 122.6),
      verify_single_thread_seconds: rep(802.5, 799.1, 806.3),
    },
    null_reasons: { prove_steady_seconds: "not_observable", "rate_prove.steady": "not_observable" },
  }),
];

export const NATIVE_METRICS = ["rate_whole_wall", "rate_prove.steady", "cost_per_1k_tokens_whole_wall", "proof_bytes_per_token", "verify_seconds_per_token"];

/** D-OVERHEAD-S: mean(ref-serve rate_S) / mean(system rate_S), same workload and profile (RFC-0004, INV-DERIVE-2). */
export function overhead(c: Configuration): Quantity | null {
  if (c.system.startsWith("ref-")) return null;
  const ref = configurations.find((r) => r.system === "ref-serve" && r.workload === c.workload && r.profile === c.profile);
  const a = ref?.statistics.rate_whole_wall?.value;
  const b = c.statistics.rate_whole_wall?.value;
  const base = { unit: "ratio", scope: "whole_wall", grade: "derived" as const, tier: c.effective_tier, mock: true, source: { kind: "derivation", ref: `mock://D-OVERHEAD-whole_wall/${c.system}/${c.workload}` } };
  if (a == null || b == null) return { ...base, value: null, null_reason: ref ? (ref.null_reasons.rate_whole_wall ?? "missing_input") : "not_applicable" };
  return { ...base, value: a / b, null_reason: null };
}

export const configsOf = (system: string) => configurations.filter((c) => c.system === system);
export const configsOn = (workload: string) => configurations.filter((c) => c.workload === workload);

// ------------------------------------------------------------------ controls (RFC-0008)

export type Outcome = "rejected" | "accepted" | "no_verdict" | "invalid_call" | "void" | "not_applicable" | "error" | "prover_failed";
export type Control = { id: string; what: string; expected: Outcome[]; outcome: Outcome; reason?: string; kind: "shared" | "system" };

const SHARED: [string, string, Outcome[]][] = [
  ["C1", "change the claimed output token", ["rejected"]],
  ["C2", "change one prompt token in the request", ["rejected"]],
  ["C3", "verify against the commitment of perturbed weights", ["rejected"]],
  ["C4", "replay a valid proof for a different request", ["rejected"]],
  ["C5", "truncate the proof's largest part", ["rejected", "invalid_call"]],
  ["C6", "flip one bit at a seeded offset, 5 seeds", ["rejected", "invalid_call"]],
  ["C7", "swap the proofs of two requests in one batch", ["rejected"]],
  ["C8", "drop one part of the proof", ["rejected", "invalid_call"]],
  ["P1", "commit W, prove with perturbed W'", ["prover_failed", "rejected"]],
  ["P2", "prove with another precision", ["prover_failed", "rejected"]],
];

function controlSet(over: Record<string, [Outcome, string?]>, extra: Control[] = []): Control[] {
  return [
    ...SHARED.map(([id, what, expected]) => {
      const [outcome, reason] = over[id] ?? [expected[0]];
      return { id, what, expected, outcome, reason, kind: "shared" as const };
    }),
    ...extra,
  ];
}

const ONE_PRECISION: [Outcome, string] = ["not_applicable", "the workload declares one precision"];

export const controls: { system: string; workload: string; profile: string; run_id: string; items: Control[] }[] = [
  {
    system: "flashprove", workload: "fp-maverick-w1024-b1", profile: "prover-h100", run_id: "mock-fp-b1-r1",
    items: controlSet({ C3: ["not_applicable", "perturbed commitment not created within the release budget (RFC-0008 Q2)"], C5: ["invalid_call"], C7: ["not_applicable", "batch size 1"], P1: ["not_applicable", "perturbed commitment not created"], P2: ONE_PRECISION }),
  },
  {
    system: "flashprove", workload: "fp-maverick-w1024-b24", profile: "prover-h100", run_id: "mock-fp-b24-r1",
    items: controlSet({ C3: ["not_applicable", "perturbed commitment not created within the release budget (RFC-0008 Q2)"], C6: ["invalid_call"], C8: ["void", "honest twin returned no_verdict: verifier timeout"], P1: ["not_applicable", "perturbed commitment not created"], P2: ONE_PRECISION }),
  },
  {
    system: "sash", workload: "sash-l31-8b-c1024", profile: "prover-h100", run_id: "mock-sash-c1024-r2",
    items: controlSet({ C4: ["not_applicable", "one request per job, no second distinct request"], C7: ["not_applicable", "batch size 1"], P2: ONE_PRECISION }),
  },
  {
    system: "sash", workload: "sash-l31-8b-c4096", profile: "prover-h100", run_id: "mock-sash-c4096-r2",
    items: controlSet(
      { C4: ["not_applicable", "one request per job, no second distinct request"], C6: ["invalid_call"], C7: ["not_applicable", "batch size 1"], P2: ONE_PRECISION },
      [{ id: "S-W1", what: "weakened prover with --unsound-skip-* (binding report must mark the edge unbound)", expected: ["accepted"], outcome: "accepted", kind: "system" }],
    ),
  },
];

export const passed = (c: Control) => c.expected.includes(c.outcome);
export const counted = (c: Control) => !["void", "not_applicable", "error"].includes(c.outcome);

// ------------------------------------------------------------------ targets (RFC-0009 §Targets)

export type Target = { id: string; author: string; metric: string; comparator: "<=" | ">=" | "=="; value: number; unit: string; scope: string | null; claim_class: string; rationale: string; file?: string };

export const targets: Target[] = [
  { id: "verify-under-60s", author: "Example relying party (mock)", metric: "verify_seconds", comparator: "<=", value: 60, unit: "s", scope: "verify", claim_class: "*/exact-match/*", rationale: "A mock target from the RFC-0009 example: a relying party that checks every proof on an 8-CPU verifier wants each check under a minute." },
  { id: "cost-under-0.05-per-1k", author: "Example relying party (mock)", metric: "cost_per_1k_tokens_whole_wall", comparator: "<=", value: 0.05, unit: "USD/1k_token", scope: "whole_wall", claim_class: "*", rationale: "A mock target that matches every claim class, so every prover configuration is evaluated against it." },
];

export type Evaluation = { target: Target; system: string; workload: string; profile: string; result: "meets" | "does_not_meet" | "not_evaluable"; reason?: string; mean: Quantity | null; least: Quantity | null };

const classMatches = (pattern: string, cls: string) => {
  if (pattern === "*") return true;
  const p = pattern.split("/"), c = cls.split("/");
  return p.length === c.length && p.every((s, i) => s === "*" || s === c[i]);
};

/** RFC-0009 §Targets: compare the least favourable completed repetition, never the mean. */
export function evaluate(t: Target): Evaluation[] {
  return configurations.flatMap((config): Evaluation[] => {
    const card = systems.find((s) => s.name === config.system)?.cards.find((k) => k.configuration === config.configuration);
    if (!card || !classMatches(t.claim_class, card.claim_class)) return [];
    const q = config.statistics[t.metric];
    const at = { target: t, system: config.system, workload: config.workload, profile: config.profile, mean: null, least: null };
    if (!q || q.value === null || !q.stats) return [{ ...at, result: "not_evaluable", reason: q?.null_reason ?? "metric missing" }];
    if (q.unit !== t.unit || q.scope !== t.scope) return [{ ...at, result: "not_evaluable", reason: "unit or scope differs" }];
    const leastFavourable = t.comparator === "<=" ? q.stats.max : q.stats.min;
    const ok = t.comparator === "<=" ? leastFavourable <= t.value : t.comparator === ">=" ? leastFavourable >= t.value : leastFavourable === t.value;
    const { stats: _, ...plain } = q;
    return [{ ...at, result: ok ? "meets" : "does_not_meet", mean: q, least: { ...plain, value: leastFavourable } }];
  });
}

// ------------------------------------------------------------------ reproductions (RFC-0007)

export const reproductions = [
  { system: "flashprove", workload: "fp-maverick-w1024-b24", by: "Mock runner B (unaffiliated)", result: "within tolerance", date: "2026-12-02" },
  { system: "sash", workload: "sash-l31-8b-c4096", by: "Mock reviewer C (another organisation)", result: "peer review recorded, rerun pending", date: "2026-12-04" },
  { system: "sash", workload: "sash-l31-8b-c1024", by: "Mock runner B (unaffiliated)", result: "failed: run aborted at commit, rerun scheduled", date: "2026-12-05" },
];
