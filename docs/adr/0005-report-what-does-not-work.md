# 5. Metrics that fail are served, not removed

Accepted.

## Context

The translation model beats every baseline on usage rate and **loses to
predicting the league average on true shooting**, by 0.3%. Stage-1 persistence
for true shooting has R² = 0.30 against 0.74 for usage: shooting efficiency is
mostly year-to-year noise.

The tempting move is to publish the metric that worked.

## Decision

Both are published, and the API reports its own failure as data:

- `model_evaluations.beats_best_baseline` is served as `false` for `ts_pct`.
- `skill_vs_best` carries the signed margin.
- The web page renders a warning above the number rather than a footnote below
  it.
- Archetype clusters below the bootstrap stability floor are served with
  `reportable: false` and labelled "unclassified" rather than named.
- Shrinkage weight is served alongside every shrunk shooting number, so a
  40-attempt shooter is visibly mostly prior.

Endpoints whose underlying quantity cannot exist from public data return **410
Gone with the reason**, not a plausible number. There is no gravity metric,
because no public tracking data supports one. Lineup offensive rating returns
`projection: null` with `projection_unavailable_reason`.

## Consequences

- A consumer can tell a working metric from a broken one without reading
  documentation.
- The presentation is less flattering and more useful. A model card showing
  only the metric that worked is the more impressive artefact and the less
  trustworthy one.
- Shipping an honest `null` is the single most credible thing this repository
  does, and it costs a feature to do it.
