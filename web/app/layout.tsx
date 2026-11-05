import type { Metadata } from "next";
import Link from "next/link";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";
import { Nav, type NavGroup } from "@/components/nav";
import { data } from "@/lib/release";
import { REPO } from "@/lib/repo";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono" });
const display = Newsreader({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-newsreader" });

export const metadata: Metadata = {
  title: { default: "Inference Proofs", template: "%s · Inference Proofs" },
  description: "An open, neutral benchmark for provable inference: same models, same reference hardware, same timing rules, and a claim card per proof.",
  // Mock numbers and release candidates must never be indexed as results.
  robots: data.release.status === "published" ? undefined : { index: false, follow: false },
};

const groups: NavGroup[] = [
  { items: [{ href: "/", label: "Overview" }, { href: `/releases/${data.release.id}/`, label: "Release", hint: data.release.id }, { href: "/divisions/native/", label: "Native division" }] },
  { title: "Systems", items: data.systems.map((s) => ({ href: `/systems/${s.name}/`, label: s.name, hint: s.kind === "reference" ? "ref" : undefined })) },
  { title: "Workloads", items: data.workloads.map((w) => ({ href: `/workloads/${w.id}/`, label: w.id })) },
  { title: "Evidence", items: [{ href: "/controls/", label: "Negative controls" }, { href: "/targets/", label: "Targets" }, { href: "/methodology/", label: "Methodology" }, { href: "/sponsors/", label: "Sponsors and conflicts" }] },
];

/** On every page: mock data, or a release candidate under review (RFC-0009 §Review window). */
function Banner() {
  const r = data.release;
  if (r.status === "published") return null;
  if (r.status === "mock")
    return (
      <div className="hatch border-b border-mock/30 bg-mock-soft/40 px-4 py-2 text-center text-[13px] text-ink">
        <strong className="font-semibold">Mock data.</strong> Run values, controls, targets and reproductions on this preview are invented for layout. Claim-card text, upstream figures, the reference price and the RFC list come from the repository.
      </div>
    );
  const window = r.review_window ? `review window ${r.review_window.opens} to ${r.review_window.closes}, freeze date ${r.freeze_date}` : `no review window recorded yet: releases/${r.id}/release.yaml does not exist`;
  return (
    <div className="hatch border-b border-mock/30 bg-mock-soft/40 px-4 py-2 text-center text-[13px] text-ink">
      <strong className="font-semibold">Release candidate {r.id}, under review; not a published release.</strong> Built from a draft {r.index_file} before the review window closes ({window}). System maintainers are reviewing their rows, controls and claim cards, and numbers may change before freeze (RFC-0009 §Review window).
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <svg viewBox="0 0 24 24" className="size-6 text-accent" aria-hidden>
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="12" cy="12" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
        <circle cx="12" cy="12" r="1.75" fill="currentColor" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight">Inference Proofs</span>
    </Link>
  );
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} ${display.variable}`}>
      <body className="min-h-dvh font-sans">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
          Skip to content
        </a>
        <Banner />
        <div className="lg:grid lg:grid-cols-[16rem_1fr]">
          <aside className="hidden border-r border-line bg-sunken/50 lg:block">
            <div className="sticky top-0 flex h-dvh flex-col overflow-y-auto px-3 py-5">
              <div className="mb-7 px-2.5"><Brand /></div>
              <Nav groups={groups} />
              <p className="mt-auto px-2.5 pt-8 text-xs leading-relaxed text-ink-3">
                Measures provers. Does not build, rank or certify them. <a className="link" href={REPO}>Source</a>
              </p>
            </div>
          </aside>
          <details className="group border-b border-line bg-sunken/50 lg:hidden">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3">
              <Brand />
              <span className="text-sm text-ink-2 group-open:hidden">Menu</span>
              <span className="hidden text-sm text-ink-2 group-open:inline">Close</span>
            </summary>
            <div className="px-2 pb-5"><Nav groups={groups} /></div>
          </details>
          <main id="main" className="min-w-0 px-4 py-10 sm:px-8 lg:px-12 xl:px-16">
            <div className="mx-auto max-w-6xl">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
