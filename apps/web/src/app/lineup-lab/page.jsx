"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardHeader } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { MetricSwitch } from "../../components/ui/metric-switch";
import { EntitySearchInput } from "../../components/filters/entity-search-input";
import { LoadingPanel, ErrorPanel, EmptyPanel } from "../../components/ui/state-panels";
import { MetricTile } from "../../components/ui/metric-tile";
import { useApi } from "../../lib/use-api";
import { MetricRadarChart } from "../../components/charts/metric-radar-chart";
import { MetricBarChart } from "../../components/charts/metric-bar-chart";
import { SEASON_OPTIONS } from "../../lib/seasons";

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
    players: ["NBA_201939", "NBA_2544", "EL_9001", "EL_9002", "NBA_201939"],
  },
  {
    label: "Spacing Heavy Five",
    team: "NBA_1610612738",
    season: "NBA_2025",
    players: ["NBA_201939", "NBA_2544", "EL_9001", "EL_9002", "NBA_201939"],
  },
];

function LineupLabPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTeam = searchParams.get("team") ?? "NBA_1610612738";
  const initialSeason = searchParams.get("season") ?? "NBA_2025";
  const initialPlayers = (searchParams.get("players") ?? "NBA_201939,NBA_2544,EL_9001,EL_9002,NBA_2544").split(",");
  const [teamInput, setTeamInput] = useState(initialTeam);
  const [seasonInput, setSeasonInput] = useState(initialSeason);
  const [slot1, setSlot1] = useState(initialPlayers[0] ?? "NBA_201939");
  const [slot2, setSlot2] = useState(initialPlayers[1] ?? "NBA_2544");
  const [slot3, setSlot3] = useState(initialPlayers[2] ?? "EL_9001");
  const [slot4, setSlot4] = useState(initialPlayers[3] ?? "EL_9002");
  const [slot5, setSlot5] = useState(initialPlayers[4] ?? "NBA_2544");
  const [team, setTeam] = useState(initialTeam);
  const [season, setSeason] = useState(initialSeason);
  const [players, setPlayers] = useState(initialPlayers.join(","));
  const [mode, setMode] = useState(searchParams.get("mode") ?? "overview");

  const { data, loading, error } = useApi(
    `/teams/${encodeURIComponent(team)}/lineup-impact?season=${encodeURIComponent(season)}&players=${encodeURIComponent(players)}`
  );
  const teamLookup = useApi(
    teamInput.trim()
      ? `/teams/${encodeURIComponent(teamInput.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );
  const slot1Lookup = useApi(
    slot1.trim()
      ? `/players/${encodeURIComponent(slot1.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );
  const slot2Lookup = useApi(
    slot2.trim()
      ? `/players/${encodeURIComponent(slot2.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );
  const slot3Lookup = useApi(
    slot3.trim()
      ? `/players/${encodeURIComponent(slot3.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );
  const slot4Lookup = useApi(
    slot4.trim()
      ? `/players/${encodeURIComponent(slot4.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );
  const slot5Lookup = useApi(
    slot5.trim()
      ? `/players/${encodeURIComponent(slot5.trim())}?season=${encodeURIComponent(seasonInput)}`
      : null
  );

  useEffect(() => {
    const next = new URLSearchParams();
    next.set("team", team);
    next.set("season", season);
    next.set("players", players);
    next.set("mode", mode);
    router.replace(`/lineup-lab?${next.toString()}`);
  }, [team, season, players, mode, router]);

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
          <div>
            <EntitySearchInput
              value={teamInput}
              onChange={setTeamInput}
              placeholder="Team (type name or ID)"
              type="team"
            />
            <p className="mt-1 text-xs text-slate-300">
              {teamLookup.data?.team?.name
                ? `${teamLookup.data.team.name} (${teamLookup.data.team.team_id})`
                : "Choose a team"}
            </p>
          </div>
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
          <Button variant="court" onClick={runLineup}>
            Evaluate Lineup
          </Button>
          <div>
            <EntitySearchInput value={slot1} onChange={setSlot1} placeholder="Player 1 (name or ID)" type="player" />
            <p className="mt-1 text-xs text-slate-300">
              {slot1Lookup.data?.player?.name
                ? `${slot1Lookup.data.player.name} (${slot1Lookup.data.player.player_id})`
                : "Choose player 1"}
            </p>
          </div>
          <div>
            <EntitySearchInput value={slot2} onChange={setSlot2} placeholder="Player 2 (name or ID)" type="player" />
            <p className="mt-1 text-xs text-slate-300">
              {slot2Lookup.data?.player?.name
                ? `${slot2Lookup.data.player.name} (${slot2Lookup.data.player.player_id})`
                : "Choose player 2"}
            </p>
          </div>
          <div>
            <EntitySearchInput value={slot3} onChange={setSlot3} placeholder="Player 3 (name or ID)" type="player" />
            <p className="mt-1 text-xs text-slate-300">
              {slot3Lookup.data?.player?.name
                ? `${slot3Lookup.data.player.name} (${slot3Lookup.data.player.player_id})`
                : "Choose player 3"}
            </p>
          </div>
          <div>
            <EntitySearchInput value={slot4} onChange={setSlot4} placeholder="Player 4 (name or ID)" type="player" />
            <p className="mt-1 text-xs text-slate-300">
              {slot4Lookup.data?.player?.name
                ? `${slot4Lookup.data.player.name} (${slot4Lookup.data.player.player_id})`
                : "Choose player 4"}
            </p>
          </div>
          <div>
            <EntitySearchInput value={slot5} onChange={setSlot5} placeholder="Player 5 (name or ID)" type="player" />
            <p className="mt-1 text-xs text-slate-300">
              {slot5Lookup.data?.player?.name
                ? `${slot5Lookup.data.player.name} (${slot5Lookup.data.player.player_id})`
                : "Choose player 5"}
            </p>
          </div>
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

export default function LineupLabPage() {
  return (
    <Suspense fallback={<LoadingPanel text="Loading lineup lab..." />}>
      <LineupLabPageContent />
    </Suspense>
  );
}
