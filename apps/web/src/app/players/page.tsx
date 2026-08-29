import Link from "next/link";
import { Card, Explanation, Provenance, Table } from "../../components/ui";
import type { PersonSummary } from "../../lib/api";
import { apiGetOptional, isProblem } from "../../lib/api";
import { year } from "../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

export const metadata = { title: "Search players — HoopsLab" };

export default async function PlayersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  // No query is not an error, and the API would rightly reject an empty one.
  // The page says what it is for instead of showing a 422.
  if (!query) {
    return (
      <Card
        title="Find a player"
        subtitle="Search by name across every person resolved in the snapshot."
      >
        <p className="text-sm text-fg-muted">
          Matching ignores diacritics in both directions, so <em>Dončić</em> and <em>Doncic</em>{" "}
          find the same person. Players who appear in more than one league are listed first, because
          they are the ones this project is about.
        </p>
      </Card>
    );
  }

  const result = await apiGetOptional<PersonSummary[]>(
    `/players/search?q=${encodeURIComponent(query)}&limit=25`
  );

  if (isProblem(result)) {
    return <Explanation title={result.title} detail={result.detail} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title={`Players matching “${query}”`}>
        {result.data.length === 0 ? (
          // An empty table reads as a rendering failure. Saying so, and naming
          // the query back, is the difference between "no such player" and
          // "something went wrong".
          <p className="text-sm text-fg-muted">
            No player in this snapshot matches <strong className="text-fg">{query}</strong>. The
            hosted demo serves a curated slice; a local run carries every person in the snapshot.
          </p>
        ) : (
          <Table
            caption={`Players matching ${query}`}
            headers={["Player", "Leagues", "Born"]}
            rows={result.data.map((person) => [
              <Link
                key={person.personId}
                className="text-accent underline"
                href={`/players/${person.personId}`}
              >
                {person.displayName ?? person.personId}
              </Link>,
              person.leagues,
              year(person.birthYear),
            ])}
          />
        )}
      </Card>

      <Provenance snapshot={result.meta.snapshot} />
    </div>
  );
}
