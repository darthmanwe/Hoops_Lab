"""Identity resolution, on synthetic data with known answers.

The cases are chosen to be the ones that would go wrong quietly: two players
sharing a name, a player with no age to corroborate against, and a G League
player who never reached the NBA.
"""

from __future__ import annotations

import polars as pl

from hoopslab.transform.crosswalk import (
    CONFIDENCE,
    MODELLING_CONFIDENCE_FLOOR,
    build_crosswalk,
    implied_birth_year,
    verify_shared_id_space,
)
from hoopslab.transform.names import match_key, normalize_name


def player_season(
    league: str, source_id: str, name: str, start_year: int, age: float | None = 25.0
) -> dict[str, object]:
    return {
        "season_id": f"{league}_{start_year}",
        "league": league,
        "start_year": float(start_year),
        "source_player_id": source_id,
        "player_name": name,
        "normalized_name": normalize_name(name),
        "match_key": match_key(name),
        "source_team_id": "T1",
        "team_name": "Team",
        "gp": 30.0,
        "minutes": 900.0,
        "pts": 400.0,
        "fga": 300.0,
        "fgm": 150.0,
        "fg3a": 100.0,
        "fg3m": 40.0,
        "fta": 80.0,
        "ftm": 60.0,
        "oreb": 30.0,
        "dreb": 100.0,
        "reb": 130.0,
        "ast": 90.0,
        "tov": 60.0,
        "stl": 30.0,
        "blk": 10.0,
        "pf": 70.0,
        "age": age,
    }


def frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows) if rows else pl.DataFrame()


class TestSharedIdSpace:
    def test_confirms_when_names_agree_behind_shared_ids(self) -> None:
        nba = frame([player_season("NBA", str(i), f"Player {i}", 2020) for i in range(200)])
        gl = frame([player_season("GL", str(i), f"Player {i}", 2019) for i in range(150)])

        evidence = verify_shared_id_space(nba, gl)

        assert evidence.n_shared_ids == 150
        assert evidence.name_agreement == 1.0
        assert evidence.confirmed

    def test_rejects_when_the_same_id_names_different_people(self) -> None:
        """Overlap alone is not evidence; the names behind it are."""
        nba = frame([player_season("NBA", str(i), f"Alpha {i}", 2020) for i in range(200)])
        gl = frame([player_season("GL", str(i), f"Beta {i}", 2019) for i in range(150)])

        evidence = verify_shared_id_space(nba, gl)

        assert evidence.n_shared_ids == 150
        assert evidence.name_agreement == 0.0
        assert not evidence.confirmed


class TestImpliedBirthYear:
    def test_uses_the_median_across_a_career(self) -> None:
        rows = [
            player_season("NBA", "1", "A B", 2018, age=24.0),
            player_season("NBA", "1", "A B", 2019, age=25.0),
            player_season("NBA", "1", "A B", 2020, age=99.0),  # a bad row
        ]
        result = implied_birth_year(frame(rows))
        assert result["birth_year"].item() == 1994


class TestBuildCrosswalk:
    def test_matches_a_euroleague_player_to_his_nba_self(self) -> None:
        nba = frame([player_season("NBA", "1629029", "Luka Doncic", 2018, age=19.0)])
        el = frame([player_season("EL", "007689", "Luka Doncic", 2017, age=18.0)])

        _, identities, report = build_crosswalk(nba, pl.DataFrame(), el)

        el_row = identities.filter(pl.col("league") == "EL").row(0, named=True)
        assert el_row["person_id"] == "nba_1629029"
        assert el_row["match_method"] == "name_and_age"
        assert report.n_matched_name_and_age == 1

    def test_refuses_to_guess_between_two_players_sharing_a_name(self) -> None:
        """A false match invents a career; being unsure is the correct answer."""
        nba = frame(
            [
                player_season("NBA", "100", "Nikola Jokic", 2018, age=23.0),
                player_season("NBA", "200", "Nikola Jokic", 2018, age=23.0),
            ]
        )
        el = frame([player_season("EL", "999", "Nikola Jokic", 2017, age=22.0)])

        _, identities, report = build_crosswalk(nba, pl.DataFrame(), el)

        el_row = identities.filter(pl.col("league") == "EL").row(0, named=True)
        assert el_row["match_method"] == "name_ambiguous"
        assert el_row["confidence"] < MODELLING_CONFIDENCE_FLOOR
        assert report.n_ambiguous == 1

    def test_a_name_match_with_no_age_stays_below_the_modelling_floor(self) -> None:
        nba = frame([player_season("NBA", "1", "Some Player", 2018, age=None)])
        el = frame([player_season("EL", "9", "Some Player", 2017, age=None)])

        _, identities, _ = build_crosswalk(nba, pl.DataFrame(), el)

        el_row = identities.filter(pl.col("league") == "EL").row(0, named=True)
        assert el_row["match_method"] == "name_only_unique"
        assert el_row["confidence"] < MODELLING_CONFIDENCE_FLOOR

    def test_a_wildly_different_age_prevents_a_match(self) -> None:
        nba = frame([player_season("NBA", "1", "Common Name", 2018, age=22.0)])
        el = frame([player_season("EL", "9", "Common Name", 2017, age=38.0)])

        _, identities, _ = build_crosswalk(nba, pl.DataFrame(), el)

        assert (
            identities.filter(pl.col("league") == "EL").row(0, named=True)["match_method"]
            != "name_and_age"
        )

    def test_a_euroleague_only_player_gets_his_own_person(self) -> None:
        nba = frame([player_season("NBA", "1", "Someone Else", 2018)])
        el = frame([player_season("EL", "9", "Euro Only", 2017)])

        persons, identities, report = build_crosswalk(nba, pl.DataFrame(), el)

        el_row = identities.filter(pl.col("league") == "EL").row(0, named=True)
        assert el_row["person_id"] == "el_9"
        assert report.n_euroleague_only == 1
        assert "el_9" in persons["person_id"].to_list()

    def test_a_manual_override_beats_name_matching(self) -> None:
        nba = frame([player_season("NBA", "555", "Different Spelling", 2018, age=30.0)])
        el = frame([player_season("EL", "9", "Totally Other Name", 2017, age=29.0)])
        overrides = pl.DataFrame(
            {"euroleague_player_id": ["9"], "nba_player_id": ["555"], "note": ["known alias"]}
        )

        _, identities, report = build_crosswalk(nba, pl.DataFrame(), el, overrides)

        el_row = identities.filter(pl.col("league") == "EL").row(0, named=True)
        assert el_row["person_id"] == "nba_555"
        assert el_row["confidence"] == CONFIDENCE["manual_override"]
        assert report.n_manual_overrides == 1

    def test_every_identity_resolves_to_a_person(self) -> None:
        """A G League player who never reached the NBA still needs a person row."""
        nba = frame([player_season("NBA", "1", "NBA Guy", 2018)])
        gl = frame([player_season("GL", "77", "Gleague Only", 2019)])
        el = frame([player_season("EL", "9", "Euro Guy", 2017)])

        persons, identities, _ = build_crosswalk(nba, gl, el)

        known = set(persons["person_id"].to_list())
        assert set(identities["person_id"].to_list()) <= known

    def test_a_player_with_no_name_still_gets_a_person(self) -> None:
        """Six real G League rows arrive with a null name; dropping them dangles references."""
        nba = frame([player_season("NBA", "1", "NBA Guy", 2018)])
        gl = frame([player_season("GL", "77", "", 2019)])

        persons, identities, _ = build_crosswalk(nba, gl, pl.DataFrame())

        assert set(identities["person_id"].to_list()) <= set(persons["person_id"].to_list())

    def test_each_source_id_maps_to_exactly_one_person(self) -> None:
        nba = frame([player_season("NBA", "1", "A B", y) for y in (2018, 2019, 2020)])
        _, identities, _ = build_crosswalk(nba, pl.DataFrame(), pl.DataFrame())

        counts = identities.group_by(["league", "source_player_id"]).agg(
            pl.n_unique("person_id").alias("n")
        )
        assert counts["n"].max() == 1
