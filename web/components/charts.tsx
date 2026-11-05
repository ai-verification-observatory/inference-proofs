// Small static charts: plain HTML and SVG, native title tooltips, no client JavaScript.
import { sig4 } from "@/lib/format";
import type { Configuration } from "@/lib/mock";
import type { Tally } from "@/lib/release";

/** Repetitions of one statistic on its own axis (min to max), so it never compares rows. */
export function RangeStrip({ values, unit }: { values: number[]; unit: string }) {
  const lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.01 || 1;
  const x = (v: number) => 6 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 188;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  return (
    <svg viewBox="0 0 200 18" className="my-1 h-[18px] w-full max-w-56" role="img" aria-label={`${values.length} repetitions from ${sig4(lo)} to ${sig4(hi)} ${unit}`}>
      <line x1={x(lo)} x2={x(hi)} y1="9" y2="9" stroke="var(--line-2)" strokeWidth="2" strokeLinecap="round" />
      <line x1={x(mean)} x2={x(mean)} y1="3" y2="15" stroke="var(--ink-3)" strokeWidth="1.5">
        <title>{`mean ${sig4(mean)} ${unit}`}</title>
      </line>
      {values.map((v, i) => (
        <circle key={i} cx={x(v)} cy="9" r="4" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2">
          <title>{`repetition ${i + 1}: ${v} ${unit}`}</title>
        </circle>
      ))}
    </svg>
  );
}

/** Control outcomes as one segmented bar, every segment named in text beside it (RFC-0009 S9). */
export function OutcomeBar({ t }: { t: Tally }) {
  const parts = [
    { label: "passed", n: t.passed, color: "var(--good)" },
    { label: "failed", n: t.failed, color: "var(--bad)" },
    { label: "void, not applicable or error", n: t.other, color: "var(--neutral-mark)" },
  ];
  return (
    <div>
      <div className="flex h-2.5 gap-0.5 overflow-hidden rounded" role="img" aria-label={parts.map((p) => `${p.n} ${p.label}`).join(", ")}>
        {parts.filter((p) => p.n).map((p) => (
          <div key={p.label} title={`${p.n} ${p.label}`} style={{ flexGrow: p.n, background: p.color }} />
        ))}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-sm" style={{ background: p.color }} aria-hidden />
            <span className="num">{p.n}</span> {p.label}
          </span>
        ))}
      </p>
    </div>
  );
}

/** One repetition laid out on the RFC-0004 timing scopes, with each proof's release time. */
export function RunAnatomy({ c }: { c: Configuration }) {
  const r = c.raw;
  const first = (k: keyof typeof r) => r[k]?.[0];
  const setup = first("setup_seconds") ?? 0, commit = first("commit_seconds"), session = first("prove_session_seconds");
  if (commit === undefined || session === undefined) return null;
  const steady = first("prove_steady_seconds");
  const verify = first("verify_seconds_total") ?? 0;
  const proveStart = setup + commit, end = proveStart + session, total = end + verify;
  const k = first("proofs_count") ?? 1;
  const r1 = steady === undefined ? end : end - steady;
  const releases = Array.from({ length: Math.min(k, 60) }, (_, i) => (k === 1 ? r1 : r1 + ((end - r1) * i) / (Math.min(k, 60) - 1)));
  const rows: [string, number, number | null][] = [
    ["setup", 0, setup],
    ["commit", setup, proveStart],
    ["prove.session", proveStart, end],
    ["prove.steady", steady === undefined ? end : r1, steady === undefined ? null : end],
    ["whole_wall", setup, end],
    ["verify", end, total],
  ];
  const pct = (v: number) => `${(v / total) * 100}%`;
  return (
    <figure>
      <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5 text-xs">
        {rows.map(([name, a, b]) => (
          <div key={name} className="contents">
            <span className="num text-ink-2">{name}</span>
            <div className="relative h-4 rounded-sm bg-sunken">
              {b === null ? (
                <span className="absolute inset-y-0 left-1 text-[11px] leading-4 text-ink-3">null (not_observable)</span>
              ) : (
                <div
                  className={`absolute inset-y-0 rounded-sm ${name === "whole_wall" ? "border border-accent/60" : "bg-accent/75"}`}
                  style={{ left: pct(a), width: `max(2px, ${pct(b - a)})` }}
                  title={`${name}: ${sig4(b - a)} s`}
                />
              )}
            </div>
          </div>
        ))}
        <span className="num text-ink-2">releases</span>
        <div className="relative h-4">
          {releases.map((t, i) => (
            <span key={i} className="absolute top-0 h-4 w-px bg-ink-2" style={{ left: pct(t) }} title={`${k > 60 ? "release tick" : `proof ${i + 1}`} at ${sig4(t)} s`} />
          ))}
        </div>
      </div>
      <figcaption className="mt-3 text-xs text-ink-3">
        Repetition 1, mock values, seconds from the setup call start; total <span className="num">{sig4(total)}</span> s.
        {k > 60 && ` ${k} proofs released; the first 60 release ticks are drawn.`} Scopes as RFC-0004 defines them.
      </figcaption>
    </figure>
  );
}
