"""The hosted slice must not quietly become a different product.

D1's free plan allows 100,000 row writes a day and the full export is 199,439,
so a public deployment serves a subset. Choosing a subset is where a demo
starts lying: take the most recent seasons and the front page's own worked
example disappears, because the transfer it describes happened in 2018 and the
EuroLeague season it starts from is 2017.

These tests pin what the slice promises — it fits, it keeps the model cohort
whole, and every foreign key still resolves.
"""

from __future__ import annotations

import polars as pl
import pytest

from hoopslab.paths import DataPaths
from hoopslab.serve.d1_export import (
    D1_FREE_DAILY_WRITES,
    DEMO_COMPS_PER_SEASON,
    DemoSlice,
    ExportResult,
    build_export,
)


@pytest.fixture(scope="module")
def gold() -> tuple[pl.DataFrame, pl.DataFrame]:
    paths = DataPaths.discover()
    if not (paths.gold / "transition_pairs.parquet").is_file():
        pytest.skip("no committed gold snapshot")
    return (
        pl.read_parquet(paths.gold / "player_seasons.parquet"),
        pl.read_parquet(paths.gold / "transition_pairs.parquet"),
    )


@pytest.fixture(scope="module")
def demo() -> ExportResult:
    """One demo export, reused. Building it refits the archetype mixture.

    A second export to compare against was the obvious way to assert nothing
    load-bearing was trimmed, and it doubled the cost of this file for an
    answer the export already knows. `dropped` reports it directly.
    """
    paths = DataPaths.discover()
    if not (paths.gold / "transition_pairs.parquet").is_file():
        pytest.skip("no committed gold snapshot")
    return build_export(paths, demo=True)


def test_the_slice_fits_a_single_day_of_free_tier_writes(demo: ExportResult) -> None:
    assert demo.total < D1_FREE_DAILY_WRITES, f"{demo.total:,} rows exceeds the daily ceiling"


def test_there_is_room_to_seed_twice(demo: ExportResult) -> None:
    """A seed that only fits once cannot be corrected the day it goes wrong.

    Re-running the loader spends the whole row count again, so a slice at 95%
    of the ceiling means any mistake waits until tomorrow.
    """
    assert demo.total * 2 < D1_FREE_DAILY_WRITES


def test_every_observed_transfer_is_still_served(demo: ExportResult) -> None:
    """The predictions table is the product. A slice that trims it is a different one."""
    for table in (
        "translation_predictions",
        "player_reports",
        "selection_summaries",
        "model_evaluations",
        "seasons",
        "archetype_definitions",
    ):
        assert demo.dropped.get(table, 0) == 0, f"the slice dropped rows from {table}"


def test_the_slice_reports_what_it_dropped(demo: ExportResult) -> None:
    """ADR 8: a filter states its losses rather than leaving them to be found."""
    assert demo.dropped, "a slice that reports no drops is not slicing anything"
    assert demo.dropped.keys() <= demo.row_counts.keys()
    for table, lost in demo.dropped.items():
        assert lost > 0, f"{table} recorded a zero drop instead of being omitted"


def test_the_whole_model_cohort_is_kept(gold: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    player_seasons, pairs = gold
    slice_ = DemoSlice.build(player_seasons, pairs)
    cohort = set(pairs["person_id"].to_list())
    assert cohort <= slice_.persons


def test_a_transfer_players_older_seasons_survive(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    """The reason a plain "recent seasons" cutoff was rejected.

    Every worked example on the site starts from a season before the browsing
    window: the source side of a transfer is by construction older than the
    target, and the oldest pairs reach back to 2005.
    """
    player_seasons, pairs = gold
    slice_ = DemoSlice.build(player_seasons, pairs)

    oldest = pairs.sort("source_season_order").row(0, named=True)
    assert oldest["person_id"] in slice_.persons
    assert not slice_.is_recent(oldest["source_season_id"]), (
        "pick a genuinely old pair, or this asserts nothing"
    )


def test_comparables_are_capped_at_what_the_interface_shows(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    player_seasons, pairs = gold
    slice_ = DemoSlice.build(player_seasons, pairs)
    person = next(iter(slice_.persons))
    columns = ["season_id", "person_id", "rank", "neighbour_person_id", "distance", "v"]
    recent = next(
        (s for s in slice_.season_orders if slice_.is_recent(s)),
        None,
    )
    assert recent is not None

    rows = [[recent, person, rank, person, 1.0, "v"] for rank in range(1, 12)]
    kept = slice_.keep("player_comps", columns, rows)
    assert [r[2] for r in kept] == list(range(1, DEMO_COMPS_PER_SEASON + 1))


def test_a_neighbour_outside_the_slice_is_dropped_not_served_nameless(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    """`neighbour_person_id` has no foreign key, so nothing else would catch it."""
    player_seasons, pairs = gold
    slice_ = DemoSlice.build(player_seasons, pairs)
    person = next(iter(slice_.persons))
    recent = next(s for s in slice_.season_orders if slice_.is_recent(s))
    columns = ["season_id", "person_id", "rank", "neighbour_person_id", "distance", "v"]

    kept = slice_.keep(
        "player_comps",
        columns,
        [[recent, person, 1, "person-who-is-not-in-the-slice", 1.0, "v"]],
    )
    assert kept == []


def test_unlisted_tables_are_served_whole(gold: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    """The default is to keep, so a new table is complete until someone decides otherwise."""
    player_seasons, pairs = gold
    slice_ = DemoSlice.build(player_seasons, pairs)
    rows = [["a"], ["b"]]
    assert slice_.keep("some_future_table", ["x"], rows) == rows
