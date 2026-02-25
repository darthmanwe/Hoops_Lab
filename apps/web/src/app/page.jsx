import { API_BASE } from "../lib/api";
import { Card, CardHeader } from "../components/ui/card";
import { MetricTile } from "../components/ui/metric-tile";

export default function HomePage() {
  const modules = [
    {
      href: "/players/NBA_201939?season=NBA_2025",
      title: "Player Studio",
      text: "See who plays most like your favorite stars, plus shot zones and cross-league translation ratings.",
    },
    {
      href: "/teams/NBA_1610612738?season=NBA_2025",
      title: "Team Lab",
      text: "Explore gravity impact, fatigue trends, style of play, and stored lineup snapshots.",
    },
    {
      href: "/games",
      title: "Game Center",
      text: "Track game flow with boxscore leaders, momentum swings, and fatigue context.",
    },
    {
      href: "/leaderboards?season=NBA_2025",
      title: "Leaderboards",
      text: "Rankings across gravity, clutch, and translation with interactive sorting.",
    },
    {
      href: "/compare",
      title: "Compare Workbench",
      text: "Pick two players, switch comparison presets, and visualize the differences instantly.",
    },
    {
      href: "/lineup-lab",
      title: "Lineup Lab",
      text: "Build five-player groups and test gravity, spacing, transition, and set-play fit.",
    },
  ];

  return (
    <section className="space-y-6">
      <Card className="p-5 md:p-6">
        <CardHeader
          title="Welcome to HoopsLab"
          subtitle="A fan-friendly analytics hub where every module answers a different basketball question."
          right={<span className="rounded-full bg-court-500/20 px-3 py-1 text-xs font-semibold text-court-300">Live API</span>}
        />
        <div className="grid gap-3 md:grid-cols-4">
          <MetricTile label="Modules" value="6+" hint="Player, Team, Game, Compare, Leaderboards, Lineups" />
          <MetricTile label="Leagues" value="NBA + EL" hint="Cross-league translation supported" />
          <MetricTile label="Style Lens" value="<=8s vs >=8s" hint="Transition versus set-play analysis" />
          <MetricTile label="API" value="Connected" hint={API_BASE.replace("https://", "").replace("http://", "")} />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="How to Use the Platform"
          subtitle="Start with any module below. Every page has visual controls, metric switching, and clear basketball context."
        />
        <div className="grid gap-3 md:grid-cols-3">
          <MetricTile label="For Fans" value="Story First" hint="Momentum, runs, clutch moments, and style matchups." />
          <MetricTile label="For Analysis" value="Metric Switches" hint="Toggle lenses without leaving your page." />
          <MetricTile label="For Lineups" value="5-Player Builder" hint="Evaluate chemistry and fit in one click." />
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {modules.map((module) => (
          <a key={module.href} href={module.href} className="glass block p-5 transition hover:translate-y-[-2px] hover:bg-white/10">
            <p className="text-base font-semibold text-white">{module.title}</p>
            <p className="mt-2 text-sm text-slate-300">{module.text}</p>
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-neon-300">Open Module</p>
          </a>
        ))}
      </div>
    </section>
  );
}
