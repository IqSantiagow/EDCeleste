import unittest
from unittest.mock import AsyncMock, Mock

from services.models.keybinds_model import Keybind
from ui.screens.settings.settings_repository import SettingsRepository


class TestSettingsRepository(unittest.IsolatedAsyncioTestCase):
    def _make_repository(self, get_keybinds_use_case=None, load_keybinds_use_case=None):
        return SettingsRepository(
            settings_load_keybinds_use_case=load_keybinds_use_case or AsyncMock(),
            settings_get_keybinds_use_case=get_keybinds_use_case or Mock(),
        )

    def test_should_delegate_get_keybinds_to_use_case(self):
        keybinds = [Keybind(key="Z", action="ToggleFlightAssist")]
        get_keybinds_use_case = Mock(return_value=keybinds)
        repository = self._make_repository(get_keybinds_use_case=get_keybinds_use_case)

        result = repository.get_keybinds()

        self.assertEqual(result, keybinds)
        get_keybinds_use_case.assert_called_once()

    async def test_should_delegate_load_keybinds_to_use_case(self):
        load_keybinds_use_case = AsyncMock()
        repository = self._make_repository(
            load_keybinds_use_case=load_keybinds_use_case
        )

        await repository.load_keybinds()

        load_keybinds_use_case.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
