import unittest

from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_texts import (
    GAME_ACTIONS_DISABLED_TEXT,
    REPLY_TEXT_OF_ONE_SHOT_ACTION,
    REPLY_TEXTS,
    build_reply_wav_file_name,
    pick_reply_text_for_pressed_action,
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
