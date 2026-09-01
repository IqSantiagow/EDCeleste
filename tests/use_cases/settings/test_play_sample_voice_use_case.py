import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.use_cases.settings.play_sample_voice_use_case import (
    PlaySampleVoiceUseCase,
)


class TestPlaySampleVoiceUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_delegate_sample_playback_to_voice_cloning_protocol(self):
        protocol = Mock()
        protocol.play_sample_voice = AsyncMock()
        use_case = PlaySampleVoiceUseCase(protocol)  # type: ignore

        await use_case("celeste")

        protocol.play_sample_voice.assert_awaited_once_with("celeste")


if __name__ == "__main__":
    unittest.main()
