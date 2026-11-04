import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ClaimSummary } from "@/components/claim";
import { ConfigBlock } from "@/components/config";
import { A, Chip, KV, PageHeader, Panel, Section } from "@/components/ui";
import { configsOn, systems, workloads } from "@/lib/mock";

type P = { params: Promise<{ workload: string }> };

export const generateStaticParams = () => workloads.map((w) => ({ workload: w.id }));
export const dynamicParams = false;
export async function generateMetadata({ params }: P): Promise<Metadata> {
  return { title: (await params).workload };
}

const pending = <span className="italic text-ink-3">not pinned yet: filled from the public model repository in the implementing issue; the schema rejects a workload without it (RFC-0003)</span>;

export default async function WorkloadPage({ params }: P) {
  const { workload } = await params;
  const w = workloads.find((x) => x.id === workload);
  if (!w) notFound();
  const rows = configsOn(w.id);
  const sys = systems.find((s) => s.name === w.system)!;
  return (
    <>
      <PageHeader eyebrow={`Workload, ${w.division} division`} title={<span className="num text-3xl sm:text-4xl">{w.id}</span>}>
        <p>
          {sys.title}&apos;s own model and shape{w.notes && `: ${w.notes}`}. A workload fixes what is proved: the model by content hash, the precision, the prompt set, the shape, the decoding rule and the phase.
        </p>
      </PageHeader>

      <Section title="Definition" note="RFC-0003 §v0.1 native workloads">
        <Panel className="px-5 pb-3">
          <KV
            rows={[
              ["Version", <span className="num">{w.version}</span>],
              ["Division", <Chip>{w.division}</Chip>],
              ["System", <A href={`/systems/${w.system}/`}>{w.system}</A>],
              ["Model", w.model],
              ["Precision", w.precision],
              ["Shape", <span className="num">{w.prompt_tokens.toLocaleString("en-US")} prompt + {w.output_tokens.toLocaleString("en-US")} output tokens, greedy</span>],
              ["Batch", <span className="num">{w.batch} requests per batch, {w.batches} batches per session, {w.prompts} prompts per job</span>],
              ["Phase", w.phase],
              ["Model digest", pending],
              ["Prompt corpus digest", pending],
              ["Active parameters per token", pending],
            ]}
          />
        </Panel>
      </Section>

      <Section title="Configurations on this workload" note="Claim summary first, then rows.">
        {rows.length === 0 && <p className="text-sm text-ink-3">No configurations in this release.</p>}
        {rows.map((c) => {
          const card = systems.find((s) => s.name === c.system)?.cards.find((k) => k.configuration === c.configuration);
          return (
            <div key={c.system} className="mb-2">
              <Panel className="mb-3 px-5 py-3"><ClaimSummary card={card} /></Panel>
              <ConfigBlock c={c} anatomy={false} />
            </div>
          );
        })}
      </Section>
    </>
  );
}
