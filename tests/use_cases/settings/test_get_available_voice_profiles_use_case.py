import unittest
from unittest.mock import Mock

from edceleste.use_cases.settings.get_available_voice_profiles_use_case import (
    GetAvailableVoiceProfilesUseCase,
)


class TestGetAvailableVoiceProfilesUseCase(unittest.TestCase):
    def test_should_return_profiles_from_voice_cloning_protocol(self):
        profiles = ["celeste.pt", "aria.pt"]
        protocol = Mock()
        protocol.get_available_profiles.return_value = profiles
        use_case = GetAvailableVoiceProfilesUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, profiles)
        protocol.get_available_profiles.assert_called_once()

    def test_should_return_empty_list_when_no_profiles_available(self):
        protocol = Mock()
        protocol.get_available_profiles.return_value = []
        use_case = GetAvailableVoiceProfilesUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
