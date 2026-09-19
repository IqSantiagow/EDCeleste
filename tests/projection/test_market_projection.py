import unittest
from datetime import datetime

from edceleste.projection.event_projections.market_projection import MarketProjection
from edceleste.services.models.game_events import (
    DockedEvent,
    LocationEvent,
    MarketEvent,
    MarketItemModel,
    StatusEvent,
    UndockedEvent,
)
from edceleste.services.models.game_models import BaseFactionModel, StationEconomyModel

FAN_HORIZONS_MARKET_ID = 3222042112
OTHER_STATION_MARKET_ID = 4222522883


def make_docked_event(**overrides) -> DockedEvent:
    defaults = dict(
        event="Docked",
        timestamp=datetime.now(),
        StarSystem="Beta Sculptoris",
        StationName="Fan Horizons",
        StationType="Coriolis",
        SystemAddress=1774711389,
        MarketID=FAN_HORIZONS_MARKET_ID,
        StationFaction=BaseFactionModel(Name="The Winged Hussars"),
        StationGovernment_Localised="Cooperative",
        StationServices=["dock", "commodities", "refuel"],
        StationEconomy_Localised="High Tech",
        StationEconomies=[
            StationEconomyModel(Name_Localised="High Tech", Proportion=1.0)
        ],
        DistFromStarLS=3877.3,
    )
    defaults.update(overrides)
    return DockedEvent(**defaults)


def make_market_event(**overrides) -> MarketEvent:
    defaults = dict(
        event="Market",
        timestamp=datetime.now(),
        MarketID=FAN_HORIZONS_MARKET_ID,
        StationName="Fan Horizons",
        StarSystem="Beta Sculptoris",
        Items=[make_market_item()],
    )
    defaults.update(overrides)
    return MarketEvent(**defaults)


def make_market_item(**overrides) -> MarketItemModel:
    defaults = dict(
        Name="$platinum_name;",
        Name_Localised="Platinum",
        Category="$MARKET_category_metals;",
        Category_Localised="Metals",
        BuyPrice=0,
        SellPrice=42220,
        MeanPrice=19756,
        StockBracket=0,
        DemandBracket=3,
        Stock=0,
        Demand=9182,
    )
    defaults.update(overrides)
    return MarketItemModel(**defaults)


class TestMarketProjectionStationTracking(unittest.TestCase):
    def test_docked_event_remembers_the_station_and_its_market(self):
        projection = MarketProjection()

        projection.process_event(make_docked_event())

        self.assertEqual(projection.station_name, "Fan Horizons")
        self.assertEqual(projection.docked_market_id, FAN_HORIZONS_MARKET_ID)
        self.assertTrue(projection.has_commodities_market)

    def test_docked_event_without_commodities_service_marks_no_market(self):
        projection = MarketProjection()

        projection.process_event(make_docked_event(StationServices=["dock", "refuel"]))

        self.assertFalse(projection.has_commodities_market)

    def test_location_event_while_docked_remembers_the_station(self):
        projection = MarketProjection()

        projection.process_event(
            LocationEvent(
                event="Location",
                timestamp=datetime.now(),
                StarSystem="Beta Sculptoris",
                SystemAddress=1774711389,
                StarPos=[0.0, 0.0, 0.0],
                DistFromStarLS=100.0,
                Docked=True,
                StationName="Fan Horizons",
                MarketID=FAN_HORIZONS_MARKET_ID,
                StationServices=["dock", "commodities"],
            )
        )

        self.assertEqual(projection.docked_market_id, FAN_HORIZONS_MARKET_ID)
        self.assertTrue(projection.has_commodities_market)

    def test_location_event_while_not_docked_is_ignored(self):
        projection = MarketProjection()

        projection.process_event(
            LocationEvent(
                event="Location",
                timestamp=datetime.now(),
                StarSystem="Beta Sculptoris",
                SystemAddress=1774711389,
                StarPos=[0.0, 0.0, 0.0],
                DistFromStarLS=100.0,
                Docked=False,
            )
        )

        self.assertIsNone(projection.docked_market_id)

    def test_undocked_event_forgets_the_station(self):
        projection = MarketProjection()
        projection.process_event(make_docked_event())

        projection.process_event(
            UndockedEvent(
                event="Undocked", timestamp=datetime.now(), StationName="Fan Horizons"
            )
        )

        self.assertIsNone(projection.station_name)
        self.assertIsNone(projection.docked_market_id)
        self.assertFalse(projection.has_commodities_market)

    def test_undocked_event_keeps_the_commodities_read_from_the_file(self):
        """The game leaves Market.json on disk, so docking here again matches
        by MarketID without the player reopening the market."""
        projection = MarketProjection()
        projection.process_event(make_market_event())

        projection.process_event(
            UndockedEvent(
                event="Undocked", timestamp=datetime.now(), StationName="Fan Horizons"
            )
        )

        self.assertEqual(len(projection.commodities), 1)

    def test_status_events_do_not_touch_the_market_state(self):
        """Status.json arrives every second - letting it in would rebuild the
        whole commodity table that often."""
        projection = MarketProjection()
        projection.process_event(make_docked_event())

        projection.process_event(
            StatusEvent(event="Status", timestamp=datetime.now(), Flags=0, Flags2=0)
        )

        self.assertEqual(projection.docked_market_id, FAN_HORIZONS_MARKET_ID)


class TestMarketProjectionStaleness(unittest.TestCase):
    def test_market_data_is_current_when_the_market_ids_match(self):
        projection = MarketProjection()
        projection.process_event(make_docked_event())
        projection.process_event(make_market_event())

        self.assertTrue(projection.is_market_data_current())

    def test_market_data_is_stale_when_the_file_belongs_to_another_station(self):
        """The edge case this card exists to survive: dock somewhere new
        without opening the market and the old file is still on disk."""
        projection = MarketProjection()
        projection.process_event(make_market_event())
        projection.process_event(
            make_docked_event(
                StationName="Rutherford Prospect", MarketID=OTHER_STATION_MARKET_ID
            )
        )

        self.assertFalse(projection.is_market_data_current())

    def test_market_data_is_stale_when_no_market_file_was_read(self):
        projection = MarketProjection()
        projection.process_event(make_docked_event())

        self.assertFalse(projection.is_market_data_current())

    def test_market_data_is_stale_when_not_docked_even_if_the_file_exists(self):
        projection = MarketProjection()
        projection.process_event(make_market_event())

        self.assertFalse(projection.is_market_data_current())


class TestMarketProjectionText(unittest.TestCase):
    def test_projection_is_empty_when_the_market_data_is_stale(self):
        projection = MarketProjection()
        projection.process_event(make_market_event())

        self.assertEqual(projection.create_projection(), "")

    def test_projection_names_the_station_and_the_commodity_count(self):
        projection = MarketProjection()
        projection.process_event(make_docked_event())
        projection.process_event(make_market_event())

        projection_text = projection.create_projection()

        self.assertIn("Fan Horizons", projection_text)
        self.assertIn("1 commodities", projection_text)

    def test_projection_names_the_best_prices_against_the_galactic_average(self):
        projection = MarketProjection()
        projection.process_event(make_docked_event())
        projection.process_event(
            make_market_event(
                Items=[
                    make_market_item(Name_Localised="Platinum"),
                    make_market_item(
                        Name_Localised="Gold", SellPrice=46990, MeanPrice=47350
                    ),
                ]
            )
        )

        projection_text = projection.create_projection()

        self.assertIn("Platinum at 42220 (+22464 per tonne)", projection_text)
        self.assertIn("Gold", projection_text)


if __name__ == "__main__":
    unittest.main()
