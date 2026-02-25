import { apiGet } from "../../lib/api";

export default async function LineupLabPage({ searchParams }) {
  const qs = await searchParams;
  const team = qs?.team ?? "NBA_1610612738";
  const season = qs?.season ?? "NBA_2025";
  const players =
    qs?.players ?? "NBA_201939,NBA_2544,EL_9001,EL_9002,NBA_2544";

  let result = null;
  try {
    result = await apiGet(
      `/teams/${encodeURIComponent(team)}/lineup-impact?season=${encodeURIComponent(season)}&players=${encodeURIComponent(players)}`
    );
  } catch {
    result = null;
  }

  return (
    <main>
      <h1>Lineup Lab</h1>
      <p>Evaluate five-player comps with gravity and play-style fit.</p>
      <p>
        Query params: <code>team</code>, <code>season</code>, <code>players</code> (comma-separated 5 IDs)
      </p>
      {result ? <pre>{JSON.stringify(result, null, 2)}</pre> : <p>No lineup result available.</p>}
    </main>
  );
}
