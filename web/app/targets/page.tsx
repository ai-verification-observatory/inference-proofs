import { A, Chip, Code, PageHeader, Panel, Q, Section, Table } from "@/components/ui";
import { data, isMock } from "@/lib/release";
import { blob } from "@/lib/repo";

export const metadata = { title: "Targets" };

const TONE = { meets: "good", does_not_meet: "bad", not_evaluable: "plain" } as const;

export default function TargetsPage() {
  return (
    <>
      <PageHeader eyebrow="Evidence, RFC-0009 §Targets" title="Targets">
        <p>
          Relying parties publish thresholds they care about, attributed to them. Each target is evaluated against the least favourable completed repetition, not the mean. The project publishes no targets of its own
          {isMock ? "; the two below are mock examples." : "."}
        </p>
      </PageHeader>
      {data.targets.length === 0 && <p className="text-sm text-ink-3">No target was evaluated in this release.</p>}
      {data.targets.map((t) => (
        <Section key={t.id} title={t.id} note={t.author}>
          <Panel className="mb-4 px-5 py-4">
            <p className="text-sm">
              <Code>{t.metric}</Code> <span className="num">{t.comparator} {t.value}</span> {t.unit}{t.scope && `, scope ${t.scope}`}, for claim class <Code>{t.claim_class}</Code>
              {t.file && <> (<A href={blob(t.file, "main")}>{t.file}</A>)</>}
            </p>
            <p className="mt-2 text-sm text-ink-2">{t.rationale}</p>
          </Panel>
          <Table head={["Configuration", "Result", "Mean", "Least favourable repetition", "Reason"]} caption={`Evaluation of ${t.id}`}>
            {data.evaluations.filter((e) => e.target === t).map((e) => (
              <tr key={e.system + e.workload + e.profile}>
                <th scope="row" className="text-left font-normal"><A href={`/systems/${e.system}/`}>{e.system}</A> <span className="num text-xs text-ink-2">{e.workload}</span></th>
                <td><Chip tone={TONE[e.result]}>{e.result}</Chip></td>
                <td>{e.mean ? <Q q={e.mean} profile={e.profile} /> : <span className="text-xs text-ink-3">none</span>}</td>
                <td>{e.least ? <Q q={e.least} profile={e.profile} /> : <span className="text-xs text-ink-3">none</span>}</td>
                <td className="text-xs text-ink-2">{e.reason ?? ""}</td>
              </tr>
            ))}
          </Table>
        </Section>
      ))}
    </>
  );
}
