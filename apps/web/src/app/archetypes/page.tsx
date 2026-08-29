import { Card, Explanation, Provenance, Table } from "../../components/ui";
import type { ArchetypeDefinition } from "../../lib/api";
import { apiGetOptional, isProblem } from "../../lib/api";
import { decimal, integer } from "../../lib/format";

/**
 * Rendered per request rather than prerendered at build time: the content is
 * database-backed, and a build should not require a running API.
 */
export const dynamic = "force-dynamic";

export default async function ArchetypesPage() {
  const result = await apiGetOptional<ArchetypeDefinition[]>("/archetypes");
  if (isProblem(result)) {
    return <Explanation title={result.title} detail={result.detail} />;
  }

  const unstable = result.data.filter((row) => !row.reportable);

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Archetypes"
        subtitle="Five clusters over role statistics and the composition of shooting possessions. Descriptive, never predictive — none of this says who is better."
      >
        <p className="text-sm text-fg-muted">
          Shot-type shares sum to one, so they are transformed with a centred log-ratio before
          anything measures distance between them; standardisation is within-season, because
          three-point rate in 2000-01 and 2024-25 describe different sports.
        </p>
      </Card>

      {unstable.length > 0 ? (
        <Explanation
          tone="warning"
          title={`${unstable.length} cluster${unstable.length > 1 ? "s" : ""} should be read as unclassified`}
          detail={
            "Clusters are not equally real. Those below the stability floor barely reproduce " +
            "when the data is resampled, so they are a boundary of the method rather than a " +
            "player type — and they are flagged here rather than presented as one."
          }
        />
      ) : null}

      <Card>
        <Table
          caption="Archetype clusters with bootstrap stability"
          headers={["Cluster", "Members", "Distinguished by", "Exemplars", "Stability"]}
          rows={result.data.map((row) => [
            `#${row.cluster}`,
            integer(row.nMembers),
            <span key="f" className="text-xs text-fg-muted">
              {row.topFeatures}
            </span>,
            <span key="e" className="text-xs">
              {row.exemplars}
            </span>,
            <span
              key="s"
              className={row.reportable ? "text-good" : "text-warn"}
              title={
                row.reportable
                  ? "Reproduces under resampling"
                  : "Below the stability floor — read as unclassified"
              }
            >
              {decimal(row.stabilityJaccard, 2)}
              {row.reportable ? "" : " — unclassified"}
            </span>,
          ])}
        />
      </Card>

      <Card title="How k was chosen">
        <p className="text-sm text-fg-muted">
          Two criteria disagreed. Held-out log-likelihood keeps improving as clusters are added but
          flattens after five; bootstrap stability collapses from a mean Jaccard of 0.52 at k=5 to
          0.40 at k=6. Where they disagree the smaller k wins, so k=5 — and the resulting mean
          stability of 0.52 is <strong>moderate</strong>, meaning real structure rather than a crisp
          taxonomy.
        </p>
      </Card>

      <Provenance snapshot={result.meta.snapshot} />
    </div>
  );
}
