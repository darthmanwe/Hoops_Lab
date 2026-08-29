import type { ScoutingReportResponse } from "../lib/api";
import { Card, Explanation } from "./ui";

/**
 * A model-written scouting report, rendered with its audit attached.
 *
 * The audit is deliberately not a footnote or a tooltip. Prose is the least
 * verifiable thing this application shows, so the count of numbers traced back
 * to the evidence sits directly above the text — a reader decides how much
 * weight to give a sentence at the moment they read it, or they do not decide
 * at all.
 *
 * Fact ids are shown under each claim for the same reason. They look like
 * clutter until you try to check one, at which point they are the only reason
 * checking is possible.
 */
export function ScoutingReport({ data }: { data: ScoutingReportResponse }) {
  const { report, audit } = data;
  const allTraced = audit.numbersTraced === audit.numbersTotal;
  const failed = audit.checks.filter((check) => !check.passed);

  return (
    <Card
      title="Scouting report"
      subtitle={`Written by ${data.reportModel} from a fixed evidence bundle, then checked.`}
    >
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <span
          className={`rounded-lg border px-3 py-1.5 ${
            allTraced
              ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
              : "border-amber-400/40 bg-amber-400/10 text-amber-200"
          }`}
        >
          {audit.numbersTraced}/{audit.numbersTotal} numbers traced to source
        </span>
        <span className="text-slate-400">
          {data.named
            ? "Named mode — the model was told who this is."
            : "Written blind: the model was not given the player's name."}
        </span>
      </div>

      {failed.length > 0 ? (
        <div className="mb-4">
          <Explanation
            tone="warning"
            title={`${failed.length} check${failed.length > 1 ? "s" : ""} failed`}
            detail={failed.map((check) => `${check.name}: ${check.detail}`).join(" · ")}
          />
        </div>
      ) : null}

      {data.named ? (
        <div className="mb-4">
          <Explanation
            tone="warning"
            title="Groundedness is not independently verifiable here"
            detail={
              "With the name in the evidence, a model can write a fluent report from what it " +
              "already knew and still pass every check. The groundedness figures quoted " +
              "elsewhere in this project come from anonymized runs for that reason."
            }
          />
        </div>
      ) : null}

      <p className="mb-5 text-lg font-medium text-white">{report.headline}</p>

      <div className="flex flex-col gap-4">
        <Claim label="Projection" text={report.projection.text} ids={report.projection.fact_ids} />
        <Claim
          label="Uncertainty"
          text={report.uncertainty.text}
          ids={report.uncertainty.fact_ids}
        />

        <ClaimList label="Strengths" claims={report.strengths} />
        <ClaimList label="Risks" claims={report.risks} />
      </div>

      <p className="mt-5 text-xs text-slate-400">
        Self-reported confidence: <strong className="text-slate-200">{report.confidence}</strong>.
        The report was written from the projection and its interval only — what the player actually
        did after the move was never in its evidence.
      </p>
    </Card>
  );
}

function Claim({ label, text, ids }: { label: string; text: string; ids: string[] }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-sm text-slate-200">{text}</p>
      <FactIds ids={ids} />
    </div>
  );
}

function ClaimList({
  label,
  claims,
}: {
  label: string;
  claims: { text: string; fact_ids: string[] }[];
}) {
  if (claims.length === 0) return null;
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <ul className="mt-1 flex flex-col gap-2">
        {claims.map((claim) => (
          <li key={claim.text} className="text-sm text-slate-200">
            {claim.text}
            <FactIds ids={claim.fact_ids} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function FactIds({ ids }: { ids: string[] }) {
  return (
    // slate-400, not slate-500: at 11px on this surface the latter measures
    // 4.12:1 against a 4.5:1 floor.
    <p className="mt-1 font-mono text-[11px] text-slate-400">
      <span className="sr-only">Supported by evidence </span>
      {ids.join(" ")}
    </p>
  );
}
