import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase


class TestGetTTSVoicesUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_return_voices_from_tts_protocol(self):
        voices = [{"ShortName": "en-GB-SoniaNeural"}]
        protocol = Mock()
        protocol.fetch_edge_tts_voice_names = AsyncMock(return_value=voices)
        use_case = GetTTSVoicesUseCase(protocol)  # type: ignore

        result = await use_case()

        self.assertEqual(result, voices)
        protocol.fetch_edge_tts_voice_names.assert_awaited_once()
