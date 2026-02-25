# Modeling

## Modules (Target)

1. Archetype Finder
2. Shot Profile Explorer
3. Clutch and Momentum
4. Fatigue and Travel Impact
5. Cross-league Translation Layer
6. NBA Gravity Effect

## Current implementation status

- Canonical schema is in place.
- ETL currently bootstraps representative seed data across all module tables via SQL artifact output.
- Implemented API coverage:
  - archetypes: player comps via cosine similarity on archetype vectors
  - shot profiles: player and team split endpoints
  - clutch/momentum: game momentum endpoint
  - fatigue/travel: team and game fatigue endpoints
  - translation: player translation endpoint and leaderboard
  - gravity effect + lineup impact: team gravity, five-player lineup impact, lineup snapshots
- Transition vs set-play metrics are exposed via team play-style endpoints using derived table values.
