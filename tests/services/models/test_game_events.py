import unittest
from datetime import datetime

from pydantic import TypeAdapter

from edceleste.services.models.game_events import UnknownCheckedEvent
from edceleste.services.models.journal_event import JournalEvent


class StartupLoadingFlagTest(unittest.TestCase):
    def test_game_event_is_live_by_default(self):
        event = UnknownCheckedEvent(event="SomeEvent", timestamp=datetime.now())

        self.assertFalse(event.is_startup_loading)

    def test_event_parsed_from_a_journal_line_is_live(self):
        journal_line = '{"timestamp":"2026-10-18T12:00:00Z","event":"SomeEvent"}'

        event = TypeAdapter(JournalEvent).validate_json(journal_line)

        self.assertFalse(event.is_startup_loading)

    def test_startup_loading_flag_is_left_out_of_every_dump(self):
        # The LLM prompt of an event reaction is the JSON dump of the event.
        # The flag is bookkeeping of the app, the model must not see it.
        event = UnknownCheckedEvent(
            event="SomeEvent", timestamp=datetime.now(), is_startup_loading=True
        )

        self.assertTrue(event.is_startup_loading)
        self.assertNotIn("is_startup_loading", event.model_dump_json())
        self.assertNotIn("is_startup_loading", event.model_dump())


if __name__ == "__main__":
    unittest.main()
