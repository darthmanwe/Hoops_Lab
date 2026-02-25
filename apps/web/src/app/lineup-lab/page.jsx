"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { MetricSwitch } from "../../components/ui/metric-switch";
import { SearchInput } from "../../components/filters/search-input";
import { EntitySearchInput } from "../../components/filters/entity-search-input";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { MetricTile } from "../../components/ui/metric-tile";
import { useApi } from "../../lib/use-api";
import { MetricRadarChart } from "../../components/charts/metric-radar-chart";
import { MetricBarChart } from "../../components/charts/metric-bar-chart";

const displayModes = [
  { value: "overview", label: "Overview" },
  { value: "gravity", label: "Gravity" },
  { value: "style", label: "Style Fit" },
];

const quickLineups = [
  {
    label: "Demo Hybrid Five",
    team: "NBA_1610612738",
    season: "NBA_2025",
    players: ["NBA_201939", "NBA_2544", "EL_9001", "EL_9002", "NBA_1629029"],
  },
  {
    label: "Spacing Heavy Five",
    team: "NBA_1610612738",
    season: "NBA_2025",
    players: ["NBA_201939", "NBA_2544", "EL_9001", "EL_9002", "NBA_201939"],
  },
];

export default function LineupLabPage() {
  const [teamInput, setTeamInput] = useState("NBA_1610612738");
  const [seasonInput, setSeasonInput] = useState("NBA_2025");
  const [slot1, setSlot1] = useState("NBA_201939");
  const [slot2, setSlot2] = useState("NBA_2544");
  const [slot3, setSlot3] = useState("EL_9001");
  const [slot4, setSlot4] = useState("EL_9002");
  const [slot5, setSlot5] = useState("NBA_2544");
  const [team, setTeam] = useState("NBA_1610612738");
  const [season, setSeason] = useState("NBA_2025");
  const [players, setPlayers] = useState("NBA_201939,NBA_2544,EL_9001,EL_9002,NBA_2544");
  const [mode, setMode] = useState("overview");

  const { data, loading, error } = useApi(
    `/teams/${encodeURIComponent(team)}/lineup-impact?season=${encodeURIComponent(season)}&players=${encodeURIComponent(players)}`
  );

  const metrics = data?.metrics ?? {};
  const radarData = useMemo(
    () => [
      { metric: "Avg Gravity", value: Number(metrics.avg_gravity ?? 0) },
      { metric: "Off Projection", value: Number(metrics.offense_projection ?? 0) },
      { metric: "Spacing", value: Number(metrics.spacing_index ?? 0) },
      { metric: "Transition Fit", value: Number(metrics.transition_fit ?? 0) },
      { metric: "Set Play Fit", value: Number(metrics.set_play_fit ?? 0) },
    ],
    [metrics]
  );

  const styleBarData = [
    { metric: "Transition Fit", value: Number(metrics.transition_fit ?? 0) },
    { metric: "Set Play Fit", value: Number(metrics.set_play_fit ?? 0) },
    { metric: "Gravity Delta", value: Number(metrics.gravity_delta_vs_team ?? 0) },
  ];

  function runLineup() {
    setTeam(teamInput.trim());
    setSeason(seasonInput.trim());
    setPlayers([slot1, slot2, slot3, slot4, slot5].map((x) => x.trim()).join(","));
  }

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader
          title="Lineup Lab"
          subtitle="Build a five-player unit and instantly check fit, spacing, and projected offense."
          right={<MetricSwitch options={displayModes} value={mode} onChange={setMode} />}
        />
        <div className="mb-3 flex flex-wrap gap-2">
          {quickLineups.map((lineup) => (
            <Button
              key={lineup.label}
              variant="ghost"
              onClick={() => {
                setTeamInput(lineup.team);
                setSeasonInput(lineup.season);
                setSlot1(lineup.players[0]);
                setSlot2(lineup.players[1]);
                setSlot3(lineup.players[2]);
                setSlot4(lineup.players[3]);
                setSlot5(lineup.players[4]);
                setTeam(lineup.team);
                setSeason(lineup.season);
                setPlayers(lineup.players.join(","));
              }}
            >
              {lineup.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <EntitySearchInput
            value={teamInput}
            onChange={setTeamInput}
            placeholder="Team (type name or ID)"
            type="team"
          />
          <SearchInput value={seasonInput} onChange={setSeasonInput} placeholder="Season (e.g. NBA_2025)" />
          <Button variant="court" onClick={runLineup}>
            Evaluate Lineup
          </Button>
          <EntitySearchInput value={slot1} onChange={setSlot1} placeholder="Player 1 (name or ID)" type="player" />
          <EntitySearchInput value={slot2} onChange={setSlot2} placeholder="Player 2 (name or ID)" type="player" />
          <EntitySearchInput value={slot3} onChange={setSlot3} placeholder="Player 3 (name or ID)" type="player" />
          <EntitySearchInput value={slot4} onChange={setSlot4} placeholder="Player 4 (name or ID)" type="player" />
          <EntitySearchInput value={slot5} onChange={setSlot5} placeholder="Player 5 (name or ID)" type="player" />
        </div>
      </Card>

      {loading ? <LoadingPanel text="Computing lineup impact..." /> : null}
      {error ? <ErrorPanel error={error} /> : null}
      {!loading && !error && !data ? (
        <EmptyPanel title="No lineup data" description="Run a lineup calculation with five valid player IDs." />
      ) : null}

      {!loading && !error && data ? (
        <>
          <div className="grid gap-3 md:grid-cols-5">
            <MetricTile label="Avg Gravity" value={Number(metrics.avg_gravity ?? 0).toFixed(2)} />
            <MetricTile label="Off Projection" value={Number(metrics.offense_projection ?? 0).toFixed(2)} />
            <MetricTile label="Spacing Index" value={Number(metrics.spacing_index ?? 0).toFixed(2)} />
            <MetricTile label="Transition Fit" value={Number(metrics.transition_fit ?? 0).toFixed(2)} />
            <MetricTile label="Set Play Fit" value={Number(metrics.set_play_fit ?? 0).toFixed(2)} />
          </div>

          {mode === "overview" || mode === "gravity" ? (
            <Card>
              <CardHeader title="Lineup Radar" subtitle="Multi-metric fit profile for the selected five." />
              <MetricRadarChart data={radarData} />
            </Card>
          ) : null}

          {mode === "overview" || mode === "style" ? (
            <Card>
              <CardHeader title="Style Fit Bars" subtitle="Transition vs set-play derived impact." />
              <MetricBarChart
                data={styleBarData}
                xKey="metric"
                bars={[{ key: "value", color: "#f39237" }]}
              />
            </Card>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
