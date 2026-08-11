# Modelling

> **Status: nothing here is fitted yet.** This document describes what will be
> built and how it will be evaluated. It deliberately contains no results,
> because there are none. The previous version of this file listed six modules
> under the heading "Implemented API coverage" when what existed was a set of
> routes that `SELECT`ed hand-written constants.

## What was removed, and why

| Removed                                      | Reason                                                                                                                                                                                                      |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nba_gravity`, `team_gravity_effect`         | Gravity measures defensive attention, which requires optical player-tracking data. The NBA does not publish it. The stored values were typed by hand.                                                       |
| `game_momentum`                              | `swing_index` and friends were constants. Real run/momentum statistics need play-by-play data that is not yet ingested.                                                                                     |
| `clutch_impact`                              | A constant on an undefined scale. Clutch estimated from per-player clutch samples is almost entirely noise.                                                                                                 |
| `team_fatigue_effect.fatigue_score`          | An invented composite. Rest days and travel distance are exactly computable and survive as schedule features; the "score" does not.                                                                         |
| `nba_equivalent_rating`, `translation_score` | Unfalsifiable composites. Translation is now modelled on primitives (usage, TS%, assist rate) that can each be checked against what actually happened.                                                      |
| `offense_projection` (lineup)                | Nine coefficients hardcoded in a route handler. Nothing fitted them. Lineup offensive rating cannot be projected without possession-level data, so the endpoint will return an explicit `null` and say why. |

## 1. Cross-league translation — the flagship

### The claim, stated precisely

The model estimates the translation function **conditional on a transition
having occurred**. It answers:

> Given that this player got an NBA contract, what does history say to expect?

It does **not** answer "what would a randomly chosen EuroLeague player do in
the NBA." Those are different questions and only the first is identified from
this data. Every reported figure is conditional on selection.

### Why this is framed as estimation rather than prediction

"Predict player X's NBA stats" invites the question "how accurate is it for
player X?", whose honest answer is _not very_ — the per-player intervals are
wide and will stay wide. Framing the deliverable as a coefficient estimate with
an interval means a wide interval is a result rather than a failure.

### Pair construction

A pair is `(player, source league A, season s) → (target league B, season s+k)`
where the player recorded ≥400 minutes in A during `s`, ≥300 minutes in B
during `s+k`, did not appear in B during `s`, and `k ∈ {1, 2}`.

Four directions are modelled, not one:

| Direction        | Expected pairs | Why it is included                                                                                                                  |
| ---------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| EuroLeague → NBA | ~40–80         | The headline question.                                                                                                              |
| NBA → EuroLeague | ~85–170        | Triples the sample, and is selected in the _opposite_ direction, which is what makes selection bias measurable rather than assumed. |
| G League → NBA   | ~150–300       | Stabilises the shared structure so the EuroLeague pairs can borrow strength instead of carrying the whole fit.                      |
| NBA → G League   | ~50–150        | Same, in the other direction.                                                                                                       |

**The exact counts get published as soon as they exist, before any modelling.**
If EuroLeague → NBA lands below 40 usable pairs, the response — decided now,
not after seeing the number — is to report coefficient estimates with
leave-one-season-out intervals only, and to refuse to serve per-player point
predictions. The serving schema enforces this: the prediction-interval columns
are `NOT NULL`, so a bare point estimate cannot physically be stored.

### Two-stage structure

The reason a sample of ~60 is usable at all is that almost nothing is estimated
from it.

**Stage 1 — ordinary player-season dynamics**, fit on _same-league_ consecutive
pairs, where n is in the thousands (NBA ≈ 10,000, EuroLeague ≈ 4,000):

```
z_{s+1} = a(age_s) + b(age_s)·z_s + c·log(minutes_s) + ε
```

with a natural cubic spline on age. This captures aging and regression to the
mean, which are not specific to changing leagues.

**Stage 2 — the league-transition offset**, fit only on transition pairs:

```
z^B_{s+k} = α_direction + β·ẑ_persist + γ·log(minutes^A) + δ_position + η·gap + ε
```

`α` and `β` are the objects of interest. `β < 1` means EuroLeague z-scores
compress in the NBA. Aging is estimated at n≈10,000; only the league offset
depends on the small sample.

### Family

Hierarchical linear (`statsmodels` MixedLM) with a cluster bootstrap that
resamples **players**, not rows, because repeat transitions exist
(NBA → EuroLeague → NBA).

Gradient boosting is deliberately **not** used. At n≈200 it overfits and
provides no usable uncertainty. This is a small-sample inference problem, not a
prediction problem, and choosing the tool that produces a confidence interval
over the tool that produces a leaderboard score is the whole point.

### Baselines, all reported every time

1. Target-league minutes-weighted mean — the scale reference.
2. The folk **×0.75 rule of thumb**, implemented literally.
3. **z-preservation** (`z_B = z_A`) — the strongest naive baseline, and the one
   `β < 1` is defined against.
4. Stage-1 persistence with **no league term** — isolates what the league
   switch actually adds over "players change from year to year".

A model that does not beat (3) and (4) has not demonstrated anything.

### Selection bias — three treatments, all shipped

1. **Show it.** Plot the z-distribution of all qualified source-league players
   against the transitioning subset. The cohort is expected to sit well above
   the league mean. One figure does more for credibility than any correction.
2. **Bound it.** Heckman two-step: fit `P(transition | z, age, minutes, era)`,
   include the inverse Mills ratio as a regressor, and report `β` with _and_
   without the correction.
3. **Exploit it.** Direction-specific intercepts with a shared slope. Positive
   and negative selection pull opposite ways; agreement between the
   direction-specific slopes is evidence the slope is not selection-driven,
   and disagreement quantifies how much of it is.

### Validation

Leave-one-target-season-out, grouped by **player**. Pooled out-of-fold MAE with
cluster-bootstrap confidence intervals and fold sizes stated. Temporal and
entity disjointness are asserted **inside the cross-validation loop at
runtime**, not checked once in a test. Every backtest also runs a
shuffled-target negative control whose score is reported alongside the real
one; if shuffling does not collapse performance to baseline, there is leakage.

## 2. Game outcome and margin — the calibration deliverable

Deliberately not a flagship. Nobody is impressed by an NBA game predictor;
competent reviewers are impressed by a reliability diagram and an honest
statement of where the model loses.

- Features are strictly pre-game and lagged: Elo difference, rest days,
  back-to-back flags, travel distance, game density, shifted rolling net
  rating, season-to-date pace.
- **Walk-forward by season. Never a random split.**
- Metrics in order of usefulness: log loss, Brier, Brier skill score, expected
  calibration error, reliability diagram with binned counts. AUC last, labelled
  as the least informative.
- Baselines: home team always wins, Elo alone, and the Vegas closing line.

The expected result is that the model loses to the closing line, and the README
will say so with the number attached. A backtest showing positive ROI against
closing lines without accounting for vig and line movement is showing a bug,
not an edge.

## 3. Player archetypes

Replaces a hand-written five-element vector.

Two preprocessing decisions carry most of the weight:

- **Shot-zone shares are compositional data.** They sum to one, so they live on
  a simplex where Euclidean distance and PCA are wrong — increasing one zone
  mechanically decreases every other. A centred log-ratio transform is applied
  before standardising.
- **Standardisation is within-season.** Three-point rate in 2013-14 and in
  2024-25 describe different sports; without this the first cluster found is
  "the year".

Gaussian mixture with full covariance rather than k-means, because archetypes
genuinely overlap and the soft membership is the interesting output. `k` is
chosen by three published criteria — out-of-sample BIC, silhouette, and
bootstrap stability — and where they disagree, the smaller `k` wins and the
disagreement is reported.

**Per-cluster stability is published, including the unstable clusters.**
Rim-running centres will be sharp; the combo-forward bucket will not be, and
saying so is more useful than presenting five equally confident labels.

## 4. Shooting

An empirical-Bayes shrunk three-point percentage: Beta-Binomial shrinkage
toward a position-group prior, with the shrinkage weight itself exposed so a
reader can see that a 40-attempt shooter is mostly prior.

This measures shooting _threat_. It does not measure defensive attention, and
it is not named as though it does.

## Roadmap position

| Phase       | Deliverable                                                                           |
| ----------- | ------------------------------------------------------------------------------------- |
| 1           | Real data, identity resolution, data contracts                                        |
| 2           | Translation model, evaluation, model card                                             |
| 4           | Archetypes, shooting, game calibration                                                |
| 8 (stretch) | Play-by-play, stint reconstruction, RAPM with standard errors, real lineup projection |

Until phase 8, lineup offensive rating and any impact metric remain
unavailable, and the API says so rather than shipping a placeholder.
