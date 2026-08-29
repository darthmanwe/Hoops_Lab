import Link from "next/link";
import { Card, Explanation, Metric, Provenance } from "../components/ui";
import type { ModelEvaluation, ModelVersion, SelectionSummary } from "../lib/api";
import { apiGetOptional, isProblem } from "../lib/api";
import { decimal, directionLabel, integer, signedSd } from "../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

type Evaluation = {
  version: ModelVersion;
  evaluations: ModelEvaluation[];
  selection: SelectionSummary[];
};

export default async function HomePage() {
  const registry = await apiGetOptional<ModelVersion[]>("/models");

  if (isProblem(registry) || registry.data.length === 0) {
    return (
      <Explanation
        title="The API is not serving a model yet"
        detail={
          isProblem(registry)
            ? registry.detail
            : "No model versions are registered. Run `hoopslab train` and `hoopslab export`."
        }
      />
    );
  }

  const version = registry.data[0]!;
  const detail = await apiGetOptional<Evaluation>(`/models/${version.modelVersion}/evaluation`);
  const evaluations = isProblem(detail) ? [] : detail.data.evaluations;
  const selection = isProblem(detail) ? [] : detail.data.selection;

  const usage = evaluations.find((e) => e.metric === "usg_pct");
  const trueShooting = evaluations.find((e) => e.metric === "ts_pct");

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="The question"
        subtitle="A EuroLeague guard posts a 28% usage rate. What should you expect if he signs in the NBA?"
      >
        <p className="text-sm text-fg-muted">
          The folk answer is &ldquo;multiply by about 0.75&rdquo;. The honest answer is that the
          question is only answerable <strong>conditional on the transfer having happened</strong> —
          and the players who make the jump are a heavily selected group. This estimates the
          translation coefficients in both directions and treats that selection as something to
          measure rather than assume away.
        </p>
      </Card>

      <Card title="What the model does, and does not, do">
        <div className="grid gap-3 sm:grid-cols-2">
          <Metric
            label="Usage rate error"
            value={usage ? decimal(usage.mae, 4) : "—"}
            hint={
              usage
                ? `${usage.beatsBestBaseline ? "Beats" : "Loses to"} the best baseline by ${Math.abs(usage.skillVsBest * 100).toFixed(1)}%`
                : undefined
            }
          />
          <Metric
            label="True shooting error"
            value={trueShooting ? decimal(trueShooting.mae, 4) : "—"}
            hint={
              trueShooting
                ? `${trueShooting.beatsBestBaseline ? "Beats" : "LOSES to"} the best baseline by ${Math.abs(trueShooting.skillVsBest * 100).toFixed(1)}%`
                : undefined
            }
          />
          <Metric label="Transitions fitted" value={integer(version.nTrain)} />
          <Metric label="Out-of-fold evaluations" value={integer(version.nEvaluated)} />
        </div>

        {trueShooting && !trueShooting.beatsBestBaseline ? (
          <div className="mt-4">
            <Explanation
              tone="warning"
              title="The model does not work for true shooting"
              detail={
                "On true shooting it is worse than simply predicting the league average, so it " +
                "should not be used for that metric. It is published rather than dropped: showing " +
                "only the metric that worked would be the more flattering and less honest choice."
              }
            />
          </div>
        ) : null}
      </Card>

      {selection.length > 0 ? (
        <Card
          title="Selection, measured rather than assumed"
          subtitle="How far above or below their own league the movers sat, in standard deviations."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {selection
              .filter((s) => s.metric === "usg_pct")
              .map((s) => (
                <Metric
                  key={s.direction}
                  label={directionLabel(s.direction)}
                  value={signedSd(s.gapSd)}
                  hint={`${integer(s.nMovers)} movers vs ${integer(s.nLeague)} peers`}
                />
              ))}
          </div>
          <p className="mt-4 text-sm text-fg-muted">
            The two headline directions are selected in <strong>opposite</strong> directions:
            players move up because they were good, and down because they were not. That opposition
            is what makes the effect testable rather than merely acknowledged.
          </p>
        </Card>
      ) : null}

      <Card title="Explore">
        <ul className="flex flex-col gap-2 text-sm">
          <li>
            <Link className="text-accent underline" href="/translation">
              Translation explorer
            </Link>{" "}
            — every observed league switch, with its prediction interval and what actually happened.
          </li>
          <li>
            <Link className="text-accent underline" href="/model">
              Model and calibration
            </Link>{" "}
            — the model&rsquo;s own error against every baseline, including the ones it loses to.
          </li>
          <li>
            <Link className="text-accent underline" href="/archetypes">
              Archetypes
            </Link>{" "}
            — five clusters, each published with how well it survives resampling.
          </li>
        </ul>
      </Card>

      <Provenance snapshot={registry.meta.snapshot} model={{ version: version.modelVersion }} />
    </div>
  );
}
