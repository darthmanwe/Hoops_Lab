"use client";

import { use, useState } from "react";
import { Card, CardHeader } from "../../../components/ui/card";
import { MetricTile } from "../../../components/ui/metric-tile";
import { MetricSwitch } from "../../../components/ui/metric-switch";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../../components/ui/state-panels";
import { useApi } from "../../../lib/use-api";
import { MetricBarChart } from "../../../components/charts/metric-bar-chart";
import { SearchInput } from "../../../components/filters/search-input";
import { Button } from "../../../components/ui/button";

export const runtime = "edge";

const modes = [
  { value: "comps", label: "Comps" },
  { value: "shot", label: "Shot Profile" },
  { value: "translation", label: "Translation" },
];

export default function PlayerPage({ params, searchParams }) {
  const resolvedParams = use(params);
  const resolvedSearchParams = use(searchParams);
  const [mode, setMode] = useState("comps");
  const playerId = decodeURIComponent(resolvedParams.id);
  const [season, setSeason] = useState(resolvedSearchParams?.season ?? "NBA_2025");
  const [seasonInput, setSeasonInput] = useState(resolvedSearchParams?.season ?? "NBA_2025");

  const playerData = useApi(`/players/${encodeURIComponent(playerId)}?season=${encodeURIComponent(season)}`);
  const compsData = useApi(`/players/${encodeURIComponent(playerId)}/comps?season=${encodeURIComponent(season)}&k=10`);
  const shotData = useApi(`/players/${encodeURIComponent(playerId)}/shot-profile?season=${encodeURIComponent(season)}`);
  const translationData = useApi(`/players/${encodeURIComponent(playerId)}/translation?season=${encodeURIComponent(season)}`);

  if (playerData.loading) return <LoadingPanel text="Loading player profile..." />;
  if (playerData.error) return <ErrorPanel error={playerData.error} />;
  if (!playerData.data?.player) return <EmptyPanel title="Player not found" description="Try another player id." />;

  const player = playerData.data.player;
  const features = playerData.data.features ?? {};
  const shot = shotData.data ?? {};
  const translation = translationData.data ?? {};
  const comps = compsData.data?.comps ?? [];

  const shotChartData = [
    { name: "Rim", rate: Number(shot.rim_rate ?? 0) },
    { name: "Mid", rate: Number(shot.mid_rate ?? 0) },
    { name: "Corner3", rate: Number(shot.corner3_rate ?? 0) },
    { name: "Above3", rate: Number(shot.abv3_rate ?? 0) },
  ];

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title={player.name}
          subtitle={`${player.player_id} • ${player.league_id}`}
          right={<MetricSwitch options={modes} value={mode} onChange={setMode} />}
        />
        <p className="mb-3 text-sm text-slate-300">
          Use this page to understand player style: who they resemble, where they shoot from, and how well production translates across leagues.
        </p>
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center">
          <SearchInput value={seasonInput} onChange={setSeasonInput} placeholder="Season (NBA_2025 / EL_2025)" className="md:w-64" />
          <Button variant="secondary" onClick={() => setSeason(seasonInput.trim())}>
            Apply Season
          </Button>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <MetricTile label="Usage Proxy" value={Number(features.usage_proxy ?? 0).toFixed(2)} />
          <MetricTile label="TS Proxy" value={Number(features.ts_proxy ?? 0).toFixed(2)} />
          <MetricTile label="Clutch Impact" value={Number(features.clutch_impact ?? 0).toFixed(2)} />
          <MetricTile label="Season" value={season} />
        </div>
      </Card>

      {mode === "comps" ? (
        <Card>
          <CardHeader title="Closest Archetype Comps" subtitle="Most similar player styles for the selected season." />
          {compsData.loading ? <LoadingPanel text="Loading comps..." /> : null}
          {compsData.error ? <ErrorPanel error={compsData.error} /> : null}
          {!compsData.loading && !compsData.error ? (
            <div className="space-y-2">
              {comps.map((comp, index) => (
                <div key={comp.player_id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                  <p className="text-sm text-white">
                    {index + 1}. {comp.name} ({comp.league_id})
                  </p>
                  <p className="text-sm font-semibold text-neon-300">{Number(comp.score).toFixed(3)}</p>
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}

      {mode === "shot" ? (
        <Card>
          <CardHeader title="Shot Profile Explorer" subtitle="Rate distribution by zone." />
          {shotData.loading ? <LoadingPanel text="Loading shot profile..." /> : null}
          {shotData.error ? <ErrorPanel error={shotData.error} /> : null}
          {!shotData.loading && !shotData.error ? (
            <MetricBarChart data={shotChartData} xKey="name" bars={[{ key: "rate", color: "#f39237" }]} />
          ) : null}
        </Card>
      ) : null}

      {mode === "translation" ? (
        <Card>
          <CardHeader title="Translation Metrics" subtitle="Cross-league standardized equivalence panel." />
          {translationData.loading ? <LoadingPanel text="Loading translation metrics..." /> : null}
          {translationData.error ? <ErrorPanel error={translationData.error} /> : null}
          {!translationData.loading && !translationData.error ? (
            <div className="grid gap-3 md:grid-cols-4">
              <MetricTile label="Std Usage" value={Number(translation.standardized_usage ?? 0).toFixed(2)} />
              <MetricTile label="Std TS" value={Number(translation.standardized_ts ?? 0).toFixed(2)} />
              <MetricTile label="Translation Score" value={Number(translation.translation_score ?? 0).toFixed(2)} />
              <MetricTile label="NBA Eq Rating" value={Number(translation.nba_equivalent_rating ?? 0).toFixed(1)} />
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}
