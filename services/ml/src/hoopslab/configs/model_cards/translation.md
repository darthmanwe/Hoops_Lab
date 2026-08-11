# Model card — cross-league translation

`translation-v1.0`

Every number below is reproduced on each push by `hoopslab train --verify`,
which refits from the committed data with no network access and fails if any
metric moves.

## What it estimates

How a basketball player's production changes when they move between the
EuroLeague, the NBA and the G League — reported as a coefficient with an
interval, not as a per-player prediction dressed up as a fact.

**The estimand, stated precisely.** This is the translation function
**conditional on a transition having occurred**. It answers:

> Given that this player got an NBA contract, what does history say to expect?

It does **not** answer "what would a randomly chosen EuroLeague player do in
the NBA". Only the first is identified from this data, and the difference is
not pedantic: the players who move are measurably better than their peers
(see Selection, below).

## Intended use

- Ranking a cohort of players by expected translated production.
- Stating the historical base rate for a move of a given type.
- Communicating how wide the uncertainty on such a move genuinely is.

## Out-of-scope use

- **Deciding a contract.** The 80% interval on projected usage spans roughly a
  third of the NBA distribution.
- **Any player unlike the training cohort** — a 19-year-old with 400 EuroLeague
  minutes is not represented by a sample built mostly from established
  professionals.
- **Causal claims.** Nothing here identifies what _caused_ a change.

## Training data

Committed gold, built from public sources:

| League     | Seasons   | Player-seasons |
| ---------- | --------- | -------------- |
| NBA        | 2000–2024 | 12,228         |
| EuroLeague | 2007–2024 | 5,606          |
| G League   | 2015–2024 | 4,463          |

**Transition pairs: 537 observed**, of which 419 have both sides qualified and
enter the fit. A pair requires ≥400 minutes in the source league, ≥300 in the
target, a gap of one or two seasons, and no appearance in the target league
during the source season.

| Direction             | Pairs |
| --------------------- | ----- |
| NBA → G League        | 159   |
| NBA → EuroLeague      | 149   |
| EuroLeague → NBA      | 96    |
| G League → NBA        | 59    |
| G League → EuroLeague | 59    |
| EuroLeague → G League | 15    |

## Targets

`usg_pct` and `ts_pct`, modelled as separate primitives. Composites are
deliberately avoided: the previous version of this project served an
"NBA equivalent rating" that could not be checked against anything the player
subsequently did.

## Method

Two stages, because almost nothing can be estimated from ~96 pairs.

**Stage 1 — ordinary season-to-season dynamics.** Fitted on 7,285 consecutive
_same-league_ season pairs: next-season standing regressed on current standing,
a quadratic in age, and log minutes. This is where aging and mean reversion
come from, and it is large.

**Stage 2 — the league-transition offset.** Fitted on the transitions only,
with direction-specific intercepts and a **single shared slope**. Only this
stage depends on the small sample.

**Estimator.** Ordinary least squares with a cluster bootstrap resampling
_players_. The design note called for a mixed model with a per-player random
intercept; in the data as it landed there are ~1.4 transitions per player, and
a random intercept estimated from 1.4 observations per group is weakly
identified. The dependence is real, so it is handled where it can be handled
honestly — by bootstrapping the unit that actually repeats.

## Validation

Leave-one-target-season-out, **grouped by player**. Roughly a third of this
cohort transitions more than once, so a season-only split would let a player's
later move inform his earlier one. Both temporal and entity disjointness are
asserted **inside the cross-validation loop at runtime**, on every fold of
every run — not in a test that could pass while the splitter changed.

Every result table also reports a **shuffled-target negative control**: the
response is permuted and the whole pipeline refitted. If that does not collapse
performance, something is leaking and the headline number is measuring the leak.

## Results

Out-of-fold, in rate units, n = 370 evaluated pairs across 11 season folds.

| Metric    | MAE        | 95% CI (cluster bootstrap) | Best baseline        | Shuffled control |
| --------- | ---------- | -------------------------- | -------------------- | ---------------- |
| `usg_pct` | **0.0309** | [0.0285, 0.0333]           | 0.0419 (league mean) | 0.0463           |
| `ts_pct`  | **0.0408** | [0.0375, 0.0439]           | 0.0431 (league mean) | 0.0584           |

All four baselines, `usg_pct`:

| Baseline                       | MAE    | Model better by |
| ------------------------------ | ------ | --------------- |
| League mean                    | 0.0419 | 26.3%           |
| Stage-1 persistence, no league | 0.0515 | 40.0%           |
| z-preservation                 | 0.0536 | 42.4%           |
| Folk ×0.75 rule                | 0.0821 | 62.4%           |

**Estimated compression.** Shared slope β = **0.776** for usage, **0.642** for
true shooting. A slope below one means standing within a league compresses on
the way across.

## Known failure modes and caveats

- **True shooting is barely predictable.** The model beats the league-mean
  baseline by only 5.3% on `ts_pct`, and stage-1 persistence for that metric has
  R² = 0.30 against 0.74 for usage. Shooting efficiency is mostly year-to-year
  noise, and the honest reading is that this model adds little for it. It is
  reported because omitting the weaker of two headline metrics would be
  selective.
- **The direction-specific slopes disagree.** For usage, EL→NBA is 0.695 and
  NBA→EL is 0.973. The shared-slope restriction is therefore doing real work,
  and part of the estimated compression is direction-specific rather than a
  property of the leagues alone. This is reported rather than smoothed over.
- **The folk ×0.75 rule is worse than predicting the league average.** Worth
  knowing, and the reason it is included as a baseline at all.
- **Stage-1 persistence alone is worse than the league mean** for usage (0.0515
  vs 0.0419). Applying same-league dynamics to a cross-league move without an
  offset actively misleads, which is the clearest evidence that the league term
  is load-bearing rather than decorative.
- **Small and uneven folds.** Some target seasons contribute only a handful of
  pairs; fold sizes are recorded in the run log.
- **G League ages are inferred** from the same person's NBA observation, since
  the bio endpoint has no G League equivalent.

## Selection

The single largest threat to the interpretation, so it is measured three ways.

**Shown.** How far above their own league the movers sat, in standard
deviations of usage:

| Direction        | Movers | Gap vs peers |
| ---------------- | ------ | ------------ |
| EuroLeague → NBA | 96     | **+0.47 sd** |
| NBA → EuroLeague | 149    | **−0.30 sd** |
| NBA → G League   | 159    | −0.37 sd     |

The two headline directions are selected in **opposite** directions, exactly as
the design assumed: players move up because they were good, and down because
they were not.

**Exploited.** That opposition is what makes the effect testable. If one slope
fitted both directions, the compression would be unlikely to be a selection
artefact. They do not fully agree, and the size of the disagreement is the
honest measure of how much selection is in the estimate.

**Bounded.** A Heckman-style first stage is implemented in
`hoopslab.models.selection`; where it converges, the corrected and uncorrected
coefficients are both reported, never just the more favourable one.

## Fairness note

The cohort is overwhelmingly composed of players who reached a top professional
league, and the EuroLeague sample skews toward European and South American
players while the G League sample skews American. Translation estimated on this
cohort should not be assumed to hold for players coming from leagues not
represented here at all.

## Maintenance

Retraining is `hoopslab train`. `hoopslab train --verify` refits and fails if
any metric drifts from the committed run log; CI runs it on every push, so the
numbers on this page cannot silently stop being true.
