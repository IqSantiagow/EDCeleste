import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    DockedEvent,
    LocationEvent,
    MarketEvent,
    UndockedEvent,
)

logger = logging.getLogger(__name__)

COMMODITIES_SERVICE = "commodities"

# How many bargains to name for the LLM. The whole table is on the dashboard.
TOP_DEALS_COUNT = 3


class MarketProjection(Projection):
    MARKET_PROJECTION = "Station {0} sells {1} commodities."

    BEST_DEALS_PROJECTION = "The best prices against the galactic average: {0}."

    def __init__(self):
        """Two market ids are kept apart on purpose: the station we are docked
        at (from the journal) and the station the Market.json prices belong to.
        Prices count only when the two match."""
        self.station_name = None
        # None means we do not know of any station we are docked at.
        self.docked_market_id = None
        self.has_commodities_market = False
        self.market_file_market_id = None
        self.commodities = []

    def process_event(self, event: BaseModel):
        """- Docked, or Location with Docked=True (game loaded at a station)
          -> remembers the station, its market id and if it has a commodities
          market.
        - Undocked -> forgets the station. The old prices stay, but they stop
          being current.
        - Market (Market.json, written when the pilot opens the market in
          game) -> market id and commodity list of that file.
        Any other event is skipped."""
        if isinstance(event, DockedEvent):
            logger.debug("Received market event: %s", event)
            self.__remember_station(
                event.StationName, event.MarketID, event.StationServices
            )
            return

        if isinstance(event, LocationEvent) and event.Docked:
            logger.debug("Received market event: %s", event)
            self.__remember_station(
                event.StationName or "", event.MarketID, event.StationServices
            )
            return

        if isinstance(event, UndockedEvent):
            logger.debug("Received market event: %s", event)
            self.station_name = None
            self.docked_market_id = None
            self.has_commodities_market = False
            return

        if isinstance(event, MarketEvent):
            logger.debug("Received market event: %s", event)
            self.market_file_market_id = event.MarketID
            self.commodities = event.Items
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def is_market_data_current(self) -> bool:
        """True only while docked at the station whose Market.json we have.
        False when undocked, or when the prices are from another station
        because the pilot has not opened the market here yet."""
        return (
            self.docked_market_id is not None
            and self.docked_market_id == self.market_file_market_id
        )

    def create_projection(self) -> str:
        """Empty string unless the prices belong to the station we are docked
        at, so the LLM never talks about another station's prices. Otherwise
        the station name and the number of commodities, then one space and
        up to TOP_DEALS_COUNT best deals. The best deals sentence is left out
        when the station buys nothing."""
        if not self.is_market_data_current():
            return ""

        sentences = [
            self.MARKET_PROJECTION.format(self.station_name, len(self.commodities))
        ]

        best_deals = self.__best_deals()
        if best_deals:
            sentences.append(self.BEST_DEALS_PROJECTION.format(best_deals))

        return " ".join(sentences)

    def __remember_station(self, station_name, market_id, station_services) -> None:
        """Shared by Docked and Location, which carry the same three fields."""
        self.station_name = station_name
        self.docked_market_id = market_id
        self.has_commodities_market = COMMODITIES_SERVICE in station_services

    def __best_deals(self) -> str:
        """Only commodities the station buys from us (SellPrice above 0),
        sorted by how far the sell price is above the galactic average. Gives
        the top TOP_DEALS_COUNT as one text like "Gold at 9500 (+300 per
        tonne)", or an empty string when the station buys nothing."""
        sold_here = [item for item in self.commodities if item.SellPrice]
        sold_here.sort(key=lambda item: item.SellPrice - item.MeanPrice, reverse=True)
        return ", ".join(
            f"{item.Name_Localised or item.Name} at {item.SellPrice} "
            f"({item.SellPrice - item.MeanPrice:+} per tonne)"
            for item in sold_here[:TOP_DEALS_COUNT]
        )
