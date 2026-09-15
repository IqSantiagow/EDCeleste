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
    StatusEvent,
    StatusFlags,
    StatusFlags2,
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
        cls.status_event_on_foot = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=0,
            Flags2=StatusFlags2.OnFoot,
        )
        cls.status_event_in_taxi = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=0,
            Flags2=StatusFlags2.InTaxi,
        )
        cls.status_event_in_srv = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.InSRV,
            Flags2=0,
        )
        cls.status_event_in_fighter = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.InFighter,
            Flags2=0,
        )
        cls.status_event_in_main_ship = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.InMainShip,
            Flags2=0,
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

    def test_should_prefer_localised_ship_name(self):
        player_projection = PlayerProjection()
        loaded_game_event = self.loaded_game_event.model_copy(
            update={"Ship": "cobramkiii", "Ship_Localised": "Cobra Mk III"}
        )

        player_projection.process_event(loaded_game_event)

        self.assertEqual(player_projection.player_ship, "Cobra Mk III")

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

    def test_should_report_on_foot_from_status_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.status_event_on_foot)

        self.assertTrue(player_projection.is_on_foot)
        self.assertIn(
            PlayerProjection.ON_FOOT_PROJECTION, player_projection.create_projection()
        )

    def test_should_report_in_taxi_from_status_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.status_event_in_taxi)

        self.assertTrue(player_projection.is_in_taxi)
        self.assertIn(
            PlayerProjection.IN_TAXI_PROJECTION, player_projection.create_projection()
        )

    def test_should_report_in_srv_from_status_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.status_event_in_srv)

        self.assertTrue(player_projection.is_in_srv)
        self.assertIn(
            PlayerProjection.IN_SRV_PROJECTION, player_projection.create_projection()
        )

    def test_should_report_in_fighter_from_status_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.status_event_in_fighter)

        self.assertTrue(player_projection.is_in_fighter)
        self.assertIn(
            PlayerProjection.IN_FIGHTER_PROJECTION,
            player_projection.create_projection(),
        )

    def test_should_not_report_vehicle_context_while_in_main_ship(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.status_event_in_main_ship)

        projection = player_projection.create_projection()

        self.assertNotIn(PlayerProjection.ON_FOOT_PROJECTION, projection)
        self.assertNotIn(PlayerProjection.IN_TAXI_PROJECTION, projection)
        self.assertNotIn(PlayerProjection.IN_SRV_PROJECTION, projection)
        self.assertNotIn(PlayerProjection.IN_FIGHTER_PROJECTION, projection)

    def test_should_prioritize_on_foot_over_vehicle_flags(self):
        # OnFoot (Flags2) and InSRV (Flags) should never really be set
        # together in a real Status.json, but on_foot takes priority if they
        # somehow are.
        player_projection = PlayerProjection()

        combined_status_event = StatusEvent(
            event="Status",
            timestamp=datetime.now(),
            Flags=StatusFlags.InSRV,
            Flags2=StatusFlags2.OnFoot,
        )

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(combined_status_event)

        self.assertIn(
            PlayerProjection.ON_FOOT_PROJECTION, player_projection.create_projection()
        )
