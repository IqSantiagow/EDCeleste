import unittest

from edceleste.services.models.keybinds_model import EdAction, Keybind
from edceleste.ui.screens.settings.widgets.keybinds.widget_keybinds_container import (
    keybind_as_text,
)


class TestKeybindAsText(unittest.TestCase):
    def test_should_show_only_the_key_when_there_is_no_modifier(self):
        keybind = Keybind(action=EdAction.TOGGLE_FLIGHT_ASSIST, key="Z")

        self.assertEqual(keybind_as_text(keybind), "Z")

    def test_should_join_modifiers_and_key_with_plus(self):
        keybind = Keybind(
            action=EdAction.NIGHT_VISION_TOGGLE,
            key="L",
            modifiers=["LeftControl", "LeftShift"],
        )

        self.assertEqual(keybind_as_text(keybind), "LeftControl+LeftShift+L")

    def test_should_say_no_keyboard_key_when_action_is_unbound(self):
        keybind = Keybind(action=EdAction.USE_SHIELD_CELL, key=None)

        self.assertEqual(keybind_as_text(keybind), "no keyboard key")


if __name__ == "__main__":
    unittest.main()
