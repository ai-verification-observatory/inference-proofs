import { OutcomeBar } from "@/components/charts";
import { ClaimSummary } from "@/components/claim";
import { A, Chip, PageHeader, Panel, ProfileChip, Section, Table, TierChip } from "@/components/ui";
import type { Tier } from "@/lib/mock";
import { data, isMock, STATUS, tally } from "@/lib/release";

const { configurations, controls, release, reproductions, systems, workloads } = data;

const TIERS: Tier[] = ["reported", "peer-reviewed", "reproduced"];
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

function Tile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Panel className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-ink-3">{label}</p>
      <p className="num mt-2 text-3xl font-medium text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-2">{detail}</p>
    </Panel>
  );
}

export default function Home() {
  const runs = configurations.flatMap((c) => c.runs);
  const by = [...new Set(runs.map((r) => r.status))].sort().map((s) => `${runs.filter((r) => r.status === s).length} ${s}`).join(", ");
  const t = tally(controls);
  const provers = systems.filter((s) => s.kind !== "reference");
  return (
    <>
      <PageHeader eyebrow={`Release ${release.id}, ${STATUS[release.status]}`} title="Provable inference, measured under one set of rules">
        <p>
          The same models, the same reference hardware, the same timing rules, and a claim card saying what each proof establishes. The benchmark measures provers. It does not build, rank or certify them, and no table on
          this site has a combined score.
        </p>
      </PageHeader>

      <div className="mb-14 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Systems" value={String(systems.length)} detail={`${provers.length} provers or test systems, ${systems.length - provers.length} reference systems`} />
        <Tile label="Workloads" value={String(workloads.length)} detail={[...new Set(workloads.map((w) => w.division))].sort().join(", ") + " division"} />
        <Tile label="Runs" value={String(runs.length)} detail={`${by}${isMock ? " (mock)" : ""}`} />
        <Tile label="Controls" value={String(t.passed + t.failed + t.other)} detail={`over ${controls.length} configurations${isMock ? " (mock)" : ""}`} />
      </div>

      <Section title="What each proof establishes" note="Claim cards come before numbers on every page (RFC-0009 S1).">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {provers.map((s) => (
            <Panel key={s.name} className="flex flex-col px-5 py-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="text-[15px] font-semibold"><A href={`/systems/${s.name}/`}>{s.title}</A></h3>
                {s.upstream && <Chip>{s.upstream.repo.split("/")[1]}@{s.upstream.commit.slice(0, 7)}</Chip>}
              </div>
              <p className="mb-4 text-sm text-ink-2">{s.summary}</p>
              <ClaimSummary card={s.cards[0]} />
            </Panel>
          ))}
        </div>
      </Section>

      <div className="grid grid-cols-1 gap-x-10 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Section title="Configurations" note="Alphabetical by system, workload and profile.">
          <Table head={["System", "Workload", "Profile", "Tier", "Runs kept"]} caption="Configurations in the release">
            {configurations.map((c) => (
              <tr key={`${c.system}-${c.workload}-${c.profile}-${c.configuration}`}>
                <th scope="row" className="whitespace-nowrap font-medium"><A href={`/systems/${c.system}/`}>{c.system}</A></th>
                <td className="num whitespace-nowrap text-xs"><A href={`/workloads/${c.workload}/`}>{c.workload}</A></td>
                <td className="whitespace-nowrap text-xs text-ink-2"><ProfileChip profile={c.profile} /></td>
                <td><TierChip tier={c.effective_tier} /></td>
                <td className="num whitespace-nowrap text-xs text-ink-2">{c.runs.filter((r) => r.status === "completed" || r.status === "included").length} of {c.runs.length}</td>
              </tr>
            ))}
          </Table>
        </Section>

        <Section title="Evidence">
          <Panel className="mb-4 px-5 py-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-3">Effective tier per configuration</p>
            <ul className="space-y-2 text-sm">
              {TIERS.map((t) => (
                <li key={t} className="flex items-center justify-between gap-3">
                  <TierChip tier={t} />
                  <span className="num text-ink-2">{plural(configurations.filter((c) => c.effective_tier === t).length, "configuration")}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-ink-3">Only reproduced numbers are called measured in prose (RFC-0007).</p>
          </Panel>
          <Panel className="mb-4 px-5 py-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-3">Negative control outcomes, all configurations</p>
            <OutcomeBar t={t} />
            <p className="mt-3 text-xs"><A href="/controls/">Every outcome</A></p>
          </Panel>
          <Panel className="px-5 py-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-3">Reproductions and reviews</p>
            <ul className="space-y-3 text-sm">
              {reproductions.length === 0 && <li className="text-ink-3">None recorded in this release.</li>}
              {reproductions.map((r) => (
                <li key={r.system + r.workload + (r.path ?? r.by)}>
                  <p><A href={`/systems/${r.system}/`}>{r.system}</A> on <span className="num text-[13px]">{r.workload}</span></p>
                  <p className="text-xs text-ink-2">{r.by}{r.date && `, ${r.date}`}: {r.result}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </Section>
      </div>

      <Section title="What the numbers do not show">
        <ul className="grid grid-cols-1 gap-3 text-sm text-ink-2 md:grid-cols-2">
          <li className="border-l-2 border-line-2 pl-3">Native workloads differ in model, shape and claim. Rows from different native workloads are not a head-to-head comparison (RFC-0003).</li>
          <li className="border-l-2 border-line-2 pl-3">Passing byte-level controls shows integrity checking, not soundness (RFC-0008).</li>
          <li className="border-l-2 border-line-2 pl-3">The benchmark does not interpret security proofs. Security fields are copied from each system&apos;s documentation, or say not stated (RFC-0002).</li>
          <li className="border-l-2 border-line-2 pl-3">Cost prices GPU time only; CPU, host memory, disk and network are not priced (RFC-0006).</li>
        </ul>
      </Section>
    </>
  );
}
