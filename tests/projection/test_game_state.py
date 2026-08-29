from datetime import datetime
import unittest
from unittest.mock import Mock

from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import LoadedGameEvent, FuelScoopEvent


class TestGameState(unittest.IsolatedAsyncioTestCase):
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

        cls.fuel_scoop_event = FuelScoopEvent(
            event="FuelScoop", timestamp=datetime.now(), Scooped=1.0, Total=1.0
        )

    async def test_should_process_event_and_refresh_state_soft_assert(self):
        # spec=EventBus makes `publish` an AsyncMock automatically (it's an
        # `async def` on the real class), so `await event_bus.publish(...)`
        # in process_event doesn't blow up on a plain Mock.
        mock_event_bus = Mock(spec=EventBus)

        game_state = GameStateService(mock_event_bus)

        await game_state.process_event(self.loaded_game_event)

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

    async def test_should_refresh_state_with_new_event(self):
        mock_event_bus = Mock(spec=EventBus)

        game_state = GameStateService(mock_event_bus)

        await game_state.process_event(self.loaded_game_event)

        new_loaded_event = self.loaded_game_event.model_copy()

        new_loaded_event.Commander = "NewCommander"

        await game_state.process_event(new_loaded_event)

        self.assertIn(
            "Commander name is {0}".format(new_loaded_event.Commander),
            game_state.get_game_state_projection(),
        )

    async def test_should_refresh_state_with_new_event_and_keep_old_data_not_in_event(
        self,
    ):
        mock_event_bus = Mock(spec=EventBus)

        game_state = GameStateService(mock_event_bus)

        await game_state.process_event(self.loaded_game_event)

        await game_state.process_event(self.fuel_scoop_event)

        self.assertIn(
            "Commander name is {0}".format(self.loaded_game_event.Commander),
            game_state.get_game_state_projection(),
        )
        self.assertIn(
            "Current fuel level is: {0}".format(self.fuel_scoop_event.Total),
            game_state.get_game_state_projection(),
        )

    def test_should_return_empty_projection_if_no_data(self):
        mock_event_bus = Mock()

        game_state = GameStateService(mock_event_bus)

        self.assertEqual("", game_state.get_game_state_projection())
