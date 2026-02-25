import { apiGet } from "../../lib/api";

export default async function LeaderboardsPage({ searchParams }) {
  const params = await searchParams;
  const season = params?.season ?? "NBA_2025";

  let gravity = { results: [] };
  let clutch = { results: [] };
  let translation = { results: [] };

  try {
    gravity = await apiGet(`/leaderboards/gravity?season=${encodeURIComponent(season)}`);
  } catch {
    gravity = { results: [] };
  }

  try {
    clutch = await apiGet(`/leaderboards/clutch?season=${encodeURIComponent(season)}`);
  } catch {
    clutch = { results: [] };
  }
  try {
    translation = await apiGet(`/leaderboards/translation?season=${encodeURIComponent(season)}`);
  } catch {
    translation = { results: [] };
  }

  return (
    <main>
      <h1>Leaderboards</h1>
      <p>
        Season: <code>{season}</code>
      </p>

      <h2>Gravity</h2>
      <ul>
        {gravity.results.slice(0, 10).map((row) => (
          <li key={row.player_id}>
            {row.name} ({row.player_id}) - {row.gravity_overall ?? "n/a"}
          </li>
        ))}
      </ul>

      <h2>Clutch</h2>
      <ul>
        {clutch.results.slice(0, 10).map((row) => (
          <li key={row.player_id}>
            {row.name} ({row.player_id}) - {row.clutch_impact ?? "n/a"}
          </li>
        ))}
      </ul>

      <h2>Translation</h2>
      <ul>
        {translation.results.slice(0, 10).map((row) => (
          <li key={row.player_id}>
            {row.name} ({row.league_id}) - score {row.translation_score ?? "n/a"}
          </li>
        ))}
      </ul>
    </main>
  );
}
