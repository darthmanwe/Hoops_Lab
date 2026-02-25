import { apiGet } from "../../../lib/api";

export default async function TeamPage({ params, searchParams }) {
  const { id } = await params;
  const qs = await searchParams;
  const season = qs?.season ?? "NBA_2025";

  let team = null;
  let fatigue = null;
  let shotProfile = null;
  let playStyle = null;
  let snapshots = null;

  try {
    team = await apiGet(`/teams/${encodeURIComponent(id)}?season=${encodeURIComponent(season)}`);
  } catch {
    team = null;
  }
  try {
    fatigue = await apiGet(`/teams/${encodeURIComponent(id)}/fatigue?season=${encodeURIComponent(season)}`);
  } catch {
    fatigue = null;
  }
  try {
    shotProfile = await apiGet(`/teams/${encodeURIComponent(id)}/shot-profile?season=${encodeURIComponent(season)}`);
  } catch {
    shotProfile = null;
  }
  try {
    playStyle = await apiGet(`/teams/${encodeURIComponent(id)}/play-style?season=${encodeURIComponent(season)}`);
  } catch {
    playStyle = null;
  }
  try {
    snapshots = await apiGet(`/teams/${encodeURIComponent(id)}/lineup-impact/snapshots?season=${encodeURIComponent(season)}`);
  } catch {
    snapshots = null;
  }

  if (!team) {
    return (
      <main>
        <h1>Team not found</h1>
      </main>
    );
  }

  return (
    <main>
      <h1>{team.team.name}</h1>
      <p>
        {team.team.team_id} | {team.team.league_id}
      </p>

      <h2>Gravity Effect</h2>
      <pre>{JSON.stringify(team.gravity, null, 2)}</pre>

      <h2>Fatigue</h2>
      <pre>{JSON.stringify(fatigue, null, 2)}</pre>

      <h2>Shot Profile</h2>
      <pre>{JSON.stringify(shotProfile, null, 2)}</pre>

      <h2>Play Style (Transition vs Set Play)</h2>
      <pre>{JSON.stringify(playStyle, null, 2)}</pre>

      <h2>Five-Player Impact Snapshots</h2>
      <pre>{JSON.stringify(snapshots, null, 2)}</pre>
    </main>
  );
}
