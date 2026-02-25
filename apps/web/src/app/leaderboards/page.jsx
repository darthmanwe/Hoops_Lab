"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader } from "../../components/ui/card";
import { MetricTile } from "../../components/ui/metric-tile";
import { MetricSwitch } from "../../components/ui/metric-switch";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { SeasonLeagueControls } from "../../components/filters/season-league-controls";
import { useApi } from "../../lib/use-api";
import { MetricBarChart } from "../../components/charts/metric-bar-chart";

const metricModes = [
  { value: "gravity", label: "Gravity" },
  { value: "clutch", label: "Clutch" },
  { value: "translation", label: "Translation" },
];

export default function LeaderboardsPage() {
  const [league, setLeague] = useState("NBA");
  const [season, setSeason] = useState("NBA_2025");
  const [metric, setMetric] = useState("gravity");
  const [sortBy, setSortBy] = useState("score_desc");
  const endpoint = `/leaderboards/${metric}?season=${encodeURIComponent(season)}`;
  const { data, loading, error } = useApi(endpoint);
  const results = data?.results ?? [];

  const scoreKey = useMemo(() => {
    if (metric === "gravity") return "gravity_overall";
    if (metric === "clutch") return "clutch_impact";
    return "translation_score";
  }, [metric]);

  const sortedResults = useMemo(() => {
    const copy = [...results];
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
  }, [results, scoreKey, sortBy]);

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
          right={
            <MetricSwitch
              options={metricModes}
              value={metric}
              onChange={setMetric}
            />
          }
        />
        <SeasonLeagueControls
          league={league}
          setLeague={setLeague}
          season={season}
          setSeason={setSeason}
        />
      </Card>

      {loading ? <LoadingPanel /> : null}
      {error ? <ErrorPanel error={error} /> : null}

      {!loading && !error && results.length === 0 ? (
        <EmptyPanel
          title="No leaderboard data"
          description="Try a different season or metric mode."
        />
      ) : null}

      {!loading && !error && results.length > 0 ? (
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
