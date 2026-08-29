/**
 * The routes under test, and how each one proves it actually rendered.
 *
 * `expect` is the load-bearing field. Every page here is a server component
 * that fetches during render, and `apiGetOptional` converts a failed fetch into
 * a rendered explanation card rather than an error — so a broken backend
 * produces HTTP 200, a full layout, a nav, a heading, and no data. Asserting on
 * the status code, or on anything in the shell, passes in exactly the situation
 * the suite exists to catch.
 *
 * So each entry names a string that only a real response can produce: a
 * measured number, a player who exists in the committed fixture, a column
 * header that is only rendered when there are rows to put under it.
 *
 * The same idea as the `expect` guard in `scripts/screenshots.mjs`, and for the
 * same reason — a screenshot of the wrong card and a green test against an
 * empty page are the same class of quiet failure.
 */

export type Page = {
  path: string;
  /** Human name, used in test titles. */
  name: string;
  /** Text that appears only when the API answered with data. */
  expect: string;
};

export const PAGES: readonly Page[] = [
  {
    path: "/",
    name: "landing",
    // The measured usage MAE, which needs both /models and the evaluation
    // endpoint to have answered.
    expect: "0.0332",
  },
  {
    path: "/projections",
    name: "projections",
    // Printed under the table, and only when rows came back to count.
    expect: "Showing",
  },
  {
    path: "/translation",
    name: "translation",
    expect: "Projected usage rate",
  },
  {
    path: "/archetypes",
    name: "archetypes",
    // The per-cluster stability column. The prose above it renders without the
    // API, so asserting on the argument would not prove the data arrived.
    expect: "Jaccard",
  },
  {
    path: "/model",
    name: "model card",
    expect: "translation-v1.0",
  },
  {
    path: "/players/nba_1629029",
    name: "player",
    expect: "Luka Dončić",
  },
];
