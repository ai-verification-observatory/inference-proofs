import type { ClaimCard, System } from "@/lib/mock";
import { Chip, Code, KV, Panel } from "./ui";

const NS = "not stated";
const V = ({ v }: { v: string }) => (v === NS || v === "not_stated" ? <span className="italic text-ink-3">not stated</span> : <>{v}</>);

/** RFC-0002 §Rules 5: a card nobody from the system has reviewed says so. */
export const Reviewed = ({ card }: { card: ClaimCard }) =>
  card.reviewed_by === null ? <Chip>card file not in this checkout</Chip>
  : card.reviewed_by.length ? <Chip tone="good">reviewed by {card.reviewed_by.join(", ")}</Chip>
  : <Chip tone="bad">card not reviewed by system maintainers</Chip>;

/** The claim card in full (RFC-0002), shown before any number of its system (RFC-0009 S1). */
export function ClaimCardView({ card, system }: { card: ClaimCard; system: System }) {
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-line bg-sunken/50 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-ink-3">What a verifier accept means</span>
          <Chip>configuration {card.configuration}</Chip>
          <Chip>card v{card.card_version}</Chip>
          <Reviewed card={card} />
        </div>
        <p className="mt-3 font-display text-xl leading-snug text-ink">
          <V v={card.relation} />
        </p>
        <p className="mt-2 text-xs text-ink-3">{card.note}</p>
      </div>
      <div className="px-5 pb-3">
        <KV
          rows={[
            ["Claim class", card.claim_class === NS ? <V v={NS} /> : <Code>{card.claim_class}</Code>],
            ["Security notion", <V v={card.security.notion} />],
            ["Verifier", <V v={card.security.verifier} />],
            ["Security level", <V v={card.security.level} />],
            ["Model", <><V v={card.security.assumption} />, adversary <V v={card.security.adversary} /></>],
            ["Setup", <V v={card.security.setup} />],
            ["Zero knowledge", <>claimed <V v={card.zero_knowledge.claimed} />; hidden: <V v={card.zero_knowledge.hidden} />; not hidden: <V v={card.zero_knowledge.not_hidden} />; status <V v={card.zero_knowledge.status} /></>],
            ["Coverage", <>phase <V v={card.coverage.phase} />, unit <V v={card.coverage.unit} />; tokens covered: <V v={card.coverage.tokens_covered} />; operations: <V v={card.coverage.operations} />; policy: <V v={card.coverage.policy} /></>],
            ["Binding", <V v={card.binding} />],
            ["Assumptions", <List items={card.assumptions} />],
            ["Residual", <List items={card.residual} />],
            ["Availability", <V v={card.availability} />],
            ["Forbidden flags", card.forbidden_flags.length ? <span className="flex flex-wrap gap-1">{card.forbidden_flags.map((f) => <Code key={f}>{f}</Code>)}</span> : "none listed"],
            ["Upstream pin", system.upstream ? <a className="link num text-xs" href={`https://github.com/${system.upstream.repo}/tree/${system.upstream.commit}`}>{system.upstream.repo}@{system.upstream.commit}</a> : "none"],
            ["Reviewed by", <Reviewed card={card} />],
          ]}
        />
      </div>
    </Panel>
  );
}

const List = ({ items }: { items: string[] }) =>
  items.length === 1 ? <V v={items[0]} /> : <ul className="list-disc space-y-1 pl-4">{items.map((i) => <li key={i}><V v={i} /></li>)}</ul>;

/** The four fields a division table shows first (RFC-0009 S1). */
export function ClaimSummary({ card }: { card: ClaimCard | undefined }) {
  if (!card) return <p className="text-xs text-ink-3">Reference row: runs the model without proving, no proof claim (RFC-0015).</p>;
  return (
    <dl className="max-w-72 space-y-1 text-xs leading-snug">
      <div><Reviewed card={card} /></div>
      {([["relation", card.relation], ["security.notion", card.security.notion], ["coverage", `${card.coverage.phase}, ${card.coverage.unit}`], ["residual", card.residual.join("; ")]] as const).map(([k, v]) => (
        <div key={k}>
          <dt className="inline font-medium text-ink-3">{k}: </dt>
          <dd className="inline text-ink-2"><V v={v} /></dd>
        </div>
      ))}
    </dl>
  );
}
