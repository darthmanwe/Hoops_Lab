# Model card — archetypes and shooting

`roles-v1.0`

Two descriptive models. Neither forecasts anything, and neither is presented as
if it did.

## What replaced what

| Removed                 | Why                                                                                                                                                                             | Replacement                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `archetype_vector_json` | A hand-written five-element vector, with cosine similarity run over it inside the Worker on every request.                                                                      | A fitted Gaussian mixture over role features, with comparables precomputed in Python. |
| `nba_gravity`           | Gravity measures defensive attention, which needs optical tracking data. The NBA does not publish it; the EuroLeague does not collect it. The stored values were typed by hand. | `player_shooting` — three-point threat, named for what it measures.                   |

## Archetypes

**Features.** Usage, true shooting, assist rate, turnover rate, assists and
rebounds per 75, plus the composition of shooting possessions (two-point,
three-point, free throw). Deliberately excludes volume: an archetype is _how_ a
player plays, and including totals would mostly recover minutes played.

**Two preprocessing decisions carry the weight.**

_Shot mix is compositional._ The three shares sum to one, so they live on a
simplex where Euclidean distance and PCA are not meaningful — raising one share
mechanically lowers the others, and a method assuming independent dimensions
reads that constraint as structure. A centred log-ratio transform is applied
first.

_Standardisation is within-season._ Three-point rate in 2000-01 and 2024-25
describe different sports. Pooled, the strongest cluster any method finds is
"which era is this" — true, and useless.

**Method.** CLR → within-season z-scores → PCA to 90% of variance → Gaussian
mixture with full covariance. A mixture rather than k-means because archetypes
genuinely overlap, and the soft membership is the informative output.

### Choosing k, and why the criteria disagree

Held-out log-likelihood, fitted on earlier seasons and scored on later ones:

| k       | 3      | 4      | 5          | 6      | 7      | 8      | 9      | 10     |
| ------- | ------ | ------ | ---------- | ------ | ------ | ------ | ------ | ------ |
| log-lik | −6.468 | −6.452 | **−6.428** | −6.431 | −6.416 | −6.409 | −6.411 | −6.401 |

It improves almost monotonically — larger k always fits a bit better — but
flattens after 5. Bootstrap stability moves the other way:

| k     | mean Jaccard | worst cluster |
| ----- | ------------ | ------------- |
| 4     | 0.524        | 0.41          |
| **5** | **0.519**    | **0.42**      |
| 6     | 0.403        | 0.27          |
| 7     | 0.406        | 0.21          |

Stability collapses at k≥6. Where the criteria disagree the smaller k wins, so
**k = 5**.

### The clusters, and how much to trust them

12,213 player-seasons, 500-minute floor.

| Cluster | n     | Distinguished by                            | Exemplars                              | Stability |
| ------- | ----- | ------------------------------------------- | -------------------------------------- | --------- |
| 0       | 2,451 | high usage and assist rate, few rebounds    | Iverson, Kobe Bryant, Antoine Walker   | 0.55      |
| 1       | 1,657 | very high assist rate and turnovers         | Eric Snow, Deron Williams, Jason Terry | 0.54      |
| 2       | 1,862 | no threes, heavy free throws, most rebounds | Dwight Howard, Ben Wallace             | 0.53      |
| 3       | 1,684 | rebounds, few threes                        | Tim Duncan, Kevin Garnett              | **0.42**  |
| 4       | 4,559 | highest three-point share, fewest turnovers | Peja Stojaković, Joe Johnson           | 0.56      |

**Mean stability is 0.52, which is moderate — real structure, not a crisp
taxonomy.** Cluster 3 falls below the 0.45 floor and is served with
`reportable: false`, meaning it should be read as _unclassified_ rather than as
a player type. That flag is in the API payload, not only on this page.

## Shooting

Empirical-Bayes shrinkage of three-point percentage toward a per-league-season
Beta prior fitted by method of moments from players with ≥50 attempts.

The problem it solves: a player who makes 4 of 6 threes has an observed 66.7%,
which measures nothing. Shrinkage pulls each observation toward the prior in
proportion to how little evidence supports it.

`shrinkage_weight` is served alongside every value — the fraction of the
posterior coming from the player's own attempts:

| Attempts | Raw   | Shrunk | Weight |
| -------- | ----- | ------ | ------ |
| 1        | 1.000 | 0.358  | 0.01   |
| 10       | 0.200 | 0.337  | 0.10   |
| 35       | 0.371 | 0.362  | 0.27   |
| 876      | 0.408 | 0.403  | 0.90   |

A 40-attempt shooter is mostly prior, and saying so is the difference between a
measurement and an impression. `spacing_score` multiplies the shrunk rate by
attempts per 75 possessions, because a great shooter who never shoots does not
stretch a defence.

The leaderboard excludes anyone below 20 attempts. Ranking on a mostly-prior
number would put the smallest samples on top — the exact failure shrinkage
exists to prevent.

## Out-of-scope use

- **These are not ratings.** Neither model says who is better.
- **Archetype labels are not positions**, and cluster 3 in particular should not
  be treated as a named type.
- **Shooting threat is not gravity.** It does not measure defensive attention,
  and no public data supports a metric that does.

## Reproducing

`hoopslab export` refits both models from committed gold with no network access
and regenerates every serving table.
