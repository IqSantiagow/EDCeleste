import unittest

from edceleste.use_cases.settings.get_stt_models_use_case import GetSttModelsUseCase


class FakeSttProtocol:
    def __init__(self, models: list[str]):
        self._models = models

    def handle_stt_request(self, audio_path: str) -> str | None:
        raise NotImplementedError

    def validate_settings(self, new_settings):
        raise NotImplementedError

    def reload_service(self) -> None:
        raise NotImplementedError

    def is_stt_enabled(self) -> bool:
        raise NotImplementedError

    def get_stt_models(self) -> list[str]:
        return self._models


class TestGetSttModelsUseCase(unittest.TestCase):
    def test_should_delegate_to_stt_protocol_and_return_models(self):
        models = ["tiny.en", "base.en"]
        use_case = GetSttModelsUseCase(FakeSttProtocol(models))  # type: ignore

        result = use_case()

        self.assertEqual(result, models)

    def test_should_return_empty_list_when_no_models_available(self):
        use_case = GetSttModelsUseCase(FakeSttProtocol([]))  # type: ignore

        result = use_case()

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
