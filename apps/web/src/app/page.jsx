import { API_BASE } from "../lib/api";

export default function HomePage() {
  return (
    <main>
      <h1>HoopsLab</h1>
      <p>NBA + EuroLeague Intelligence Platform</p>
      <p>
        API base: <code>{API_BASE}</code>
      </p>
      <ul>
        <li>
          <a href="/players/NBA_201939?season=NBA_2025">Player Example (Stephen Curry)</a>
        </li>
        <li>
          <a href="/leaderboards?season=NBA_2025">Leaderboards</a>
        </li>
        <li>
          <a href="/games">Games</a>
        </li>
      </ul>
    </main>
  );
}
