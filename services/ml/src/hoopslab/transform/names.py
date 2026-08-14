"""Player-name normalisation, for matching identities across four id systems.

Each source writes names differently:

===============  ==========================  ==============================
Source           Format                      Example
===============  ==========================  ==============================
stats.nba.com    ``First Last``              ``Nikola Jokic``
ESPN             ``First Last`` w/ initials  ``P.J. Washington``
EuroLeague       ``LAST, FIRST`` uppercase   ``DONCIC, LUKA``
===============  ==========================  ==============================

Matching them is the part of this project most likely to quietly lose a day.
The failure is asymmetric: a missed match drops a player from the transition
cohort, which for a sample of a few dozen pairs is material, while a false
match invents a career that never happened. So the normaliser is deliberately
aggressive about formatting differences and the crosswalk stays conservative
about accepting a match on name alone.

Diacritic stripping is not optional. Roughly a third of EuroLeague players
have them, and no two sources agree on whether to keep them.
"""

from __future__ import annotations

import re
import unicodedata

#: Generational suffixes carry no identity information and are inconsistently
#: recorded. "Gary Payton II" is "Gary Payton" in some feeds.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

#: Removed outright, joining the letters either side. "P.J." must become "pj"
#: and not "p j", or it stops matching a source that writes "PJ".
#:
#: The class deliberately contains four visually near-identical characters:
#: full stop, straight apostrophe, right single quotation mark, grave accent
#: and acute accent. Different feeds spell "O'Neal" with different ones, and
#: treating them as distinct is precisely what breaks a match. Ruff's
#: ambiguous-character rule is suppressed here because the ambiguity is the
#: subject matter rather than a mistake.
_INTRA_WORD_PUNCTUATION = re.compile("[.'’`´]", flags=re.UNICODE)  # noqa: RUF001

#: Replaced with a space, because these separate genuine name parts.
#: "Karl-Anthony Towns" and "Karl Anthony Towns" are the same person.
_SEPARATING_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)

_WHITESPACE = re.compile(r"\s+")


def strip_diacritics(value: str) -> str:
    """``Nikola Jokić`` -> ``Nikola Jokic``.

    NFKD splits a composed character into its base plus combining marks, which
    are then dropped. A few letters are folded explicitly first: NFKD leaves
    the Croatian d-with-stroke, the Polish l-with-stroke and the Nordic
    o-with-stroke intact, because they are distinct letters rather than
    decorated ones, yet no two sources agree on how to write them.
    """
    # Both U+0110 (D with stroke, Croatian/Serbian) and U+00D0 (eth) appear in
    # these feeds and render near-identically, so both are folded. Missing
    # either one silently drops a player from the transition cohort.
    pre_folded = (
        value.replace("đ", "d")
        .replace("Đ", "D")
        .replace("ð", "d")
        .replace("Ð", "D")
        .replace("ø", "o")
        .replace("Ø", "O")
        .replace("ł", "l")
        .replace("Ł", "L")
        .replace("ß", "ss")
    )
    decomposed = unicodedata.normalize("NFKD", pre_folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(value: str) -> str:
    """Reduce a name to a comparable key.

    Lowercased, de-accented, punctuation removed and suffixes dropped, so
    ``P.J. Washington``, ``PJ Washington`` and ``P J Washington`` all collapse
    to ``pj washington``.
    """
    if not value:
        return ""

    text = strip_diacritics(value).lower()
    text = _INTRA_WORD_PUNCTUATION.sub("", text)
    text = _SEPARATING_PUNCTUATION.sub(" ", text)
    tokens = [t for t in _WHITESPACE.split(text) if t and t not in _SUFFIXES]
    return " ".join(_join_initials(tokens))


def _join_initials(tokens: list[str]) -> list[str]:
    """Merge runs of single letters, so "P J Washington" matches "P.J. Washington".

    Feeds disagree on whether initials are punctuated, spaced or run together.
    Collapsing a run of single characters covers all three without affecting
    ordinary names, since no real name part is one letter on its own.
    """
    merged: list[str] = []
    run: list[str] = []

    for token in tokens:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            merged.append("".join(run))
            run = []
        merged.append(token)

    if run:
        merged.append("".join(run))
    return merged


def match_key(value: str) -> str:
    """Order-insensitive key, for sources that disagree on name order.

    ``DONCIC, LUKA`` and ``Luka Doncic`` both reduce to ``doncic luka``. This
    is looser than :func:`normalize_name` and is only ever used as a *candidate
    generator* — the crosswalk still requires corroboration before accepting a
    link, because sorted tokens will happily match two different people who
    share a surname and an initial.
    """
    return " ".join(sorted(normalize_name(value).split()))


def from_euroleague(value: str) -> str:
    """``DONCIC, LUKA`` -> ``Luka Doncic``.

    EuroLeague reports ``LAST, FIRST`` in capitals. Producing a conventional
    display name keeps the gold layer readable and means the UI does not have
    to know which league a row came from.
    """
    if not value:
        return ""

    if "," in value:
        last, _, first = value.partition(",")
        ordered = f"{first.strip()} {last.strip()}"
    else:
        ordered = value.strip()

    return _titlecase(ordered)


def _titlecase(value: str) -> str:
    """Title-case that leaves internal capitals and particles sensible.

    ``str.title()`` turns ``O'NEAL`` into ``O'Neal`` correctly but also turns
    ``MCGEE`` into ``Mcgee``; neither is worth special-casing further, since
    the display name is never a join key — :func:`normalize_name` is.
    """
    parts = []
    for word in value.split():
        if "'" in word:
            head, _, tail = word.partition("'")
            parts.append(f"{head.capitalize()}'{tail.capitalize()}")
        elif "-" in word:
            parts.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            parts.append(word.capitalize())
    return " ".join(parts)
