import unittest

from edceleste.use_cases.dashboard.get_stt_enabled_use_case import GetSttEnabledUseCase


class FakeSttProtocol:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def handle_stt_request(self, audio_path: str) -> str | None:
        raise NotImplementedError

    def validate_settings(self, new_settings):
        raise NotImplementedError

    def reload_service(self) -> None:
        raise NotImplementedError

    def is_stt_enabled(self) -> bool:
        return self._enabled

    def get_stt_models(self) -> list[str]:
        raise NotImplementedError


class TestGetSttEnabledUseCase(unittest.TestCase):
    def test_should_return_true_when_stt_enabled(self):
        use_case = GetSttEnabledUseCase(FakeSttProtocol(enabled=True))  # type: ignore

        self.assertTrue(use_case())

    def test_should_return_false_when_stt_disabled(self):
        use_case = GetSttEnabledUseCase(FakeSttProtocol(enabled=False))  # type: ignore

        self.assertFalse(use_case())


if __name__ == "__main__":
    unittest.main()
