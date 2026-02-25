import "./globals.css";

export const metadata = {
  title: "HoopsLab",
  description: "NBA + EuroLeague Intelligence Platform"
};

export default function RootLayout({ children }) {
  const navItems = [
    { href: "/", label: "Home" },
    { href: "/players/NBA_201939?season=NBA_2025", label: "Players" },
    { href: "/teams/NBA_1610612738?season=NBA_2025", label: "Teams" },
    { href: "/games", label: "Games" },
    { href: "/leaderboards?season=NBA_2025", label: "Leaderboards" },
    { href: "/compare", label: "Compare" },
    { href: "/lineup-lab", label: "Lineup Lab" },
  ];

  return (
    <html lang="en">
      <body>
        <div className="mx-auto min-h-screen max-w-[1320px] px-4 pb-16 pt-6 md:px-8">
          <header className="glass mb-6 p-4 md:p-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-court-300">Basketball Intelligence Platform</p>
                <h1 className="mt-1 text-2xl font-bold text-white md:text-3xl">HoopsLab</h1>
                <p className="mt-1 text-sm text-slate-300">
                  Follow the story of every game with interactive NBA + EuroLeague analytics made for basketball fans.
                </p>
              </div>
              <p className="text-xs uppercase tracking-widest text-slate-400">Live tools · Compare · Lineup lab</p>
            </div>
            <nav className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
              {navItems.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-center text-sm text-slate-100 transition hover:bg-white/10"
                >
                  {item.label}
                </a>
              ))}
            </nav>
          </header>

          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
