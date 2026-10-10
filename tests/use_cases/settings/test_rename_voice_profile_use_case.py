import unittest
from unittest.mock import Mock

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.use_cases.settings.rename_voice_profile_use_case import (
    RenameVoiceProfileUseCase,
)


class TestRenameVoiceProfileUseCase(unittest.TestCase):
    def test_should_delegate_profile_rename_to_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        use_case = RenameVoiceProfileUseCase(protocol)  # type: ignore

        use_case("celeste", "celeste-v2", params)

        protocol.rename_profile.assert_called_once_with("celeste", "celeste-v2", params)

    def test_should_propagate_error_raised_by_voice_cloning_protocol(self):
        params = ChatterboxParamsModel(type="chatterbox", profile="celeste")
        protocol = Mock()
        protocol.rename_profile.side_effect = FileExistsError("name taken")
        use_case = RenameVoiceProfileUseCase(protocol)  # type: ignore

        with self.assertRaises(FileExistsError):
            use_case("celeste", "celeste-v2", params)


if __name__ == "__main__":
    unittest.main()
