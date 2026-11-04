import { A, Chip, Code, PageHeader, Panel, Section, Table, TierChip } from "@/components/ui";
import { sig4 } from "@/lib/format";
import { evaluate, targets } from "@/lib/mock";

export const metadata = { title: "Targets" };

const TONE = { meets: "good", does_not_meet: "bad", not_evaluable: "plain" } as const;

export default function TargetsPage() {
  return (
    <>
      <PageHeader eyebrow="Evidence, RFC-0009 §Targets" title="Targets">
        <p>
          Relying parties publish thresholds they care about, attributed to them. Each target is evaluated against the least favourable completed repetition, not the mean. The project publishes no targets of its own; the two
          below are mock examples.
        </p>
      </PageHeader>
      {targets.map((t) => (
        <Section key={t.id} title={t.id} note={t.author}>
          <Panel className="mb-4 px-5 py-4">
            <p className="text-sm">
              <Code>{t.metric}</Code> <span className="num">{t.comparator} {t.value}</span> {t.unit}, scope {t.scope}, for claim class <Code>{t.claim_class}</Code>
            </p>
            <p className="mt-2 text-sm text-ink-2">{t.rationale}</p>
          </Panel>
          <Table head={["Configuration", "Result", "Mean", "Least favourable repetition", "Labels", "Reason"]} caption={`Evaluation of ${t.id}`}>
            {evaluate(t).map((e) => (
              <tr key={e.config.system + e.config.workload}>
                <th scope="row" className="text-left font-normal"><A href={`/systems/${e.config.system}/`}>{e.config.system}</A> <span className="num text-xs text-ink-2">{e.config.workload}</span></th>
                <td><Chip tone={TONE[e.result]}>{e.result}</Chip></td>
                <td className="num whitespace-nowrap text-xs">{e.mean !== undefined ? <span title={String(e.mean)}>{sig4(e.mean)} {t.unit}</span> : "none"}</td>
                <td className="num whitespace-nowrap text-xs">{e.leastFavourable !== undefined ? <span title={String(e.leastFavourable)}>{sig4(e.leastFavourable)} {t.unit}</span> : "none"}</td>
                <td>
                  {e.mean !== undefined && (
                    <span className="flex flex-wrap gap-1">
                      <Chip>scope {t.scope}</Chip>
                      <Chip>grade {e.config.statistics[t.metric].grade}</Chip>
                      <TierChip tier={e.config.effective_tier} />
                      <Chip tone="mock">mock</Chip>
                    </span>
                  )}
                </td>
                <td className="text-xs text-ink-2">{e.reason ?? ""}</td>
              </tr>
            ))}
          </Table>
        </Section>
      ))}
    </>
  );
}
