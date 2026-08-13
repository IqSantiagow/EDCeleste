from datetime import datetime
import unittest
from unittest.mock import AsyncMock

from services.game_state_service import GameStateService
from services.event_bus import EventBus
from services.models.game_events import LoadedGameEvent
from services.models.game_state_changed_event import GameStateChangedEvent


class GameStateIntegration(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded_game_event = LoadedGameEvent(
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

    async def test_should_receive_event_from_bus(self):
        event_bus = EventBus()

        game_state = GameStateService(event_bus)

        await event_bus.publish(self.loaded_game_event)

        self.assertIn(
            "Commander name is {0}".format(self.loaded_game_event.Commander),
            game_state.get_game_state_projection(),
        )
        self.assertIn(
            "Commander has {0} of credits".format(self.loaded_game_event.Credits),
            game_state.get_game_state_projection(),
        )
        self.assertIn(
            "Commander ship is {0}".format(self.loaded_game_event.Ship),
            game_state.get_game_state_projection(),
        )
        self.assertIn(
            "Current fuel level is: {0}".format(self.loaded_game_event.FuelLevel),
            game_state.get_game_state_projection(),
        )

    async def test_should_publish_game_state_changed_event_after_processing_event(
        self,
    ):
        event_bus = EventBus()
        game_state = GameStateService(event_bus)
        subscriber = AsyncMock()
        event_bus.subscribe(GameStateChangedEvent, subscriber)

        await event_bus.publish(self.loaded_game_event)

        subscriber.assert_called_once()
        published_event = subscriber.call_args.args[0]
        self.assertIsInstance(published_event, GameStateChangedEvent)
        self.assertEqual(
            published_event.game_state, game_state.get_game_state_projection()
        )
