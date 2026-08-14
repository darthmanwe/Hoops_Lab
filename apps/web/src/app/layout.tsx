import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "HoopsLab — cross-league translation",
  description:
    "Estimating how basketball production translates between the EuroLeague and the NBA, " +
    "with the sample size, the selection bias and the error bars stated up front.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/translation", label: "Translation" },
  { href: "/model", label: "Model & calibration" },
  { href: "/archetypes", label: "Archetypes" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Keyboard users should not have to tab the whole nav on every page. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-slate-900"
        >
          Skip to content
        </a>

        <div className="mx-auto min-h-screen max-w-[1180px] px-4 pb-16 pt-6 md:px-8">
          <header className="glass mb-6 p-4 md:p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-court-300">
              Cross-league translation modelling
            </p>
            <h1 className="mt-1 text-2xl font-bold text-white md:text-3xl">HoopsLab</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-300">
              How basketball production travels between the EuroLeague, the NBA and the G League —
              with the sample size, the selection bias and the width of the error bars stated up
              front.
            </p>

            {/* next/link, not a raw anchor: the previous nav forced a full page
                reload on every click and lost keyboard focus with it. */}
            <nav aria-label="Primary" className="mt-4 flex flex-wrap gap-2">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-slate-100 transition hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-300"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </header>

          <main id="main">{children}</main>

          <footer className="mt-10 text-xs text-slate-400">
            <p>
              Every number here is produced by a fitted model over committed data, and carries the
              model version that produced it. Metrics the models do not beat a trivial baseline on
              are labelled as such rather than omitted.
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
