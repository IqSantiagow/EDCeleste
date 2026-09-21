import unittest

from edceleste.services.models.settings_model import LLMProviderModel
from edceleste.use_cases.settings.get_llm_models_use_case import GetLlmModelsUseCase


class FakeLlmProtocol:
    def __init__(self, models: list[str]):
        self._models = models
        self.asked_for_provider = None

    def add_llm_request_to_queue(self, message: str) -> None:
        raise NotImplementedError

    def consume_llm_queue(self):
        raise NotImplementedError

    async def validate_settings(self, new_settings):
        raise NotImplementedError

    def reload_service(self) -> None:
        raise NotImplementedError

    async def get_models(self, provider=None) -> list[str]:
        self.asked_for_provider = provider
        return self._models


class TestGetLlmModelsUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_the_edited_provider_through_and_return_models(self):
        # The pilot may still be editing the provider, so the not yet saved one
        # has to reach the service - otherwise the list belongs to the old one.
        models = ["anthropic/claude-haiku-4.5", "openai/gpt-4o"]
        fake_llm_protocol = FakeLlmProtocol(models)
        use_case = GetLlmModelsUseCase(fake_llm_protocol)  # type: ignore
        provider = LLMProviderModel(type="openai", model="gpt-4o", api_key="key")

        result = await use_case(provider)

        self.assertEqual(result, models)
        self.assertIs(fake_llm_protocol.asked_for_provider, provider)

    async def test_should_return_empty_list_when_no_models_available(self):
        use_case = GetLlmModelsUseCase(FakeLlmProtocol([]))  # type: ignore

        result = await use_case()

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
