import { apiGet } from "../../../lib/api";

export default async function PlayerPage({ params, searchParams }) {
  const { id } = await params;
  const qs = await searchParams;
  const season = qs?.season ?? "NBA_2025";

  let player = null;
  let comps = null;
  let shotProfile = null;
  let translation = null;
  try {
    player = await apiGet(`/players/${encodeURIComponent(id)}?season=${encodeURIComponent(season)}`);
  } catch {
    player = null;
  }
  try {
    comps = await apiGet(`/players/${encodeURIComponent(id)}/comps?season=${encodeURIComponent(season)}&k=10`);
  } catch {
    comps = null;
  }
  try {
    shotProfile = await apiGet(`/players/${encodeURIComponent(id)}/shot-profile?season=${encodeURIComponent(season)}`);
  } catch {
    shotProfile = null;
  }
  try {
    translation = await apiGet(`/players/${encodeURIComponent(id)}/translation?season=${encodeURIComponent(season)}`);
  } catch {
    translation = null;
  }

  if (!player) {
    return (
      <main>
        <h1>Player not found</h1>
      </main>
    );
  }

  return (
    <main>
      <h1>{player.player.name}</h1>
      <p>
        {player.player.player_id} | {player.player.league_id}
      </p>

      <h2>Season Features</h2>
      <pre>{JSON.stringify(player.features, null, 2)}</pre>

      <h2>Closest Comps</h2>
      {comps?.comps?.length ? (
        <ul>
          {comps.comps.map((c) => (
            <li key={c.player_id}>
              {c.name} ({c.league_id}) - similarity {c.score}
            </li>
          ))}
        </ul>
      ) : (
        <p>No comps available for this season.</p>
      )}

      <h2>Shot Profile</h2>
      {shotProfile ? <pre>{JSON.stringify(shotProfile, null, 2)}</pre> : <p>No shot profile available.</p>}

      <h2>Translation Metrics</h2>
      {translation ? <pre>{JSON.stringify(translation, null, 2)}</pre> : <p>No translation metrics available.</p>}
    </main>
  );
}
