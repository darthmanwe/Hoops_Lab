"""Rate statistics, computed identically for every league.

**This is the most important design decision in the data layer.**

`stats.nba.com` publishes official ``USG_PCT`` and ``TS_PCT``. The EuroLeague
publishes neither, so they have to be derived from counting stats. Taking the
official numbers for one league and derived numbers for the other would be a
mistake that is very hard to see afterwards: the estimated translation
coefficient would absorb the difference between two *formulas* alongside the
difference between two *leagues*, and there would be no way to tell how much of
the result was which.

So every rate here is computed from counting stats, for all three leagues, with
one implementation. The official NBA values are still carried through to gold,
but only as a validation series — :func:`usage_rate` should reproduce them to
within rounding, and a data-contract check asserts that it does. If the formula
is wrong, that check fails loudly instead of the error being absorbed into a
coefficient.

Definitions follow Basketball-Reference, which is the convention EuroLeague
analysts also use:

- ``TS% = PTS / (2 * (FGA + 0.44 * FTA))``
- ``USG% = 100 * (FGA + 0.44*FTA + TOV) * (TmMP/5) / (MP * (TmFGA + 0.44*TmFTA + TmTOV))``

The 0.44 free-throw weight is an estimate of trips to the line per free throw,
accounting for and-ones and technical shots. It is a convention rather than a
measurement, and it is applied consistently here for that reason.
"""

from __future__ import annotations

import polars as pl

#: Free-throw-to-possession weight. See module docstring.
FT_POSSESSION_WEIGHT = 0.44


def true_shooting_pct(
    pts: pl.Expr | str = "pts", fga: pl.Expr | str = "fga", fta: pl.Expr | str = "fta"
) -> pl.Expr:
    """Points per shooting possession, on the 0-1 scale.

    Returns null rather than zero when a player took no shots. A player with
    no attempts has *undefined* efficiency, not zero efficiency, and the
    previous version's habit of coercing missing values to 0 is exactly how a
    bench player ends up looking like the worst shooter in the league.
    """
    pts_e, fga_e, fta_e = (_expr(x) for x in (pts, fga, fta))
    attempts = 2 * (fga_e + FT_POSSESSION_WEIGHT * fta_e)
    return pl.when(attempts > 0).then(pts_e / attempts).otherwise(None)


def usage_rate(
    *,
    fga: pl.Expr | str = "fga",
    fta: pl.Expr | str = "fta",
    tov: pl.Expr | str = "tov",
    minutes: pl.Expr | str = "minutes",
    team_fga: pl.Expr | str = "team_fga",
    team_fta: pl.Expr | str = "team_fta",
    team_tov: pl.Expr | str = "team_tov",
    team_minutes: pl.Expr | str = "team_minutes",
) -> pl.Expr:
    """Share of team possessions a player used while on the floor, as 0-1.

    Returned on the 0-1 scale rather than 0-100 to match `stats.nba.com`'s
    ``USG_PCT``, so the validation check compares like with like.
    """
    fga_e, fta_e, tov_e, min_e = (_expr(x) for x in (fga, fta, tov, minutes))
    tfga_e, tfta_e, ttov_e, tmin_e = (
        _expr(x) for x in (team_fga, team_fta, team_tov, team_minutes)
    )

    player_possessions = fga_e + FT_POSSESSION_WEIGHT * fta_e + tov_e
    team_possessions = tfga_e + FT_POSSESSION_WEIGHT * tfta_e + ttov_e
    denominator = min_e * team_possessions

    return (
        pl.when((denominator > 0) & (min_e > 0))
        .then(player_possessions * (tmin_e / 5.0) / denominator)
        .otherwise(None)
    )


def per_75(stat: pl.Expr | str, minutes: pl.Expr | str = "minutes") -> pl.Expr:
    """Rate per 75 possessions, approximated as per-36-minutes scaled.

    Per-75 is preferred over per-36 for cross-league work because the leagues
    play different game lengths: an NBA game is 48 minutes, a EuroLeague game
    40. Comparing per-game or per-40 figures directly would make every
    EuroLeague player look less productive purely because of the clock.
    """
    stat_e, min_e = _expr(stat), _expr(minutes)
    return pl.when(min_e > 0).then(stat_e / min_e * 36.0).otherwise(None)


def ratio(numerator: pl.Expr | str, denominator: pl.Expr | str) -> pl.Expr:
    """Safe division that yields null, never zero or infinity, on a zero denominator.

    NaN and infinity are illegal in the gold layer: the previous version's SQL
    writer serialised them as the bare tokens ``nan`` and ``inf``, which are
    not valid SQLite and would fail an entire data load partway through.
    """
    num, den = _expr(numerator), _expr(denominator)
    return pl.when(den > 0).then(num / den).otherwise(None)


def _expr(value: pl.Expr | str) -> pl.Expr:
    return pl.col(value) if isinstance(value, str) else value
