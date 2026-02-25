"use client";

import { use, useMemo, useState } from "react";
import { Card, CardHeader } from "../../../components/ui/card";
import { MetricTile } from "../../../components/ui/metric-tile";
import { MetricSwitch } from "../../../components/ui/metric-switch";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../../components/ui/state-panels";
import { useApi } from "../../../lib/use-api";
import { MetricBarChart } from "../../../components/charts/metric-bar-chart";

export const runtime = "edge";

const modes = [
  { value: "box", label: "Boxscore" },
  { value: "fatigue", label: "Fatigue" },
  { value: "momentum", label: "Momentum" },
];

export default function GameDetailPage({ params }) {
  const resolvedParams = use(params);
  const [mode, setMode] = useState("box");
  const gameId = decodeURIComponent(resolvedParams.id);
  const gameData = useApi(`/games/${encodeURIComponent(gameId)}`);
  const fatigueData = useApi(`/games/${encodeURIComponent(gameId)}/fatigue-flags`);
  const momentumData = useApi(`/games/${encodeURIComponent(gameId)}/momentum`);

  if (gameData.loading) return <LoadingPanel text="Loading game detail..." />;
  if (gameData.error) return <ErrorPanel error={gameData.error} />;
  if (!gameData.data?.game) return <EmptyPanel title="Game not found" description="No detail available for this game id." />;

  const game = gameData.data.game;
  const boxscore = gameData.data.boxscore ?? [];

  const boxChartData = useMemo(
    () =>
      boxscore.map((line) => ({
        player: line.player_id,
        pts: Number(line.pts ?? 0),
        ast: Number(line.ast ?? 0),
        reb: Number(line.reb ?? 0),
      })),
    [boxscore]
  );

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title={`Game ${game.game_id}`}
          subtitle={`${game.game_date} • ${game.home_team_id} vs ${game.away_team_id}`}
          right={<MetricSwitch options={modes} value={mode} onChange={setMode} />}
        />
        <p className="mb-3 text-sm text-slate-300">
          Follow this matchup with three views: traditional production, fatigue pressure, and momentum swings.
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          <MetricTile label="Home" value={game.home_team_id} hint={`Score ${game.home_score ?? "-"}`} />
          <MetricTile label="Away" value={game.away_team_id} hint={`Score ${game.away_score ?? "-"}`} />
          <MetricTile label="Venue" value={game.venue ?? "Unknown"} />
          <MetricTile label="Mode" value={mode.toUpperCase()} />
        </div>
      </Card>

      {mode === "box" ? (
        <Card>
          <CardHeader title="Boxscore View" subtitle="Points, assists, and rebounds by player line." />
          <MetricBarChart
            data={boxChartData}
            xKey="player"
            bars={[
              { key: "pts", color: "#5ba0ff" },
              { key: "ast", color: "#f39237" },
              { key: "reb", color: "#87bbff" },
            ]}
          />
        </Card>
      ) : null}

      {mode === "fatigue" ? (
        <>
          {fatigueData.loading ? <LoadingPanel text="Loading fatigue metrics..." /> : null}
          {fatigueData.error ? <ErrorPanel error={fatigueData.error} /> : null}
          {fatigueData.data ? (
            <Card>
              <CardHeader title="Fatigue Flags" subtitle="Rest and travel pressure indicators." />
              <div className="grid gap-3 md:grid-cols-4">
                <MetricTile label="Home Fatigue" value={Number(fatigueData.data.home_fatigue_score ?? 0).toFixed(2)} />
                <MetricTile label="Away Fatigue" value={Number(fatigueData.data.away_fatigue_score ?? 0).toFixed(2)} />
                <MetricTile label="Rest Disadvantage" value={fatigueData.data.rest_disadvantage_flag ? "Yes" : "No"} />
                <MetricTile label="Travel Disadvantage" value={fatigueData.data.travel_disadvantage_flag ? "Yes" : "No"} />
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {mode === "momentum" ? (
        <>
          {momentumData.loading ? <LoadingPanel text="Loading momentum metrics..." /> : null}
          {momentumData.error ? <ErrorPanel error={momentumData.error} /> : null}
          {momentumData.data ? (
            <Card>
              <CardHeader title="Momentum and Clutch" subtitle="Run strength and clutch net swings." />
              <div className="grid gap-3 md:grid-cols-4">
                <MetricTile label="Best Run Team" value={momentumData.data.best_run_team_id ?? "-"} />
                <MetricTile label="Best Run Points" value={momentumData.data.best_run_points ?? 0} />
                <MetricTile label="Swing Index" value={Number(momentumData.data.swing_index ?? 0).toFixed(2)} />
                <MetricTile label="Clutch Possessions" value={momentumData.data.clutch_possessions ?? 0} />
              </div>
            </Card>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
