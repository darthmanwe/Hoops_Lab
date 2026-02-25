"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { MetricSwitch } from "../../components/ui/metric-switch";
import { SearchInput } from "../../components/filters/search-input";
import { EntitySearchInput } from "../../components/filters/entity-search-input";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { useApi } from "../../lib/use-api";
import { MetricBarChart } from "../../components/charts/metric-bar-chart";

const presets = [
  { value: "efficiency", label: "Efficiency", keys: ["ts_proxy", "usage_proxy"] },
  { value: "creation", label: "Creation", keys: ["ast_rate_proxy", "tov_rate_proxy"] },
  { value: "rebounding", label: "Rebounding", keys: ["reb_share_proxy", "usage_proxy"] },
];

const metricLabels = {
  ts_proxy: "True Shooting Proxy",
  usage_proxy: "Usage Proxy",
  ast_rate_proxy: "Assist Rate Proxy",
  tov_rate_proxy: "Turnover Rate Proxy",
  reb_share_proxy: "Rebound Share Proxy",
};

const quickMatchups = [
  { label: "Curry vs LeBron", a: "NBA_201939", b: "NBA_2544", season: "NBA_2025" },
  { label: "NBA vs EL Example", a: "NBA_201939", b: "EL_9001", season: "NBA_2025" },
];

export default function ComparePage() {
  const [playerAInput, setPlayerAInput] = useState("NBA_201939");
  const [playerBInput, setPlayerBInput] = useState("NBA_2544");
  const [seasonInput, setSeasonInput] = useState("NBA_2025");
  const [playerA, setPlayerA] = useState("NBA_201939");
  const [playerB, setPlayerB] = useState("NBA_2544");
  const [season, setSeason] = useState("NBA_2025");
  const [preset, setPreset] = useState("efficiency");

  const { data, loading, error } = useApi(
    playerA && playerB
      ? `/compare?playerA=${encodeURIComponent(playerA)}&playerB=${encodeURIComponent(playerB)}&season=${encodeURIComponent(season)}`
      : null
  );

  const selectedPreset = presets.find((p) => p.value === preset) ?? presets[0];
  const chartData = useMemo(() => {
    if (!data) return [];
    return selectedPreset.keys.map((key) => ({
      metric: metricLabels[key] ?? key,
      key,
      playerA: Number(data.playerA?.[key] ?? 0),
      playerB: Number(data.playerB?.[key] ?? 0),
    }));
  }, [data, selectedPreset]);

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title="Compare Workbench"
          subtitle="Pick two players, choose a lens, and see a side-by-side performance story."
          right={<MetricSwitch options={presets.map((p) => ({ value: p.value, label: p.label }))} value={preset} onChange={setPreset} />}
        />
        <div className="mb-3 flex flex-wrap gap-2">
          {quickMatchups.map((matchup) => (
            <Button
              key={matchup.label}
              variant="ghost"
              onClick={() => {
                setPlayerAInput(matchup.a);
                setPlayerBInput(matchup.b);
                setSeasonInput(matchup.season);
                setPlayerA(matchup.a);
                setPlayerB(matchup.b);
                setSeason(matchup.season);
              }}
            >
              {matchup.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <EntitySearchInput
            value={playerAInput}
            onChange={setPlayerAInput}
            placeholder="Player A (type name or ID)"
            type="player"
          />
          <EntitySearchInput
            value={playerBInput}
            onChange={setPlayerBInput}
            placeholder="Player B (type name or ID)"
            type="player"
          />
          <SearchInput value={seasonInput} onChange={setSeasonInput} placeholder="Season (e.g. NBA_2025)" />
          <Button
            variant="court"
            onClick={() => {
              setPlayerA(playerAInput.trim());
              setPlayerB(playerBInput.trim());
              setSeason(seasonInput.trim());
            }}
          >
            Run Comparison
          </Button>
        </div>
      </Card>

      {loading ? <LoadingPanel text="Running comparison..." /> : null}
      {error ? <ErrorPanel error={error} /> : null}
      {!loading && !error && !data ? (
        <EmptyPanel title="No matchup loaded yet" description="Enter two player IDs or tap a quick matchup." />
      ) : null}

      {!loading && !error && data ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader title={data.playerA.name} subtitle={`League ${data.playerA.league_id}`} />
              <div className="space-y-2 text-sm text-slate-200">
                {Object.entries(data.playerA)
                  .filter(([k]) => selectedPreset.keys.includes(k))
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between rounded bg-black/20 px-3 py-2">
                      <span>{metricLabels[k] ?? k}</span>
                      <strong>{Number(v ?? 0).toFixed(3)}</strong>
                    </div>
                  ))}
              </div>
            </Card>
            <Card>
              <CardHeader title={data.playerB.name} subtitle={`League ${data.playerB.league_id}`} />
              <div className="space-y-2 text-sm text-slate-200">
                {Object.entries(data.playerB)
                  .filter(([k]) => selectedPreset.keys.includes(k))
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between rounded bg-black/20 px-3 py-2">
                      <span>{metricLabels[k] ?? k}</span>
                      <strong>{Number(v ?? 0).toFixed(3)}</strong>
                    </div>
                  ))}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Comparison Chart" subtitle={`Preset: ${selectedPreset.label}`} />
            <MetricBarChart
              data={chartData}
              xKey="metric"
              bars={[
                { key: "playerA", color: "#5ba0ff" },
                { key: "playerB", color: "#f39237" },
              ]}
            />
          </Card>
        </>
      ) : null}
    </section>
  );
}
