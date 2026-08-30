import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.use_cases.settings.clone_voice_use_case import CloneVoiceUseCase


class TestCloneVoiceUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_delegate_clone_voice_to_voice_cloning_protocol(self):
        protocol = Mock()
        protocol.clone_voice = AsyncMock()
        use_case = CloneVoiceUseCase(protocol)  # type: ignore

        await use_case("C:/audio/celeste.wav", "celeste")

        protocol.clone_voice.assert_awaited_once_with("C:/audio/celeste.wav", "celeste")

    async def test_should_propagate_error_raised_by_voice_cloning_protocol(self):
        protocol = Mock()
        protocol.clone_voice = AsyncMock(side_effect=RuntimeError("cloning failed"))
        use_case = CloneVoiceUseCase(protocol)  # type: ignore

        with self.assertRaises(RuntimeError):
            await use_case("C:/audio/celeste.wav", "celeste")


if __name__ == "__main__":
    unittest.main()
