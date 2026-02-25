import { apiGet } from "../../../lib/api";

export default async function GameDetailPage({ params }) {
  const { id } = await params;
  let data = null;
  let fatigue = null;
  try {
    data = await apiGet(`/games/${encodeURIComponent(id)}`);
  } catch {
    data = null;
  }
  try {
    fatigue = await apiGet(`/games/${encodeURIComponent(id)}/fatigue-flags`);
  } catch {
    fatigue = null;
  }

  if (!data) {
    return (
      <main>
        <h1>Game not found</h1>
      </main>
    );
  }

  return (
    <main>
      <h1>{data.game.game_id}</h1>
      <p>{data.game.game_date}</p>
      <p>
        {data.game.home_team_id} vs {data.game.away_team_id}
      </p>

      <h2>Boxscore</h2>
      <ul>
        {data.boxscore.map((line, idx) => (
          <li key={`${line.player_id}_${idx}`}>
            {line.player_id} - PTS {line.pts ?? 0}, AST {line.ast ?? 0}, REB {line.reb ?? 0}
          </li>
        ))}
      </ul>

      <h2>Fatigue Flags</h2>
      {fatigue ? (
        <ul>
          <li>Home fatigue: {fatigue.home_fatigue_score}</li>
          <li>Away fatigue: {fatigue.away_fatigue_score}</li>
          <li>Rest disadvantage flag: {fatigue.rest_disadvantage_flag}</li>
          <li>Travel disadvantage flag: {fatigue.travel_disadvantage_flag}</li>
        </ul>
      ) : (
        <p>No fatigue flags available.</p>
      )}
    </main>
  );
}
