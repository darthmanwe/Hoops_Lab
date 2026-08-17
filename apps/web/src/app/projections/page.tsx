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

const DIRECTIONS = ["EL->NBA", "GL->NBA"] as const;

/** Recent enough that the player is plausibly still signable. */
const DEFAULT_SINCE = 2023;

export default async function ProjectionsPage({
  searchParams,
}: {
  searchParams: Promise<{ direction?: string; since?: string; all?: string }>;
}) {
  const { direction = "EL->NBA", since = String(DEFAULT_SINCE), all } = await searchParams;
  const showAllSeasons = all === "true";

  const query = new URLSearchParams({ direction, limit: "60" });
  if (!showAllSeasons) query.set("sinceSeason", since);

  const result = await apiGetOptional<HypotheticalProjection[]>(`/projections?${query}`);

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Who hasn't moved yet"
        subtitle="The counterfactual this project exists to answer: if this player signed, what does history say about players who did?"
      >
        <p className="mb-4 text-sm text-slate-300">
          Every player here has a qualifying season in their own league and{" "}
          <strong>has not made this move</strong>. The projection applies the same fitted
          translation function used on the {directionLabel(direction)} transfers that actually
          happened.
        </p>

        <nav aria-label="Direction" className="flex flex-wrap gap-2">
          {DIRECTIONS.map((option) => {
            const active = option === direction;
            return (
              <Link
                key={option}
                href={`/projections?direction=${encodeURIComponent(option)}${showAllSeasons ? "&all=true" : ""}`}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg border px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-300 ${
                  active
                    ? "border-court-300 bg-court-300/20 text-white"
                    : "border-white/15 bg-white/5 text-slate-200 hover:bg-white/10"
                }`}
              >
                {directionLabel(option)}
              </Link>
            );
          })}
          <Link
            href={`/projections?direction=${encodeURIComponent(direction)}${showAllSeasons ? "" : "&all=true"}`}
            className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-300"
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
            <Table
              caption={`Projected ${directionLabel(direction)} usage rate for players who have not moved`}
              headers={[
                "Player",
                "Season",
                "Min",
                "Source usage",
                "vs league",
                "Projected (80% interval)",
                "",
              ]}
              rows={result.data.map((row) => [
                <Link
                  key={row.personId}
                  className="text-court-300 underline"
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
                      className="text-xs text-slate-400"
                      title="Has moved league before"
                    >
                      moved before
                    </span>
                  ) : null
                ) : (
                  <span
                    key="f"
                    className="text-xs text-amber-300"
                    title="Outside the range of source production where transferring players were observed"
                  >
                    extrapolated
                  </span>
                ),
              ])}
            />
          </Card>

          <Card title="Why the top of this list is the least reliable part of it">
            <p className="text-sm text-slate-300">
              Rows marked <span className="text-amber-300">extrapolated</span> sit outside the range
              of source production where transferring players were actually observed. The interval
              comes from the residual spread <em>inside</em> that range, so for these players it
              understates the real uncertainty — the model has no data at that end and its error
              bars cannot know it.
            </p>
            <p className="mt-3 text-sm text-slate-300">
              This is not incidental. Ranking by projected usage puts the highest-usage players in
              the league first, and those are precisely the ones beyond the observed range. The
              names that look most exciting are the ones the model is least entitled to speak about,
              so the flag is shown rather than the rows being quietly dropped.
            </p>
            <p className="mt-3 text-sm text-slate-300">
              Only usage rate is projected. True shooting is omitted because the model loses to
              predicting the league average on it — for a transfer that already happened you can see
              that miss against what the player actually did, but a hypothetical has no actual
              beside it, so the number would be unfalsifiable.{" "}
              <Link className="text-court-300 underline" href="/model">
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
