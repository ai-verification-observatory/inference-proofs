import Link from "next/link";
import type { ReactNode } from "react";
import { sig4 } from "@/lib/format";
import type { Quantity, Tier } from "@/lib/mock";
import { blob } from "@/lib/repo";

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-10 border-b border-line pb-8">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink-3">{eyebrow}</p>
      <h1 className="mt-2 font-display text-4xl leading-tight text-ink sm:text-[2.75rem]">{title}</h1>
      {children && <div className="mt-4 max-w-3xl text-[15px] leading-relaxed text-ink-2">{children}</div>}
    </header>
  );
}

export function Section({ id, title, note, children }: { id?: string; title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="mb-14 scroll-mt-20">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {note && <p className="text-sm text-ink-3">{note}</p>}
      </div>
      {children}
    </section>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-surface ${className}`}>{children}</div>;
}

export function Chip({ children, tone = "plain", title }: { children: ReactNode; tone?: "plain" | "accent" | "good" | "bad" | "mock"; title?: string }) {
  const tones = {
    plain: "border-line-2 text-ink-2",
    accent: "border-transparent bg-accent-soft text-accent",
    good: "border-transparent bg-good-soft text-good",
    bad: "border-transparent bg-bad-soft text-bad",
    mock: "border-mock/40 text-mock hatch",
  };
  return (
    <span title={title} className={`inline-flex items-center whitespace-nowrap rounded border px-1.5 py-px text-[11px] leading-4 ${tones[tone]}`}>
      {children}
    </span>
  );
}

const TIER_TONE: Record<Tier, "plain" | "accent" | "good"> = { reported: "plain", "peer-reviewed": "accent", reproduced: "good" };
export const TierChip = ({ tier }: { tier: Tier }) => <Chip tone={TIER_TONE[tier]}>tier {tier}</Chip>;

export function SourceRef({ q }: { q: Pick<Quantity, "source" | "mock"> }) {
  const { kind, ref } = q.source;
  const cls = "text-[11px] text-ink-3";
  if (ref.startsWith("http")) return <a className={`${cls} link`} href={ref}>source: {kind}</a>;
  if (ref.startsWith("mock://")) return <span className={cls} title={ref}>source: mock {kind} record</span>;
  return <a className={`${cls} link`} href={blob(ref.replace(/#.*/, ""))} title={ref}>source: {kind}</a>;
}

/** A labelled quantity: value, unit, scope, grade, tier and source side by side (RFC-0009 S2, S3, S4). */
export function Q({ q, chart }: { q: Quantity; chart?: ReactNode }) {
  return (
    <div className="min-w-44">
      {q.value === null ? (
        <p className="num text-[15px] text-ink-3">
          null <span className="font-sans text-xs">({q.null_reason})</span> <span className="font-sans text-xs">{q.unit}</span>
        </p>
      ) : (
        <p className="text-[15px] text-ink">
          <span className="num font-medium" title={String(q.value)}>{sig4(q.value)}</span> <span className="text-xs text-ink-2">{q.unit}</span>
        </p>
      )}
      <div className="mt-1 flex flex-wrap gap-1">
        {q.scope && <Chip>scope {q.scope}</Chip>}
        <Chip>grade {q.grade}</Chip>
        <TierChip tier={q.tier} />
        {q.mock && <Chip tone="mock" title="Invented for layout; no benchmark run produced it">mock</Chip>}
      </div>
      {q.stats && (
        <p className="num mt-1 text-[11px] leading-4 text-ink-3">
          mean <span title={String(q.stats.mean)}>{sig4(q.stats.mean)}</span>, sd <span title={String(q.stats.stdev)}>{sig4(q.stats.stdev)}</span>, min{" "}
          <span title={String(q.stats.min)}>{sig4(q.stats.min)}</span>, max <span title={String(q.stats.max)}>{sig4(q.stats.max)}</span>, n {q.stats.n}, n_failed {q.stats.n_failed}
        </p>
      )}
      {chart}
      <SourceRef q={q} />
    </div>
  );
}

export function KV({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-8 sm:grid-cols-[minmax(10rem,auto)_1fr]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="pt-2.5 text-xs font-medium uppercase tracking-wider text-ink-3 sm:border-t sm:border-line sm:pb-2.5">{k}</dt>
          <dd className="pb-2.5 text-sm text-ink sm:border-t sm:border-line sm:pt-2.5">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Table({ head, children, caption }: { head: ReactNode[]; children: ReactNode; caption?: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full border-collapse text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-sunken/60">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className="whitespace-nowrap border-b border-line px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-ink-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr:not(:last-child)>*]:border-b [&>tr>*]:border-line [&>tr>*]:px-4 [&>tr>*]:py-3 [&>tr>*]:align-top">{children}</tbody>
      </table>
    </div>
  );
}

export const A = ({ href, children }: { href: string; children: ReactNode }) =>
  href.startsWith("http") ? <a className="link" href={href}>{children}</a> : <Link className="link" href={href}>{children}</Link>;

export const Code = ({ children }: { children: ReactNode }) => <code className="num rounded bg-sunken px-1 py-px text-[12.5px] text-ink-2">{children}</code>;
