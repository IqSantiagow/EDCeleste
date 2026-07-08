import unittest
from unittest.mock import Mock

from services.models.keybinds_model import Keybind
from use_cases.settings.settings_get_keybinds_use_case import SettingsGetKeybindsUseCase


class TestSettingsGetKeybindsUseCase(unittest.TestCase):
    def test_should_return_keybinds_from_protocol(self):
        keybinds = [Keybind(key="Z", action="ToggleFlightAssist")]
        protocol = Mock()
        protocol.get_keybinds.return_value = keybinds
        use_case = SettingsGetKeybindsUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, keybinds)

    def test_should_return_empty_list_when_no_keybinds_loaded(self):
        protocol = Mock()
        protocol.get_keybinds.return_value = []
        use_case = SettingsGetKeybindsUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
