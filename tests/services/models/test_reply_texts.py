import unittest

from edceleste.services.models.game_events import StatusFlags
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_texts import (
    ACTIONS_SAID_BY_GAME_STATE,
    GAME_ACTIONS_DISABLED_TEXT,
    JOURNAL_EVENT_REPLY_TEXTS,
    REPLY_TEXT_OF_ONE_SHOT_ACTION,
    REPLY_TEXTS,
    SHIP_FLAG_REPLY_TEXTS,
    build_reply_wav_file_name,
    pick_reply_text_for_pressed_action,
    pick_reply_texts_for_changed_flags,
)
from tests.use_cases.dashboard.game_stats_fixtures import make_ship_stats


class TestReplyWavFileName(unittest.TestCase):
    def test_lowercases_and_joins_the_words_with_underscores(self):
        self.assertEqual(
            build_reply_wav_file_name("Landing gear deployed"),
            "landing_gear_deployed.wav",
        )

    def test_drops_punctuation_and_edge_underscores(self):
        self.assertEqual(
            build_reply_wav_file_name("  Hello, Commander! "), "hello_commander.wav"
        )


# The six toggles: the key press of Instinct, the flag of Status.json and the
# field of the ship before the press
TOGGLES = [
    (
        EdAction.TOGGLE_FLIGHT_ASSIST,
        StatusFlags.FlightAssistOff,
        "is_flight_assist_off",
    ),
    (
        EdAction.DEPLOY_HARDPOINT_TOGGLE,
        StatusFlags.HardpointsDeployed,
        "are_hardpoints_deployed",
    ),
    (EdAction.LANDING_GEAR_TOGGLE, StatusFlags.LandingGearDown, "is_landing_gear_down"),
    (
        EdAction.TOGGLE_CARGO_SCOOP,
        StatusFlags.CargoScoopDeployed,
        "is_cargo_scoop_deployed",
    ),
    (EdAction.SHIP_SPOT_LIGHT_TOGGLE, StatusFlags.LightsOn, "are_lights_on"),
    (EdAction.NIGHT_VISION_TOGGLE, StatusFlags.NightVision, "is_night_vision_on"),
]


class TestReplyTextsForChangedFlags(unittest.TestCase):
    def test_says_deployed_when_the_landing_gear_bit_is_set(self):
        self.assertEqual(
            pick_reply_texts_for_changed_flags(0, StatusFlags.LandingGearDown),
            ["Landing gear deployed"],
        )

    def test_says_retracted_when_the_landing_gear_bit_is_cleared(self):
        self.assertEqual(
            pick_reply_texts_for_changed_flags(StatusFlags.LandingGearDown, 0),
            ["Landing gear retracted"],
        )

    def test_says_flight_assist_off_when_the_flight_assist_off_bit_is_set(self):
        self.assertEqual(
            pick_reply_texts_for_changed_flags(0, StatusFlags.FlightAssistOff),
            ["Flight assist off"],
        )

    def test_says_the_texts_of_the_shields_and_the_fuel_scoop_both_ways(self):
        for flag, set_text, cleared_text in [
            (StatusFlags.ShieldsUp, "Shields online", "Shields offline"),
            (StatusFlags.ScoopingFuel, "Fuel scooping", "Fuel scoop disengaged"),
            (StatusFlags.SrvDriveAssist, "Drive assist on", "Drive assist off"),
        ]:
            with self.subTest(flag=flag.name):
                self.assertEqual(
                    pick_reply_texts_for_changed_flags(0, flag), [set_text]
                )
                self.assertEqual(
                    pick_reply_texts_for_changed_flags(flag, 0), [cleared_text]
                )

    def test_says_a_warning_only_when_its_bit_is_set(self):
        for flag, text in [
            (StatusFlags.LowFuel, "Main fuel tank low"),
            (StatusFlags.FsdCharging, "Frame shift drive charging"),
            (StatusFlags.SrvHandbrake, "Handbrake is on"),
        ]:
            with self.subTest(flag=flag.name):
                self.assertEqual(pick_reply_texts_for_changed_flags(0, flag), [text])
                self.assertEqual(pick_reply_texts_for_changed_flags(flag, 0), [])

    def test_says_nothing_when_the_flags_are_the_same(self):
        flags = StatusFlags.LandingGearDown | StatusFlags.LightsOn

        self.assertEqual(pick_reply_texts_for_changed_flags(flags, flags), [])

    def test_ignores_bits_that_are_not_ship_switches(self):
        self.assertEqual(
            pick_reply_texts_for_changed_flags(0, StatusFlags.Supercruise), []
        )

    def test_says_every_changed_switch_in_the_order_of_the_table(self):
        self.assertEqual(
            pick_reply_texts_for_changed_flags(
                StatusFlags.LightsOn,
                StatusFlags.HardpointsDeployed | StatusFlags.LandingGearDown,
            ),
            ["Landing gear deployed", "Hardpoints deployed", "Lights off"],
        )

    def test_every_text_of_the_game_state_has_a_clip_in_reply_texts(self):
        for _, set_text, cleared_text in SHIP_FLAG_REPLY_TEXTS:
            for text in (set_text, cleared_text):
                if text is not None:
                    self.assertIn(text, REPLY_TEXTS)
        for text in JOURNAL_EVENT_REPLY_TEXTS.values():
            self.assertIn(text, REPLY_TEXTS)

    def test_a_toggle_says_the_same_after_a_key_press_and_after_the_flag_changes(self):
        for action, flag, ship_field in TOGGLES:
            with self.subTest(action=action.value):
                switched_off = make_ship_stats(**{ship_field: False})
                switched_on = make_ship_stats(**{ship_field: True})

                self.assertEqual(
                    [pick_reply_text_for_pressed_action(action, switched_off)],
                    pick_reply_texts_for_changed_flags(0, flag),
                )
                self.assertEqual(
                    [pick_reply_text_for_pressed_action(action, switched_on)],
                    pick_reply_texts_for_changed_flags(flag, 0),
                )

    def test_every_action_said_by_the_game_state_has_a_reply_text(self):
        for action in ACTIONS_SAID_BY_GAME_STATE:
            with self.subTest(action=action.value):
                text = pick_reply_text_for_pressed_action(action, make_ship_stats())

                self.assertIn(text, REPLY_TEXTS)

    def test_the_toggles_are_said_by_the_game_state(self):
        self.assertTrue(
            {action for action, _, _ in TOGGLES} <= ACTIONS_SAID_BY_GAME_STATE
        )


class TestReplyTexts(unittest.TestCase):
    def test_every_reply_text_has_its_own_file_name(self):
        file_names = [build_reply_wav_file_name(text) for text in REPLY_TEXTS]

        self.assertEqual(len(set(file_names)), len(REPLY_TEXTS))

    def test_the_game_actions_disabled_text_is_in_the_set(self):
        self.assertIn(GAME_ACTIONS_DISABLED_TEXT, REPLY_TEXTS)


class TestPickReplyTextForPressedAction(unittest.TestCase):
    def test_every_action_gets_a_text_of_the_set_whatever_the_ship_is_doing(self):
        for action in EdAction:
            for is_on in (True, False):
                ship = make_ship_stats(
                    is_landing_gear_down=is_on,
                    are_hardpoints_deployed=is_on,
                    are_lights_on=is_on,
                    is_cargo_scoop_deployed=is_on,
                    is_flight_assist_off=is_on,
                    is_night_vision_on=is_on,
                )
                with self.subTest(action=action, is_on=is_on):
                    self.assertIn(
                        pick_reply_text_for_pressed_action(action, ship), REPLY_TEXTS
                    )

    def test_a_toggle_is_named_after_the_opposite_of_the_state_before_the_press(self):
        cases = [
            (EdAction.LANDING_GEAR_TOGGLE, "is_landing_gear_down", "Landing gear"),
            (EdAction.DEPLOY_HARDPOINT_TOGGLE, "are_hardpoints_deployed", "Hardpoints"),
            (EdAction.TOGGLE_CARGO_SCOOP, "is_cargo_scoop_deployed", "Cargo scoop"),
        ]
        for action, ship_field, name in cases:
            with self.subTest(action=action):
                before_is_down = make_ship_stats(**{ship_field: True})
                before_is_up = make_ship_stats(**{ship_field: False})

                self.assertEqual(
                    pick_reply_text_for_pressed_action(action, before_is_down),
                    f"{name} retracted",
                )
                self.assertEqual(
                    pick_reply_text_for_pressed_action(action, before_is_up),
                    f"{name} deployed",
                )

    def test_lights_and_night_vision_say_on_or_off(self):
        cases = [
            (EdAction.SHIP_SPOT_LIGHT_TOGGLE, "are_lights_on", "Lights"),
            (EdAction.NIGHT_VISION_TOGGLE, "is_night_vision_on", "Night vision"),
        ]
        for action, ship_field, name in cases:
            with self.subTest(action=action):
                self.assertEqual(
                    pick_reply_text_for_pressed_action(
                        action, make_ship_stats(**{ship_field: True})
                    ),
                    f"{name} off",
                )
                self.assertEqual(
                    pick_reply_text_for_pressed_action(
                        action, make_ship_stats(**{ship_field: False})
                    ),
                    f"{name} on",
                )

    def test_flight_assist_is_read_from_the_flag_that_says_it_is_off(self):
        flight_assist_was_off = make_ship_stats(is_flight_assist_off=True)
        flight_assist_was_on = make_ship_stats(is_flight_assist_off=False)

        self.assertEqual(
            pick_reply_text_for_pressed_action(
                EdAction.TOGGLE_FLIGHT_ASSIST, flight_assist_was_off
            ),
            "Flight assist on",
        )
        self.assertEqual(
            pick_reply_text_for_pressed_action(
                EdAction.TOGGLE_FLIGHT_ASSIST, flight_assist_was_on
            ),
            "Flight assist off",
        )

    def test_an_action_without_a_direction_has_one_text_whatever_the_ship_does(self):
        ship = make_ship_stats(is_landing_gear_down=True, are_lights_on=True)

        self.assertEqual(
            pick_reply_text_for_pressed_action(EdAction.SET_SPEED_50, ship),
            "Throttle fifty percent",
        )

    def test_the_one_shot_table_has_no_toggle_and_no_text_outside_the_set(self):
        toggles = {
            EdAction.TOGGLE_FLIGHT_ASSIST,
            EdAction.DEPLOY_HARDPOINT_TOGGLE,
            EdAction.LANDING_GEAR_TOGGLE,
            EdAction.TOGGLE_CARGO_SCOOP,
            EdAction.SHIP_SPOT_LIGHT_TOGGLE,
            EdAction.NIGHT_VISION_TOGGLE,
        }

        self.assertEqual(set(REPLY_TEXT_OF_ONE_SHOT_ACTION), set(EdAction) - toggles)
        self.assertTrue(set(REPLY_TEXT_OF_ONE_SHOT_ACTION.values()) <= set(REPLY_TEXTS))


if __name__ == "__main__":
    unittest.main()
