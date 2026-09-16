"""Pilot rank names.

The game journal stores a rank as a number, e.g. {"event":"Promotion","Explore":5}.
That number is a position in the fixed name list below, so 5 means "Pathfinder".
"""

UNKNOWN_RANK = "Unranked"

COMBAT_RANKS = (
    "Harmless",
    "Mostly Harmless",
    "Novice",
    "Competent",
    "Expert",
    "Master",
    "Dangerous",
    "Deadly",
    "Elite",
)

TRADE_RANKS = (
    "Penniless",
    "Mostly Penniless",
    "Peddler",
    "Dealer",
    "Merchant",
    "Broker",
    "Entrepreneur",
    "Tycoon",
    "Elite",
)

EXPLORATION_RANKS = (
    "Aimless",
    "Mostly Aimless",
    "Scout",
    "Surveyor",
    "Trailblazer",
    "Pathfinder",
    "Ranger",
    "Pioneer",
    "Elite",
)


def rank_name(ladder: tuple[str, ...], rank_value: int | None) -> str:
    """Turn a rank number into its name. An unknown number gives "Unranked"."""
    if rank_value is not None and 0 <= rank_value < len(ladder):
        return ladder[rank_value]
    return UNKNOWN_RANK
