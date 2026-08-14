# 2. Identity is person-centric, not league-scoped

Accepted.

## Context

The original schema keyed players as `(league_id, player_id)`. A player who
appeared in both the EuroLeague and the NBA was therefore **two unrelated
rows with no join key between them**.

This is not a modelling inconvenience. The project's flagship claim is about
what happens to a player when they change league. Under that schema the
question is not merely hard to answer — it is not expressible. There is no
key on "the same person, before and after".

## Decision

Three tables:

- `persons` — one row per human being.
- `player_identities` — one row per (league, source id), pointing at a person,
  carrying `match_method` and `confidence`.
- `player_seasons` — keyed on the person.

Identities are resolved by normalised name plus implied birth year plus team
overlap, with a committed override CSV for the residual.

## Consequences

- The transition frame has a join key, so the model can be fitted at all.
- Confidence is **served**, not hidden. A link made on name alone is weaker
  evidence than one corroborated by age, and the API says which is which
  rather than presenting both as fact.
- Matching Balkan and Francophone names across three id systems is where this
  project actually spends its time. 1,035 ids are shared between the NBA and
  G League feeds, with 99.9% name agreement, which is what let that pair be
  joined on id rather than on name.
- A person with no resolvable identity anywhere is dropped rather than
  invented. Six persons out of 5,347 carry no name; a check fails the build
  above ten.
