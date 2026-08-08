import unittest
from unittest.mock import AsyncMock, Mock

from use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase


class TestGetTTSVoicesUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_return_voices_from_tts_protocol(self):
        voices = [{"ShortName": "en-GB-SoniaNeural"}]
        protocol = Mock()
        protocol.get_tts_voices = AsyncMock(return_value=voices)
        use_case = GetTTSVoicesUseCase(protocol)  # type: ignore

        result = await use_case()

        self.assertEqual(result, voices)
        protocol.get_tts_voices.assert_awaited_once()
