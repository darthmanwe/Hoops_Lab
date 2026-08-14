"""Tests against the committed gold snapshot.

These run on a clean clone with no network and no credentials, which is the
whole reason gold is committed rather than downloaded. They are the guard
against a transform change quietly altering the data the README quotes.
"""

from __future__ import annotations

import polars as pl
import pytest

from hoopslab.paths import DataPaths
from hoopslab.transform.build import GOLD_TABLES, verify_gold
from hoopslab.validate import checks


@pytest.fixture(scope="module")
def paths() -> DataPaths:
    resolved = DataPaths.discover()
    if not (resolved.gold / "player_seasons.parquet").is_file():
        pytest.skip("gold snapshot missing; run `hoopslab ingest` then `hoopslab build`")
    return resolved


@pytest.fixture(scope="module")
def tables(paths: DataPaths) -> dict[str, pl.DataFrame]:
    return {name: pl.read_parquet(paths.gold / f"{name}.parquet") for name in GOLD_TABLES}


def test_every_gold_table_is_present(tables: dict[str, pl.DataFrame]) -> None:
    assert set(tables) == set(GOLD_TABLES)
    assert all(not frame.is_empty() for frame in tables.values())


def test_contents_match_the_committed_contracts(paths: DataPaths) -> None:
    """Data drift becomes a failed build rather than a changed number."""
    assert verify_gold(paths) == []


def test_all_integrity_checks_pass(tables: dict[str, pl.DataFrame]) -> None:
    failures = [r.render() for r in checks.run_all(tables) if not r.passed]
    assert not failures, "\n".join(failures)


class TestCoverage:
    def test_all_three_leagues_are_present(self, tables: dict[str, pl.DataFrame]) -> None:
        assert set(tables["player_seasons"]["league"].unique()) == {"NBA", "EL", "GL"}

    def test_the_nba_history_is_deep_enough_for_an_aging_curve(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        """Stage one of the translation model needs thousands of same-league pairs."""
        nba = tables["player_seasons"].filter(pl.col("league") == "NBA")
        assert nba["season_order"].n_unique() >= 20
        assert nba.height > 8_000

    def test_the_euroleague_reaches_back_to_2007(self, tables: dict[str, pl.DataFrame]) -> None:
        euro = tables["player_seasons"].filter(pl.col("league") == "EL")
        assert euro["season_order"].min() == 2007


class TestTransitionCohort:
    """The sample the flagship model depends on.

    The floor was set before the data was pulled: below 40 usable EuroLeague to
    NBA pairs, the commitment was to report coefficients with intervals only
    and refuse per-player point predictions.
    """

    def test_euroleague_to_nba_clears_the_pre_committed_floor(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        pairs = tables["transition_pairs"]
        el_to_nba = pairs.filter(pl.col("direction") == "EL->NBA")

        assert el_to_nba.height >= 40, (
            f"only {el_to_nba.height} EuroLeague to NBA pairs; the modelling plan changes below 40"
        )

    def test_both_directions_are_represented(self, tables: dict[str, pl.DataFrame]) -> None:
        """Opposite selection in the two directions is what identifies the bias."""
        directions = set(tables["transition_pairs"]["direction"].unique())
        assert "EL->NBA" in directions
        assert "NBA->EL" in directions

    def test_the_g_league_adds_a_meaningful_number_of_pairs(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        pairs = tables["transition_pairs"]
        gl = pairs.filter(pl.col("direction").str.contains("GL"))
        assert gl.height >= 50

    def test_every_pair_belongs_to_a_confident_identity(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        """A guessed identity must never enter the modelling cohort."""
        pairs = tables["transition_pairs"]
        identities = tables["player_identities"]

        low_confidence = set(identities.filter(pl.col("confidence") < 0.8)["person_id"].to_list())
        anchored = set(identities.filter(pl.col("confidence") >= 0.8)["person_id"].to_list())
        suspect = low_confidence - anchored

        assert not set(pairs["person_id"].to_list()) & suspect

    def test_known_transfers_are_present(self, tables: dict[str, pl.DataFrame]) -> None:
        """Spot check against transfers that unambiguously happened."""
        pairs = tables["transition_pairs"].filter(pl.col("direction") == "EL->NBA")
        names = set(pairs["player_name"].to_list())

        for expected in ("Vasilije Micic", "Facundo Campazzo", "Nicolo Melli"):
            assert expected in names, f"{expected} missing from the EuroLeague to NBA cohort"


class TestRatesAreComparableAcrossLeagues:
    def test_median_usage_is_similar_in_every_league(self, tables: dict[str, pl.DataFrame]) -> None:
        """Usage is a share of team possessions, so its median is ~1/5 everywhere.

        A league whose median lands far from the others means its rates were
        computed against a different denominator — which is exactly the bug
        that made EuroLeague usage five times too large.
        """
        qualified = tables["player_seasons"].filter(pl.col("qualified"))
        medians = qualified.group_by("league").agg(pl.median("usg_pct").alias("usg")).to_dicts()

        for row in medians:
            assert 0.14 < row["usg"] < 0.26, f"{row['league']} median usage {row['usg']:.3f}"

    def test_median_true_shooting_is_plausible_in_every_league(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        qualified = tables["player_seasons"].filter(pl.col("qualified"))
        for row in qualified.group_by("league").agg(pl.median("ts_pct").alias("ts")).to_dicts():
            assert 0.45 < row["ts"] < 0.65, f"{row['league']} median TS% {row['ts']:.3f}"

    def test_z_scores_are_centred_within_each_league_season(
        self, tables: dict[str, pl.DataFrame]
    ) -> None:
        """Standardising within season is what stops era being the first cluster found."""
        qualified = tables["player_seasons"].filter(
            pl.col("qualified") & pl.col("z_ts_pct").is_not_null()
        )
        per_season = qualified.group_by("season_id").agg(pl.mean("z_ts_pct").alias("mean_z"))

        assert per_season["mean_z"].abs().max() < 0.5
