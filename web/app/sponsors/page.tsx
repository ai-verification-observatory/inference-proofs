import { readFileSync } from "node:fs";
import path from "node:path";
import { A, PageHeader, Panel, Section, Table } from "@/components/ui";
import { blob, ROOT } from "@/lib/repo";

export const metadata = { title: "Sponsors and conflicts" };

// The "## Maintainers" table of MAINTAINERS.md, read at build time.
function maintainers(): string[][] {
  const text = readFileSync(path.join(ROOT, "MAINTAINERS.md"), "utf-8");
  const section = text.split(/^## /m).find((s) => s.startsWith("Maintainers\n")) ?? "";
  return section.split("\n").filter((l) => l.startsWith("|")).slice(2).map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
}

export default function Sponsors() {
  const rows = maintainers();
  return (
    <>
      <PageHeader eyebrow="Governance" title="Sponsors and conflicts">
        <p>Sponsors as listed in the release file and conflicts as declared in MAINTAINERS.md, in separate sections (RFC-0009).</p>
      </PageHeader>
      <Section title="Sponsors">
        <Panel className="px-5 py-4 text-sm text-ink-2">None listed: the mock release has no release.yaml yet.</Panel>
      </Section>
      <Section title="Maintainers and declared interests" note={<A href={blob("MAINTAINERS.md")}>MAINTAINERS.md</A>}>
        <Table head={["Handle", "Role", "Organisation", "Systems maintained", "Declared interests", "Since"]} caption="Maintainers">
          {rows.map((r) => (
            <tr key={r[0]}>
              <th scope="row" className="font-medium">{r[0]}</th>
              {r.slice(1).map((c, i) => <td key={i} className={c === "undeclared" ? "italic text-ink-3" : "text-ink-2"}>{c}</td>)}
            </tr>
          ))}
        </Table>
        <p className="mt-2 text-xs text-ink-3">undeclared means the person has not yet stated the fact; it is not a valid final value.</p>
      </Section>
    </>
  );
}
