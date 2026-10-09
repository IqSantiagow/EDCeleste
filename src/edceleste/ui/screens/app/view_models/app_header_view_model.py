from dataclasses import dataclass


@dataclass(slots=True)
class AppHeaderViewModel:
    player_name: str
    player_ship: str
    credits: int

    @classmethod
    def empty(cls) -> "AppHeaderViewModel":
        """Blank names and 0 credits. The header shows it before the first
        game stats arrive."""
        return cls(player_name="", player_ship="", credits=0)
