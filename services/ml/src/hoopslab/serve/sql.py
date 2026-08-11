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


def insert_many(
    table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]], *, chunk: int = 400
) -> list[str]:
    """Multi-row INSERT statements, chunked to keep each statement parseable.

    Chunking matters: a single INSERT with 22,000 value tuples is one enormous
    statement that some clients refuse outright.
    """
    statements: list[str] = []
    buffer: list[str] = []
    column_list = ", ".join(f'"{c}"' for c in columns)

    for row in rows:
        buffer.append("(" + ", ".join(literal(v) for v in row) + ")")
        if len(buffer) >= chunk:
            statements.append(
                f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(buffer) + ";"
            )
            buffer = []

    if buffer:
        statements.append(
            f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(buffer) + ";"
        )

    return statements


def transaction(statements: Iterable[str]) -> str:
    """Wrap statements so a failure leaves the database untouched.

    Deletes and inserts land together or not at all — which is what stops a
    failed load from leaving the tables empty but the schema intact.
    """
    body = "\n".join(statements)
    return f"BEGIN TRANSACTION;\n{body}\nCOMMIT;\n"
