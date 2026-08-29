"""SQL generation for the D1 load artefact.

The load file is the one artefact in this project whose only failure mode is at
the point of use: it is valid SQL, it passes every check that reads it as text,
and it can still be impossible to execute. These tests are about executability.
"""

from __future__ import annotations

import re
from pathlib import Path

from hoopslab.serve import d1_export, sql


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


def test_the_load_carries_no_transaction_wrapper() -> None:
    """D1 rejects the file outright if it does.

    Remote D1 runs statements through Durable Object storage, which coalesces
    writes atomically on its own and refuses to be told how:

        To execute a transaction, please use the state.storage.transaction()
        API instead of the SQL BEGIN TRANSACTION or SAVEPOINT statements.

    The local miniflare executor has no such objection, so the wrapper worked in
    every test and every local load and failed the first time it met production.
    Atomicity is not lost — `wrangler d1 execute --file` provides it and says so
    before it starts — but the next person to notice this file has no
    transaction and helpfully restore one would break the seed and pass CI.
    """
    artefact = sql.transaction(["INSERT INTO t VALUES (1);"])

    assert "BEGIN TRANSACTION" not in artefact
    assert "COMMIT" not in artefact
    assert "SAVEPOINT" not in artefact


def test_every_sql_artefact_pins_its_line_endings() -> None:
    """Otherwise the artefact differs by the platform that generated it.

    ``Path.write_text`` translates newlines on Windows, so the same command
    produced CRLF here and LF on a Linux runner. The committed fixture is loaded
    by the Worker suite and the export is content-hashed, which makes this a
    reproducibility bug rather than a cosmetic one — and ``.gitattributes``
    cannot reach it, because it normalises what git stores rather than what a
    generator emits.

    Asserted against the source rather than by writing a file and reading it
    back: the thing that must not regress is the argument, and a round-trip
    check would pass on Linux whether or not it was there.
    """
    source = Path(d1_export.__file__).read_text(encoding="utf-8")
    # To end of line rather than to the closing paren: the argument itself
    # contains parentheses, and a non-greedy match stops inside them.
    writes = re.findall(r"^\s*\w*\.write_text\(.*$", source, flags=re.MULTILINE)

    assert writes, "no write_text call found, so this test is checking nothing"
    for call in writes:
        assert "newline=" in call, (
            f"writes an artefact without pinning the line ending: {call.strip()}"
        )
