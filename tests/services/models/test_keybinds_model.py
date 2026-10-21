import unittest

from edceleste.services.models.keybinds_model import (
    EdAction,
    Keybind,
    action_in_plain_words,
    find_keybind_using_key,
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


class TestFindKeybindUsingKey(unittest.TestCase):
    def test_finds_keybind_that_uses_the_key(self):
        keybind = Keybind(action=EdAction.DEPLOY_HARDPOINT_TOGGLE, key="F9")

        self.assertIs(find_keybind_using_key("Key.f9", [keybind]), keybind)

    def test_finds_keybind_for_normal_character_key(self):
        keybind = Keybind(action=EdAction.SUPERCRUISE, key="K")

        self.assertIs(find_keybind_using_key("'k'", [keybind]), keybind)

    def test_finds_keybind_that_uses_the_key_as_modifier(self):
        keybind = Keybind(action=EdAction.SUPERCRUISE, key="K", modifiers=["LeftShift"])

        self.assertIs(find_keybind_using_key("Key.shift", [keybind]), keybind)

    def test_modifier_names_are_translated_to_game_names(self):
        names = [
            ("Key.shift", "LeftShift"),
            ("Key.shift_l", "LeftShift"),
            ("Key.shift_r", "RightShift"),
            ("Key.ctrl", "LeftControl"),
            ("Key.ctrl_l", "LeftControl"),
            ("Key.ctrl_r", "RightControl"),
            ("Key.alt", "LeftAlt"),
            ("Key.alt_l", "LeftAlt"),
            ("Key.alt_r", "RightAlt"),
            ("Key.alt_gr", "RightAlt"),
        ]
        for pynput_name, game_name in names:
            with self.subTest(pynput_name=pynput_name):
                keybind = Keybind(action=EdAction.SUPERCRUISE, key=game_name)

                self.assertIs(find_keybind_using_key(pynput_name, [keybind]), keybind)

    def test_left_and_right_modifier_are_different_keys(self):
        keybind = Keybind(action=EdAction.SUPERCRUISE, key="LeftShift")

        self.assertIsNone(find_keybind_using_key("Key.shift_r", [keybind]))

    def test_underscores_in_pynput_names_are_ignored(self):
        keybind = Keybind(action=EdAction.SUPERCRUISE, key="PageUp")

        self.assertIs(find_keybind_using_key("Key.page_up", [keybind]), keybind)

    def test_arrow_and_escape_names_are_translated(self):
        names = [
            ("Key.up", "UpArrow"),
            ("Key.down", "DownArrow"),
            ("Key.left", "LeftArrow"),
            ("Key.right", "RightArrow"),
            ("Key.esc", "Escape"),
        ]
        for pynput_name, game_name in names:
            with self.subTest(pynput_name=pynput_name):
                keybind = Keybind(action=EdAction.SUPERCRUISE, key=game_name)

                self.assertIs(find_keybind_using_key(pynput_name, [keybind]), keybind)

    def test_returns_none_when_key_is_free(self):
        keybinds = [
            Keybind(action=EdAction.DEPLOY_HARDPOINT_TOGGLE, key="F9"),
            Keybind(action=EdAction.SUPERCRUISE, key="K", modifiers=["LeftShift"]),
        ]

        self.assertIsNone(find_keybind_using_key("Key.f10", keybinds))

    def test_mouse_button_is_never_found(self):
        keybind = Keybind(action=EdAction.SUPERCRUISE, key="X1")

        self.assertIsNone(find_keybind_using_key("Button.x1", [keybind]))

    def test_keybinds_without_keyboard_key_are_skipped(self):
        keybind = Keybind(action=EdAction.HYPERSPACE, key=None)

        self.assertIsNone(find_keybind_using_key("Key.f9", [keybind]))

    def test_returns_first_keybind_when_several_use_the_key(self):
        first = Keybind(action=EdAction.DEPLOY_HARDPOINT_TOGGLE, key="F9")
        second = Keybind(action=EdAction.SUPERCRUISE, key="F9")

        self.assertIs(find_keybind_using_key("Key.f9", [first, second]), first)


if __name__ == "__main__":
    unittest.main()
