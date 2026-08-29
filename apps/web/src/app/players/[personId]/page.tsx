import { ScoutingReport } from "../../../components/report";
import { Card, Explanation, Metric, Provenance, Table } from "../../../components/ui";
import type {
  CompRow,
  Identity,
  PersonSummary,
  PlayerSeason,
  ScoutingReportResponse,
  ShootingRow,
  TranslationPrediction,
} from "../../../lib/api";
import { apiGetOptional, isProblem } from "../../../lib/api";
import { decimal, directionLabel, integer, percent, withInterval, year } from "../../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

type PlayerDetail = {
  person: PersonSummary;
  seasons: PlayerSeason[];
  identities: Identity[];
};

export default async function PlayerPage({ params }: { params: Promise<{ personId: string }> }) {
  const { personId } = await params;

  const [detail, translation, shooting, comps, report] = await Promise.all([
    apiGetOptional<PlayerDetail>(`/players/${personId}`),
    apiGetOptional<TranslationPrediction[]>(`/players/${personId}/translation`),
    apiGetOptional<ShootingRow[]>(`/players/${personId}/shooting`),
    apiGetOptional<CompRow[]>(`/players/${personId}/comps?limit=6`),
    apiGetOptional<ScoutingReportResponse>(`/players/${personId}/report`),
  ]);

  if (isProblem(detail)) {
    return <Explanation title={detail.title} detail={detail.detail} />;
  }

  const { person, seasons, identities } = detail.data;
  const lowConfidence = identities.filter((identity) => identity.confidence < 0.8);

  return (
    <div className="flex flex-col gap-6">
      <Card title={person.displayName ?? personId} subtitle={`Appears in: ${person.leagues}`}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Seasons recorded" value={integer(seasons.length)} />
          <Metric label="Birth year" value={year(person.birthYear)} />
          <Metric label="Identity links" value={integer(identities.length)} />
        </div>

        {lowConfidence.length > 0 ? (
          <div className="mt-4">
            <Explanation
              tone="warning"
              title="Low-confidence identity link"
              detail={
                "At least one cross-league link for this player was made on name alone, without " +
                "an age corroborating it. Shown rather than hidden: a guessed identity is weaker " +
                "evidence than a confirmed one."
              }
            />
          </div>
        ) : null}
      </Card>

      <Card
        title="Career"
        subtitle="Chronological across every league, using an integer season key."
      >
        <Table
          caption="Season-by-season rates"
          headers={["Season", "League", "Team", "Min", "Usage", "TS%", "Assist rate", "Age"]}
          rows={seasons.map((season) => [
            season.label,
            season.league,
            season.teamName ?? "—",
            integer(season.minutes),
            percent(season.usgPct),
            percent(season.tsPct),
            percent(season.astPct),
            decimal(season.age, 0),
          ])}
        />
      </Card>

      {!isProblem(translation) ? (
        <Card
          title="Cross-league translation"
          subtitle="Projected usage rate with an 80% interval, alongside what actually happened."
        >
          <Table
            caption="Translation predictions"
            headers={["Direction", "From", "To", "Source", "Projected (80%)", "Actual"]}
            rows={translation.data
              .filter((row) => row.metric === "usg_pct")
              .map((row) => [
                directionLabel(row.direction),
                row.sourceSeasonId,
                row.targetSeasonId,
                percent(row.sourceValue),
                withInterval(row.predicted, row.pi80Low, row.pi80High),
                percent(row.actualValue),
              ])}
          />
          <p className="mt-3 text-xs text-fg-subtle">
            The interval is the result, not a caveat on it.
          </p>
        </Card>
      ) : (
        <Card title="Cross-league translation">
          <Explanation title={translation.title} detail={translation.detail} />
        </Card>
      )}

      {!isProblem(report) ? <ScoutingReport data={report.data} /> : null}

      {!isProblem(shooting) ? (
        <Card
          title="Three-point threat"
          subtitle="Shrunk toward the league prior in proportion to how little evidence supports it."
        >
          <Table
            caption="Shooting by season"
            headers={["Season", "Attempts", "Raw 3P%", "Shrunk", "Weight on own data", "Spacing"]}
            rows={shooting.data.map((row) => [
              row.seasonId,
              integer(row.fg3a),
              percent(row.fg3PctRaw),
              percent(row.fg3PctShrunk),
              <span key="w" className={row.reportable ? "" : "text-warn"}>
                {percent(row.shrinkageWeight, 0)}
                {row.reportable ? "" : " (mostly prior)"}
              </span>,
              decimal(row.spacingScore, 2),
            ])}
          />
        </Card>
      ) : null}

      {!isProblem(comps) && comps.data.length > 0 ? (
        <Card
          title="Comparables"
          subtitle="Nearest neighbours in the archetype space, within the same season."
        >
          <Table
            caption="Most similar players"
            headers={["Season", "Rank", "Player", "Distance"]}
            rows={comps.data.map((row) => [
              row.seasonId,
              `#${row.rank}`,
              row.neighbourName ?? row.neighbourPersonId,
              decimal(row.distance, 3),
            ])}
          />
        </Card>
      ) : null}

      <Provenance
        snapshot={detail.meta.snapshot}
        model={!isProblem(translation) ? translation.meta.model : undefined}
      />
    </div>
  );
}
