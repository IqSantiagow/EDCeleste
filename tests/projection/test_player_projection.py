from datetime import datetime
import unittest

from edceleste.projection.event_projections.player_projection import PlayerProjection
from edceleste.services.models.game_events import (
    LoadedGameEvent,
    CommanderEvent,
    RankEvent,
    PromotionEvent,
    ReputationEvent,
    DiedEvent,
    ResurrectEvent,
)


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
        cls.commander_event = CommanderEvent(
            event="Commander",
            timestamp=datetime.now(),
            FID="F123456",
            Name="SANTIAGOW",
        )
        cls.rank_event = RankEvent(
            event="Rank",
            timestamp=datetime.now(),
            Combat=5,
            Trade=3,
            Explore=1,
        )
        cls.reputation_event = ReputationEvent(
            event="Reputation",
            timestamp=datetime.now(),
            Empire=6.7,
            Federation=0.2,
            Independent=0.0,
            Alliance=1.5,
        )
        cls.combat_promotion_event = PromotionEvent(
            event="Promotion",
            timestamp=datetime.now(),
            Combat=6,
        )
        cls.died_event = DiedEvent(event="Died", timestamp=datetime.now())
        cls.resurrect_event = ResurrectEvent(
            event="Resurrect",
            timestamp=datetime.now(),
            Option="rebuy",
            Cost=26799,
            Bankrupt=False,
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

        expected_projection = (
            "Commander name is {0}.Commander has {1} of credits.Commander ship is {2}."
        ).format(
            self.loaded_game_event.Commander,
            self.loaded_game_event.Credits,
            self.loaded_game_event.Ship,
        )

        self.assertEqual(expected_projection, player_projection.create_projection())

    def test_should_set_player_name_from_commander_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.commander_event)

        self.assertEqual(player_projection.player_name, self.commander_event.Name)

    def test_should_process_rank_event_and_map_rank_names(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.rank_event)

        expected_ranks = PlayerProjection.RANK_PROJECTION.format(
            "Master", "Dealer", "Mostly Aimless"
        )

        self.assertIn(expected_ranks, player_projection.create_projection())

    def test_should_omit_rank_line_when_ranks_partially_known(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.combat_promotion_event)

        projection = player_projection.create_projection()

        self.assertNotIn("Commander ranks are", projection)
        self.assertNotIn("None", projection)

    def test_should_process_reputation_event_and_create_projection(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.reputation_event)

        expected_reputation = PlayerProjection.REPUTATION_PROJECTION.format(
            6.7, 0.2, 1.5
        )

        self.assertIn(expected_reputation, player_projection.create_projection())

    def test_should_mark_commander_dead_on_died_and_alive_on_resurrect(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.died_event)

        self.assertFalse(player_projection.is_alive)
        self.assertIn(
            PlayerProjection.DEAD_PROJECTION, player_projection.create_projection()
        )

        player_projection.process_event(self.resurrect_event)

        self.assertTrue(player_projection.is_alive)
        self.assertNotIn(
            PlayerProjection.DEAD_PROJECTION, player_projection.create_projection()
        )
