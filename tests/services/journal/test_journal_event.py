from datetime import datetime
import unittest

from pydantic import TypeAdapter

from services.models.game_events import UnknownCheckedEvent
from services.models.journal_event import JournalEvent

from tests import TEST_KNOWN_EVENTS_FILE_LOCATION


class JournalEventTest(unittest.TestCase):
    event_template = '{{"event": "{0}", "timestamp": "{1}"}}'

    @classmethod
    def setUpClass(cls):
        cls.adapter = TypeAdapter(JournalEvent)

    def test_should_return_unknown_discriminator(self):
        json_event = self.event_template.format("Unknown", datetime.now())

        parsed_json_event_obj = self.adapter.validate_json(json_event)

        self.assertIsInstance(parsed_json_event_obj, UnknownCheckedEvent)

    def test_should_return_known_event(self):
        with open(TEST_KNOWN_EVENTS_FILE_LOCATION, mode="r") as f:
            while line := f.readline():
                parsed_json_event_obj = self.adapter.validate_json(line)
                self.assertNotIsInstance(parsed_json_event_obj, UnknownCheckedEvent)
