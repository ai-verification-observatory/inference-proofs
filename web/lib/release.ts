// What the dashboard renders: the newest releases/<release>/index.json (release-index/1, written by
// `iproofs release freeze`, RFC-0009) when one exists, else the mock data of mock.ts. Index numbers
// are copied with their unit, scope, grade, tier and source, never recomputed (AGENTS.md rule 3).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import * as mock from "./mock.ts";
import type { ClaimCard, Configuration, Control, Evaluation, Outcome, Quantity, Run, System, Target, Tier, Workload } from "./mock.ts";
import { ROOT } from "./repo.ts";

export type Status = "mock" | "candidate" | "published";
export type Release = {
  id: string;
  status: Status;
  /** the index file, null on the mock path */
  index_file: string | null;
  /** release.yaml, null when it does not exist (mock, or a draft index without one) */
  record_file: string | null;
  freeze_date: string | null;
  review_window: { opens: string; closes: string } | null;
  reference_file: string;
  rfc_commit: string | null;
  scope: string;
  sponsors: { name: string; provided: string; period: string }[] | null;
};
export type ControlSet = {
  system: string;
  workload: string;
  profile: string;
  run_id: string | null;
  /** per-control records; the index keeps counts and the outcomes outside their expected set only */
  items: Control[] | null;
  counts: Record<Outcome, number>;
  outside_expected: { control_id: string; run_id: string; outcome: Outcome }[];
};
export type Reproduction = { system: string; workload: string; by: string; result: string; date: string | null; path: string | null };
export type Data = {
  release: Release;
  systems: System[];
  workloads: Workload[];
  configurations: Configuration[];
  controls: ControlSet[];
  targets: Target[];
  evaluations: Evaluation[];
  reproductions: Reproduction[];
};

// ------------------------------------------------------------------ helpers

type Doc = Record<string, unknown>;
const NS = "not stated";
const MISSING = "not in this checkout";
const OUTCOMES: Outcome[] = ["rejected", "accepted", "no_verdict", "invalid_call", "void", "not_applicable", "error", "prover_failed"];
const NOT_COUNTED: Outcome[] = ["void", "not_applicable", "error"];

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const read = (root: string, rel: string) => (existsSync(path.join(root, rel)) ? readFileSync(path.join(root, rel), "utf-8") : null);
const yamlAt = (root: string, rel: string): Doc | null => {
  const t = read(root, rel);
  return t === null ? null : (parse(t) as Doc);
};
const need = (root: string, rel: string, why: string): Doc => {
  const d = yamlAt(root, rel);
  if (!d) throw new Error(`${rel} is missing, but ${why}`);
  return d;
};
const dig = (doc: unknown, dotted: string): unknown =>
  dotted.split(".").reduce<unknown>((d, k) => (d && typeof d === "object" ? (d as Doc)[k] : undefined), doc);
/** A claim card field on one line: mappings as `key value`, lists joined by `; ` (as site.py). */
const text = (v: unknown): string =>
  v == null ? NS : Array.isArray(v) ? v.map(text).join("; ") : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k} ${text(x)}`).join(", ") : String(v);
const pointer = (...parts: (string | number)[]) => parts.map((p) => "/" + String(p).replaceAll("~", "~0").replaceAll("/", "~1")).join("");

/** RFC-0009 S5: system, workload, profile, then configuration. */
const s5 = (c: { system: string; workload: string; profile: string; configuration?: string | null }) => [c.system, c.workload, c.profile, c.configuration ?? ""].join("\u0000");
const byS5 = <T extends Parameters<typeof s5>[0]>(a: T, b: T) => cmp(s5(a), s5(b));

// ------------------------------------------------------------------ the release index (schema/release-index/1.schema.json)

type IxWorkload = { id: string; version: number };
type Index = {
  schema: string;
  release: string;
  configurations: {
    system: string; workload: IxWorkload; profile: string; configuration: string | null; runs: string[];
    ineligible: { run_id: string; reasons: string[] }[]; insufficient_repetitions: boolean;
    statistics: Record<string, Quantity>; effective_tier: Tier; evidence: { reviews: string[]; reproductions: string[] };
  }[];
  controls: { system: string; workload: IxWorkload; profile: string; counts: Record<Outcome, number>; outside_expected: ControlSet["outside_expected"] }[];
  targets: { target: string; system: string; workload: IxWorkload; profile: string; result: Evaluation["result"]; reason: string | null; mean: Quantity | null; least_favourable: Quantity | null }[];
  claim_cards: { system: string; configuration: string; card_version: number; path: string; digest: string }[];
  reference: { file: string; digest: string };
  inputs_digest: string;
};

/** The newest release with an index.json, by version number (v0.10 after v0.9), or null. */
export function newestRelease(root = ROOT): string | null {
  const dir = path.join(root, "releases");
  if (!existsSync(dir)) return null;
  const ids = readdirSync(dir).filter((r) => /^v\d+\.\d+$/.test(r) && existsSync(path.join(dir, r, "index.json")));
  return ids.sort((a, b) => a.localeCompare(b, "en", { numeric: true })).at(-1) ?? null;
}

/**
 * RFC-0009 §Review window: the index has no draft field, so release.yaml decides. Published only
 * once the review window has closed and the freeze date has come; a missing release.yaml or window
 * means a release candidate.
 */
export function releaseStatus(record: Doc | null, today: string): "candidate" | "published" {
  const closes = dig(record, "review_window.closes"), freeze = dig(record, "freeze_date");
  return closes != null && freeze != null && today > String(closes) && today >= String(freeze) ? "published" : "candidate";
}

function card(k: Index["claim_cards"][number], doc: Doc | null): ClaimCard {
  const f = (dotted: string) => (doc ? text(dig(doc, dotted)) : MISSING);
  const list = (key: string) => (!doc ? [MISSING] : Array.isArray(doc[key]) ? (doc[key] as unknown[]).map(text) : [text(doc[key])]);
  const edges = dig(doc, "binding.edges");
  return {
    configuration: k.configuration,
    card_version: k.card_version,
    note: doc ? `Copied from ${k.path} (frozen digest ${k.digest}).` : `The card file ${k.path} (frozen digest ${k.digest}) is not in this checkout, so its fields are not shown.`,
    claim_class: f("claim_class"),
    relation: f("relation"),
    security: {
      notion: f("security.notion.kind"),
      verifier: f("security.notion.verifier"),
      level: f("security.level"),
      assumption: f("security.model.assumption"),
      adversary: f("security.model.adversary"),
      setup: f("security.setup"),
    },
    zero_knowledge: { claimed: f("zero_knowledge.claimed"), hidden: f("zero_knowledge.hidden"), not_hidden: f("zero_knowledge.not_hidden"), status: f("zero_knowledge.status") },
    assumptions: list("assumptions"),
    coverage: { phase: f("coverage.phase"), unit: f("coverage.unit"), tokens_covered: f("coverage.tokens_covered"), operations: f("coverage.operations"), policy: f("coverage.policy") },
    binding: Array.isArray(edges) ? edges.map((e) => `${text(dig(e, "edge"))}: ${text(dig(e, "state"))}`).join("; ") : f("binding"),
    residual: list("residual"),
    availability: f("availability"),
    forbidden_flags: Array.isArray(doc?.forbidden_flags) ? (doc.forbidden_flags as unknown[]).map(String) : [],
    reviewed_by: !doc ? null : Array.isArray(doc.reviewed_by) ? (doc.reviewed_by as unknown[]).map(text) : [],
  };
}

function system(root: string, name: string, cards: ClaimCard[], reply: string | null): System {
  const y = need(root, `systems/${name}/system.yaml`, `the release index lists system ${name}`);
  const kind = y.kind === "reference" || y.kind === "test" ? y.kind : "prover";
  const summary =
    kind === "reference" ? `Reference row, role ${text(y.reference_role)}: runs the model without proving (RFC-0015).`
    : kind === "test" ? "Test system for CI, not a prover under benchmark (RFC-0013 §G10)."
    : `Proofs per ${text(dig(y, "proofs.granularity"))}; tokens covered: ${text(dig(y, "proofs.tokens_covered"))} (systems/${name}/system.yaml).`;
  const up = y.upstream as { repo?: string; commit?: string } | undefined;
  return { name, title: name, kind, upstream: up?.repo && up.commit ? { repo: up.repo, commit: up.commit } : null, summary, cards, reply };
}

function workload(root: string, w: IxWorkload, kinds: Map<string, string>): Workload {
  const y = need(root, `workloads/${w.id}.yaml`, `the release index lists workload ${w.id}`);
  const n = (d: string) => Number(dig(y, d));
  const listed = (y.systems as string[] | undefined) ?? [];
  const src = dig(y, "model.source") as Doc | undefined;
  return {
    id: w.id,
    version: w.version,
    system: listed.find((s) => kinds.get(s) !== "reference") ?? listed[0] ?? NS,
    division: text(y.division),
    model: `${text(src?.repo ?? src?.hub)}${src?.path ? `, ${text(src.path)}` : ""}, revision ${text(dig(y, "model.revision"))}`,
    precision: `served ${text(dig(y, "precision.served"))}, proved ${text(dig(y, "precision.proved"))}`,
    prompt_tokens: n("shape.prompt_tokens"),
    output_tokens: n("shape.output_tokens"),
    batch: n("shape.batch_size"),
    batches: n("shape.batches_per_session"),
    prompts: n("prompts.count"),
    phase: text(y.phase),
    active_parameters_per_token: text(dig(y, "model.parameters.active_per_token")),
    notes: "",
    model_digest: text(dig(y, "model.digest")),
    corpus_digest: text(dig(y, "prompts.corpus_digest")),
  };
}

function target(root: string, file: string): Target {
  const y = need(root, file, "the release index evaluates it");
  return {
    id: text(y.id),
    author: `${text(dig(y, "author.name"))} (${text(dig(y, "author.affiliation"))})`,
    metric: text(y.metric),
    comparator: y.comparator as Target["comparator"],
    value: Number(dig(y, "threshold.value")),
    unit: text(dig(y, "threshold.unit")),
    scope: (dig(y, "threshold.scope") as string | null) ?? null,
    claim_class: text(y.claim_class),
    rationale: text(y.rationale),
    file,
  };
}

export function fromIndex(root: string, id: string, today: string): Data {
  const file = `releases/${id}/index.json`;
  const ix = JSON.parse(readFileSync(path.join(root, file), "utf-8")) as Index;
  if (ix.schema !== "release-index/1") throw new Error(`${file}: schema ${ix.schema}, expected release-index/1`);
  const recordFile = `releases/${id}/release.yaml`;
  const record = yamlAt(root, recordFile);
  const at = (q: Quantity | null, ...parts: (string | number)[]) => (q ? { ...q, pointer: `${file}#${pointer(...parts)}` } : null);

  const configurations = ix.configurations
    .map((c, i): Configuration => ({
      system: c.system,
      configuration: c.configuration,
      workload: c.workload.id,
      profile: c.profile,
      effective_tier: c.effective_tier,
      // index runs are the kept repetitions, completed or failed; statistics count the failed ones in n_failed
      runs: [
        ...c.runs.map((run_id): Run => ({ run_id, status: "included" })),
        ...c.ineligible.map(({ run_id, reasons }): Run => ({ run_id, status: reasons.some((r) => r.startsWith("superseded")) ? "superseded" : "ineligible", reason: reasons.join("; ") })),
      ],
      insufficient_repetitions: c.insufficient_repetitions,
      raw: {},
      null_reasons: {},
      reps: {},
      statistics: Object.fromEntries(Object.entries(c.statistics).map(([m, q]) => [m, at(q, "configurations", i, "statistics", m)!])),
    }))
    .sort(byS5);

  const names = [...new Set([...ix.configurations.map((c) => c.system), ...ix.claim_cards.map((c) => c.system)])].sort(cmp);
  const replies = (record?.replies ?? {}) as Record<string, string>;
  const systems = names.map((name) =>
    system(
      root,
      name,
      ix.claim_cards.filter((k) => k.system === name).sort((a, b) => cmp(a.configuration, b.configuration)).map((k) => card(k, yamlAt(root, k.path))),
      replies[name] ? read(root, replies[name]) : null,
    ),
  );
  const kinds = new Map(systems.map((s) => [s.name, s.kind]));
  const seen = new Map(ix.configurations.map((c) => [c.workload.id, c.workload]));
  const workloads = [...seen.keys()].sort(cmp).map((w) => workload(root, seen.get(w)!, kinds));

  const controls = ix.controls
    .map((c): ControlSet => ({ system: c.system, workload: c.workload.id, profile: c.profile, run_id: null, items: null, counts: c.counts, outside_expected: c.outside_expected }))
    .sort(byS5);

  const targets = [...new Set(ix.targets.map((t) => t.target))].sort(cmp).map((f) => target(root, f));
  const evaluations = ix.targets
    .map((t, i): Evaluation => ({
      target: targets.find((x) => x.file === t.target)!,
      system: t.system,
      workload: t.workload.id,
      profile: t.profile,
      result: t.result,
      reason: t.reason ?? undefined,
      mean: at(t.mean, "targets", i, "mean"),
      least: at(t.least_favourable, "targets", i, "least_favourable"),
    }))
    .sort(byS5);

  const reproductions = ix.configurations.flatMap((c) =>
    c.evidence.reproductions.map((p): Reproduction => {
      const doc = read(root, p);
      const d = doc ? (JSON.parse(doc) as Doc) : null;
      return { system: c.system, workload: c.workload.id, by: d ? text(dig(d, "runner.organisation")) : MISSING, result: d ? text(d.outcome) : MISSING, date: null, path: p };
    }),
  );

  const window = record?.review_window as Release["review_window"] | undefined;
  return {
    release: {
      id,
      status: releaseStatus(record, today),
      index_file: file,
      record_file: record ? recordFile : null,
      freeze_date: record?.freeze_date != null ? String(record.freeze_date) : null,
      review_window: window ? { opens: String(window.opens), closes: String(window.closes) } : null,
      reference_file: ix.reference.file,
      rfc_commit: record?.rfc_commit != null ? String(record.rfc_commit) : null,
      scope: `Configurations, controls, targets and claim cards as frozen in ${file} (inputs digest ${ix.inputs_digest}).`,
      sponsors: record ? ((record.sponsors as Release["sponsors"]) ?? []) : null,
    },
    systems,
    workloads,
    configurations,
    controls,
    targets,
    evaluations,
    reproductions,
  };
}

// ------------------------------------------------------------------ the mock path

function fromMock(): Data {
  const controls = mock.controls.map((s): ControlSet => {
    const counts = Object.fromEntries(OUTCOMES.map((o) => [o, s.items.filter((c) => c.outcome === o).length])) as Record<Outcome, number>;
    const outside_expected = s.items.filter((c) => !mock.passed(c)).map((c) => ({ control_id: c.id, run_id: s.run_id, outcome: c.outcome }));
    return { ...s, counts, outside_expected };
  });
  return {
    release: {
      id: mock.RELEASE.id,
      status: "mock",
      index_file: null,
      record_file: null,
      freeze_date: mock.RELEASE.freeze_date,
      review_window: null,
      reference_file: mock.RELEASE.reference_file,
      rfc_commit: null,
      scope: mock.RELEASE.scope,
      sponsors: null,
    },
    systems: mock.systems,
    workloads: mock.workloads,
    configurations: mock.configurations,
    controls,
    targets: mock.targets,
    evaluations: mock.targets.flatMap(mock.evaluate),
    reproductions: mock.reproductions.map((r) => ({ ...r, path: null })),
  };
}

export function load(root = ROOT, today = new Date().toISOString().slice(0, 10)): Data {
  const id = newestRelease(root);
  return id ? fromIndex(root, id, today) : fromMock();
}

// ------------------------------------------------------------------ what the pages import

export const data = load();
export const isMock = data.release.status === "mock";
export const STATUS: Record<Status, string> = { mock: "draft, mock", candidate: "release candidate under review", published: "published" };
export { counted, NATIVE_METRICS, passed } from "./mock.ts";

export const configsOf = (system: string, d = data) => d.configurations.filter((c) => c.system === system);
export const configsOn = (workload: string, d = data) => d.configurations.filter((c) => c.workload === workload);
export const cardOf = (c: Configuration, d = data) => d.systems.find((s) => s.name === c.system)?.cards.find((k) => k.configuration === c.configuration);

/** D-OVERHEAD-whole_wall: the index statistic when there is one; the mock path computes it from mock values. */
export const overhead = (c: Configuration, d = data): Quantity | null =>
  d.release.status === "mock" ? mock.overhead(c) : (c.statistics.overhead_vs_serving_whole_wall ?? null);

/**
 * Reference rows next to the rows they serve: alphabetical by the system that owns the workload,
 * then workload and profile (S5), the system's own rows before the reference rows on them.
 */
export function served(rows: Configuration[], d = data): Configuration[] {
  const owner = (c: Configuration) => d.workloads.find((w) => w.id === c.workload)?.system ?? c.system;
  const ref = (c: Configuration) => (d.systems.find((s) => s.name === c.system)?.kind === "reference" ? "1" : "0");
  const key = (c: Configuration) => [owner(c), c.workload, c.profile, ref(c), c.system, c.configuration ?? ""].join("\u0000");
  return [...rows].sort((a, b) => cmp(key(a), key(b)));
}

export type Tally = { passed: number; failed: number; other: number };

/** Control outcomes in three groups: in the expected set, outside it, and not counted (void, not applicable, error). */
export function tally(sets: ControlSet[]): Tally {
  const t = { passed: 0, failed: 0, other: 0 };
  for (const s of sets) {
    const total = OUTCOMES.reduce((n, o) => n + s.counts[o], 0);
    const other = NOT_COUNTED.reduce((n, o) => n + s.counts[o], 0);
    const failed = s.outside_expected.filter((o) => !NOT_COUNTED.includes(o.outcome)).length;
    t.passed += total - other - failed;
    t.failed += failed;
    t.other += other;
  }
  return t;
}
