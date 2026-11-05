// Real records read from the repository at build time. Nothing here is mock data.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import type { Quantity } from "./mock.ts";

// next build and npm test both run in web/; Vercel clones the whole repository.
export const ROOT = path.join(process.cwd(), "..");
export const REPO = "https://github.com/ai-verification-observatory/inference-proofs";
export const RFC_COMMIT = "6e28a7f4454ecc61c922fb59961e08e574934442";

const yaml = (rel: string) => parse(readFileSync(path.join(ROOT, rel), "utf-8"));

export type Figure = { id: string; metric: string; workload: string; quantity: Quantity & { upstream_scope: string; mapping: string; note: string } };
export type External = { system: string; upstream: { repo: string; commit: string }; figures: Figure[]; file: string };

export function externals(): External[] {
  return ["flashprove", "sash"].map((s) => ({ ...yaml(`systems/${s}/external.yaml`), file: `systems/${s}/external.yaml` }));
}

export type Reference = {
  release: string;
  profiles: Record<string, { kind: string; gpu: { model: string; form_factor: string; count: number } | null; cpu: Record<string, number>; host_memory_gib_min?: number; host_memory_gib?: number }>;
  cost: { price_per_gpu_hour_usd: Quantity; basis: string; providers: string[]; date: string; readings: { provider: string; url: string; offer: string; list_price_usd_per_hour: number; gpus: number }[]; priced: string[]; not_priced: string[] };
};

export const reference = (): Reference => yaml("reference/v0.1.yaml");

/** RFC-0001 §System inclusion: `maintainers: []` in system.yaml means no system maintainer has been reached. */
export function notReached(system: string, root = ROOT): boolean {
  const file = path.join(root, "systems", system, "system.yaml");
  const m = existsSync(file) ? parse(readFileSync(file, "utf-8"))?.maintainers : undefined;
  return Array.isArray(m) && m.length === 0;
}

export function rfcs(): { id: string; title: string; status: string; file: string }[] {
  return readdirSync(path.join(ROOT, "rfcs"))
    .filter((f) => /^0\d{3}-/.test(f) && !f.startsWith("0000"))
    .sort()
    .map((file) => {
      const text = readFileSync(path.join(ROOT, "rfcs", file), "utf-8");
      const [, id, title] = text.match(/^# RFC-(\d{4}): (.+)$/m) ?? [];
      return { id, title, status: text.match(/^- Status: (.+)$/m)?.[1] ?? "not stated", file };
    });
}

export const blob = (rel: string, commit = RFC_COMMIT) => `${REPO}/blob/${commit}/${rel}`;
