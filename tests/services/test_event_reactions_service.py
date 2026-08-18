from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock

from services.event_bus import EventBus
from services.event_reactions_service import EventReactionsService
from services.models.event_reaction_event import EventReactionEvent
from services.models.game_events import LoadedGameEvent
from services.models.settings_model import (
    EventReactionModel,
    LLMModel,
    PathModel,
    SettingsModel,
    TTSModel,
)
from services.settings_service import SettingsService


def _make_settings(event_reaction: dict[str, bool] | None = None) -> SettingsModel:
    settings = SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="prompt", user_prompt=""),
    )
    if event_reaction is not None:
        settings.event_reaction = EventReactionModel(event_reaction=event_reaction)
    return settings


def _loaded_game_event(**overrides) -> LoadedGameEvent:
    defaults = dict(
        event="LoadGame",
        timestamp=datetime.now(),
        Commander="TestCommander",
        FID="F123456",
        Horizons=True,
        Odyssey=False,
        Ship="Sidewinder",
        ShipID=1,
        ShipIdent="TS-001",
        ShipName="Test Ship",
        StartLanded=False,
        StartDead=False,
        GameMode="Solo",
        Group="",
        Credits=1000000,
        Loan=0,
        FuelLevel=1.0,
        FuelCapacity=4.0,
    )
    defaults.update(overrides)
    return LoadedGameEvent(**defaults)


class EventReactionsServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings()

    def _make_service(self, event_bus=None):
        # EventReactionsService.__init__ eagerly calls reload_service(), so
        # settings_service.get_settings.return_value must be set beforehand.
        return EventReactionsService(
            event_bus=event_bus if event_bus is not None else Mock(spec=EventBus),
            settings_service=self.settings_service,
        )

    async def test_process_event_does_not_publish_when_setting_disabled(self):
        self.settings_service.get_settings.return_value = _make_settings(
            event_reaction={"LoadGame": False}
        )
        event_bus = Mock(spec=EventBus)
        service = self._make_service(event_bus)

        await service.process_event(_loaded_game_event())

        event_bus.publish.assert_not_called()

    async def test_process_event_does_not_publish_when_event_type_missing(self):
        # An event type absent from the mapping defaults to False (opt-in
        # behavior), same as an explicit False.
        self.settings_service.get_settings.return_value = _make_settings(
            event_reaction={}
        )
        event_bus = Mock(spec=EventBus)
        service = self._make_service(event_bus)

        await service.process_event(_loaded_game_event())

        event_bus.publish.assert_not_called()

    async def test_process_event_publishes_event_reaction_when_setting_enabled(self):
        loaded_game_event = _loaded_game_event()
        self.settings_service.get_settings.return_value = _make_settings(
            event_reaction={"LoadGame": True}
        )
        event_bus = Mock(spec=EventBus)
        service = self._make_service(event_bus)

        await service.process_event(loaded_game_event)

        event_bus.publish.assert_called_once_with(
            EventReactionEvent(event=loaded_game_event)
        )

    def test_validate_settings_returns_issue_for_non_mapping_event_reaction(self):
        service = self._make_service()
        new_settings = _make_settings()
        # SettingsModel has no validate_assignment=True, so this plain
        # attribute assignment is allowed and lets us exercise the defensive
        # isinstance check in validate_settings.
        new_settings.event_reaction = ["not", "a", "mapping"]

        issue = service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "event_reaction")
        self.assertEqual(issue.field, "event_reaction")

    def test_validate_settings_returns_none_for_valid_mapping(self):
        service = self._make_service()
        new_settings = _make_settings(event_reaction={"LoadGame": True})

        issue = service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_reload_service_refreshes_cached_settings_from_settings_service(self):
        service = self._make_service()
        new_settings = _make_settings(event_reaction={"FSDJump": True})
        self.settings_service.get_settings.return_value = new_settings

        service.reload_service()

        self.assertIs(service.settings, new_settings)

    async def test_publishing_game_event_on_real_bus_triggers_reaction(self):
        # Same scenario as
        # test_process_event_publishes_event_reaction_when_setting_enabled above,
        # exercised end-to-end through a real EventBus.
        self.settings_service.get_settings.return_value = _make_settings(
            event_reaction={"LoadGame": True}
        )
        event_bus = EventBus()
        EventReactionsService(
            event_bus=event_bus, settings_service=self.settings_service
        )
        subscriber = AsyncMock()
        event_bus.subscribe(EventReactionEvent, subscriber)
        loaded_game_event = _loaded_game_event()

        await event_bus.publish(loaded_game_event)

        subscriber.assert_called_once()
        published_event = subscriber.call_args.args[0]
        self.assertIsInstance(published_event, EventReactionEvent)
        self.assertEqual(published_event.event, loaded_game_event)


if __name__ == "__main__":
    unittest.main()
