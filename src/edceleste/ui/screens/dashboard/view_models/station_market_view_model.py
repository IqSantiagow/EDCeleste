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
    column, so the bars of every row line up under each other.

    Left of the axis = cheaper than average, right = dearer. Capped at
    MAX_BLOCKS each side. Only the axis when either price is 0."""
    blocks = 0
    if price and mean_price:
        percent_off = (price - mean_price) / mean_price * 100
        blocks = round(percent_off / PERCENT_PER_BLOCK)
        blocks = max(-MAX_BLOCKS, min(MAX_BLOCKS, blocks))

    left = BAR_BLOCK * -blocks if blocks < 0 else ""
    right = BAR_BLOCK * blocks if blocks > 0 else ""
    return f"{left:>{MAX_BLOCKS}}{ZERO_AXIS}{right:<{MAX_BLOCKS}}"


def format_price(value: int) -> str:
    """1284 -> "1 284". Used for prices, stock and demand. 0 means the
    station does not trade it, so it shows NO_VALUE ("-")."""
    return format_thousands(value) if value else NO_VALUE


def format_delta(value: int) -> str:
    """Always with a sign: 300 -> "+300", -1284 -> "-1 284". 0 shows NO_VALUE
    ("-")."""
    if not value:
        return NO_VALUE
    return (
        f"+{format_thousands(value)}" if value > 0 else f"-{format_thousands(-value)}"
    )


def note_text(item: MarketItemModel) -> str:
    """The NOTE column, e.g. "high demand · rare". The demand bracket wins: the
    stock bracket is shown only when there is no demand bracket. NO_VALUE
    ("-") when there is nothing to say."""
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
        """One table row, every cell already a text. Localised names win over
        the raw ones. The bar and the delta compare the SELL price with the
        galactic average. When the station does not buy the item (SellPrice
        0) the delta is "-" and the bar is empty."""
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
        """Checks in order and stops at the first problem:
        1. not docked -> no header, NO_STATION_MESSAGE,
        2. station has no commodity market -> NO_MARKET_MESSAGE,
        3. no Market.json for this station yet -> STALE_MARKET_MESSAGE.
        In these cases there are no rows. Otherwise the header says the station
        and the number of commodities, the message is empty and there is one
        row per commodity."""
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
