import unittest

from edceleste.use_cases.settings.get_llm_models_use_case import GetLlmModelsUseCase


class FakeLlmProtocol:
    def __init__(self, models: list[str]):
        self._models = models
        self.requested_provider_type: str | None = None

    def add_llm_request_to_queue(self, message: str) -> None:
        raise NotImplementedError

    def consume_llm_queue(self):
        raise NotImplementedError

    def validate_settings(self, new_settings):
        raise NotImplementedError

    def reload_service(self) -> None:
        raise NotImplementedError

    def get_models(self, provider_type: str) -> list[str]:
        self.requested_provider_type = provider_type
        return self._models


class TestGetLlmModelsUseCase(unittest.TestCase):
    def test_should_delegate_to_llm_protocol_and_return_models(self):
        models = ["claude-haiku-4-5-20251001", "claude-sonnet-5"]
        fake_llm_protocol = FakeLlmProtocol(models)
        use_case = GetLlmModelsUseCase(fake_llm_protocol)  # type: ignore

        result = use_case("claude_agent_sdk")

        self.assertEqual(result, models)
        self.assertEqual(fake_llm_protocol.requested_provider_type, "claude_agent_sdk")

    def test_should_return_empty_list_when_no_models_available(self):
        use_case = GetLlmModelsUseCase(FakeLlmProtocol([]))  # type: ignore

        result = use_case("lm_studio")

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
