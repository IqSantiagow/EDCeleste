import unittest
from unittest.mock import Mock

from edceleste.use_cases.settings.clone_voice_use_case import CloneVoiceUseCase


async def _cloning_states():
    yield "completed"


class TestCloneVoiceUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_delegate_clone_voice_to_voice_cloning_protocol(self):
        protocol = Mock()
        protocol.clone_voice.return_value = _cloning_states()
        use_case = CloneVoiceUseCase(protocol)  # type: ignore

        result = [state async for state in use_case("C:/audio/celeste.wav", "celeste")]

        self.assertEqual(result, ["completed"])
        protocol.clone_voice.assert_called_once_with("C:/audio/celeste.wav", "celeste")

    async def test_should_propagate_error_raised_by_voice_cloning_protocol(self):
        protocol = Mock()

        async def raise_cloning_error(*args, **kwargs):
            raise RuntimeError("cloning failed")
            yield

        protocol.clone_voice.return_value = raise_cloning_error()
        use_case = CloneVoiceUseCase(protocol)  # type: ignore

        with self.assertRaises(RuntimeError):
            [state async for state in use_case("C:/audio/celeste.wav", "celeste")]


if __name__ == "__main__":
    unittest.main()
