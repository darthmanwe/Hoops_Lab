import { Card, Explanation, Metric, Provenance, Table } from "../../components/ui";
import type { ModelEvaluation, ModelVersion, SelectionSummary } from "../../lib/api";
import { apiGetOptional, isProblem } from "../../lib/api";
import { decimal, directionLabel, integer, metricLabel, signedSd } from "../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

type Evaluation = {
  version: ModelVersion;
  evaluations: ModelEvaluation[];
  selection: SelectionSummary[];
  interpretation: { estimand: string; selection_note: string };
};

/**
 * The model's own report card.
 *
 * The page that makes the project worth showing: almost no portfolio project
 * publishes its own error against every baseline, including the ones it loses
 * to.
 */
export default async function ModelPage() {
  const registry = await apiGetOptional<ModelVersion[]>("/models");
  if (isProblem(registry) || registry.data.length === 0) {
    return (
      <Explanation
        title="No model registered"
        detail={isProblem(registry) ? registry.detail : "The registry is empty."}
      />
    );
  }

  const version = registry.data[0]!;
  const detail = await apiGetOptional<Evaluation>(`/models/${version.modelVersion}/evaluation`);
  if (isProblem(detail)) {
    return <Explanation title={detail.title} detail={detail.detail} />;
  }

  const { evaluations, selection, interpretation } = detail.data;
  const metrics = [...new Set(evaluations.map((e) => e.metric))];

  return (
    <div className="flex flex-col gap-6">
      <Card title="What this model claims" subtitle={interpretation.estimand}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Version" value={version.modelVersion} />
          <Metric label="Seed" value={String(version.seed)} hint={`git ${version.gitSha}`} />
          <Metric label="Transitions fitted" value={integer(version.nTrain)} />
          <Metric label="Out-of-fold rows" value={integer(version.nEvaluated)} />
        </div>
      </Card>

      {metrics.map((metric) => {
        const rows = evaluations.filter((e) => e.metric === metric);
        const first = rows[0]!;
        const beats = first.beatsBestBaseline;

        return (
          <Card
            key={metric}
            title={metricLabel(metric)}
            subtitle={`Out-of-fold MAE ${decimal(first.mae, 4)} over ${integer(first.nEvaluated)} predictions, 95% CI [${decimal(first.maeCiLow, 4)}, ${decimal(first.maeCiHigh, 4)}]`}
          >
            {!beats ? (
              <div className="mb-4">
                <Explanation
                  tone="warning"
                  title="Worse than a trivial baseline"
                  detail={
                    `This model loses to simply predicting the league average by ` +
                    `${Math.abs(first.skillVsBest * 100).toFixed(1)}%. Do not use it for this ` +
                    `metric. It is shown rather than hidden, because publishing only the metric ` +
                    `that worked would be the more flattering and less honest presentation.`
                  }
                />
              </div>
            ) : null}

            <Table
              caption={`Baselines for ${metricLabel(metric)}`}
              headers={["Baseline", "Baseline MAE", "Model MAE", "Difference"]}
              rows={rows
                .sort((a, b) => a.baselineMae - b.baselineMae)
                .map((row) => {
                  const better = row.mae < row.baselineMae;
                  const delta = ((row.baselineMae - row.mae) / row.baselineMae) * 100;
                  return [
                    row.baselineName,
                    decimal(row.baselineMae, 4),
                    decimal(row.mae, 4),
                    <span key="d" className={better ? "text-good" : "text-warn"}>
                      {better ? "model better by " : "model worse by "}
                      {Math.abs(delta).toFixed(1)}%
                    </span>,
                  ];
                })}
            />

            {first.shuffledMae !== null ? (
              <p className="mt-3 text-xs text-fg-subtle">
                Shuffled-target control: {decimal(first.shuffledMae, 4)}. Permuting the response and
                refitting collapses performance toward the baseline, which is what a pipeline
                without leakage looks like.
              </p>
            ) : null}
          </Card>
        );
      })}

      <Card title="Selection" subtitle={interpretation.selection_note}>
        <Table
          caption="How selected the movers were"
          headers={["Direction", "Metric", "Movers", "Peers", "Gap"]}
          rows={selection.map((row) => [
            directionLabel(row.direction),
            metricLabel(row.metric),
            integer(row.nMovers),
            integer(row.nLeague),
            signedSd(row.gapSd),
          ])}
        />
        <p className="mt-4 text-sm text-fg-muted">
          Positive means the movers were better than the peers they left behind. The two headline
          directions carry opposite signs, which is what makes the selection effect measurable
          rather than merely acknowledged.
        </p>
      </Card>

      <Provenance snapshot={detail.meta.snapshot} model={{ version: version.modelVersion }} />
    </div>
  );
}
