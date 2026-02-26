"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardHeader } from "../../components/ui/card";
import { SeasonLeagueControls } from "../../components/filters/season-league-controls";
import { SearchInput } from "../../components/filters/search-input";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { useApi } from "../../lib/use-api";
import { DEFAULT_SEASON_BY_LEAGUE, seasonLabel } from "../../lib/seasons";

function formatGameDate(gameDate) {
  if (!gameDate) return "-";
  const date = new Date(gameDate);
  if (Number.isNaN(date.getTime())) return String(gameDate);
  return date.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
}

function gameTitle(game) {
  const home = game.home_team_name ?? game.home_team_abbrev ?? game.home_team_id;
  const away = game.away_team_name ?? game.away_team_abbrev ?? game.away_team_id;
  return `${home} vs ${away}`;
}

function GamesPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [league, setLeague] = useState(searchParams.get("league")?.toUpperCase() === "EL" ? "EL" : "NBA");
  const [season, setSeason] = useState(
    searchParams.get("season") ?? DEFAULT_SEASON_BY_LEAGUE[searchParams.get("league")?.toUpperCase() === "EL" ? "EL" : "NBA"]
  );
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const { data, loading, error } = useApi(
    `/games?league=${encodeURIComponent(league)}&season=${encodeURIComponent(season)}&limit=50`
  );
  const games = data?.games ?? [];

  useEffect(() => {
    const next = new URLSearchParams();
    next.set("league", league);
    next.set("season", season);
    if (query.trim()) next.set("q", query.trim());
    router.replace(`/games?${next.toString()}`);
  }, [league, season, query, router]);

  const filtered = useMemo(() => {
    if (!query) return games;
    const q = query.toLowerCase();
    return games.filter(
      (g) =>
        String(g.game_id).toLowerCase().includes(q) ||
        String(g.home_team_name ?? "").toLowerCase().includes(q) ||
        String(g.away_team_name ?? "").toLowerCase().includes(q) ||
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
          <SearchInput value={query} onChange={setQuery} placeholder="Search by game, team name, or team ID..." className="md:w-80" />
        </div>
      </Card>

      {loading ? <LoadingPanel text="Loading games..." /> : null}
      {error ? <ErrorPanel error={error} /> : null}
      {!loading && !error && filtered.length === 0 ? (
        <EmptyPanel title="No games found" description="Try another league/season or adjust your filter." />
      ) : null}

      {!loading && !error && filtered.length > 0 ? (
        <Card>
          <CardHeader title={`${filtered.length} Games`} subtitle={`Season: ${seasonLabel(season)}`} />
          <div className="grid gap-3 md:grid-cols-2">
            {filtered.map((game) => (
              <a
                key={game.game_id}
                href={`/games/${encodeURIComponent(game.game_id)}`}
                className="rounded-xl border border-white/10 bg-black/20 p-3 transition hover:bg-black/35"
              >
                <p className="text-sm font-semibold text-white">{gameTitle(game)}</p>
                <p className="mt-1 text-xs text-slate-300">{formatGameDate(game.game_date)} · {game.game_id}</p>
                <p className="mt-2 text-sm text-neon-300">{game.home_team_abbrev ?? game.home_team_id} <span className="text-slate-400">vs</span> {game.away_team_abbrev ?? game.away_team_id}</p>
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

export default function GamesPage() {
  return (
    <Suspense fallback={<LoadingPanel text="Loading games..." />}>
      <GamesPageContent />
    </Suspense>
  );
}
