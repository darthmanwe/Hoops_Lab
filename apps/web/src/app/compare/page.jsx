import { apiGet } from "../../lib/api";

export default async function ComparePage({ searchParams }) {
  const params = await searchParams;
  const playerA = params?.playerA ?? "";
  const playerB = params?.playerB ?? "";
  const season = params?.season ?? "NBA_2025";

  let result = null;
  if (playerA && playerB) {
    try {
      result = await apiGet(
        `/compare?playerA=${encodeURIComponent(playerA)}&playerB=${encodeURIComponent(playerB)}&season=${encodeURIComponent(season)}`
      );
    } catch {
      result = null;
    }
  }

  return (
    <main>
      <h1>Compare</h1>
      <p>Provide query params: playerA, playerB, season</p>
      <code>?playerA=NBA_123&playerB=EL_456&season=NBA_2025</code>
      {result ? (
        <>
          <h2>{result.playerA.name}</h2>
          <pre>{JSON.stringify(result.playerA, null, 2)}</pre>
          <h2>{result.playerB.name}</h2>
          <pre>{JSON.stringify(result.playerB, null, 2)}</pre>
        </>
      ) : (
        <p>No comparison loaded yet.</p>
      )}
    </main>
  );
}
