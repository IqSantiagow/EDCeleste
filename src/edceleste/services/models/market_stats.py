from dataclasses import dataclass

from edceleste.services.models.game_events import MarketItemModel


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    station_name: str
    is_docked: bool
    has_commodities_market: bool
    is_market_data_current: bool
    commodities: tuple[MarketItemModel, ...]
