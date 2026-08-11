import Link from "next/link";
import { Card, Explanation, Provenance, Table } from "../../components/ui";
import type { TranslationPrediction } from "../../lib/api";
import { apiGetOptional, isProblem } from "../../lib/api";
import { directionLabel, percent, withInterval } from "../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

const DIRECTIONS = ["EL->NBA", "NBA->EL", "GL->NBA", "NBA->GL"] as const;

export default async function TranslationPage({
  searchParams,
}: {
  searchParams: Promise<{ direction?: string }>;
}) {
  const { direction = "EL->NBA" } = await searchParams;
  const result = await apiGetOptional<TranslationPrediction[]>(
    `/leaderboards/translation?direction=${encodeURIComponent(direction)}&metric=usg_pct&limit=40`
  );

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Translation explorer"
        subtitle="Every observed league switch, its projected usage rate with an 80% interval, and — where the move is already in the past — what actually happened."
      >
        <nav aria-label="Direction" className="flex flex-wrap gap-2">
          {DIRECTIONS.map((option) => {
            const active = option === direction;
            return (
              <Link
                key={option}
                href={`/translation?direction=${encodeURIComponent(option)}`}
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
        </nav>
      </Card>

      {isProblem(result) ? (
        <Explanation title={result.title} detail={result.detail} />
      ) : (
        <>
          <Card>
            <Table
              caption={`Projected usage rate for ${directionLabel(direction)} transitions`}
              headers={[
                "Player",
                "From",
                "To",
                "Source usage",
                "Projected (80% interval)",
                "Actual",
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
                row.targetSeasonId,
                percent(row.sourceValue),
                withInterval(row.predicted, row.pi80Low, row.pi80High),
                percent(row.actualValue),
              ])}
            />
          </Card>

          <Card title="How to read this">
            <ul className="flex flex-col gap-2 text-sm text-slate-300">
              <li>
                <strong>The interval is the result</strong>, not a caveat on it. It spans roughly a
                third of the NBA usage distribution, which is useful for ranking a cohort and
                useless for deciding a contract.
              </li>
              <li>
                <strong>This is conditional on the move happening.</strong> It answers what history
                says to expect given a player got a contract, not what a randomly chosen player
                would do.
              </li>
              <li>
                <strong>The &ldquo;actual&rdquo; column is the honest check.</strong> Where it is
                filled in, the move has already happened and you can see how far the projection was
                out.
              </li>
            </ul>
          </Card>

          <Provenance snapshot={result.meta.snapshot} model={result.meta.model} />
        </>
      )}
    </div>
  );
}
