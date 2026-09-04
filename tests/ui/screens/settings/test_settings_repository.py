import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.services.models.keybinds_model import Keybind
from edceleste.services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.ui.screens.settings.settings_repository import SettingsRepository


async def _cloning_states():
    yield "completed"


def _make_settings() -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


class TestSettingsRepository(unittest.IsolatedAsyncioTestCase):
    def _make_repository(
        self,
        get_keybinds_use_case=None,
        load_keybinds_use_case=None,
        update_settings_use_case=None,
        get_settings_use_case=None,
        get_tts_voices_use_case=None,
        get_llm_models_use_case=None,
        get_stt_models_use_case=None,
        get_stt_input_devices_use_case=None,
        clone_voice_use_case=None,
        get_available_voice_profiles_use_case=None,
        remove_voice_profile_use_case=None,
        rename_voice_profile_use_case=None,
        play_sample_voice_use_case=None,
        play_audio_file_use_case=None,
        analyze_voice_sample_use_case=None,
        preview_voice_sample_use_case=None,
        get_available_device_use_case=None,
    ):
        return SettingsRepository(
            settings_load_keybinds_use_case=load_keybinds_use_case or Mock(),
            settings_get_keybinds_use_case=get_keybinds_use_case or Mock(),
            update_settings_use_case=update_settings_use_case or Mock(),
            get_settings_use_case=get_settings_use_case or Mock(),
            get_tts_voices_use_case=get_tts_voices_use_case or Mock(),
            get_llm_models_use_case=get_llm_models_use_case or Mock(),
            get_stt_models_use_case=get_stt_models_use_case or Mock(),
            get_stt_input_devices_use_case=get_stt_input_devices_use_case or Mock(),
            clone_voice_use_case=clone_voice_use_case or Mock(),
            get_available_voice_profiles_use_case=get_available_voice_profiles_use_case
            or Mock(),
            remove_voice_profile_use_case=remove_voice_profile_use_case or Mock(),
            rename_voice_profile_use_case=rename_voice_profile_use_case or Mock(),
            play_sample_voice_use_case=play_sample_voice_use_case or AsyncMock(),
            play_audio_file_use_case=play_audio_file_use_case or AsyncMock(),
            analyze_voice_sample_use_case=analyze_voice_sample_use_case or Mock(),
            preview_voice_sample_use_case=preview_voice_sample_use_case or AsyncMock(),
            get_available_device_use_case=get_available_device_use_case or Mock(),
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

    def test_should_delegate_update_settings_to_use_case(self):
        update_settings_use_case = Mock()
        repository = self._make_repository(
            update_settings_use_case=update_settings_use_case
        )
        new_settings = _make_settings()

        repository.update_settings(new_settings)

        update_settings_use_case.assert_called_once_with(new_settings)

    def test_should_delegate_get_settings_to_use_case(self):
        settings = _make_settings()
        get_settings_use_case = Mock(return_value=settings)
        repository = self._make_repository(get_settings_use_case=get_settings_use_case)

        result = repository.get_settings()

        self.assertEqual(result, settings)
        get_settings_use_case.assert_called_once()

    async def test_should_delegate_get_voices_to_use_case(self):
        voices = ["en-US-AriaNeural", "en-GB-SoniaNeural"]
        get_tts_voices_use_case = AsyncMock(return_value=voices)
        repository = self._make_repository(
            get_tts_voices_use_case=get_tts_voices_use_case
        )

        result = await repository.get_voices()

        self.assertEqual(result, voices)
        get_tts_voices_use_case.assert_awaited_once()

    def test_should_delegate_get_llm_models_to_use_case(self):
        models = ["claude-haiku-4-5-20251001", "claude-sonnet-5"]
        get_llm_models_use_case = Mock(return_value=models)
        repository = self._make_repository(
            get_llm_models_use_case=get_llm_models_use_case
        )

        result = repository.get_llm_models("claude_agent_sdk")

        self.assertEqual(result, models)
        get_llm_models_use_case.assert_called_once_with("claude_agent_sdk")

    def test_should_delegate_get_stt_models_to_use_case(self):
        models = ["tiny.en", "base.en"]
        get_stt_models_use_case = Mock(return_value=models)
        repository = self._make_repository(
            get_stt_models_use_case=get_stt_models_use_case
        )

        result = repository.get_stt_models()

        self.assertEqual(result, models)
        get_stt_models_use_case.assert_called_once()

    async def test_should_delegate_clone_voice_to_use_case(self):
        clone_voice_use_case = Mock(return_value=_cloning_states())
        repository = self._make_repository(
            clone_voice_use_case=clone_voice_use_case,
        )

        result = [
            state
            async for state in repository.clone_voice("C:/audio/celeste.wav", "celeste")
        ]

        self.assertEqual(result, ["completed"])
        clone_voice_use_case.assert_called_once_with("C:/audio/celeste.wav", "celeste")

    def test_should_delegate_get_available_voice_profiles_to_use_case(self):
        profiles = ["celeste.pt"]
        get_available_voice_profiles_use_case = Mock(return_value=profiles)
        repository = self._make_repository(
            get_available_voice_profiles_use_case=get_available_voice_profiles_use_case
        )

        result = repository.get_available_voice_profiles()

        self.assertEqual(result, profiles)
        get_available_voice_profiles_use_case.assert_called_once()

    def test_should_delegate_get_available_device_to_use_case(self):
        get_available_device_use_case = Mock(return_value="cuda")
        repository = self._make_repository(
            get_available_device_use_case=get_available_device_use_case
        )

        result = repository.get_available_device()

        self.assertEqual(result, "cuda")
        get_available_device_use_case.assert_called_once()

    def test_should_delegate_remove_voice_profile_to_use_case(self):
        remove_voice_profile_use_case = Mock()
        repository = self._make_repository(
            remove_voice_profile_use_case=remove_voice_profile_use_case
        )

        repository.remove_voice_profile("celeste")

        remove_voice_profile_use_case.assert_called_once_with("celeste")

    async def test_should_delegate_play_sample_voice_to_use_case(self):
        play_sample_voice_use_case = AsyncMock()
        repository = self._make_repository(
            play_sample_voice_use_case=play_sample_voice_use_case
        )

        await repository.play_sample_voice("celeste")

        play_sample_voice_use_case.assert_awaited_once_with("celeste")

    async def test_should_delegate_play_audio_file_to_use_case(self):
        play_audio_file_use_case = AsyncMock()
        repository = self._make_repository(
            play_audio_file_use_case=play_audio_file_use_case
        )

        await repository.play_audio_file("C:/ref.wav")

        play_audio_file_use_case.assert_awaited_once_with("C:/ref.wav")

    def test_should_delegate_analyze_voice_sample_to_use_case(self):
        analysis = {"is_valid": True}
        analyze_voice_sample_use_case = Mock(return_value=analysis)
        repository = self._make_repository(
            analyze_voice_sample_use_case=analyze_voice_sample_use_case
        )

        result = repository.analyze_voice_sample("C:/ref.wav")

        self.assertEqual(result, analysis)
        analyze_voice_sample_use_case.assert_called_once_with("C:/ref.wav")

    def test_should_delegate_rename_voice_profile_to_use_case(self):
        rename_voice_profile_use_case = Mock()
        repository = self._make_repository(
            rename_voice_profile_use_case=rename_voice_profile_use_case
        )

        repository.rename_voice_profile("celeste", "celeste-v2")

        rename_voice_profile_use_case.assert_called_once_with("celeste", "celeste-v2")

    async def test_should_delegate_preview_voice_sample_to_use_case(self):
        preview_voice_sample_use_case = AsyncMock()
        repository = self._make_repository(
            preview_voice_sample_use_case=preview_voice_sample_use_case
        )

        await repository.preview_voice_sample("celeste", "Hello there.")

        preview_voice_sample_use_case.assert_awaited_once_with(
            "celeste", "Hello there."
        )


if __name__ == "__main__":
    unittest.main()
