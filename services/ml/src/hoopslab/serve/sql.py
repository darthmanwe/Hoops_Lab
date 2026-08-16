"""SQL literal generation for the D1 load.

The previous implementation of this got three things wrong, each of which
would break a real load:

1. ``float('nan')`` and ``float('inf')`` were serialised as the bare tokens
   ``nan`` and ``inf``, which are not valid SQLite and abort the statement.
2. Only single quotes were escaped, so a backslash or a NUL in a scraped
   player name corrupted the file.
3. ``begin()`` and ``commit()`` wrote comments. No transaction was ever
   emitted, so a failure midway left the database half-updated with the
   ``DELETE`` already applied.

All three are fixed here, and the non-finite case raises rather than writing
something that will fail later at a less informative moment.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any


class NonFiniteValueError(ValueError):
    """Raised when NaN or infinity reaches the SQL writer.

    Gold forbids these, so arriving here means a validation gap upstream. It is
    raised rather than coerced: silently writing NULL would turn a pipeline bug
    into missing data that looks like a legitimately absent measurement.
    """


def literal(value: Any) -> str:
    """Render one Python value as a SQL literal."""
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise NonFiniteValueError(
                f"Refusing to serialise {value!r}: NaN and infinity are not valid SQLite "
                "and are forbidden in gold. Fix the transform rather than the writer."
            )
        return repr(value)

    return quote(str(value))


def quote(text: str) -> str:
    """Single-quoted SQL string with everything dangerous handled.

    NUL cannot appear in a SQLite text literal at all, so it is stripped; the
    alternative is a file that fails to parse on a name nobody will think to
    look at.
    """
    return "'" + text.replace("\x00", "").replace("'", "''") + "'"


#: Bytes of VALUES text after which a statement is closed and a new one begun.
#:
#: D1 caps a single SQL statement at 100 KB — far below SQLite's own
#: SQLITE_MAX_SQL_LENGTH of a megabyte, and the limit that actually bites. It
#: reports the overrun as `statement too long: SQLITE_TOOBIG`, which points at
#: the SQLite constant and sends you looking a factor of ten too high.
#:
#: 50 KB leaves room for the column list, and for one row that turns out much
#: larger than the rows measured when this was tuned.
MAX_STATEMENT_BYTES = 50_000


def insert_many(
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    chunk: int = 400,
    max_bytes: int = MAX_STATEMENT_BYTES,
) -> list[str]:
    """Multi-row INSERT statements, chunked to keep each statement executable.

    Chunked on **both** row count and byte size, because row count alone is a
    proxy for size that fails exactly where it matters. Rows in this export
    span three orders of magnitude: a `seasons` row is about 60 bytes, while a
    `player_reports` row carries a whole rendered evidence bundle and runs to
    ~4 KB. At 400 rows a statement the first is trivial and the second is 1.5 MB
    — over SQLite's limit, so the load failed outright with
    `statement too long: SQLITE_TOOBIG`.

    The failure is worth noting for what it was not: the SQL was valid, the
    tests passed, and the artefact was only unusable at the point of loading a
    real database. A size cap on the generator is the fix; a bigger cap on the
    consumer is not available.
    """
    statements: list[str] = []
    buffer: list[str] = []
    buffered_bytes = 0
    column_list = ", ".join(f'"{c}"' for c in columns)

    def flush() -> None:
        nonlocal buffer, buffered_bytes
        if buffer:
            statements.append(
                f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(buffer) + ";"
            )
            buffer = []
            buffered_bytes = 0

    for row in rows:
        values = "(" + ", ".join(literal(v) for v in row) + ")"
        # Flush *before* appending when this row would take the statement over,
        # so a single oversized row lands alone rather than being appended to a
        # statement that is already at the cap.
        if buffer and buffered_bytes + len(values) > max_bytes:
            flush()

        buffer.append(values)
        buffered_bytes += len(values) + 2  # the ",\n" joining it to the next

        if len(buffer) >= chunk:
            flush()

    flush()
    return statements


def transaction(statements: Iterable[str]) -> str:
    """Wrap statements so a failure leaves the database untouched.

    Deletes and inserts land together or not at all — which is what stops a
    failed load from leaving the tables empty but the schema intact.
    """
    body = "\n".join(statements)
    return f"BEGIN TRANSACTION;\n{body}\nCOMMIT;\n"
