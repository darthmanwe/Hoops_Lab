from __future__ import annotations


def canonical_player_id(league: str, raw_id: str | int) -> str:
    return f"{league}_{raw_id}"


def canonical_team_id(league: str, raw_id: str | int) -> str:
    return f"{league}_{raw_id}"


def canonical_game_id(league: str, raw_id: str | int) -> str:
    return f"{league}_{raw_id}"
