import unittest
from unittest.mock import AsyncMock, Mock

from services.models.keybinds_model import Keybind
from services.models.settings_model import LLMModel, PathModel, SettingsModel, TTSModel
from ui.screens.settings.settings_repository import SettingsRepository


def _make_settings() -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
    )


class TestSettingsRepository(unittest.IsolatedAsyncioTestCase):
    def _make_repository(
        self,
        get_keybinds_use_case=None,
        load_keybinds_use_case=None,
        update_settings_use_case=None,
        get_settings_use_case=None,
    ):
        return SettingsRepository(
            settings_load_keybinds_use_case=load_keybinds_use_case or Mock(),
            settings_get_keybinds_use_case=get_keybinds_use_case or Mock(),
            update_settings_use_case=update_settings_use_case or AsyncMock(),
            get_settings_use_case=get_settings_use_case or Mock(),
        )

    def test_should_delegate_get_keybinds_to_use_case(self):
        keybinds = [Keybind(key="Z", action="ToggleFlightAssist")]
        get_keybinds_use_case = Mock(return_value=keybinds)
        repository = self._make_repository(get_keybinds_use_case=get_keybinds_use_case)

        result = repository.get_keybinds()

        self.assertEqual(result, keybinds)
        get_keybinds_use_case.assert_called_once()

    def test_should_delegate_load_keybinds_to_use_case(self):
        load_keybinds_use_case = Mock()
        repository = self._make_repository(
            load_keybinds_use_case=load_keybinds_use_case
        )

        repository.load_keybinds()

        load_keybinds_use_case.assert_called_once()

    async def test_should_delegate_update_settings_to_use_case(self):
        update_settings_use_case = AsyncMock()
        repository = self._make_repository(
            update_settings_use_case=update_settings_use_case
        )
        new_settings = _make_settings()

        await repository.update_settings(new_settings)

        update_settings_use_case.assert_awaited_once_with(new_settings)

    def test_should_delegate_get_settings_to_use_case(self):
        settings = _make_settings()
        get_settings_use_case = Mock(return_value=settings)
        repository = self._make_repository(get_settings_use_case=get_settings_use_case)

        result = repository.get_settings()

        self.assertEqual(result, settings)
        get_settings_use_case.assert_called_once()


if __name__ == "__main__":
    unittest.main()
