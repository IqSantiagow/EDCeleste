from datetime import datetime
import unittest

from projection.game_state import GameState
from services.event_bus import EventBus
from services.models.game_events import LoadedGameEvent


class GameStateIntegration(unittest.TestCase):
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

    def test_should_receive_event_from_bus(self):
        event_bus = EventBus()

        game_state = GameState(event_bus)

        event_bus.publish(self.loaded_game_event)

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
