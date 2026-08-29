import unittest
from unittest.mock import Mock

from edceleste.use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)


class TestSettingsLoadKeybindsUseCase(unittest.TestCase):
    def test_should_call_load_keybinds_on_protocol(self):
        protocol = Mock()
        use_case = SettingsLoadKeybindsUseCase(protocol)  # type: ignore

        use_case()

        protocol.load_keybinds.assert_called_once()

    def test_should_propagate_exception_from_protocol(self):
        protocol = Mock()
        protocol.load_keybinds.side_effect = FileNotFoundError("boom")
        use_case = SettingsLoadKeybindsUseCase(protocol)  # type: ignore

        with self.assertRaises(FileNotFoundError):
            use_case()


if __name__ == "__main__":
    unittest.main()
