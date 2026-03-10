from datetime import datetime
import unittest

from projection.event_projections.player_projection import PlayerProjection
from services.models.game_events import LoadedGameEvent


class PlayerProjectionTest(unittest.TestCase):
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

    def test_should_process_event_and_set_player_state_data(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)

        self.assertEqual(
            player_projection.player_name, self.loaded_game_event.Commander
        )
        self.assertEqual(
            player_projection.player_credits, self.loaded_game_event.Credits
        )
        self.assertEqual(player_projection.player_ship, self.loaded_game_event.Ship)

    def test_should_create_projection(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)

        expected_projection = "Commander name is {0}.Commander has {1} of credits.Commander ship is {2}.".format(
            self.loaded_game_event.Commander,
            self.loaded_game_event.Credits,
            self.loaded_game_event.Ship,
        )

        self.assertEqual(expected_projection, player_projection.create_projection())
