import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { OutcomeBar } from "@/components/charts";
import { ClaimCardView } from "@/components/claim";
import { ConfigBlock } from "@/components/config";
import { A, Chip, Code, PageHeader, Panel, Q, Section, Table } from "@/components/ui";
import { configsOf, configurations, controls, systems, workloads } from "@/lib/mock";
import { blob, externals } from "@/lib/repo";

type P = { params: Promise<{ system: string }> };

export const generateStaticParams = () => systems.map((s) => ({ system: s.name }));
export const dynamicParams = false;

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const { system } = await params;
  return { title: systems.find((s) => s.name === system)?.title };
}

export default async function SystemPage({ params }: P) {
  const { system: name } = await params;
  const s = systems.find((x) => x.name === name);
  if (!s) notFound();
  const own = configsOf(s.name);
  const ws = [...new Set(own.map((c) => c.workload))];
  const refRows = configurations.filter((c) => c.system.startsWith("ref-") && c.system !== s.name && ws.includes(c.workload));
  const ext = externals().find((e) => e.system === s.name);
  const ctl = controls.filter((c) => c.system === s.name);
  const nav = [["claim-card", "Claim card"], ["rows", "Rows"], ["controls", "Controls"], ["reference-rows", "Reference rows"], ...(ext ? [["upstream", "Upstream figures"]] : []), ["reply", "Reply"]];

  return (
    <>
      <PageHeader eyebrow={s.kind === "reference" ? "Reference system" : "Prover"} title={s.title}>
        <p>{s.summary}</p>
        {s.upstream && (
          <p className="mt-2 text-sm">
            Pinned at <a className="link num text-[13px]" href={`https://github.com/${s.upstream.repo}/tree/${s.upstream.commit}`}>{s.upstream.repo}@{s.upstream.commit}</a>
          </p>
        )}
      </PageHeader>

      <nav aria-label="On this page" className="mb-10 flex flex-wrap gap-2">
        {nav.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-full border border-line px-3 py-1 text-xs text-ink-2 hover:border-line-2 hover:text-ink">{label}</a>
        ))}
      </nav>

      <Section id="claim-card" title="Claim card">
        {s.kind === "reference" ? (
          <Panel className="px-5 py-4 text-sm text-ink-2">A reference row: it runs the model without proving and makes no proof claim (RFC-0015).</Panel>
        ) : s.cards.length ? (
          s.cards.map((card) => <ClaimCardView key={card.configuration} card={card} system={s} />)
        ) : (
          <p className="text-sm text-ink-3">No claim card is listed for this system in the release.</p>
        )}
      </Section>

      <Section id="rows" title="Rows" note="One block per workload and configuration. Repetition strips use each metric's own axis.">
        {ws.length === 0 && <p className="text-sm text-ink-3">No rows in this release.</p>}
        {ws.map((w) => (
          <div key={w} className="mb-2">
            <h3 className="mb-3 text-sm text-ink-2">Workload <A href={`/workloads/${w}/`}>{w}</A></h3>
            {own.filter((c) => c.workload === w).map((c) => <ConfigBlock key={c.workload + c.configuration} c={c} />)}
          </div>
        ))}
      </Section>

      <Section id="controls" title="Controls" note={<A href="/controls/">All controls</A>}>
        {ctl.length === 0 ? (
          <p className="text-sm text-ink-3">{s.kind === "reference" ? "Reference rows run no negative controls: they produce no proof." : "No controls in this release."}</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {ctl.map((c) => (
              <Panel key={c.workload} className="px-5 py-4">
                <p className="mb-3 text-sm"><span className="num text-[13px]">{c.workload}</span> <span className="text-ink-3">profile {c.profile}</span></p>
                <OutcomeBar items={c.items} />
              </Panel>
            ))}
          </div>
        )}
      </Section>

      <Section id="reference-rows" title="Reference rows on the same workloads" note="RFC-0015">
        {refRows.length ? refRows.map((c) => <ConfigBlock key={c.system + c.workload} c={c} anatomy={false} />) : <p className="text-sm text-ink-3">None.</p>}
      </Section>

      {ext && (
        <Section id="upstream" title="Figures the system publishes upstream" note={<>Real data from <A href={blob(ext.file)}>{ext.file}</A>, grade external</>}>
          <p className="mb-4 max-w-3xl text-sm text-ink-2">
            Copied at the pin, never recomputed or rounded in the record. They are context, never inputs to a measured number (RFC-0004 INV-MAP-1). The mapping from the upstream scope is marked approximate where the
            definitions differ.
          </p>
          <Table head={["Metric", "Workload", "Value and labels", "Upstream scope", "Note"]} caption="Upstream figures">
            {ext.figures.map((f) => (
              <tr key={f.id}>
                <th scope="row" className="num text-xs font-normal text-ink-2">{f.metric}</th>
                <td className="num text-xs">{workloads.some((w) => w.id === f.workload) ? <A href={`/workloads/${f.workload}/`}>{f.workload}</A> : f.workload}</td>
                <td><Q q={f.quantity} /></td>
                <td className="text-xs text-ink-2">{f.quantity.upstream_scope} <Chip>mapping {f.quantity.mapping}</Chip></td>
                <td className="max-w-64 text-xs text-ink-2">{f.quantity.note}</td>
              </tr>
            ))}
          </Table>
          <p className="mt-2 text-xs text-ink-3">Upstream pin <Code>{ext.upstream.repo}@{ext.upstream.commit}</Code></p>
        </Section>
      )}

      <Section id="reply" title="Reply from the system maintainers">
        <Panel className="px-5 py-4 text-sm text-ink-3">{s.reply ?? "No reply for this release. System maintainers may write up to 300 words, shown here unedited (RFC-0009 §Right of reply)."}</Panel>
      </Section>
    </>
  );
}
