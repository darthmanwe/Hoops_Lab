import type { ReactNode } from "react";
import { MISSING } from "../lib/format";

export function Card({
  title,
  subtitle,
  children,
}: {
  title?: string | undefined;
  subtitle?: string | undefined;
  children: ReactNode;
}) {
  return (
    <section className="glass p-5">
      {title ? <h2 className="text-lg font-semibold text-fg">{title}</h2> : null}
      {subtitle ? <p className="mt-1 text-sm text-fg-muted">{subtitle}</p> : null}
      <div className={title ? "mt-4" : ""}>{children}</div>
    </section>
  );
}

/**
 * A single figure.
 *
 * `value` is a pre-formatted string precisely so that a caller cannot pass a
 * raw number and have a missing one render as zero — the formatting helpers
 * return an em dash, and this shows it with a tooltip rather than silently.
 */
export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string | undefined;
}) {
  const missing = value === MISSING;
  return (
    <div className="rounded-lg border border-edge bg-surface p-3">
      <p className="text-xs uppercase tracking-wide text-fg-subtle">{label}</p>
      <p
        // slate-400 rather than slate-500. Measured on the deployed site,
        // slate-500 on this surface is 4.12:1 against the 4.5:1 AA floor — and
        // of everything on the page it is the em dash, which exists so that a
        // missing value cannot be read as a zero. Styling it in the one colour
        // a reader with low vision cannot resolve defeats the point of it.
        className={`mt-1 text-xl font-semibold ${missing ? "text-fg-subtle" : "text-fg"}`}
        title={missing ? "Not recorded for this season" : undefined}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-fg-subtle">{hint}</p> : null}
    </div>
  );
}

/** Explains an expected absence, using the API's own problem document. */
export function Explanation({
  title,
  detail,
  tone = "neutral",
}: {
  title: string;
  detail: string;
  tone?: "neutral" | "warning" | undefined;
}) {
  const border = tone === "warning" ? "border-warn/50" : "border-edge";
  return (
    <div className={`rounded-lg border ${border} bg-surface p-4`}>
      <p className="font-medium text-fg">{title}</p>
      <p className="mt-1 text-sm text-fg-muted">{detail}</p>
    </div>
  );
}

/**
 * Provenance strip.
 *
 * Shown on every page that displays model output, because a number without its
 * version and its measured error is the thing this project was rebuilt to stop
 * publishing.
 */
export function Provenance({
  snapshot,
  model,
}: {
  snapshot: string | null;
  model?:
    | {
        version: string;
        primary_metric?: string | undefined;
        primary_value?: number | undefined;
        primary_ci?: [number, number] | null | undefined;
      }
    | undefined;
}) {
  return (
    <p className="text-xs text-fg-subtle">
      {model ? (
        <>
          <span className="text-fg-muted">{model.version}</span>
          {model.primary_value !== undefined ? (
            <>
              {" · "}
              {model.primary_metric} {model.primary_value.toFixed(4)}
              {model.primary_ci ? (
                <>
                  {" "}
                  [{model.primary_ci[0].toFixed(4)}, {model.primary_ci[1].toFixed(4)}]
                </>
              ) : null}
            </>
          ) : null}
          {" · "}
        </>
      ) : null}
      snapshot {snapshot ?? "unknown"}
    </p>
  );
}

export function Table({
  headers,
  rows,
  caption,
}: {
  headers: string[];
  rows: ReactNode[][];
  caption?: string | undefined;
}) {
  return (
    // Wide tables scroll inside their own container so the page body never
    // scrolls horizontally.
    //
    // `tabIndex` and `role` are what make that scrolling reachable without a
    // mouse. Every table here is `min-w-[36rem]`, so on a phone all of them
    // overflow, and a container that only scrolls by dragging leaves the
    // right-hand columns unreachable by keyboard. On the pages whose rows
    // contain links — projections, translation — tabbing to a link scrolls the
    // region incidentally, which is why axe reported this on the archetype,
    // model and career tables only: exactly the three that are pure data.
    <div
      className="overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      tabIndex={0}
      role="region"
      {...(caption ? { "aria-label": caption } : {})}
    >
      <table className="w-full min-w-[36rem] text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-edge-strong text-left text-xs uppercase tracking-wide text-fg-subtle">
            {headers.map((header) => (
              <th key={header} scope="col" className="px-2 py-2 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-edge last:border-0">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-2 py-2 text-fg-muted">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
