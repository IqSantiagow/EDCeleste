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

    BEST_DEALS_PROJECTION = " The best prices against the galactic average: {0}."

    def __init__(self):
        self.station_name = None
        # None means we do not know of any station we are docked at.
        self.docked_market_id = None
        self.has_commodities_market = False
        self.market_file_market_id = None
        self.commodities = []

    def process_event(self, event: BaseModel):
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
        return (
            self.docked_market_id is not None
            and self.docked_market_id == self.market_file_market_id
        )

    def create_projection(self) -> str:
        if not self.is_market_data_current():
            return ""

        projection_string = self.MARKET_PROJECTION.format(
            self.station_name, len(self.commodities)
        )

        best_deals = self.__best_deals()
        if best_deals:
            projection_string += self.BEST_DEALS_PROJECTION.format(best_deals)

        return projection_string

    def __remember_station(self, station_name, market_id, station_services) -> None:
        self.station_name = station_name
        self.docked_market_id = market_id
        self.has_commodities_market = COMMODITIES_SERVICE in station_services

    def __best_deals(self) -> str:
        sold_here = [item for item in self.commodities if item.SellPrice]
        sold_here.sort(key=lambda item: item.SellPrice - item.MeanPrice, reverse=True)
        return ", ".join(
            f"{item.Name_Localised or item.Name} at {item.SellPrice} "
            f"({item.SellPrice - item.MeanPrice:+} per tonne)"
            for item in sold_here[:TOP_DEALS_COUNT]
        )
