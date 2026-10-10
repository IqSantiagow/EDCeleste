import unittest
from unittest.mock import Mock

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.use_cases.settings.get_available_voice_profiles_use_case import (
    GetAvailableVoiceProfilesUseCase,
)


class TestGetAvailableVoiceProfilesUseCase(unittest.TestCase):
    def test_should_return_profiles_from_voice_cloning_protocol(self):
        profiles = ["celeste.pt", "aria.pt"]
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.get_available_profiles.return_value = profiles
        use_case = GetAvailableVoiceProfilesUseCase(protocol)  # type: ignore

        result = use_case(params)

        self.assertEqual(result, profiles)
        protocol.get_available_profiles.assert_called_once_with(params)

    def test_should_return_empty_list_when_no_profiles_available(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.get_available_profiles.return_value = []
        use_case = GetAvailableVoiceProfilesUseCase(protocol)  # type: ignore

        result = use_case(params)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
