import unittest
from unittest.mock import AsyncMock

from use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)


class TestSettingsLoadKeybindsUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_call_load_keybinds_on_protocol(self):
        protocol = AsyncMock()
        use_case = SettingsLoadKeybindsUseCase(protocol)  # type: ignore

        await use_case()

        protocol.load_keybinds.assert_awaited_once()

    async def test_should_propagate_exception_from_protocol(self):
        protocol = AsyncMock()
        protocol.load_keybinds.side_effect = FileNotFoundError("boom")
        use_case = SettingsLoadKeybindsUseCase(protocol)  # type: ignore

        with self.assertRaises(FileNotFoundError):
            await use_case()


if __name__ == "__main__":
    unittest.main()
