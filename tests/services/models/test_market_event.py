import json
import unittest

from edceleste.services.models.game_events import (
    MarketEvent,
    NonJournalFileEvent,
)
from edceleste.services.models.journal_event import KNOWN_EVENTS

MARKET_FILE = json.dumps(
    {
        "timestamp": "2026-09-14T09:42:30Z",
        "event": "Market",
        "MarketID": 3222042112,
        "StationName": "Fan Horizons",
        "StarSystem": "Beta Sculptoris",
        "Items": [
            {
                "id": 128049152,
                "Name": "$platinum_name;",
                "Name_Localised": "Platinum",
                "Category": "$MARKET_category_metals;",
                "Category_Localised": "Metals",
                "BuyPrice": 0,
                "SellPrice": 42220,
                "MeanPrice": 19756,
                "StockBracket": 0,
                "DemandBracket": 3,
                "Stock": 0,
                "Demand": 9182,
                "Consumer": True,
                "Producer": False,
                "Rare": False,
            }
        ],
    }
)


class TestMarketEvent(unittest.TestCase):
    def test_parses_the_market_file_the_game_writes(self):
        event = MarketEvent.model_validate_json(MARKET_FILE)

        self.assertEqual(event.MarketID, 3222042112)
        self.assertEqual(event.StationName, "Fan Horizons")
        self.assertEqual(event.Items[0].Name_Localised, "Platinum")
        self.assertEqual(event.Items[0].SellPrice, 42220)
        self.assertEqual(event.Items[0].MeanPrice, 19756)

    def test_ignores_fields_the_model_does_not_know(self):
        event = MarketEvent.model_validate_json(MARKET_FILE)

        self.assertFalse(hasattr(event.Items[0], "Consumer"))

    def test_items_default_to_empty_when_the_station_sells_nothing(self):
        event = MarketEvent.model_validate_json(
            json.dumps(
                {
                    "timestamp": "2026-09-14T09:42:30Z",
                    "event": "Market",
                    "MarketID": 1,
                    "StationName": "Empty Dock",
                    "StarSystem": "Sol",
                }
            )
        )

        self.assertEqual(event.Items, [])

    def test_is_a_non_journal_file_event(self):
        """GameStateService routes on this marker - without it the market would
        be pushed into the journal log stream shown on the dashboard."""
        event = MarketEvent.model_validate_json(MARKET_FILE)

        self.assertIsInstance(event, NonJournalFileEvent)

    def test_market_is_not_a_known_journal_event(self):
        """KNOWN_EVENTS drives the event_reactions keys in config.yaml, so
        adding Market there would change the shape of the user's config file."""
        self.assertNotIn("Market", [event.value for event in KNOWN_EVENTS])


if __name__ == "__main__":
    unittest.main()
