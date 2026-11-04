import Link from "next/link";
import { ClaimSummary } from "@/components/claim";
import { A, PageHeader, Q, Table } from "@/components/ui";
import { configurations, NATIVE_METRICS, overhead, RELEASE, systems, type Configuration } from "@/lib/mock";

export const SORTS = ["workload", "profile", ...NATIVE_METRICS, "overhead_vs_serving_whole_wall"];
// Metric ids hold dots (rate_prove.steady); a dot in a path segment reads as a file extension.
export const slug = (id: string) => id.replaceAll(".", "-");

const metric = (c: Configuration, m: string) => (m === "overhead_vs_serving_whole_wall" ? overhead(c) : c.statistics[m]);

/** A reader-requested sort: a separate static page, never the default (RFC-0009 S5). Nulls go last. */
function sorted(sort: string | null) {
  if (!sort) return configurations;
  if (sort === "workload" || sort === "profile") return [...configurations].sort((a, b) => a[sort].localeCompare(b[sort]));
  const v = (c: Configuration) => metric(c, sort)?.value ?? null;
  return [...configurations].sort((a, b) => (v(a) === null ? 1 : v(b) === null ? -1 : v(a)! - v(b)!));
}

export function DivisionTable({ sort }: { sort: string | null }) {
  const rows = sorted(sort);
  const cols = [...NATIVE_METRICS, "overhead_vs_serving_whole_wall"];
  const head = (id: string, label = id) => (
    <Link href={sort === id ? "/divisions/native/" : `/divisions/native/by/${slug(id)}/`} className={`underline decoration-dotted underline-offset-4 hover:text-ink ${sort === id ? "text-ink decoration-solid" : ""}`}>
      {label}
    </Link>
  );
  return (
    <>
      <PageHeader eyebrow={`Release ${RELEASE.id}`} title="Native division">
        <p className="rounded-md border border-line-2 bg-surface px-4 py-3 font-medium text-ink">Native workloads differ: rows are not a head-to-head comparison.</p>
        <p className="mt-3">
          Each system runs its own model and shape, shown side by side with the normalised metrics of RFC-0004. Rows are in alphabetical order by system, workload and profile.{" "}
          {sort ? (
            <>This page is sorted by <span className="num text-[13px]">{sort}</span>, as requested by following that column&apos;s link; <A href="/divisions/native/">alphabetical order</A>.</>
          ) : (
            "A column heading links to a page sorted by that column."
          )}{" "}
          There is no combined score and no highlighted value.
        </p>
      </PageHeader>
      <Table head={[<Link key="s" href="/divisions/native/" className="underline decoration-dotted underline-offset-4 hover:text-ink">System</Link>, "Claim card summary", head("workload", "Workload"), head("profile", "Profile"), ...cols.map((m) => head(m))]} caption="Native division rows">
        {rows.map((c) => {
          const card = systems.find((s) => s.name === c.system)?.cards.find((k) => k.configuration === c.configuration);
          return (
            <tr key={c.system + c.workload}>
              <th scope="row" className="whitespace-nowrap font-medium"><A href={`/systems/${c.system}/`}>{c.system}</A></th>
              <td className="min-w-64"><ClaimSummary card={card} /></td>
              <td className="num whitespace-nowrap text-xs"><A href={`/workloads/${c.workload}/`}>{c.workload}</A></td>
              <td className="whitespace-nowrap text-xs text-ink-2">{c.profile}</td>
              {cols.map((m) => {
                const q = metric(c, m);
                return <td key={m}>{q ? <Q q={q} /> : <span className="text-xs text-ink-3">not reported</span>}</td>;
              })}
            </tr>
          );
        })}
      </Table>
    </>
  );
}
