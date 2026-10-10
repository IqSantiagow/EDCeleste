import unittest
from unittest.mock import Mock

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.use_cases.settings.remove_voice_profile_use_case import (
    RemoveVoiceProfileUseCase,
)


class TestRemoveVoiceProfileUseCase(unittest.TestCase):
    def test_should_delegate_profile_removal_to_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        use_case = RemoveVoiceProfileUseCase(protocol)  # type: ignore

        use_case("celeste", params)

        protocol.remove_profile.assert_called_once_with("celeste", params)


if __name__ == "__main__":
    unittest.main()
