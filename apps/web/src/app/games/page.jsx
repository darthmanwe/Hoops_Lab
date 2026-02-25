"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader } from "../../components/ui/card";
import { SeasonLeagueControls } from "../../components/filters/season-league-controls";
import { SearchInput } from "../../components/filters/search-input";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { useApi } from "../../lib/use-api";

export default function GamesPage() {
  const [league, setLeague] = useState("NBA");
  const [season, setSeason] = useState("NBA_2025");
  const [query, setQuery] = useState("");
  const { data, loading, error } = useApi(
    `/games?league=${encodeURIComponent(league)}&season=${encodeURIComponent(season)}&limit=50`
  );
  const games = data?.games ?? [];

  const filtered = useMemo(() => {
    if (!query) return games;
    const q = query.toLowerCase();
    return games.filter(
      (g) =>
        String(g.game_id).toLowerCase().includes(q) ||
        String(g.home_team_id).toLowerCase().includes(q) ||
        String(g.away_team_id).toLowerCase().includes(q)
    );
  }, [games, query]);

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader title="Games Center" subtitle="Find a game and open its full story: box score leaders, momentum swings, and fatigue context." />
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <SeasonLeagueControls
            league={league}
            setLeague={setLeague}
            season={season}
            setSeason={setSeason}
          />
          <SearchInput value={query} onChange={setQuery} placeholder="Search by game ID or team ID..." className="md:w-80" />
        </div>
      </Card>

      {loading ? <LoadingPanel text="Loading games..." /> : null}
      {error ? <ErrorPanel error={error} /> : null}
      {!loading && !error && filtered.length === 0 ? (
        <EmptyPanel title="No games found" description="Try another league/season or adjust your filter." />
      ) : null}

      {!loading && !error && filtered.length > 0 ? (
        <Card>
          <CardHeader title={`${filtered.length} Games`} subtitle="Open any game for detailed breakdowns." />
          <div className="grid gap-3 md:grid-cols-2">
            {filtered.map((game) => (
              <a
                key={game.game_id}
                href={`/games/${encodeURIComponent(game.game_id)}`}
                className="rounded-xl border border-white/10 bg-black/20 p-3 transition hover:bg-black/35"
              >
                <p className="text-sm font-semibold text-white">{game.game_id}</p>
                <p className="mt-1 text-xs text-slate-300">{game.game_date}</p>
                <p className="mt-2 text-sm text-neon-300">
                  {game.home_team_id} <span className="text-slate-400">vs</span> {game.away_team_id}
                </p>
                <p className="mt-1 text-xs text-slate-300">
                  {game.home_score ?? "-"} - {game.away_score ?? "-"}
                </p>
              </a>
            ))}
          </div>
        </Card>
      ) : null}
    </section>
  );
}
