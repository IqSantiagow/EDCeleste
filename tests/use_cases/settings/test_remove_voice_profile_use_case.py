import unittest
from unittest.mock import Mock

from edceleste.use_cases.settings.remove_voice_profile_use_case import (
    RemoveVoiceProfileUseCase,
)


class TestRemoveVoiceProfileUseCase(unittest.TestCase):
    def test_should_delegate_profile_removal_to_voice_cloning_protocol(self):
        protocol = Mock()
        use_case = RemoveVoiceProfileUseCase(protocol)  # type: ignore

        use_case("celeste")

        protocol.remove_profile.assert_called_once_with("celeste")


if __name__ == "__main__":
    unittest.main()
