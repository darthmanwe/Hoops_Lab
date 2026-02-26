"use client";

import { use, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardHeader } from "../../../components/ui/card";
import { MetricTile } from "../../../components/ui/metric-tile";
import { MetricSwitch } from "../../../components/ui/metric-switch";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../../components/ui/state-panels";
import { useApi } from "../../../lib/use-api";
import { MetricLineChart } from "../../../components/charts/metric-line-chart";
import { EntitySearchInput } from "../../../components/filters/entity-search-input";
import { Button } from "../../../components/ui/button";
import { SEASON_OPTIONS, seasonLabel } from "../../../lib/seasons";

export const runtime = "edge";

const modes = [
  { value: "gravity", label: "Gravity" },
  { value: "fatigue", label: "Fatigue" },
  { value: "style", label: "Play Style" },
  { value: "shots", label: "Shot Profile" },
  { value: "lineups", label: "Lineup Snapshots" },
];

export default function TeamPage({ params, searchParams }) {
  const router = useRouter();
  const resolvedParams = use(params);
  const resolvedSearchParams = use(searchParams);
  const [mode, setMode] = useState("gravity");
  const teamId = decodeURIComponent(resolvedParams.id);
  const [season, setSeason] = useState(resolvedSearchParams?.season ?? "NBA_2025");
  const [seasonInput, setSeasonInput] = useState(resolvedSearchParams?.season ?? "NBA_2025");
  const [teamInput, setTeamInput] = useState(teamId);

  const teamData = useApi(`/teams/${encodeURIComponent(teamId)}?season=${encodeURIComponent(season)}`);
  const fatigueData = useApi(`/teams/${encodeURIComponent(teamId)}/fatigue?season=${encodeURIComponent(season)}`);
  const shotData = useApi(`/teams/${encodeURIComponent(teamId)}/shot-profile?season=${encodeURIComponent(season)}`);
  const styleData = useApi(`/teams/${encodeURIComponent(teamId)}/play-style?season=${encodeURIComponent(season)}`);
  const lineupData = useApi(`/teams/${encodeURIComponent(teamId)}/lineup-impact/snapshots?season=${encodeURIComponent(season)}`);

  if (teamData.loading) return <LoadingPanel text="Loading team dashboard..." />;
  if (teamData.error) return <ErrorPanel error={teamData.error} />;
  if (!teamData.data?.team) return <EmptyPanel title="Team not found" description="Try another team id." />;

  const team = teamData.data.team;
  const gravity = teamData.data.gravity ?? {};
  const fatigue = fatigueData.data ?? {};
  const shot = shotData.data ?? {};
  const style = styleData.data ?? {};
  const snapshots = lineupData.data?.results ?? [];

  const styleChartData = useMemo(
    () => [
      { phase: "Transition", rating: Number(style.transition_off_rating ?? 0), rate: Number(style.transition_poss_rate ?? 0) * 100 },
      { phase: "Set Play", rating: Number(style.set_play_off_rating ?? 0), rate: Number(style.set_play_poss_rate ?? 0) * 100 },
    ],
    [style]
  );

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title={team.name}
          subtitle={`${team.team_id} • ${team.league_id} • ${seasonLabel(season)}`}
          right={<MetricSwitch options={modes} value={mode} onChange={setMode} />}
        />
        <p className="mb-3 text-sm text-slate-300">
          Switch tabs to understand how this team creates offense, handles travel fatigue, and what lineup combinations project best.
        </p>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <EntitySearchInput
            value={teamInput}
            onChange={setTeamInput}
            placeholder="Search team by name or ID"
            type="team"
          />
          <select
            value={seasonInput}
            onChange={(e) => setSeasonInput(e.target.value)}
            className="w-full rounded-lg border border-white/15 bg-black/25 px-3 py-2 text-sm text-slate-100 outline-none focus:border-neon-400"
          >
            {SEASON_OPTIONS.map((option) => (
              <option key={option.value} value={option.value} className="bg-ink-900 text-slate-100">
                {option.label}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            onClick={() => {
              const nextSeason = seasonInput.trim();
              setSeason(nextSeason);
              router.replace(`/teams/${encodeURIComponent(teamInput.trim() || teamId)}?season=${encodeURIComponent(nextSeason)}`);
            }}
          >
            Open Team
          </Button>
        </div>
      </Card>

      {mode === "gravity" ? (
        <Card>
          <CardHeader title="Gravity Effect" subtitle="Team-level gravity and adjusted offense outcomes." />
          <div className="grid gap-3 md:grid-cols-4">
            <MetricTile label="Gravity Load" value={Number(gravity.team_gravity_load ?? 0).toFixed(2)} />
            <MetricTile label="Adj Offense" value={Number(gravity.gravity_adjusted_offense ?? 0).toFixed(2)} />
            <MetricTile label="Spillover" value={Number(gravity.gravity_spillover ?? 0).toFixed(2)} />
            <MetricTile label="Model" value={gravity.model_version ?? "n/a"} />
          </div>
        </Card>
      ) : null}

      {mode === "fatigue" ? (
        <Card>
          <CardHeader title="Fatigue and Travel" subtitle="Rest disadvantage and mileage effects." />
          {fatigueData.loading ? <LoadingPanel text="Loading fatigue..." /> : null}
          {fatigueData.error ? <ErrorPanel error={fatigueData.error} /> : null}
          {!fatigueData.loading && !fatigueData.error ? (
            <div className="grid gap-3 md:grid-cols-4">
              <MetricTile label="Fatigue Score" value={Number(fatigue.fatigue_score ?? 0).toFixed(2)} />
              <MetricTile label="Rest Disadvantage Games" value={fatigue.rest_disadvantage_games ?? 0} />
              <MetricTile label="Travel (km)" value={fatigue.travel_km ?? 0} />
              <MetricTile label="Model" value={fatigue.model_version ?? "n/a"} />
            </div>
          ) : null}
        </Card>
      ) : null}

      {mode === "style" ? (
        <Card>
          <CardHeader title="Transition vs Set Play" subtitle="Possession split and offensive rating comparison." />
          {styleData.loading ? <LoadingPanel text="Loading play style..." /> : null}
          {styleData.error ? <ErrorPanel error={styleData.error} /> : null}
          {!styleData.loading && !styleData.error ? (
            <MetricLineChart
              data={styleChartData}
              xKey="phase"
              lines={[
                { key: "rating", color: "#5ba0ff" },
                { key: "rate", color: "#f39237" },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {mode === "shots" ? (
        <Card>
          <CardHeader title="Team Shot Profile" subtitle="Rate and efficiency by zone." />
          {shotData.loading ? <LoadingPanel text="Loading shot profile..." /> : null}
          {shotData.error ? <ErrorPanel error={shotData.error} /> : null}
          {!shotData.loading && !shotData.error ? (
            <div className="grid gap-3 md:grid-cols-4">
              <MetricTile label="Rim Rate" value={Number(shot.rim_rate ?? 0).toFixed(2)} />
              <MetricTile label="Mid Rate" value={Number(shot.mid_rate ?? 0).toFixed(2)} />
              <MetricTile label="3PT (Corner+Above)" value={Number((shot.corner3_rate ?? 0) + (shot.abv3_rate ?? 0)).toFixed(2)} />
              <MetricTile label="3PT FG%" value={Number(shot.three_fg_pct ?? 0).toFixed(2)} />
            </div>
          ) : null}
        </Card>
      ) : null}

      {mode === "lineups" ? (
        <Card>
          <CardHeader title="Lineup Snapshots" subtitle="Stored five-player impact snapshots." />
          {lineupData.loading ? <LoadingPanel text="Loading lineup snapshots..." /> : null}
          {lineupData.error ? <ErrorPanel error={lineupData.error} /> : null}
          {!lineupData.loading && !lineupData.error && snapshots.length === 0 ? (
            <EmptyPanel title="No snapshots available" description="Build lineup candidates in Lineup Lab." />
          ) : null}
          {!lineupData.loading && !lineupData.error && snapshots.length > 0 ? (
            <div className="space-y-2">
              {snapshots.map((row) => (
                <div key={row.lineup_key} className="rounded-lg border border-white/10 bg-black/25 p-3">
                  <p className="text-sm font-semibold text-white">{row.lineup_key}</p>
                  <p className="mt-1 text-xs text-slate-300">Players: {row.player_ids_json}</p>
                  <div className="mt-2 grid gap-2 md:grid-cols-3">
                    <MetricTile label="Offense Projection" value={Number(row.offense_projection ?? 0).toFixed(2)} />
                    <MetricTile label="Transition Fit" value={Number(row.transition_fit ?? 0).toFixed(2)} />
                    <MetricTile label="Set Play Fit" value={Number(row.set_play_fit ?? 0).toFixed(2)} />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}
