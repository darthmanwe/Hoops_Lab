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
        <li>
          <a href="/teams/NBA_1610612738?season=NBA_2025">Team Example (Boston Celtics)</a>
        </li>
        <li>
          <a href="/lineup-lab?team=NBA_1610612738&season=NBA_2025&players=NBA_201939,NBA_2544,EL_9001,EL_9002,NBA_2544">
            Lineup Lab Example
          </a>
        </li>
      </ul>
    </main>
  );
}
