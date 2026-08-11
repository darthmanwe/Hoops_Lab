"""Leakage assertions, called inside the cross-validation loop at runtime.

Not in a test. A test proves the splitter behaved on one occasion; these run on
every fold of every real training run, so a change to the splitting logic
cannot quietly stop being safe while the tests still pass.

Two distinct hazards, and both apply here:

*Temporal* — a model that has seen 2023 must not be scored on 2019. Time only
runs one way, and a translation estimated with future seasons in the training
set is not a forecast of anything.

*Entity* — the same player appearing on both sides. Roughly a third of the
players in this cohort transition more than once (NBA to EuroLeague and back is
a common career shape), so leaving one season out is **not** on its own enough
to keep a player out of his own training data.
"""

from __future__ import annotations

import polars as pl


class LeakageError(AssertionError):
    """Raised when a split would let a model see what it is being scored on."""


def assert_temporal_disjoint(
    train: pl.DataFrame, test: pl.DataFrame, *, order_column: str = "target_season_order"
) -> None:
    """Training data must not extend into or beyond the evaluated season."""
    if train.is_empty() or test.is_empty():
        return

    latest_train = _as_number(train[order_column].max())
    earliest_test = _as_number(test[order_column].min())

    if latest_train is not None and earliest_test is not None and latest_train >= earliest_test:
        raise LeakageError(
            f"training data reaches {latest_train:g} while the test fold starts at "
            f"{earliest_test:g}; the model would be scored on seasons it has seen"
        )


def _as_number(value: object) -> float | None:
    """Narrow a polars aggregate, whose static type is a wide union."""
    return float(value) if isinstance(value, int | float) else None


def assert_no_entity_overlap(
    train: pl.DataFrame, test: pl.DataFrame, *, entity_column: str = "person_id"
) -> None:
    """No player may appear in both sides of a split."""
    if train.is_empty() or test.is_empty():
        return

    shared = set(train[entity_column].to_list()) & set(test[entity_column].to_list())
    if shared:
        raise LeakageError(
            f"{len(shared)} player(s) appear in both the training and test folds, "
            f"for example {sorted(shared)[:3]}; a repeat transition would be "
            "predicted partly from itself"
        )
