from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlayerStats:
    name: str
    ship: str
    credits: int


@dataclass(frozen=True, slots=True)
class GameStatsSnapshot:
    player: PlayerStats
