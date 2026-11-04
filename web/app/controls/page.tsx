import { OutcomeBar } from "@/components/charts";
import { A, Chip, Code, PageHeader, Panel, Section, Table } from "@/components/ui";
import { controls, counted, passed } from "@/lib/mock";

export const metadata = { title: "Negative controls" };

export default function ControlsPage() {
  return (
    <>
      <PageHeader eyebrow="Evidence, RFC-0008" title="Negative controls">
        <p>
          After an honest run, every verifier faces the same tampering tests, produced by the harness, never the adapter. Each control runs next to an honest twin that must be accepted; when the twin is not accepted the control
          is void. A control passes when its outcome is in its expected set. Passing byte-level controls shows integrity checking, not soundness.
        </p>
      </PageHeader>
      {controls.map((set) => (
        <Section key={set.system + set.workload} title={`${set.system} on ${set.workload}`} note={<>profile {set.profile}, run <Code>{set.run_id}</Code>, mock outcomes</>}>
          <Panel className="mb-4 px-5 py-4"><OutcomeBar items={set.items} /></Panel>
          <Table head={["Control", "Mutation", "Expected", "Outcome", "Result", "Reason"]} caption={`Controls for ${set.system} on ${set.workload}`}>
            {set.items.map((c) => (
              <tr key={c.id}>
                <th scope="row" className="num whitespace-nowrap text-xs font-medium">{c.id}{c.kind === "system" && <span className="ml-1 font-sans font-normal text-ink-3">(system suite)</span>}</th>
                <td className="text-ink-2">{c.what}</td>
                <td className="num whitespace-nowrap text-xs text-ink-2">{c.expected.join(", ")}</td>
                <td className="num whitespace-nowrap text-xs">{c.outcome}</td>
                <td>{counted(c) ? (passed(c) ? <Chip tone="good">passed</Chip> : <Chip tone="bad">failed</Chip>) : <Chip>not counted</Chip>}</td>
                <td className="text-xs text-ink-2">{c.reason ?? ""}</td>
              </tr>
            ))}
          </Table>
          <p className="mt-2 text-xs text-ink-3"><A href={`/systems/${set.system}/`}>System page</A></p>
        </Section>
      ))}
    </>
  );
}
