# 4. The translation model is fitted in two stages, and estimates a conditional quantity

Accepted.

## Context

The flagship question — how production translates between leagues — is
identified from 61 EuroLeague→NBA transitions. Nothing useful can be estimated
from 61 observations if the model also has to learn how players age and revert
to the mean.

Worse, the cohort is not a sample of EuroLeague players. It is the subset good
enough to be offered an NBA contract, and it sits **+0.46 sd above its own
league's average usage**. The mirror direction is selected the opposite way:
players who move NBA→EuroLeague sit **−0.31 sd below** theirs.

## Decision

**Stage 1** estimates ordinary season-to-season dynamics — aging, mean
reversion, minutes — on 7,680 consecutive _same-league_ pairs.

**Stage 2** fits only the league-transition offset, on the 414 transitions,
with direction-specific intercepts and a single shared slope.

Aging is therefore estimated at n = 7,680. Only the league term depends on the
small sample.

The estimand is stated everywhere the model is reported:

> This estimates the translation function **conditional on a transition having
> occurred** — what history records for players who were selected to move, not
> what a randomly chosen player would do.

## Consequences

- Ordinary least squares with a cluster bootstrap resampling **players**, not a
  mixed model. There are ~1.4 transitions per player; a random intercept
  estimated from 1.4 observations per group is weakly identified. The
  dependence is real, so it is handled where it can be handled honestly.
- Selection is treated three ways rather than apologised for: shown (the gap is
  measured and served), exploited (opposite selection in the two directions
  makes the effect testable), and bounded (a Heckman first stage, reported with
  and without).
- The direction-specific slopes **disagree** — 0.579 for EL→NBA against 0.982
  for NBA→EL. The shared-slope restriction is doing real work, and that gap is
  the honest measure of how much selection remains in the estimate. It is
  published rather than smoothed.
