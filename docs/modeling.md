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
- ETL currently bootstraps `leagues`, `seasons`, and `etl_runs` via SQL artifact output.
- API routes currently expose health, player search/detail, and team detail + gravity lookup.
- Feature model jobs will be added incrementally on top of the existing contracts.
