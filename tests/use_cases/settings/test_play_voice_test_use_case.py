import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.services.models.settings_model import TTSModel
from edceleste.use_cases.settings.play_voice_test_use_case import (
    PlayVoiceTestUseCase,
)


class TestPlayVoiceTestUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_delegate_play_to_voice_test_protocol(self):
        tts_settings = TTSModel(volume=0.4)
        protocol = Mock()
        protocol.play_voice_test_sentence = AsyncMock()
        use_case = PlayVoiceTestUseCase(protocol)  # type: ignore

        await use_case(tts_settings)

        protocol.play_voice_test_sentence.assert_awaited_once_with(tts_settings)

    async def test_should_propagate_error_raised_by_voice_test_protocol(self):
        protocol = Mock()
        protocol.play_voice_test_sentence = AsyncMock(
            side_effect=RuntimeError("no network")
        )
        use_case = PlayVoiceTestUseCase(protocol)  # type: ignore

        with self.assertRaises(RuntimeError):
            await use_case(TTSModel(volume=0.4))


if __name__ == "__main__":
    unittest.main()
