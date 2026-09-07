"""Archetype and shooting models."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from hoopslab.models.archetypes import (
    clr_transform,
    describe_clusters,
    standardize_within_season,
)
from hoopslab.models.shooting import fit_beta_prior, shrink_three_point


class TestCentredLogRatio:
    def test_maps_a_simplex_to_a_zero_sum_space(self) -> None:
        shares = np.array([[0.5, 0.3, 0.2], [0.1, 0.8, 0.1]])
        transformed = clr_transform(shares)

        assert transformed.shape == shares.shape
        assert np.allclose(transformed.sum(axis=1), 0.0, atol=1e-9)

    def test_handles_a_zero_share_without_blowing_up(self) -> None:
        """A player who never attempted a three still needs a defined value."""
        transformed = clr_transform(np.array([[0.7, 0.0, 0.3]]))

        assert np.isfinite(transformed).all()

    def test_is_invariant_to_rescaling(self) -> None:
        """Compositional data carries only relative information, by definition."""
        a = clr_transform(np.array([[0.5, 0.3, 0.2]]))
        b = clr_transform(np.array([[50.0, 30.0, 20.0]]) / 100.0)

        assert np.allclose(a, b, atol=1e-9)

    def test_separates_shape_from_the_sum_constraint(self) -> None:
        """Two players with the same mix but different volume land together."""
        transformed = clr_transform(np.array([[0.6, 0.2, 0.2], [0.6, 0.2, 0.2]]))

        assert np.allclose(transformed[0], transformed[1])


class TestWithinSeasonStandardisation:
    def test_centres_each_season_separately(self) -> None:
        """Era adjustment: pooled, the first thing any clustering finds is the decade."""
        frame = pl.DataFrame(
            {
                "season_id": ["NBA_2000"] * 3 + ["NBA_2020"] * 3,
                "x": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
            }
        )
        out = standardize_within_season(frame, ["x"])

        assert out[:3].mean() == pytest.approx(0.0, abs=1e-9)
        assert out[3:].mean() == pytest.approx(0.0, abs=1e-9)
        # The 2020 block is ten times larger in raw units but identical once
        # standardised, which is the entire point.
        assert np.allclose(out[:3], out[3:])

    def test_a_constant_season_becomes_zero_rather_than_nan(self) -> None:
        frame = pl.DataFrame({"season_id": ["NBA_2000"] * 3, "x": [5.0, 5.0, 5.0]})
        out = standardize_within_season(frame, ["x"])

        assert np.isfinite(out).all()
        assert np.allclose(out, 0.0)


class TestBetaPrior:
    def test_recovers_the_population_mean(self) -> None:
        rng = np.random.default_rng(0)
        attempts = np.full(200, 300.0)
        makes = rng.binomial(300, 0.36, size=200).astype(float)

        alpha, beta = fit_beta_prior(makes, attempts)

        assert alpha / (alpha + beta) == pytest.approx(0.36, abs=0.02)

    def test_falls_back_when_there_is_too_little_evidence(self) -> None:
        assert fit_beta_prior(np.array([1.0]), np.array([3.0])) == (1.0, 1.0)


def shooting_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)


class TestShrinkage:
    @staticmethod
    def _population(n: int = 200) -> list[dict[str, object]]:
        """A league with genuine spread in shooting talent.

        Drawing every player from one true rate would be the wrong fixture:
        with no talent variance, method-of-moments correctly infers an
        extremely strong prior and shrinks even large samples heavily. Real
        populations differ, so the synthetic one does too — talent from a Beta,
        then binomial attempts around it.
        """
        rng = np.random.default_rng(1)
        talent = rng.beta(36, 64, size=n)  # mean 0.36, realistic spread
        return [
            {
                "season_id": "NBA_2020",
                "person_id": f"p{i}",
                "fg3a": 300.0,
                "fg3m": float(rng.binomial(300, talent[i])),
                "minutes": 2000.0,
            }
            for i in range(n)
        ]

    def test_a_tiny_sample_lands_near_the_prior(self) -> None:
        """The failure this exists to prevent: 2-for-3 reading as elite."""
        rows = [
            *self._population(),
            {
                "season_id": "NBA_2020",
                "person_id": "small",
                "fg3a": 3.0,
                "fg3m": 3.0,
                "minutes": 400.0,
            },
        ]
        result = shrink_three_point(shooting_frame(rows))
        small = result.filter(pl.col("person_id") == "small").row(0, named=True)

        assert small["fg3_pct_raw"] == 1.0
        assert small["fg3_pct_shrunk"] < 0.45
        assert small["shrinkage_weight"] < 0.05
        assert small["reportable"] is False

    def test_a_large_sample_stays_close_to_its_observed_rate(self) -> None:
        rows = [
            *self._population(),
            {
                "season_id": "NBA_2020",
                "person_id": "big",
                "fg3a": 800.0,
                "fg3m": 336.0,
                "minutes": 2800.0,
            },
        ]
        result = shrink_three_point(shooting_frame(rows))
        big = result.filter(pl.col("person_id") == "big").row(0, named=True)

        assert big["shrinkage_weight"] > 0.8
        assert abs(big["fg3_pct_shrunk"] - 0.42) < 0.02
        assert big["reportable"] is True

    def test_shrinkage_is_monotone_in_attempts(self) -> None:
        rows = [
            *self._population(),
            *[
                {
                    "season_id": "NBA_2020",
                    "person_id": f"v{n}",
                    "fg3a": float(n),
                    "fg3m": float(n) * 0.5,
                    "minutes": 1000.0,
                }
                for n in (10, 100, 500)
            ],
        ]
        result = shrink_three_point(shooting_frame(rows))
        weights = [
            result.filter(pl.col("person_id") == f"v{n}").row(0, named=True)["shrinkage_weight"]
            for n in (10, 100, 500)
        ]

        assert weights == sorted(weights)

    def test_spacing_score_rewards_volume_as_well_as_accuracy(self) -> None:
        """A great shooter who never shoots does not stretch a defence."""
        rows = [
            *self._population(),
            {
                "season_id": "NBA_2020",
                "person_id": "volume",
                "fg3a": 600.0,
                "fg3m": 228.0,
                "minutes": 2400.0,
            },
            {
                "season_id": "NBA_2020",
                "person_id": "sniper_no_volume",
                "fg3a": 40.0,
                "fg3m": 20.0,
                "minutes": 2400.0,
            },
        ]
        result = shrink_three_point(shooting_frame(rows))
        volume = result.filter(pl.col("person_id") == "volume").row(0, named=True)
        sniper = result.filter(pl.col("person_id") == "sniper_no_volume").row(0, named=True)

        assert volume["spacing_score"] > sniper["spacing_score"]

    def test_no_non_finite_values(self) -> None:
        rows = [
            *self._population(),
            {
                "season_id": "NBA_2020",
                "person_id": "zero",
                "fg3a": 0.0,
                "fg3m": 0.0,
                "minutes": 500.0,
            },
        ]
        result = shrink_three_point(shooting_frame(rows))

        for column in ("fg3_pct_shrunk", "shrinkage_weight", "spacing_score"):
            values = result[column].to_numpy().astype(float)
            assert np.isfinite(values).all()


def cluster_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    """A feature frame shaped like `build_feature_frame` output.

    Only the columns `describe_clusters` reads are varied; the rest are held
    constant so the exemplar ordering is decided by minutes alone.
    """
    return pl.DataFrame(
        [
            {
                "person_id": row["person_id"],
                "season_id": row["season_id"],
                "league": "NBA",
                "season_order": 0,
                "player_name": row["player_name"],
                "minutes": row["minutes"],
                "usg_pct": 0.2,
                "ts_pct": 0.55,
                "ast_pct": 0.15,
                "tov_rate": 0.1,
                "ast_per_75": 3.0,
                "reb_per_75": 5.0,
                "share_2pa": 0.5,
                "share_3pa": 0.3,
                "share_fta": 0.2,
            }
            for row in rows
        ]
    )


def seasons_of(person: str, name: str, minutes: list[float]) -> list[dict[str, object]]:
    return [
        {
            "person_id": person,
            "player_name": name,
            "season_id": f"NBA_{2000 + i}",
            "minutes": m,
        }
        for i, m in enumerate(minutes)
    ]


class TestClusterExemplars:
    """The frame is player-seasons, and an exemplar list is people.

    Taking the top five rows by minutes took the top five *seasons*, and a
    player who anchors a cluster tends to anchor it several years running.
    Cluster 2 shipped as "Dwight Howard, Ben Wallace, Dwight Howard, Ben
    Wallace" — five slots holding two people, which looks like a list of five.
    """

    def test_names_a_person_once_however_many_seasons_they_contribute(self) -> None:
        rows = seasons_of("howard", "Dwight Howard", [3000.0, 2900.0, 2800.0]) + seasons_of(
            "wallace", "Ben Wallace", [2700.0, 2600.0]
        )
        frame = cluster_frame(rows)

        described = describe_clusters(frame, np.zeros(frame.height, dtype=int), {0: 0.5})

        assert described["exemplars"].to_list() == ["Dwight Howard, Ben Wallace"]

    def test_lists_only_as_many_people_as_the_cluster_has(self) -> None:
        frame = cluster_frame(seasons_of("solo", "Solo Player", [3000.0, 2000.0, 1000.0]))

        described = describe_clusters(frame, np.zeros(frame.height, dtype=int), {0: 0.5})

        assert described["exemplars"].to_list() == ["Solo Player"]

    def test_still_stops_at_five_when_more_people_qualify(self) -> None:
        rows = [
            season
            for i in range(8)
            for season in seasons_of(f"p{i}", f"Player {i}", [3000.0 - i * 100])
        ]
        frame = cluster_frame(rows)

        described = describe_clusters(frame, np.zeros(frame.height, dtype=int), {0: 0.5})
        exemplars = described["exemplars"][0].split(", ")

        assert len(exemplars) == 5
        assert len(set(exemplars)) == 5

    def test_keeps_the_minutes_ranking_after_deduplicating(self) -> None:
        # The biggest season survives for each person, and the people stay in
        # order of it — a naive unique() would return them in arbitrary order.
        rows = (
            seasons_of("second", "Second Most", [2000.0, 1900.0])
            + seasons_of("most", "Most Minutes", [3000.0, 100.0])
            + seasons_of("third", "Third Most", [1500.0])
        )
        frame = cluster_frame(rows)

        described = describe_clusters(frame, np.zeros(frame.height, dtype=int), {0: 0.5})

        assert described["exemplars"].to_list() == ["Most Minutes, Second Most, Third Most"]

    def test_two_people_sharing_a_name_are_two_exemplars(self) -> None:
        # Deduplicating by name rather than person_id would collapse these into
        # one, and the cohort spans twenty-five years of NBA and EuroLeague
        # rosters, where a repeated name is ordinary.
        rows = seasons_of("elder", "Glen Rice", [3000.0]) + seasons_of(
            "younger", "Glen Rice", [2000.0]
        )
        frame = cluster_frame(rows)

        described = describe_clusters(frame, np.zeros(frame.height, dtype=int), {0: 0.5})

        assert described["exemplars"].to_list() == ["Glen Rice, Glen Rice"]
