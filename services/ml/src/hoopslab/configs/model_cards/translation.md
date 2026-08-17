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

**Transition pairs: 414 observed**, all of which enter the fit.

An earlier build fitted only 324 of them. `leaguedashplayerstats` returns no
AGE column for the G League, age is a covariate here, and the transition frame
drops rows without one — so every pair _originating_ in the G League was
discarded in silence. Age was first recovered from the same person's seasons in
leagues that do report it, which is arithmetic rather than imputation and
restored the missing 90 pairs.

That recovery is no longer the main source. `leaguedashplayerbiostats` accepts
`league_id` and serves the G League directly, one request per season — a fact a
comment in this repository denied for several phases, having reasoned from the
absence of a `league_id_nullable` parameter without calling the endpoint. It
cost nothing here, because every G League player in a transition pair has an
NBA season by definition. It cost a great deal one layer over, where projecting
players who have _not_ moved needs an age for people who never reached the NBA:
2,129 G League seasons had none, and 716 players were excluded from that feature
by a docstring. Direct ingestion leaves 6 seasons without an age.

A pair requires ≥400 minutes in the source league, ≥300 in the target, a gap of
one or two seasons, and no appearance in the target league during the source
season.

Candidates are then reduced to a **matching**: within a person and direction,
each source season and each target season is used at most once. Deduplicating
only one side is not enough — two qualifying seasons before a move duplicate
the response variable, and one source season with both a one- and a two-season
gap counts the same departure twice. An earlier version deduplicated on the
target alone and reported 96 EuroLeague→NBA pairs; the correct figure is 61.

| Direction             | Pairs | Players |
| --------------------- | ----- | ------- |
| NBA → G League        | 134   | 132     |
| NBA → EuroLeague      | 115   | 110     |
| EuroLeague → NBA      | 61    | 61      |
| G League → NBA        | 45    | 45      |
| G League → EuroLeague | 45    | 45      |
| EuroLeague → G League | 14    | 14      |

## Targets

`usg_pct` and `ts_pct`, modelled as separate primitives. Composites are
deliberately avoided: the previous version of this project served an
"NBA equivalent rating" that could not be checked against anything the player
subsequently did.

## Method

Two stages, because almost nothing can be estimated from a few hundred pairs.

**Stage 1 — ordinary season-to-season dynamics.** Fitted on 7,902 consecutive
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

Out-of-fold, in rate units, n = 367 evaluated pairs.

| Metric    | MAE        | 95% CI (cluster bootstrap) | Best baseline        | Verdict                      |
| --------- | ---------- | -------------------------- | -------------------- | ---------------------------- |
| `usg_pct` | **0.0332** | [0.0306, 0.0357]           | 0.0428 (league mean) | **beats it by 22.4%**        |
| `ts_pct`  | 0.0472     | [0.0433, 0.0513]           | 0.0470 (league mean) | **loses by 0.4% — unusable** |

All four baselines, `usg_pct`:

| Baseline                       | MAE    | Model better by |
| ------------------------------ | ------ | --------------- |
| League mean                    | 0.0428 | 22.4%           |
| Stage-1 persistence, no league | 0.0504 | 34.1%           |
| z-preservation                 | 0.0527 | 37.1%           |
| Folk ×0.75 rule                | 0.0749 | 55.7%           |

Shuffled-target controls: 0.0427 for usage, 0.0523 for true shooting. Both are
worse than the fitted model and close to the league-mean baseline, which is
what a clean pipeline looks like.

**Estimated compression.** Shared slope β = **0.727** for usage, 0.693 for true
shooting. A slope below one means standing within a league compresses on the
way across.

### The model does not work for true shooting

On the corrected cohort it is **worse than predicting the league average**
(0.0472 against 0.0470). It should not be used for that metric, and the API
says so: `model_evaluations.beats_best_baseline` is served as `false`, so a
consumer can tell without reading this page.

It is kept and published rather than quietly dropped. Removing the metric that
did not work would leave a model card showing only the metric that did, which
is the more flattering and less honest presentation.

## Known failure modes and caveats

- **True shooting is not predictable by this model** — see above. Stage-1
  persistence for that metric has R² = 0.30 against 0.73 for usage; shooting
  efficiency is mostly year-to-year noise.
- **The direction-specific slopes disagree, and by more than before.** For
  usage, EL→NBA is 0.580 and NBA→EL is 0.986, a gap of 0.41. The shared-slope
  restriction is therefore doing substantial work, and a meaningful part of the
  estimated compression is direction-specific rather than a property of the
  leagues alone. On the smaller, correctly matched cohort this is the largest
  open question about the estimate.
- **The folk ×0.75 rule is worse than predicting the league average.** Worth
  knowing, and the reason it is included as a baseline at all.
- **Stage-1 persistence alone is worse than the league mean** for usage (0.0504
  vs 0.0428). Applying same-league dynamics to a cross-league move without an
  offset actively misleads, which is the clearest evidence that the league term
  is load-bearing rather than decorative.
- **Small and uneven folds.** Some target seasons contribute only a handful of
  pairs; fold sizes are recorded in the run log.
- **G League ages come from the bio endpoint, and 6 seasons still lack one.**
  `leaguedashplayerstats` carries no AGE column for that league, which for
  several phases was taken to mean no source did; ages were derived from the
  same person's seasons elsewhere, so anyone who never left the G League had
  none. `leaguedashplayerbiostats` accepts `league_id` and reports them
  directly. Derivation is now the fallback rather than the mechanism, and the
  residual is 6 player-seasons instead of 2,129.

## Selection

The single largest threat to the interpretation, so it is measured three ways.

**Shown.** How far above their own league the movers sat, in standard
deviations of usage:

| Direction        | Movers | Gap vs peers |
| ---------------- | ------ | ------------ |
| EuroLeague → NBA | 61     | **positive** |
| NBA → EuroLeague | 115    | **negative** |
| NBA → G League   | 134    | negative     |

Exact figures are in the run log and served at
`/models/{version}/evaluation`.

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
