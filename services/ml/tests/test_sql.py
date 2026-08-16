"""SQL generation for the D1 load artefact.

The load file is the one artefact in this project whose only failure mode is at
the point of use: it is valid SQL, it passes every check that reads it as text,
and it can still be impossible to execute. These tests are about executability.
"""

from __future__ import annotations

from hoopslab.serve import sql


def test_rows_are_chunked_by_count() -> None:
    rows = [[i, "x"] for i in range(1000)]
    statements = sql.insert_many("t", ["a", "b"], rows, chunk=400)
    assert len(statements) == 3
    assert all(s.startswith('INSERT INTO t ("a", "b") VALUES') for s in statements)
    assert all(s.endswith(";") for s in statements)


def test_large_rows_are_chunked_by_size_before_count() -> None:
    """The regression that made the artefact unloadable.

    `player_reports` carries a whole rendered evidence bundle per row. At 400
    rows a statement that is over a megabyte, and SQLite refuses anything past
    SQLITE_MAX_SQL_LENGTH with `statement too long: SQLITE_TOOBIG` — so the
    export succeeded, the file looked fine, and `wrangler d1 execute` failed on
    the first oversized table.
    """
    big = "y" * 5_000
    rows = [[i, big] for i in range(400)]

    statements = sql.insert_many("t", ["a", "b"], rows, chunk=400)

    assert len(statements) > 1, "400 rows of 5 KB must not become one statement"
    assert all(len(s) <= sql.MAX_STATEMENT_BYTES * 1.1 for s in statements)


def test_every_statement_stays_under_sqlite_limit() -> None:
    """One million bytes is the limit; nothing generated may approach it."""
    rows = [[i, "z" * 20_000] for i in range(50)]
    for statement in sql.insert_many("t", ["a", "b"], rows):
        assert len(statement) < 1_000_000


def test_a_single_oversized_row_is_emitted_alone() -> None:
    """It cannot be split, so it must not also carry neighbours over the cap."""
    rows = [[1, "a" * 10], [2, "b" * 400_000], [3, "c" * 10]]
    statements = sql.insert_many("t", ["a", "b"], rows, max_bytes=100_000)

    holding_the_big_row = [s for s in statements if "b" * 1_000 in s]
    assert len(holding_the_big_row) == 1
    assert holding_the_big_row[0].count("(") >= 1


def test_no_rows_produces_no_statements() -> None:
    assert sql.insert_many("t", ["a"], []) == []


def test_every_row_survives_chunking() -> None:
    """Chunking must not drop a row at a boundary."""
    rows = [[i] for i in range(997)]
    statements = sql.insert_many("t", ["a"], rows, chunk=100)
    assert sum(s.count("(") - 1 for s in statements) == 997
