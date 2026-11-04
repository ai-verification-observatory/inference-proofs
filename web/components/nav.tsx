"use client";
// The only client component: it marks the current page. Links work without JavaScript.
import Link from "next/link";
import { usePathname } from "next/navigation";

export type NavGroup = { title?: string; items: { href: string; label: string; hint?: string }[] };

export function Nav({ groups }: { groups: NavGroup[] }) {
  const path = usePathname();
  return (
    <nav aria-label="Site" className="space-y-6">
      {groups.map((g, i) => (
        <div key={i}>
          {g.title && <p className="mb-1.5 px-2.5 text-[11px] font-medium uppercase tracking-[0.14em] text-ink-3">{g.title}</p>}
          <ul className="space-y-px">
            {g.items.map((it) => {
              const h = it.href.replace(/\/$/, ""), p = path.replace(/\/$/, "");
              const on = h === "" ? p === "" : p === h || p.startsWith(`${h}/`);
              return (
                <li key={it.href}>
                  <Link
                    href={it.href}
                    aria-current={on ? "page" : undefined}
                    className={`flex items-baseline justify-between gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors ${on ? "bg-surface font-medium text-ink shadow-[inset_2px_0_0_var(--accent)]" : "text-ink-2 hover:bg-surface/70 hover:text-ink"}`}
                  >
                    <span>{it.label}</span>
                    {it.hint && <span className="num text-[11px] text-ink-3">{it.hint}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
