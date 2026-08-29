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
  { href: "/projections", label: "Who hasn't moved" },
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
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-fg focus:px-3 focus:py-2 focus:text-bg"
        >
          Skip to content
        </a>

        <div className="mx-auto min-h-screen max-w-[1180px] px-4 pb-16 pt-6 md:px-8">
          <header className="glass mb-6 p-4 md:p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-accent">
              Cross-league translation modelling
            </p>
            <h1 className="mt-1 text-2xl font-bold text-fg md:text-3xl">HoopsLab</h1>
            <p className="mt-1 max-w-2xl text-sm text-fg-muted">
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
                  className="rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm text-fg transition hover:bg-surface-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* A plain GET form, which is the whole design.

                The API has had diacritic-insensitive search since phase 3 and
                nothing on the site could reach it: there was no `input` or
                `form` anywhere in this app, so the only route to a player page
                was following a link out of a table. Anyone arriving to look up
                a specific player could not.

                No client JavaScript. It submits without it, it is keyboard
                accessible by construction, and it keeps every page in this app
                a server component — which is what makes the whole thing
                testable without waiting on hydration. */}
            <form action="/players" method="get" className="mt-3 flex gap-2" role="search">
              <label htmlFor="player-search" className="sr-only">
                Search players by name
              </label>
              <input
                id="player-search"
                type="search"
                name="q"
                placeholder="Find a player…"
                autoComplete="off"
                className="w-full max-w-xs rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              />
              <button
                type="submit"
                className="rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm text-fg transition hover:bg-surface-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Search
              </button>
            </form>
          </header>

          <main id="main">{children}</main>

          <footer className="mt-10 text-xs text-fg-subtle">
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
