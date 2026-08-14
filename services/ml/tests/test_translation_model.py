"""The translation model: leakage guards, baselines, and the fit itself."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from hoopslab.eval.leakage import (
    LeakageError,
    assert_no_entity_overlap,
    assert_temporal_disjoint,
)
from hoopslab.models.baselines import FOLK_MULTIPLIER, folk_rule, z_preservation
from hoopslab.models.translation import (
    AGE_REFERENCE,
    fit_persistence,
    fit_translation,
)


def persistence_frame(n: int = 500, slope: float = 0.8, seed: int = 0) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    z_from = rng.normal(size=n)
    return pl.DataFrame(
        {
            "person_id": [f"p{i}" for i in range(n)],
            "z_from": z_from,
            "z_to": slope * z_from + rng.normal(scale=0.3, size=n),
            "age": rng.uniform(22, 33, size=n),
            "log_minutes": rng.uniform(6.5, 7.8, size=n),
            "season_order": rng.integers(2005, 2020, size=n),
        }
    )


class TestLeakageGuards:
    def test_flags_training_data_that_reaches_the_test_season(self) -> None:
        train = pl.DataFrame({"target_season_order": [2018, 2019], "person_id": ["a", "b"]})
        test = pl.DataFrame({"target_season_order": [2019], "person_id": ["c"]})

        with pytest.raises(LeakageError, match="scored on seasons it has seen"):
            assert_temporal_disjoint(train, test)

    def test_accepts_a_strictly_earlier_training_set(self) -> None:
        train = pl.DataFrame({"target_season_order": [2017, 2018], "person_id": ["a", "b"]})
        test = pl.DataFrame({"target_season_order": [2019], "person_id": ["c"]})

        assert_temporal_disjoint(train, test)

    def test_flags_a_player_present_on_both_sides(self) -> None:
        """A third of this cohort transitions twice, so this is not hypothetical."""
        train = pl.DataFrame({"person_id": ["a", "b"], "target_season_order": [2017, 2017]})
        test = pl.DataFrame({"person_id": ["b"], "target_season_order": [2019]})

        with pytest.raises(LeakageError, match="appear in both"):
            assert_no_entity_overlap(train, test)

    def test_accepts_disjoint_players(self) -> None:
        train = pl.DataFrame({"person_id": ["a"], "target_season_order": [2017]})
        test = pl.DataFrame({"person_id": ["b"], "target_season_order": [2019]})

        assert_no_entity_overlap(train, test)

    def test_empty_folds_are_not_an_error(self) -> None:
        empty = pl.DataFrame({"person_id": [], "target_season_order": []})
        other = pl.DataFrame({"person_id": ["a"], "target_season_order": [2019]})

        assert_temporal_disjoint(empty, other)
        assert_no_entity_overlap(empty, other)


class TestPersistenceFit:
    def test_recovers_a_known_slope(self) -> None:
        model = fit_persistence(persistence_frame(slope=0.8), "usg_pct")
        assert model.coefficients["z"] == pytest.approx(0.8, abs=0.05)

    def test_reports_variance_explained(self) -> None:
        model = fit_persistence(persistence_frame(slope=0.8), "usg_pct")
        assert 0.5 < model.r_squared < 1.0

    def test_refuses_to_fit_on_a_small_sample(self) -> None:
        """The two-stage design only works if stage one is large."""
        with pytest.raises(ValueError, match="the two-stage design depends"):
            fit_persistence(persistence_frame(n=50), "usg_pct")

    def test_prediction_is_centred_on_the_reference_age(self) -> None:
        model = fit_persistence(persistence_frame(), "usg_pct")
        predicted = model.predict(
            np.array([0.0]),
            np.array([AGE_REFERENCE]),
            np.array([model.coefficients["log_minutes_mean"]]),
        )
        assert predicted[0] == pytest.approx(model.coefficients["intercept"], abs=1e-9)


class TestBaselines:
    def test_folk_rule_applies_the_stated_multiplier(self) -> None:
        frame = pl.DataFrame({"source_value": [0.20, 0.30]})
        assert folk_rule(frame).predictions.tolist() == pytest.approx(
            [0.20 * FOLK_MULTIPLIER, 0.30 * FOLK_MULTIPLIER]
        )

    def test_z_preservation_maps_standing_into_target_units(self) -> None:
        frame = pl.DataFrame({"z_source": [1.0], "target_mean": [0.20], "target_sd": [0.05]})
        assert z_preservation(frame).predictions[0] == pytest.approx(0.25)

    def test_z_preservation_of_an_average_player_is_the_target_mean(self) -> None:
        frame = pl.DataFrame({"z_source": [0.0], "target_mean": [0.20], "target_sd": [0.05]})
        assert z_preservation(frame).predictions[0] == pytest.approx(0.20)


def transition_frame(n: int = 200, seed: int = 1) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    directions = rng.choice(["EL->NBA", "NBA->EL"], size=n)
    z_source = rng.normal(size=n)
    return pl.DataFrame(
        {
            "person_id": [f"p{i}" for i in range(n)],
            "direction": directions,
            "z_source": z_source,
            "z_target": 0.7 * z_source + rng.normal(scale=0.4, size=n),
            "age_at_source": rng.uniform(22, 32, size=n),
            "log_source_minutes": rng.uniform(6.2, 7.6, size=n),
            "gap_seasons": rng.integers(1, 3, size=n),
            "target_mean": np.full(n, 0.20),
            "target_sd": np.full(n, 0.05),
            "target_season_order": rng.integers(2013, 2023, size=n),
        }
    )


class TestTranslationFit:
    def test_recovers_a_compression_below_one(self) -> None:
        persistence = fit_persistence(persistence_frame(slope=1.0), "usg_pct")
        model = fit_translation(transition_frame(), persistence, "usg_pct")

        assert 0.3 < model.beta < 1.1

    def test_fits_one_intercept_per_observed_direction(self) -> None:
        persistence = fit_persistence(persistence_frame(), "usg_pct")
        model = fit_translation(transition_frame(), persistence, "usg_pct")

        assert set(model.intercepts) == {"EL->NBA", "NBA->EL"}

    def test_predictions_land_in_rate_units(self) -> None:
        persistence = fit_persistence(persistence_frame(), "usg_pct")
        frame = transition_frame()
        model = fit_translation(frame, persistence, "usg_pct")

        predicted = model.predict_rate(frame)
        assert 0.0 < float(np.median(predicted)) < 0.5

    def test_intervals_bracket_the_point_estimate(self) -> None:
        persistence = fit_persistence(persistence_frame(), "usg_pct")
        frame = transition_frame()
        model = fit_translation(frame, persistence, "usg_pct")

        centre = model.predict_rate(frame)
        interval = model.prediction_interval(frame, level=0.80)

        assert (interval[:, 0] < centre).all()
        assert (centre < interval[:, 1]).all()

    def test_a_wider_level_gives_a_wider_interval(self) -> None:
        persistence = fit_persistence(persistence_frame(), "usg_pct")
        frame = transition_frame()
        model = fit_translation(frame, persistence, "usg_pct")

        narrow = model.prediction_interval(frame, level=0.80)
        wide = model.prediction_interval(frame, level=0.95)

        assert (wide[:, 1] - wide[:, 0] > narrow[:, 1] - narrow[:, 0]).all()

    def test_residual_spread_is_positive(self) -> None:
        persistence = fit_persistence(persistence_frame(), "usg_pct")
        model = fit_translation(transition_frame(), persistence, "usg_pct")

        assert model.residual_sd > 0
