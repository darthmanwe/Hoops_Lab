import Link from "next/link";
import { Card, Explanation, Provenance, Table } from "../../components/ui";
import type { HypotheticalProjection } from "../../lib/api";
import { apiGetOptional, isProblem } from "../../lib/api";
import { directionLabel, percent, signedSd, withInterval } from "../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

/**
 * Every direction with observed transfers behind it, ordered by how much data
 * supports each. The two NBA-bound moves are the headline, but they are not the
 * best-evidenced: more players have gone the other way.
 */
const DIRECTIONS = ["EL->NBA", "GL->NBA", "NBA->EL", "NBA->GL", "GL->EL", "EL->GL"] as const;

/** Recent enough that the player is plausibly still signable. */
const DEFAULT_SINCE = 2023;

const PAGE_SIZE = 100;

export default async function ProjectionsPage({
  searchParams,
}: {
  searchParams: Promise<{ direction?: string; since?: string; all?: string; offset?: string }>;
}) {
  const {
    direction = "EL->NBA",
    since = String(DEFAULT_SINCE),
    all,
    offset: rawOffset,
  } = await searchParams;
  const showAllSeasons = all === "true";
  const offset = Math.max(0, Number.parseInt(rawOffset ?? "0", 10) || 0);

  const query = new URLSearchParams({
    direction,
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (!showAllSeasons) query.set("sinceSeason", since);

  const result = await apiGetOptional<HypotheticalProjection[]>(`/projections?${query}`);

  /** Preserves every filter except the one being changed. */
  const href = (next: Partial<{ direction: string; all: boolean; offset: number }>) => {
    const params = new URLSearchParams({ direction: next.direction ?? direction });
    if (next.all ?? showAllSeasons) params.set("all", "true");
    const page = next.offset ?? 0;
    if (page > 0) params.set("offset", String(page));
    return `/projections?${params}`;
  };

  const page = isProblem(result) ? undefined : result.meta.page;
  const movers = isProblem(result) ? undefined : result.data[0]?.supportNMovers;

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Who hasn't moved yet"
        subtitle="The counterfactual this project exists to answer: if this player signed, what does history say about players who did?"
      >
        <p className="mb-4 text-sm text-fg-muted">
          Every player here has a qualifying season in their own league and{" "}
          <strong>has not made this move</strong>. The projection applies the same fitted
          translation function used on the {directionLabel(direction)} transfers that actually
          happened{movers ? `, of which there are ${movers}` : ""}.
        </p>

        <nav aria-label="Direction" className="flex flex-wrap gap-2">
          {DIRECTIONS.map((option) => {
            const active = option === direction;
            return (
              <Link
                key={option}
                href={href({ direction: option })}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg border px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  active
                    ? "border-accent bg-accent/20 text-fg"
                    : "border-edge-strong bg-surface text-fg-muted hover:bg-surface-strong"
                }`}
              >
                {directionLabel(option)}
              </Link>
            );
          })}
          <Link
            href={href({ all: !showAllSeasons })}
            className="rounded-lg border border-edge-strong bg-surface px-3 py-1.5 text-sm text-fg-muted transition hover:bg-surface-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {showAllSeasons ? `Recent only (${DEFAULT_SINCE}+)` : "Include every season"}
          </Link>
        </nav>
      </Card>

      <Explanation
        tone="warning"
        title="Read this as a shortlist, not a valuation"
        detail={
          "The model is fitted on players who were signed, and being good is why they were " +
          "signed — the transferring cohort sits about half a standard deviation above its own " +
          "league. Applying that function to someone nobody has signed assumes the same " +
          "relationship holds for him, which is an assumption, not a finding. The 80% interval " +
          "spans roughly two standard deviations of the receiving league: enough to sort a " +
          "shortlist, nowhere near enough to price a contract."
        }
      />

      {isProblem(result) ? (
        <Explanation title={result.title} detail={result.detail} />
      ) : (
        <>
          <Card>
            {page ? (
              <p className="mb-3 text-sm text-fg-subtle">
                Showing{" "}
                <strong className="text-fg-muted">
                  {page.offset + 1}–{page.offset + page.returned}
                </strong>{" "}
                of <strong className="text-fg-muted">{page.total.toLocaleString("en-GB")}</strong>{" "}
                eligible {directionLabel(direction).split(" → ")[0]} players
                {showAllSeasons ? "" : ` with a ${DEFAULT_SINCE}+ season`}, ranked by projection.
              </p>
            ) : null}

            <Table
              caption={`Projected ${directionLabel(direction)} usage rate for players who have not moved`}
              headers={[
                "Player",
                "Season",
                "Min",
                "Source usage",
                "vs league",
                "Projected (80% interval)",
                // Named rather than left blank. The column carries the
                // `extrapolated` flag, which the prose above calls the most
                // important signal on the page, and an empty `th` leaves a
                // screen reader announcing those cells against nothing.
                "Support",
              ]}
              rows={result.data.map((row) => [
                <Link
                  key={row.personId}
                  className="text-accent underline"
                  href={`/players/${row.personId}`}
                >
                  {row.displayName ?? row.personId}
                </Link>,
                row.sourceSeasonId,
                Math.round(row.minutes).toLocaleString("en-GB"),
                percent(row.sourceValue),
                signedSd(row.zSource),
                withInterval(row.predicted, row.pi80Low, row.pi80High),
                row.inSupport ? (
                  row.movedBefore ? (
                    <span
                      key="f"
                      className="text-xs text-fg-subtle"
                      title="Has moved league before"
                    >
                      moved before
                    </span>
                  ) : null
                ) : (
                  <span
                    key="f"
                    className="text-xs text-warn"
                    title="Outside the range of source production where transferring players were observed"
                  >
                    extrapolated
                  </span>
                ),
              ])}
            />

            {page && page.total > page.returned ? (
              <nav aria-label="Pagination" className="mt-4 flex items-center gap-3 text-sm">
                {offset > 0 ? (
                  <Link
                    className="rounded-lg border border-edge-strong bg-surface px-3 py-1.5 text-fg-muted transition hover:bg-surface-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    href={href({ offset: Math.max(0, offset - PAGE_SIZE) })}
                  >
                    ← Previous
                  </Link>
                ) : null}
                {offset + page.returned < page.total ? (
                  <Link
                    className="rounded-lg border border-edge-strong bg-surface px-3 py-1.5 text-fg-muted transition hover:bg-surface-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    href={href({ offset: offset + PAGE_SIZE })}
                  >
                    Next {Math.min(PAGE_SIZE, page.total - offset - page.returned)} →
                  </Link>
                ) : null}
              </nav>
            ) : null}
          </Card>

          <Card title="Why the top of this list is the least reliable part of it">
            <p className="text-sm text-fg-muted">
              Rows marked <span className="text-warn">extrapolated</span> sit outside the range of
              source production where transferring players were actually observed. The interval
              comes from the residual spread <em>inside</em> that range, so for these players it
              understates the real uncertainty — the model has no data at that end and its error
              bars cannot know it.
            </p>
            <p className="mt-3 text-sm text-fg-muted">
              This is not incidental. Ranking by projected usage puts the highest-usage players in
              the league first, and those are precisely the ones beyond the observed range. The
              names that look most exciting are the ones the model is least entitled to speak about,
              so the flag is shown rather than the rows being quietly dropped.
            </p>
            <p className="mt-3 text-sm text-fg-muted">
              The direction matters as much as the player. Moves <em>out</em> of the NBA are the
              best-evidenced in this data — 134 to the G League and 115 to the EuroLeague, against
              61 the other way — but that cohort was selected in reverse: players who left the NBA
              sat about a third of a standard deviation <em>below</em> their league. So an NBA
              regular projected into the EuroLeague is being scored by a function fitted mostly on
              players who could not hold an NBA roster spot, and almost every star is flagged{" "}
              <span className="text-warn">extrapolated</span> for exactly that reason.
            </p>
            <p className="mt-3 text-sm text-fg-muted">
              Only usage rate is projected. True shooting is omitted because the model loses to
              predicting the league average on it — for a transfer that already happened you can see
              that miss against what the player actually did, but a hypothetical has no actual
              beside it, so the number would be unfalsifiable.{" "}
              <Link className="text-accent underline" href="/model">
                The model page shows both.
              </Link>
            </p>
          </Card>

          <Provenance snapshot={result.meta.snapshot} model={result.meta.model} />
        </>
      )}
    </div>
  );
}
