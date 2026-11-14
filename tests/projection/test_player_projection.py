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
    GameScreen,
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
            "Commander name is {0}. Commander has {1} of credits. "
            "Commander ship is {2}. Commander plays in {3} game mode."
        ).format(
            self.loaded_game_event.Commander,
            self.loaded_game_event.Credits,
            self.loaded_game_event.Ship,
            self.loaded_game_event.GameMode,
        )

        self.assertEqual(expected_projection, player_projection.create_projection())

    def test_should_set_game_mode_from_loaded_game_event(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)

        self.assertEqual(player_projection.game_mode, "Solo")

    def test_should_omit_game_mode_before_game_is_loaded(self):
        player_projection = PlayerProjection()

        self.assertNotIn("game mode", player_projection.create_projection())

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

    def test_should_warn_only_while_name_or_ship_is_unknown(self):
        player_projection = PlayerProjection()
        player_logger = "edceleste.projection.event_projections.player_projection"

        # A Commander event gives the name, but the ship is still unknown.
        player_projection.process_event(self.commander_event)
        with self.assertLogs(player_logger, level="WARNING"):
            player_projection.create_projection()

        player_projection.process_event(self.loaded_game_event)
        with self.assertNoLogs(player_logger, level="WARNING"):
            player_projection.create_projection()

    def test_should_join_every_optional_commander_sentence_with_one_space(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self.loaded_game_event)
        player_projection.process_event(self.rank_event)
        player_projection.process_event(self.reputation_event)
        player_projection.process_event(self.died_event)
        player_projection.process_event(self.status_event_on_foot)

        expected_projection = (
            "Commander name is TestCommander. Commander has 1000000 of credits. "
            "Commander ship is Sidewinder. Commander plays in Solo game mode. "
            "Commander ranks are Combat: Master, Trade: Dealer, "
            "Exploration: Mostly Aimless. "
            "Commander reputation is Empire: 6.7%, Federation: 0.2%, Alliance: 1.5%. "
            "Commander has been destroyed and is awaiting rebuy. "
            "Commander is currently on foot."
        )

        self.assertEqual(expected_projection, player_projection.create_projection())

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

    def test_should_start_with_unknown_screen(self):
        self.assertEqual(PlayerProjection().current_screen, GameScreen.UNKNOWN)

    def test_should_read_the_screen_from_every_gui_focus_the_game_writes(self):
        expected_screens = {
            0: GameScreen.COCKPIT,
            1: GameScreen.RIGHT_PANEL,
            2: GameScreen.LEFT_PANEL,
            3: GameScreen.COMMS_PANEL,
            4: GameScreen.ROLE_PANEL,
            5: GameScreen.STATION_SERVICES,
            6: GameScreen.GALAXY_MAP,
            7: GameScreen.SYSTEM_MAP,
            8: GameScreen.ORRERY,
            9: GameScreen.FSS,
            10: GameScreen.SAA,
            11: GameScreen.CODEX,
        }
        for gui_focus, expected_screen in expected_screens.items():
            with self.subTest(gui_focus=gui_focus):
                player_projection = PlayerProjection()

                player_projection.process_event(self._make_status_event(gui_focus))

                self.assertEqual(player_projection.current_screen, expected_screen)

    def test_should_read_the_screen_from_a_recorded_status_json(self):
        recorded_status_json = (
            '{ "timestamp":"2026-11-09T20:10:11Z", "event":"Status", '
            '"Flags":16842765, "Flags2":0, "Pips":[4,8,0], "FireGroup":0, '
            '"GuiFocus":6, "Fuel":{ "FuelMain":16.0, "FuelReservoir":0.63 } }'
        )
        player_projection = PlayerProjection()

        player_projection.process_event(
            StatusEvent.model_validate_json(recorded_status_json)
        )

        self.assertEqual(player_projection.current_screen, GameScreen.GALAXY_MAP)

    def test_should_report_unknown_screen_when_gui_focus_is_missing(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self._make_status_event(None))

        self.assertEqual(player_projection.current_screen, GameScreen.UNKNOWN)

    def test_should_report_unknown_screen_when_gui_focus_is_not_a_known_number(self):
        player_projection = PlayerProjection()

        player_projection.process_event(self._make_status_event(99))

        self.assertEqual(player_projection.current_screen, GameScreen.UNKNOWN)

    def test_should_go_back_to_unknown_when_a_later_status_has_no_gui_focus(self):
        player_projection = PlayerProjection()
        player_projection.process_event(self._make_status_event(6))

        player_projection.process_event(self._make_status_event(None))

        self.assertEqual(player_projection.current_screen, GameScreen.UNKNOWN)

    def test_should_log_the_screen_change_and_stay_quiet_when_it_is_the_same(self):
        player_projection = PlayerProjection()
        player_projection.process_event(self._make_status_event(0))

        with self.assertLogs(
            "edceleste.projection.event_projections.player_projection", level="INFO"
        ) as logs:
            player_projection.process_event(self._make_status_event(2))
            player_projection.process_event(self._make_status_event(2))

        self.assertEqual(len(logs.records), 1)
        self.assertIn("cockpit", logs.output[0])
        self.assertIn("left panel", logs.output[0])

    def test_should_set_the_screen_silently_when_status_comes_from_startup_loading(
        self,
    ):
        player_projection = PlayerProjection()
        startup_status_event = self._make_status_event(6)
        startup_status_event.is_startup_loading = True

        with self.assertNoLogs(
            "edceleste.projection.event_projections.player_projection", level="INFO"
        ):
            player_projection.process_event(startup_status_event)

        self.assertEqual(player_projection.current_screen, GameScreen.GALAXY_MAP)

    def test_should_not_tell_the_llm_which_screen_the_pilot_is_on(self):
        player_projection = PlayerProjection()
        player_projection.process_event(self.loaded_game_event)
        projection_before = player_projection.create_projection()

        player_projection.process_event(self._make_status_event(6))

        self.assertEqual(player_projection.create_projection(), projection_before)

    @staticmethod
    def _make_status_event(gui_focus) -> StatusEvent:
        return StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=0, GuiFocus=gui_focus
        )

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
