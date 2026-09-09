from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.services.event_bus import EventBus
from edceleste.services.event_reactions_service import EventReactionsService
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_events import LoadedGameEvent
from edceleste.services.models.settings_model import (
    EventReactionModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.settings_service import SettingsService


def _make_settings(event_reactions: dict[str, bool] | None = None) -> SettingsModel:
    settings = SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="prompt", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )
    if event_reactions is not None:
        settings.event_reactions = EventReactionModel(reactions=event_reactions)
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
        # EventReactionsService no longer builds its state in __init__ - that
        # now happens in reload_service(), driven by the cold-start flow. Call
        # it here so self.settings is wired in before the test uses it.
        service = EventReactionsService(
            event_bus=event_bus if event_bus is not None else Mock(spec=EventBus),
            settings_service=self.settings_service,
        )
        service.reload_service()
        return service

    async def test_process_event_does_not_publish_when_setting_disabled(self):
        self.settings_service.get_settings.return_value = _make_settings(
            event_reactions={"LoadGame": False}
        )
        event_bus = Mock(spec=EventBus)
        service = self._make_service(event_bus)

        await service.process_event(_loaded_game_event())

        event_bus.publish.assert_not_called()

    async def test_process_event_does_not_publish_when_event_type_missing(self):
        # An event type absent from the mapping defaults to False (opt-in
        # behavior), same as an explicit False.
        self.settings_service.get_settings.return_value = _make_settings(
            event_reactions={}
        )
        event_bus = Mock(spec=EventBus)
        service = self._make_service(event_bus)

        await service.process_event(_loaded_game_event())

        event_bus.publish.assert_not_called()

    async def test_process_event_publishes_event_reaction_when_setting_enabled(self):
        loaded_game_event = _loaded_game_event()
        self.settings_service.get_settings.return_value = _make_settings(
            event_reactions={"LoadGame": True}
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
        new_settings.event_reactions = ["not", "a", "mapping"]

        issue = service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "event_reactions")
        self.assertEqual(issue.field, "event_reactions")

    def test_validate_settings_returns_none_for_valid_mapping(self):
        service = self._make_service()
        new_settings = _make_settings(event_reactions={"LoadGame": True})

        issue = service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_reload_service_refreshes_cached_settings_from_settings_service(self):
        service = self._make_service()
        new_settings = _make_settings(event_reactions={"FSDJump": True})
        self.settings_service.get_settings.return_value = new_settings

        service.reload_service()

        self.assertIs(service.settings, new_settings)

    async def test_publishing_game_event_on_real_bus_triggers_reaction(self):
        # Same scenario as
        # test_process_event_publishes_event_reaction_when_setting_enabled above,
        # exercised end-to-end through a real EventBus.
        self.settings_service.get_settings.return_value = _make_settings(
            event_reactions={"LoadGame": True}
        )
        event_bus = EventBus()
        service = EventReactionsService(
            event_bus=event_bus, settings_service=self.settings_service
        )
        service.reload_service()
        subscriber = AsyncMock()
        event_bus.subscribe(EventReactionEvent, subscriber)
        loaded_game_event = _loaded_game_event()

        await event_bus.publish(loaded_game_event)

        subscriber.assert_called_once()
        published_event = subscriber.call_args.args[0]
        self.assertIsInstance(published_event, EventReactionEvent)
        self.assertEqual(published_event.event, loaded_game_event)

    # --- cold_start ---

    async def test_cold_start_yields_pending_status_first(self):
        service = self._make_service()
        service.reload_service = Mock()

        # ColdStartStatus is mutated in place and re-yielded on completion, so
        # the pending status must be inspected right after this first yield -
        # collecting every yield into a list first would show the mutated,
        # already-completed object instead.
        first_status = await service.cold_start().__anext__()

        self.assertEqual(first_status.service, "event_reactions")
        self.assertFalse(first_status.is_critical)
        self.assertFalse(first_status.completed)
        self.assertIsNone(first_status.message)

    async def test_cold_start_yields_completed_status_when_reload_service_succeeds(
        self,
    ):
        service = self._make_service()
        service.reload_service = Mock()

        statuses = [status async for status in service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertIsNone(last_status.message)

    async def test_cold_start_yields_error_message_when_reload_service_fails(self):
        service = self._make_service()
        service.reload_service = Mock(side_effect=RuntimeError("settings unreachable"))

        statuses = [status async for status in service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "settings unreachable")


if __name__ == "__main__":
    unittest.main()
