import { apiGet } from "../../lib/api";

export default async function GamesPage() {
  let data = { games: [] };
  try {
    data = await apiGet("/games?limit=25");
  } catch {
    data = { games: [] };
  }

  return (
    <main>
      <h1>Games</h1>
      <ul>
        {data.games.map((g) => (
          <li key={g.game_id}>
            <a href={`/games/${encodeURIComponent(g.game_id)}`}>{g.game_id}</a> - {g.game_date}
          </li>
        ))}
      </ul>
    </main>
  );
}
