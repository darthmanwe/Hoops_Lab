"""HoopsLab: cross-league basketball translation modelling.

The package is organised by pipeline stage:

- ``ingest``    fetches raw payloads into the bronze layer (operator-only)
- ``transform`` normalises bronze into typed silver, then joins to gold
- ``validate``  enforces the data contracts that gold must satisfy
- ``features``  builds model-ready frames from gold
- ``models``    fits and serialises estimators
- ``eval``      backtests, leakage assertions and calibration reporting
- ``serve``     exports gold into the D1 tables the Worker reads

Only ``data/gold`` is committed to the repository, so a clean clone reproduces
every reported number without network access.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
