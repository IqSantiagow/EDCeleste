import unittest

from edceleste.services.models.keybinds_model import (
    EdAction,
    Keybind,
    action_in_plain_words,
)


class TestKeybind(unittest.TestCase):
    def test_should_have_no_key_and_no_modifiers_by_default(self):
        keybind = Keybind(action=EdAction.USE_SHIELD_CELL)

        self.assertIsNone(keybind.key)
        self.assertEqual(keybind.modifiers, [])


class TestActionInPlainWords(unittest.TestCase):
    def test_should_split_words_and_lowercase_all_but_the_first(self):
        self.assertEqual(
            action_in_plain_words(EdAction.USE_SHIELD_CELL), "Use shield cell"
        )

    def test_should_keep_capital_letter_shortcuts(self):
        self.assertEqual(action_in_plain_words(EdAction.UI_FOCUS), "UI focus")
        self.assertEqual(
            action_in_plain_words(EdAction.EXPLORATION_FSS_ENTER),
            "Exploration FSS enter",
        )

    def test_should_keep_numbers_as_own_word(self):
        self.assertEqual(action_in_plain_words(EdAction.SET_SPEED_50), "Set speed 50")

    def test_should_keep_one_word_action_as_is(self):
        self.assertEqual(action_in_plain_words(EdAction.SUPERCRUISE), "Supercruise")


if __name__ == "__main__":
    unittest.main()
