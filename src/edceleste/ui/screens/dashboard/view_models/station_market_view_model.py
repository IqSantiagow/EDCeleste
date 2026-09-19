from dataclasses import dataclass

from edceleste.services.models.game_events import MarketItemModel
from edceleste.services.models.market_stats import MarketSnapshot
from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    format_thousands,
)

NO_VALUE = "-"

BAR_BLOCK = "█"
ZERO_AXIS = "▏"
# One block per 3% away from the galactic average. Deliberately coarse - the
# DELTA/T column carries the exact number, the bar is only for scanning.
PERCENT_PER_BLOCK = 3
MAX_BLOCKS = 10

NO_STATION_MESSAGE = "NO STATION · dock at a station to see its commodity market"
NO_MARKET_MESSAGE = "THIS STATION HAS NO COMMODITY MARKET"
STALE_MARKET_MESSAGE = "OPEN THE COMMODITY MARKET IN GAME TO LOAD THE PRICES"

DEMAND_BRACKET_NOTES = {1: "low demand", 2: "steady demand", 3: "high demand"}
STOCK_BRACKET_NOTES = {1: "low stock", 2: "steady stock", 3: "high stock"}


def vs_galactic_average_bar(price: int, mean_price: int) -> str:
    """'       ███▏' / '▏██████████' - the zero axis always sits in the same
    column, so the bars of every row line up under each other."""
    blocks = 0
    if price and mean_price:
        percent_off = (price - mean_price) / mean_price * 100
        blocks = round(percent_off / PERCENT_PER_BLOCK)
        blocks = max(-MAX_BLOCKS, min(MAX_BLOCKS, blocks))

    left = BAR_BLOCK * -blocks if blocks < 0 else ""
    right = BAR_BLOCK * blocks if blocks > 0 else ""
    return f"{left:>{MAX_BLOCKS}}{ZERO_AXIS}{right:<{MAX_BLOCKS}}"


def format_price(value: int) -> str:
    return format_thousands(value) if value else NO_VALUE


def format_delta(value: int) -> str:
    if not value:
        return NO_VALUE
    return (
        f"+{format_thousands(value)}" if value > 0 else f"-{format_thousands(-value)}"
    )


def note_text(item: MarketItemModel) -> str:
    notes = []
    if item.DemandBracket:
        notes.append(DEMAND_BRACKET_NOTES.get(item.DemandBracket, ""))
    elif item.StockBracket:
        notes.append(STOCK_BRACKET_NOTES.get(item.StockBracket, ""))
    if item.Rare:
        notes.append("rare")
    return " · ".join(note for note in notes if note) or NO_VALUE


@dataclass(frozen=True, slots=True)
class StationMarketRowViewModel:
    commodity: str
    category: str
    buy: str
    sell: str
    stock: str
    demand: str
    galactic_average: str
    vs_galactic_average: str
    delta: str
    note: str

    @classmethod
    def from_item(cls, item: MarketItemModel) -> "StationMarketRowViewModel":
        return cls(
            commodity=item.Name_Localised or item.Name,
            category=item.Category_Localised or item.Category,
            buy=format_price(item.BuyPrice),
            sell=format_price(item.SellPrice),
            stock=format_price(item.Stock),
            demand=format_price(item.Demand),
            galactic_average=format_price(item.MeanPrice),
            vs_galactic_average=vs_galactic_average_bar(item.SellPrice, item.MeanPrice),
            delta=format_delta(
                item.SellPrice - item.MeanPrice if item.SellPrice else 0
            ),
            note=note_text(item),
        )


@dataclass(frozen=True, slots=True)
class StationMarketViewModel:
    header: str
    # Empty when there is a table to show.
    message: str
    rows: tuple[StationMarketRowViewModel, ...]

    @classmethod
    def from_snapshot(cls, snapshot: MarketSnapshot) -> "StationMarketViewModel":
        if not snapshot.is_docked:
            return cls("", NO_STATION_MESSAGE, ())

        station = snapshot.station_name.upper()
        if not snapshot.has_commodities_market:
            return cls(station, NO_MARKET_MESSAGE, ())
        if not snapshot.is_market_data_current:
            return cls(station, STALE_MARKET_MESSAGE, ())

        return cls(
            f"{station} · {len(snapshot.commodities)} COMMODITIES",
            "",
            tuple(
                StationMarketRowViewModel.from_item(item)
                for item in snapshot.commodities
            ),
        )
