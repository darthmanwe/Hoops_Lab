"""Name normalisation.

Every case here is a real name from the ingested data, not an invented one.
"""

from __future__ import annotations

import pytest

from hoopslab.transform.names import from_euroleague, match_key, normalize_name, strip_diacritics


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Nikola Jokić", "Nikola Jokic"),
        ("Luka Dončić", "Luka Doncic"),
        ("Šarūnas Jasikevičius", "Sarunas Jasikevicius"),
        ("Théo Maledon", "Theo Maledon"),
        ("Bogdan Bogdanović", "Bogdan Bogdanovic"),
        # NFKD alone leaves these intact: they are distinct letters, not
        # decorated ones, so they need explicit folding.
        ("Ðorđe Petrović", "Dorde Petrovic"),
        ("Łukasz Kowalski", "Lukasz Kowalski"),
    ],
)
def test_strips_diacritics(raw: str, expected: str) -> None:
    assert strip_diacritics(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("P.J. Washington", "pj washington"),
        ("PJ Washington", "pj washington"),
        ("P J Washington", "pj washington"),
        ("Gary Payton II", "gary payton"),
        ("Kelly Oubre Jr.", "kelly oubre"),
        ("Nikola Jokić", "nikola jokic"),
        ("  Extra   Spaces  ", "extra spaces"),
        ("", ""),
    ],
)
def test_normalizes_to_a_comparable_key(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_initials_written_two_ways_collapse_together() -> None:
    """The single most common cross-source formatting difference."""
    assert normalize_name("P.J. Washington") == normalize_name("PJ Washington")


def test_suffix_presence_does_not_break_a_match() -> None:
    assert normalize_name("Gary Payton II") == normalize_name("Gary Payton")


class TestMatchKey:
    def test_is_order_insensitive(self) -> None:
        assert match_key("DONCIC, LUKA") == match_key("Luka Doncic")

    def test_survives_diacritics_and_case(self) -> None:
        assert match_key("JOKIĆ, NIKOLA") == match_key("Nikola Jokic")

    def test_different_people_do_not_collide(self) -> None:
        assert match_key("Nikola Jokic") != match_key("Nikola Jovic")


class TestEuroLeagueNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("DONCIC, LUKA", "Luka Doncic"),
            ("GAZI, ERTEN", "Erten Gazi"),
            ("MICIC, VASILIJE", "Vasilije Micic"),
            ("O'NEAL, SHAQUILLE", "Shaquille O'Neal"),
            ("HEZONJA, MARIO", "Mario Hezonja"),
        ],
    )
    def test_reorders_and_titlecases(self, raw: str, expected: str) -> None:
        assert from_euroleague(raw) == expected

    def test_handles_a_hyphenated_surname(self) -> None:
        assert from_euroleague("ABDUL-JABBAR, KAREEM") == "Kareem Abdul-Jabbar"

    def test_passes_through_a_name_with_no_comma(self) -> None:
        assert from_euroleague("NANDO DE COLO") == "Nando De Colo"

    def test_handles_empty_input(self) -> None:
        assert from_euroleague("") == ""

    def test_result_matches_the_nba_spelling(self) -> None:
        """The property that actually matters for the crosswalk."""
        assert normalize_name(from_euroleague("DONCIC, LUKA")) == normalize_name("Luka Doncic")
