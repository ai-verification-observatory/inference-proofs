import { RangeStrip, RunAnatomy } from "@/components/charts";
import type { Configuration } from "@/lib/mock";
import { notReached } from "@/lib/repo";
import { A, Chip, Code, Panel, ProfileChip, Q, TierChip } from "./ui";

export function configTitle(c: Configuration) {
  return `${c.system}${c.configuration ? ` / ${c.configuration}` : ""} on ${c.workload}`;
}

export function Runs({ c }: { c: Configuration }) {
  if (!c.runs.length) return <p className="text-sm text-ink-3">No runs: the reference system cannot run this workload on the profile.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {c.runs.map((r) => (
        <li key={r.run_id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          {r.status === "completed" || r.status === "included" ? <Code>{r.run_id}</Code> : <del className="num text-[12.5px] text-ink-3">{r.run_id}</del>}
          <Chip tone={r.status === "failed" ? "bad" : "plain"} title={r.status === "included" ? "a kept repetition, completed or failed: n_failed in each statistic counts the failed ones" : undefined}>{r.status}</Chip>
          {r.reason && <span className="text-ink-2">{r.reason}</span>}
          {r.exit_code !== undefined && (
            <span className="w-full pl-1 text-xs text-ink-2">
              exit code <span className="num">{r.exit_code}</span>, last lines:
              <pre className="num mt-1 overflow-x-auto rounded bg-sunken px-3 py-2 text-[11.5px] text-ink-2">{r.last_lines?.join("\n")}</pre>
            </span>
          )}
        </li>
      ))}
      <li className="pt-1 text-xs text-ink-3">Superseded, failed and ineligible runs never contribute to statistics (RFC-0009 S7).</li>
    </ul>
  );
}

export function ConfigBlock({ c, anatomy = true }: { c: Configuration; anatomy?: boolean }) {
  const measured = Object.entries(c.statistics).filter(([, q]) => q.grade === "measured");
  const derived = Object.entries(c.statistics).filter(([, q]) => q.grade === "derived");
  return (
    <Panel className="mb-6 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3.5">
        <h4 className="mr-2 text-[15px] font-semibold">
          <A href={`/systems/${c.system}/`}>{c.system}</A>
          {c.configuration && <span className="font-normal text-ink-2"> / {c.configuration}</span>}
          <span className="font-normal text-ink-2"> on </span>
          <A href={`/workloads/${c.workload}/`}>{c.workload}</A>
        </h4>
        <ProfileChip profile={c.profile} />
        <TierChip tier={c.effective_tier} />
        {notReached(c.system) && <Chip tone="bad">system maintainers not reached</Chip>}
        {(c.insufficient_repetitions ?? (c.runs.filter((r) => r.status === "completed").length < 3 && c.runs.length > 0)) && <Chip tone="bad">below minimum repetitions</Chip>}
      </div>
      <div className="grid grid-cols-1 gap-x-8 gap-y-6 px-5 py-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          {[["Measured", measured], ["Derived (computed by the derivation code)", derived]].map(([title, rows]) =>
            (rows as typeof measured).length ? (
              <div key={title as string}>
                <h5 className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-3">{title as string}</h5>
                <div className="grid grid-cols-1 gap-x-6 gap-y-5 sm:grid-cols-2 2xl:grid-cols-3">
                  {(rows as typeof measured).map(([id, q]) => (
                    <div key={id} className="min-w-0 border-t border-line pt-2.5">
                      <p className="num mb-1 truncate text-xs text-ink-2" title={id}>{id}</p>
                      <Q q={q} profile={c.profile} chart={c.reps[id] && q.stats && q.stats.max > q.stats.min ? <RangeStrip values={c.reps[id]} unit={q.unit} /> : null} />
                    </div>
                  ))}
                </div>
              </div>
            ) : null,
          )}
        </div>
        <div className="space-y-6">
          <div>
            <h5 className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-3">Runs</h5>
            <Runs c={c} />
          </div>
          {anatomy && c.raw.prove_session_seconds && (
            <div>
              <h5 className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-3">Run anatomy</h5>
              <RunAnatomy c={c} />
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
