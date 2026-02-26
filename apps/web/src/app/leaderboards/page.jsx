"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardHeader } from "../../components/ui/card";
import { MetricTile } from "../../components/ui/metric-tile";
import { MetricSwitch } from "../../components/ui/metric-switch";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { SeasonLeagueControls } from "../../components/filters/season-league-controls";
import { SearchInput } from "../../components/filters/search-input";
import { useApi } from "../../lib/use-api";
import { MetricBarChart } from "../../components/charts/metric-bar-chart";
import { DEFAULT_SEASON_BY_LEAGUE } from "../../lib/seasons";

const metricModes = [
  { value: "gravity", label: "Gravity" },
  { value: "clutch", label: "Clutch" },
  { value: "translation", label: "Translation" },
];

function LeaderboardsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialLeague = searchParams.get("league")?.toUpperCase() === "EL" ? "EL" : "NBA";
  const [league, setLeague] = useState(initialLeague);
  const [season, setSeason] = useState(searchParams.get("season") ?? DEFAULT_SEASON_BY_LEAGUE[initialLeague]);
  const [metric, setMetric] = useState(searchParams.get("metric") ?? "gravity");
  const [sortBy, setSortBy] = useState(searchParams.get("sort") ?? "score_desc");
  const [playerQuery, setPlayerQuery] = useState(searchParams.get("player") ?? "");
  const endpoint = `/leaderboards/${metric}?season=${encodeURIComponent(season)}`;
  const { data, loading, error } = useApi(endpoint);
  const results = data?.results ?? [];

  useEffect(() => {
    const next = new URLSearchParams();
    next.set("league", league);
    next.set("season", season);
    next.set("metric", metric);
    next.set("sort", sortBy);
    if (playerQuery.trim()) next.set("player", playerQuery.trim());
    router.replace(`/leaderboards?${next.toString()}`);
  }, [league, season, metric, sortBy, playerQuery, router]);

  const scoreKey = useMemo(() => {
    if (metric === "gravity") return "gravity_overall";
    if (metric === "clutch") return "clutch_impact";
    return "translation_score";
  }, [metric]);

  const filteredResults = useMemo(() => {
    if (!playerQuery.trim()) return results;
    const q = playerQuery.trim().toLowerCase();
    return results.filter((row) => {
      return (
        String(row.name ?? "").toLowerCase().includes(q) ||
        String(row.player_id ?? "").toLowerCase().includes(q)
      );
    });
  }, [results, playerQuery]);

  const sortedResults = useMemo(() => {
    const copy = [...filteredResults];
    if (sortBy === "name_asc") {
      copy.sort((a, b) => String(a.name ?? "").localeCompare(String(b.name ?? "")));
      return copy;
    }
    if (sortBy === "name_desc") {
      copy.sort((a, b) => String(b.name ?? "").localeCompare(String(a.name ?? "")));
      return copy;
    }
    if (sortBy === "score_asc") {
      copy.sort((a, b) => Number(a[scoreKey] ?? 0) - Number(b[scoreKey] ?? 0));
      return copy;
    }
    copy.sort((a, b) => Number(b[scoreKey] ?? 0) - Number(a[scoreKey] ?? 0));
    return copy;
  }, [filteredResults, scoreKey, sortBy]);

  const chartData = sortedResults.slice(0, 10).map((r) => ({
    name: r.name,
    score: Number(r[scoreKey] ?? 0),
  }));

  const top = sortedResults[0];

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title="Leaderboards"
          subtitle="Rank players by selected advanced lens and switch metrics instantly."
          right={<MetricSwitch options={metricModes} value={metric} onChange={setMetric} />}
        />
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <SeasonLeagueControls
            league={league}
            setLeague={setLeague}
            season={season}
            setSeason={setSeason}
          />
          <div className="flex w-full flex-col gap-2 md:w-[520px] md:flex-row">
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="w-full rounded-lg border border-white/15 bg-black/25 px-3 py-2 text-sm text-slate-100 outline-none focus:border-neon-400 md:w-48"
            >
              {metricModes.map((mode) => (
                <option key={mode.value} value={mode.value} className="bg-ink-900 text-slate-100">
                  {mode.label}
                </option>
              ))}
            </select>
            <SearchInput
              value={playerQuery}
              onChange={setPlayerQuery}
              placeholder="Filter players by name or ID..."
            />
          </div>
        </div>
      </Card>

      {loading ? <LoadingPanel /> : null}
      {error ? <ErrorPanel error={error} /> : null}

      {!loading && !error && sortedResults.length === 0 ? (
        <EmptyPanel
          title="No leaderboard data"
          description="Try a different season/metric or clear player filter."
        />
      ) : null}

      {!loading && !error && sortedResults.length > 0 ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <MetricTile label="Metric Mode" value={metric.toUpperCase()} />
            <MetricTile label="League" value={league} />
            <MetricTile
              label="Top Performer"
              value={top?.name ?? "N/A"}
              hint={`${scoreKey}: ${Number(top?.[scoreKey] ?? 0).toFixed(2)}`}
            />
          </div>

          <Card>
            <CardHeader title="Top 10 Snapshot" subtitle={`Scored by ${scoreKey}`} />
            <MetricBarChart
              data={chartData}
              xKey="name"
              bars={[{ key: "score", color: "#5ba0ff" }]}
            />
          </Card>

          <Card>
            <CardHeader
              title="Top 20 Table"
              subtitle="Use sorting controls to view rankings your way."
              right={
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="rounded-md border border-white/15 bg-black/30 px-2 py-1 text-xs text-slate-100"
                >
                  <option value="score_desc">Score High to Low</option>
                  <option value="score_asc">Score Low to High</option>
                  <option value="name_asc">Name A-Z</option>
                  <option value="name_desc">Name Z-A</option>
                </select>
              }
            />
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-slate-300">
                  <tr className="border-b border-white/10">
                    <th className="px-2 py-2">Rank</th>
                    <th className="px-2 py-2">Player</th>
                    <th className="px-2 py-2">League</th>
                    <th className="px-2 py-2">{scoreKey}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.slice(0, 20).map((row, idx) => (
                    <tr key={row.player_id} className="border-b border-white/5">
                      <td className="px-2 py-2 text-slate-300">{idx + 1}</td>
                      <td className="px-2 py-2 text-white">{row.name}</td>
                      <td className="px-2 py-2 text-slate-300">{row.league_id ?? "-"}</td>
                      <td className="px-2 py-2 text-neon-300">{Number(row[scoreKey] ?? 0).toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : null}
    </section>
  );
}

export default function LeaderboardsPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <LeaderboardsPageContent />
    </Suspense>
  );
}
