import { A, Chip, PageHeader, Section, Table } from "@/components/ui";
import { blob, RFC_COMMIT, rfcs } from "@/lib/repo";

export const metadata = { title: "Methodology" };

export default function Methodology() {
  return (
    <>
      <PageHeader eyebrow="Methodology" title="The rules every number follows">
        <p>
          Every RFC at the release&apos;s RFC commit <A href={blob("rfcs")}><span className="num text-[13px]">{RFC_COMMIT.slice(0, 12)}</span></A>. Accepted and Final RFCs are normative; Draft RFCs are proposals. Read from the
          repository at build time.
        </p>
      </PageHeader>
      <Section title="RFCs">
        <Table head={["RFC", "Title", "Status"]} caption="RFCs">
          {rfcs().map((r) => (
            <tr key={r.id}>
              <th scope="row" className="num whitespace-nowrap text-xs font-medium">RFC-{r.id}</th>
              <td><A href={blob(`rfcs/${r.file}`)}>{r.title}</A></td>
              <td><Chip tone={r.status.startsWith("Accepted") || r.status.startsWith("Final") ? "good" : "plain"}>{r.status}</Chip></td>
            </tr>
          ))}
        </Table>
      </Section>
      <Section title="Vocabulary">
        <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          {[
            ["Timing scope", "The interval a time or rate covers: setup, commit, prove.steady, prove.session, whole_wall, verify, verify.single_thread, primitive (RFC-0004)."],
            ["Grade", "How a number was obtained: measured, derived, projected, external or asserted (RFC-0004)."],
            ["Evidence tier", "Who stands behind a number: reported, peer-reviewed or reproduced (RFC-0007)."],
            ["Tokens covered", "The positions whose computation a proof binds; the denominator of every per-token metric (RFC-0004)."],
          ].map(([k, v]) => (
            <div key={k} className="border-l-2 border-accent/50 pl-3">
              <dt className="font-medium">{k}</dt>
              <dd className="mt-1 text-ink-2">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-sm"><A href={blob("docs/spec/10-glossary.md")}>Full glossary</A></p>
      </Section>
    </>
  );
}
