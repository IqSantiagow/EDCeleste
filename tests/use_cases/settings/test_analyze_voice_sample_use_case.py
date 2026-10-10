import unittest
from unittest.mock import Mock

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.use_cases.settings.analyze_voice_sample_use_case import (
    AnalyzeVoiceSampleUseCase,
)


class TestAnalyzeVoiceSampleUseCase(unittest.TestCase):
    def test_should_return_analysis_from_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        analysis = Mock()
        protocol = Mock()
        protocol.perform_sample_voice_analysis_and_validate.return_value = analysis
        use_case = AnalyzeVoiceSampleUseCase(protocol)  # type: ignore

        result = use_case("C:/ref.wav", params)

        self.assertIs(result, analysis)
        protocol.perform_sample_voice_analysis_and_validate.assert_called_once_with(
            "C:/ref.wav", params
        )

    def test_should_propagate_error_raised_by_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.perform_sample_voice_analysis_and_validate.side_effect = RuntimeError(
            "cannot clone"
        )
        use_case = AnalyzeVoiceSampleUseCase(protocol)  # type: ignore

        with self.assertRaises(RuntimeError):
            use_case("C:/ref.wav", params)


if __name__ == "__main__":
    unittest.main()
