import { OutcomeBar } from "@/components/charts";
import { A, Chip, Code, PageHeader, Panel, ProfileChip, Section, Table } from "@/components/ui";
import { counted, data, isMock, passed, tally } from "@/lib/release";

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
      {data.controls.length === 0 && <p className="text-sm text-ink-3">No controls in this release.</p>}
      {data.controls.map((set) => (
        <Section
          key={set.system + set.workload + set.profile}
          title={`${set.system} on ${set.workload}`}
          note={<span className="inline-flex flex-wrap items-center gap-1"><ProfileChip profile={set.profile} />{set.run_id && <>run <Code>{set.run_id}</Code></>}{isMock && " mock outcomes"}</span>}
        >
          <Panel className="mb-4 px-5 py-4"><OutcomeBar t={tally([set])} /></Panel>
          {set.items ? (
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
          ) : (
            <>
              <Table head={["Outcome", "Controls"]} caption={`Control outcome counts for ${set.system} on ${set.workload}`}>
                {Object.entries(set.counts).sort(([a], [b]) => (a < b ? -1 : 1)).map(([o, n]) => (
                  <tr key={o}>
                    <th scope="row" className="num text-xs font-normal">{o}</th>
                    <td className="num text-xs">{n}</td>
                  </tr>
                ))}
              </Table>
              <h3 className="mb-2 mt-5 text-sm font-semibold">Outcomes outside their expected set</h3>
              {set.outside_expected.length === 0 ? (
                <p className="text-sm text-ink-3">None.</p>
              ) : (
                <Table head={["Control", "Run", "Outcome"]} caption={`Unexpected control outcomes for ${set.system} on ${set.workload}`}>
                  {set.outside_expected.map((o) => (
                    <tr key={o.control_id + o.run_id}>
                      <th scope="row" className="num text-xs font-medium">{o.control_id}</th>
                      <td><Code>{o.run_id}</Code></td>
                      <td className="num text-xs">{o.outcome}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </>
          )}
          <p className="mt-2 text-xs text-ink-3"><A href={`/systems/${set.system}/`}>System page</A></p>
        </Section>
      ))}
    </>
  );
}
