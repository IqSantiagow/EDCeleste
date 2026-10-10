import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.use_cases.settings.preview_voice_sample_use_case import (
    PreviewVoiceSampleUseCase,
)


class TestPreviewVoiceSampleUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_delegate_preview_to_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.preview_voice_sample = AsyncMock()
        use_case = PreviewVoiceSampleUseCase(protocol)  # type: ignore

        await use_case("celeste", "Hello there.", params)

        protocol.preview_voice_sample.assert_awaited_once_with(
            "celeste", "Hello there.", params
        )

    async def test_should_propagate_error_raised_by_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.preview_voice_sample = AsyncMock(side_effect=RuntimeError("no model"))
        use_case = PreviewVoiceSampleUseCase(protocol)  # type: ignore

        with self.assertRaises(RuntimeError):
            await use_case("celeste", "Hello there.", params)


if __name__ == "__main__":
    unittest.main()
