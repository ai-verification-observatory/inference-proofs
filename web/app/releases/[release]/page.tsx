import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { A, Chip, Code, KV, PageHeader, Panel, ProfileChip, Q, Section, Table, TierChip } from "@/components/ui";
import { data, isMock, STATUS } from "@/lib/release";
import { blob, reference, RFC_COMMIT } from "@/lib/repo";

type P = { params: Promise<{ release: string }> };

const { configurations, release: RELEASE, reproductions, systems } = data;

export const generateStaticParams = () => [{ release: RELEASE.id }];
export const dynamicParams = false;
export const metadata = { title: `Release ${RELEASE.id}` };

export default async function ReleasePage({ params }: P) {
  if ((await params).release !== RELEASE.id) notFound();
  const ref = reference();
  const runs = configurations.flatMap((c) => c.runs.map((r) => ({ ...r, c })));
  const notCompleted = runs.filter((r) => r.status !== "completed" && r.status !== "included");
  return (
    <>
      <PageHeader eyebrow={`Release, ${STATUS[RELEASE.status]}`} title={`Release ${RELEASE.id}`}>
        <p>{RELEASE.scope}</p>
      </PageHeader>

      <div className="grid grid-cols-1 gap-x-10 xl:grid-cols-2">
        <Section title="Scope">
          <Panel className="px-5 pb-3">
            <KV
              rows={[
                ["Status", <Chip tone={RELEASE.status === "published" ? "plain" : "mock"}>{STATUS[RELEASE.status]}</Chip>],
                ["Freeze date", <span className="num">{RELEASE.freeze_date ? `${RELEASE.freeze_date}${isMock ? " (mock)" : ""}` : "not set: no release.yaml yet"}</span>],
                ["Review window", <span className="num">{RELEASE.review_window ? `${RELEASE.review_window.opens} to ${RELEASE.review_window.closes}` : isMock ? "14 days before freeze for every listed system" : "not set: no release.yaml yet"}</span>],
                ...(RELEASE.index_file ? [["Release index", <A href={blob(RELEASE.index_file, "main")}>{RELEASE.index_file}</A>] as [string, ReactNode]] : []),
                ["RFC commit", RELEASE.rfc_commit ? <a className="link num text-xs" href={blob("rfcs", RELEASE.rfc_commit)}>{RELEASE.rfc_commit}</a> : <a className="link num text-xs" href={blob("rfcs")}>{RFC_COMMIT}{RELEASE.index_file && " (dashboard pin; no release.yaml yet)"}</a>],
                ["Reference file", <A href={blob(RELEASE.reference_file)}>{RELEASE.reference_file}</A>],
                ["Systems", <span className="flex flex-wrap gap-1.5">{systems.map((s) => <A key={s.name} href={`/systems/${s.name}/`}>{s.name}</A>)}</span>],
              ]}
            />
          </Panel>
        </Section>

        <Section title="Reference cost basis" note="Real data, RFC-0006">
          <Panel className="px-5 py-4">
            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-ink-3">Price per GPU hour</p>
            <Q q={ref.cost.price_per_gpu_hour_usd} />
            <p className="mt-3 text-sm text-ink-2">{ref.cost.basis}, {ref.cost.date}. Priced: {ref.cost.priced.join(", ")}. Not priced: {ref.cost.not_priced.join(", ")}.</p>
            <ul className="mt-3 space-y-1 text-xs text-ink-2">
              {ref.cost.readings.map((r) => (
                <li key={r.provider}>
                  <a className="link" href={r.url}>{r.provider}</a>: {r.offer}, <span className="num">{r.list_price_usd_per_hour}</span> USD/hour for <span className="num">{r.gpus}</span> GPU{r.gpus > 1 && "s"} (asserted, list price)
                </li>
              ))}
            </ul>
          </Panel>
        </Section>
      </div>

      <Section title="Reference profiles" note={<>From <A href={blob(RELEASE.reference_file)}>{RELEASE.reference_file}</A></>}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Object.entries(ref.profiles).map(([id, p]) => (
            <Panel key={id} className="px-5 pb-3">
              <p className="pt-4 text-sm font-semibold"><Code>{id}</Code> <span className="ml-1 font-normal text-ink-3">{p.kind}</span></p>
              <KV
                rows={[
                  ["GPU", p.gpu ? `${p.gpu.count} × ${p.gpu.model}, ${p.gpu.form_factor}` : "none"],
                  ["CPU", Object.entries(p.cpu).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join("; ")],
                  ["Host memory", `${p.host_memory_gib_min ?? p.host_memory_gib} GiB${p.host_memory_gib_min ? " minimum" : ""}`],
                ]}
              />
            </Panel>
          ))}
        </div>
      </Section>

      <Section title="Reproduced, reviewed and failed" note={isMock ? "Mock records, RFC-0007" : "RFC-0007"}>
        {reproductions.length === 0 ? (
          <p className="text-sm text-ink-3">No reproduction records in this release.</p>
        ) : (
          <Table head={["System", "Workload", "By", "Date", "Result", "Effective tier"]} caption="Reproductions">
            {reproductions.map((r) => {
              const tier = configurations.find((c) => c.system === r.system && c.workload === r.workload)?.effective_tier;
              return (
                <tr key={r.system + r.workload + (r.path ?? r.by)}>
                  <th scope="row" className="font-medium"><A href={`/systems/${r.system}/`}>{r.system}</A></th>
                  <td className="num text-xs">{r.workload}</td>
                  <td className="text-ink-2">{r.by}</td>
                  <td className="num text-xs text-ink-2">{r.date ?? (r.path ? <A href={blob(r.path, "main")}>record</A> : "not stated")}</td>
                  <td className="text-ink-2">{r.result}</td>
                  <td>{tier && <TierChip tier={tier} />}</td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      <Section title="Runs that did not contribute" note="Listed with the reason; never in statistics (RFC-0009 S7)">
        <Table head={["Run", "Configuration", "Status", "Reason"]} caption="Failed and superseded runs">
          {notCompleted.length === 0 && <tr><td colSpan={4} className="text-sm text-ink-3">None.</td></tr>}
          {notCompleted.map((r) => (
            <tr key={r.run_id}>
              <th scope="row"><del className="num text-xs font-normal text-ink-2">{r.run_id}</del></th>
              <td className="text-xs"><A href={`/systems/${r.c.system}/`}>{r.c.system}</A> on {r.c.workload} <ProfileChip profile={r.c.profile} /></td>
              <td><Chip tone={r.status === "failed" ? "bad" : "plain"}>{r.status}</Chip></td>
              <td className="text-xs text-ink-2">{r.reason ?? `exit code ${r.exit_code}: ${r.last_lines?.at(-1)}`}</td>
            </tr>
          ))}
        </Table>
      </Section>
    </>
  );
}
